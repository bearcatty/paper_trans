#!/usr/bin/env python
"""
PDF翻译工具
使用LM Studio MCP服务将PDF文件从英文翻译成中文，并生成新的PDF文件
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Dict, List

import fitz  # PyMuPDF
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from mcp_server import LMStudioClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
DEFAULT_MODEL = os.getenv("LM_STUDIO_MODEL", "openai/gpt-oss-20b")

# 翻译配置
CHUNK_SIZE = 2000  # 每次翻译的字符数
MAX_TOKENS = 4000  # 最大token数
QA_MAX_ATTEMPTS = 3  # 质量检查最大尝试次数
MAX_ENGLISH_RATIO = 0.2  # 译文中英文字符占比阈值
SUPPORTED_OUTPUT_FORMATS = ("pdf", "md")


def compute_text_hash(text: str) -> str:
    """计算文本的哈希值，用于缓存校验"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def english_char_ratio(text: str) -> float:
    """估算文本中英文字母占比"""
    if not text:
        return 0.0
    english_chars = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return english_chars / max(len(text), 1)


def sanitize_text(text: str) -> str:
    """清理翻译文本"""
    return (text or "").replace("\x00", "").strip()


def sanitize_markdown_text(text: str) -> str:
    """清理并转换 Markdown 友好的文本"""
    text = sanitize_text(text)

    def block_math_repl(match: re.Match) -> str:
        content = match.group(1).strip()
        return f"$$\n{content}\n$$"

    def inline_math_repl(match: re.Match) -> str:
        content = match.group(1).strip()
        return f"${content}$"

    text = re.sub(r"\\\[(.+?)\\\]", block_math_repl, text, flags=re.DOTALL)
    text = re.sub(r"\\\((.+?)\\\)", inline_math_repl, text, flags=re.DOTALL)
    return text


class TranslationCache:
    """翻译缓存，支持断点续译"""

    def __init__(self, cache_path: str):
        self.cache_path = cache_path
        self.data: Dict[str, any] = {"meta": {}, "pages": {}}
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                    logger.info(f"已加载翻译缓存: {self.cache_path}")
            except Exception as e:
                logger.warning(f"加载缓存失败，将重新创建。错误: {e}")
                self.data = {"meta": {}, "pages": {}}
        self._loaded = True

    def initialize(self, meta: dict):
        self.load()
        existing_meta = self.data.get("meta") or {}
        if not existing_meta:
            self.data["meta"] = meta
            self.save()
            return

        # 如果元数据不匹配，则清空缓存
        if any(
            existing_meta.get(key) != meta.get(key)
            for key in ["input_pdf", "output_pdf", "model", "chunk_size"]
        ):
            logger.warning("缓存元数据与当前任务不一致，重置缓存。")
            self.data = {"meta": meta, "pages": {}}
            self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
        tmp_path = f"{self.cache_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.cache_path)

    def prepare_page(self, page_num: int, page_hash: str, chunk_count: int) -> dict:
        pages = self.data.setdefault("pages", {})
        key = str(page_num)
        page_data = pages.get(key)
        if (
            page_data
            and (
                page_data.get("hash") != page_hash
                or page_data.get("chunk_count") != chunk_count
            )
        ):
            logger.info(f"第 {page_num} 页内容发生变化，清除旧缓存。")
            pages.pop(key, None)
            page_data = None

        if not page_data:
            page_data = {
                "hash": page_hash,
                "chunk_count": chunk_count,
                "translated_chunks": [],
                "status": "in_progress",
                "updated_at": time.time(),
            }
            pages[key] = page_data
            self.save()

        return page_data

    def append_chunk(self, page_num: int, translated_text: str):
        page_data = self.data["pages"][str(page_num)]
        page_data["translated_chunks"].append(translated_text)
        page_data["status"] = "in_progress"
        page_data["updated_at"] = time.time()
        self.save()

    def mark_page_complete(self, page_num: int):
        page_data = self.data["pages"].get(str(page_num))
        if page_data:
            page_data["status"] = "complete"
            page_data["updated_at"] = time.time()
            self.save()

    def clear(self):
        if os.path.exists(self.cache_path):
            try:
                os.remove(self.cache_path)
                logger.info(f"已删除缓存文件: {self.cache_path}")
            except Exception as e:
                logger.warning(f"删除缓存文件失败: {e}")


class PDFTranslator:
    """PDF翻译器"""
    
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        source_lang: str = "English",
        target_lang: str = "Chinese"
    ):
        self.client = LMStudioClient(base_url=base_url, model=model)
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.cache: TranslationCache | None = None
    
    async def extract_content_from_pdf(self, pdf_path: str) -> List[dict]:
        """
        从PDF文件中提取文本与图像
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            包含页面内容的列表，每项包含页码、文本、图像
        """
        logger.info(f"正在提取PDF文本: {pdf_path}")
        doc = fitz.open(pdf_path)
        pages_content = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            images = []

            for img_index, img in enumerate(page.get_images(full=True), 1):
                xref = img[0]
                try:
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image.get("image")
                    if not image_bytes:
                        continue
                    images.append(
                        {
                            "bytes": image_bytes,
                            "ext": base_image.get("ext", "png"),
                            "width": base_image.get("width"),
                            "height": base_image.get("height"),
                        }
                    )
                except Exception as e:
                    logger.debug(f"第 {page_num + 1} 页提取图像失败: {e}")

            if text.strip() or images:
                pages_content.append(
                    {
                        "page_num": page_num + 1,
                        "text": text,
                        "images": images,
                    }
                )
                logger.info(
                    f"提取第 {page_num + 1} 页，文本长度: {len(text)} 字符，图像数: {len(images)}"
                )
        
        doc.close()
        logger.info(f"总共提取了 {len(pages_content)} 页内容")
        return pages_content
    
    def split_text_into_chunks(self, text: str, chunk_size: int = CHUNK_SIZE) -> List[str]:
        """
        将文本分割成适合翻译的块
        
        Args:
            text: 要分割的文本
            chunk_size: 每块的最大字符数
            
        Returns:
            文本块列表
        """
        # 尝试按段落分割
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            # 如果当前块加上新段落不超过限制，则添加
            if len(current_chunk) + len(para) + 2 <= chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
            else:
                # 保存当前块
                if current_chunk:
                    chunks.append(current_chunk)
                # 如果单个段落就超过限制，按句子分割
                if len(para) > chunk_size:
                    sentences = re.split(r'([.!?]\s+)', para)
                    temp_chunk = ""
                    for i in range(0, len(sentences), 2):
                        sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else "")
                        if len(temp_chunk) + len(sentence) <= chunk_size:
                            temp_chunk += sentence
                        else:
                            if temp_chunk:
                                chunks.append(temp_chunk)
                            temp_chunk = sentence
                    current_chunk = temp_chunk
                else:
                    current_chunk = para
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks if chunks else [text]
    
    async def translate_text(
        self,
        text: str,
        retry_count: int = 3
    ) -> str:
        """
        使用LM Studio翻译文本
        
        Args:
            text: 要翻译的文本
            retry_count: 重试次数
            
        Returns:
            翻译后的文本
        """
        prompt = f"""请将以下{self.source_lang}文本翻译成{self.target_lang}。要求：
1. 保持原文的格式和结构
2. 翻译准确、流畅
3. 保留专业术语的准确性
4. 翻译图表、表格标题和脚注，并保留编号
5. 仅输出翻译后的{self.target_lang}内容，不要重复原文或添加额外解释

原文：
{text}

翻译："""
        
        messages = [
            {
                "role": "system",
                "content": f"你是一个专业的翻译助手，擅长将{self.source_lang}翻译成{self.target_lang}。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        for attempt in range(retry_count):
            try:
                logger.info(f"正在翻译文本块（长度: {len(text)} 字符）...")
                response = await self.client.chat_completion(
                    messages=messages,
                    temperature=0.3,  # 降低温度以获得更稳定的翻译
                    max_tokens=MAX_TOKENS
                )
                
                if "choices" in response and len(response["choices"]) > 0:
                    translated = response["choices"][0].get("message", {}).get("content", "")
                    # 清理翻译结果，移除可能的提示词
                    translated = translated.strip()
                    # 如果翻译结果以"翻译："开头，移除它
                    if translated.startswith("翻译："):
                        translated = translated[3:].strip()
                    translated = translated.replace('\x00', '')
                    translated = await self.ensure_translation_quality(text, translated)
                    logger.info(f"翻译完成，结果长度: {len(translated)} 字符")
                    return translated
                else:
                    raise ValueError("API响应中没有找到翻译结果")
                    
            except Exception as e:
                logger.warning(f"翻译尝试 {attempt + 1}/{retry_count} 失败: {e}")
                if attempt == retry_count - 1:
                    raise
                await asyncio.sleep(2)  # 等待后重试
        
        raise Exception("翻译失败，已达到最大重试次数")

    def analyze_translation_quality(self, source_text: str, translated_text: str) -> List[str]:
        """简单启发式检测翻译质量问题"""
        issues: List[str] = []
        stripped = translated_text.strip()
        if not stripped:
            issues.append("译文为空或仅包含空白。")
        ratio = english_char_ratio(stripped)
        if ratio > MAX_ENGLISH_RATIO:
            issues.append(
                f"译文包含过多英文字符（占比 {ratio:.0%}），请全部翻译成中文。"
            )
        if stripped and stripped.strip() == source_text.strip():
            issues.append("输出与原文相同，看起来未翻译。")
        if "Translation" in translated_text or "翻译：" in translated_text:
            issues.append("译文中包含提示词或“Translation”字样，请去除。")
        return issues

    async def ensure_translation_quality(
        self,
        source_text: str,
        initial_translation: str,
    ) -> str:
        """调用LLM进行质量复查，如不合格则请求改写"""
        candidate = initial_translation
        for attempt in range(QA_MAX_ATTEMPTS):
            issues = self.analyze_translation_quality(source_text, candidate)
            if not issues:
                return candidate
            if attempt == QA_MAX_ATTEMPTS - 1:
                logger.warning(
                    f"质量检查仍存在问题：{' ; '.join(issues)}，返回最新结果。"
                )
                return candidate
            logger.info(
                f"质量检查发现问题（{issues}），尝试自动修复 {attempt + 1}/{QA_MAX_ATTEMPTS - 1}"
            )
            candidate = await self.request_translation_revision(
                source_text, candidate, issues
            )
            candidate = candidate.replace('\x00', '').strip()
        return candidate

    async def request_translation_revision(
        self,
        source_text: str,
        current_translation: str,
        issues: List[str],
    ) -> str:
        """请求LLM基于反馈重新润色译文"""
        messages = [
            {
                "role": "system",
                "content": "你是一名资深的中英翻译审校专家，需要确保输出严格为流畅、准确的中文。",
            },
            {
                "role": "user",
                "content": (
                    "请根据以下原文和当前译文，修复列出的问题，输出改进后的中文译文。"
                    "不要重复原文，不要添加额外解释或提示词，只输出修改后的译文正文。\n"
                    f"原文：\n{source_text}\n\n"
                    f"当前译文：\n{current_translation}\n\n"
                    f"需修复的问题：\n- " + "\n- ".join(issues)
                ),
            },
        ]
        response = await self.client.chat_completion(
            messages=messages,
            temperature=0.2,
            max_tokens=MAX_TOKENS,
        )
        if "choices" in response and response["choices"]:
            revised = response["choices"][0].get("message", {}).get("content", "").strip()
            if revised:
                return revised
        logger.warning("质量修复调用失败，返回原译文。")
        return current_translation
    
    async def translate_pdf(
        self,
        pdf_path: str,
        output_path: str | None = None,
        chunk_size: int = CHUNK_SIZE,
        output_format: str = "pdf",
    ) -> str:
        """
        翻译整个PDF文件
        
        Args:
            pdf_path: 输入PDF文件路径
            output_path: 输出PDF文件路径，如果为None则自动生成
            chunk_size: 翻译块大小
            output_format: 输出格式（pdf 或 md）
            
        Returns:
            输出PDF文件路径
        """
        output_format = output_format.lower()
        if output_format not in SUPPORTED_OUTPUT_FORMATS:
            raise ValueError(
                f"不支持的输出格式: {output_format}，可选值: {SUPPORTED_OUTPUT_FORMATS}"
            )

        # 生成输出路径
        if output_path is None:
            input_path = Path(pdf_path)
            suffix = ".pdf" if output_format == "pdf" else ".md"
            output_path = str(input_path.parent / f"{input_path.stem}_translated{suffix}")
        else:
            output_path_path = Path(output_path)
            expected_suffix = ".pdf" if output_format == "pdf" else ".md"
            if output_path_path.suffix.lower() != expected_suffix:
                output_path = str(output_path_path.with_suffix(expected_suffix))
        
        logger.info(f"开始翻译PDF: {pdf_path} -> {output_path}")
        
        # 提取文本与图像
        pages_content = await self.extract_content_from_pdf(pdf_path)
        
        if not pages_content:
            raise ValueError("PDF文件中没有提取到文本内容")
        
        # 初始化缓存
        cache_path = f"{output_path}.cache.json"
        cache_meta = {
            "input_pdf": str(Path(pdf_path).resolve()),
            "output_pdf": str(Path(output_path).resolve()),
            "model": self.client.model,
            "chunk_size": chunk_size,
            "output_format": output_format,
        }
        self.cache = TranslationCache(cache_path)
        self.cache.initialize(cache_meta)

        # 翻译每一页
        translated_pages = []
        total_pages = len(pages_content)
        
        for idx, page in enumerate(pages_content, 1):
            page_num = page["page_num"]
            text = page.get("text", "")
            logger.info(f"正在翻译第 {page_num} 页 ({idx}/{total_pages})...")
            
            if not text.strip():
                logger.info(f"第 {page_num} 页无可翻译文本，跳过文本翻译，仅保留图像内容。")
                translated_pages.append(
                    {
                        "page_num": page_num,
                        "text": "",
                        "images": page.get("images", []),
                    }
                )
                continue

            # 将文本分割成块
            chunks = self.split_text_into_chunks(text, chunk_size)
            page_hash = compute_text_hash(text)
            page_cache = self.cache.prepare_page(page_num, page_hash, len(chunks))
            translated_chunks = page_cache.setdefault("translated_chunks", [])
            start_chunk = len(translated_chunks)
            if start_chunk > 0:
                logger.info(
                    f"  从缓存中恢复第 {page_num} 页，已完成 {start_chunk}/{len(chunks)} 个块"
                )
            logger.info(f"第 {page_num} 页分割成 {len(chunks)} 个块")
            
            # 翻译每个块
            translated_chunks = page_cache.setdefault("translated_chunks", [])
            for chunk_idx in range(start_chunk, len(chunks)):
                chunk = chunks[chunk_idx]
                logger.info(f"  翻译块 {chunk_idx + 1}/{len(chunks)}...")
                translated_chunk = await self.translate_text(chunk)
                if self.cache:
                    self.cache.append_chunk(page_num, translated_chunk)
                    translated_chunks = page_cache["translated_chunks"]
                else:
                    translated_chunks.append(translated_chunk)
                # 添加小延迟避免API限流
                await asyncio.sleep(0.5)

            # 标记该页完成
            if self.cache:
                self.cache.mark_page_complete(page_num)
            
            # 合并翻译结果
            translated_text = sanitize_text("\n\n".join(page_cache.get("translated_chunks", [])))
            translated_pages.append(
                {
                    "page_num": page_num,
                    "text": translated_text,
                    "images": page.get("images", []),
                }
            )
        
        # 生成新的PDF
        if output_format == "pdf":
            logger.info(f"正在生成翻译后的PDF: {output_path}")
            self.create_pdf_from_text(translated_pages, output_path)
        else:
            logger.info(f"正在生成翻译后的Markdown: {output_path}")
            self.create_markdown_from_text(translated_pages, output_path)

        # 翻译完成后清理缓存
        if self.cache:
            self.cache.clear()
        
        logger.info(f"翻译完成！输出文件: {output_path}")
        return output_path
    
    def create_pdf_from_text(
        self,
        pages_content: List[dict],
        output_path: str
    ):
        """
        从翻译后的文本创建新的PDF文件
        
        Args:
            pages_content: 每页包含页码、文本和图像的列表
            output_path: 输出PDF路径
        """
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        # 创建样式
        styles = getSampleStyleSheet()
        
        # 尝试注册中文字体（如果系统有的话）
        try:
            # 常见的中文字体路径
            font_paths = [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "C:/Windows/Fonts/simsun.ttc",
            ]
            
            chinese_font_registered = False
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
                        chinese_font_registered = True
                        logger.info(f"成功注册中文字体: {font_path}")
                        break
                    except Exception as e:
                        logger.debug(f"无法注册字体 {font_path}: {e}")
                        continue
            
            if chinese_font_registered:
                # 创建支持中文的样式
                normal_style = ParagraphStyle(
                    'CustomNormal',
                    parent=styles['Normal'],
                    fontName='ChineseFont',
                    fontSize=11,
                    leading=14,
                    spaceAfter=12
                )
            else:
                normal_style = styles['Normal']
                logger.warning("未找到中文字体，PDF可能无法正确显示中文")
        except Exception as e:
            logger.warning(f"字体注册失败，使用默认字体: {e}")
            normal_style = styles['Normal']
        
        # 构建PDF内容
        story = []
        
        page_width, page_height = A4
        max_image_width = page_width - doc.leftMargin - doc.rightMargin
        max_image_height = (page_height - doc.topMargin - doc.bottomMargin) / 2

        for page_data in pages_content:
            page_num = page_data.get("page_num")
            text = page_data.get("text", "")
            if page_num > 1:
                story.append(PageBreak())
            
            # 添加页码标题（可选）
            # story.append(Paragraph(f"第 {page_num} 页", styles['Heading2']))
            # story.append(Spacer(1, 0.2*inch))
            
            # 将文本按段落分割并添加
            sanitized_text = text.replace('\x00', '')
            paragraphs = sanitized_text.split('\n\n')
            for para in paragraphs:
                if para.strip():
                    # 清理文本，移除特殊字符
                    para = para.replace('\x00', '')  # 移除空字符
                    try:
                        story.append(Paragraph(para, normal_style))
                        story.append(Spacer(1, 0.1*inch))
                    except Exception as e:
                        logger.warning(f"处理段落时出错: {e}，跳过该段落")
                        continue

            # 添加图像
            for img in page_data.get("images", []):
                image_bytes = img.get("bytes")
                if not image_bytes:
                    continue
                try:
                    bio = BytesIO(image_bytes)
                    rl_image = RLImage(bio)
                    rl_image.hAlign = 'CENTER'
                    rl_image._restrictSize(max_image_width, max_image_height)
                    story.append(rl_image)
                    story.append(Spacer(1, 0.1 * inch))
                except Exception as e:
                    logger.warning(f"插入图像失败: {e}")
                    continue
        
        # 生成PDF
        doc.build(story)
        logger.info(f"PDF文件已生成: {output_path}")
    
    def create_markdown_from_text(
        self,
        pages_content: List[dict],
        output_path: str
    ):
        """
        从翻译后的文本创建Markdown文件
        """
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        safe_stem = re.sub(r"[^A-Za-z0-9._-]", "_", output_path_obj.stem)
        image_dir = output_path_obj.parent / f"{safe_stem}_assets"
        image_dir.mkdir(parents=True, exist_ok=True)

        lines: List[str] = [
            "# 翻译结果",
            "",
            f"_生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}_",
            "",
        ]

        for page in pages_content:
            page_num = page.get("page_num")
            text = sanitize_markdown_text(page.get("text", ""))
            lines.append(f"## 第 {page_num} 页")
            lines.append("")
            if text:
                for para in text.split("\n\n"):
                    sanitized_para = sanitize_text(para)
                    if sanitized_para:
                        lines.append(sanitized_para)
                        lines.append("")
            else:
                lines.append("_（本页无文本，仅包含图表）_")
                lines.append("")

            for idx, img in enumerate(page.get("images", []), 1):
                image_bytes = img.get("bytes")
                if not image_bytes:
                    continue
                ext = img.get("ext", "png")
                safe_ext = re.sub(r"[^A-Za-z0-9]", "", ext) or "png"
                image_path = image_dir / f"page_{page_num}_img_{idx}.{safe_ext}"
                try:
                    with open(image_path, "wb") as f:
                        f.write(image_bytes)
                    rel_path = os.path.relpath(image_path, output_path_obj.parent)
                    lines.append(f"![第 {page_num} 页 图 {idx}]({rel_path})")
                    lines.append("")
                except Exception as e:
                    logger.warning(f"写入图像失败: {e}")
                    continue

        with open(output_path_obj, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).strip() + "\n")
        logger.info(f"Markdown文件已生成: {output_path}")

    async def close(self):
        """关闭客户端连接"""
        await self.client.close()


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="PDF翻译工具 - 使用LM Studio将PDF从英文翻译成中文"
    )
    parser.add_argument(
        "input_pdf",
        type=str,
        help="输入的PDF文件路径"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="输出的PDF文件路径（默认：输入文件名_translated.pdf）"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=DEFAULT_BASE_URL,
        help=f"LM Studio服务器地址（默认: {DEFAULT_BASE_URL}）"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"使用的模型名称（默认: {DEFAULT_MODEL}）"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=CHUNK_SIZE,
        help=f"翻译块大小（默认: {CHUNK_SIZE} 字符）"
    )
    parser.add_argument(
        "--format",
        choices=SUPPORTED_OUTPUT_FORMATS,
        default="pdf",
        help="输出格式：pdf 或 md（默认: pdf）",
    )
    
    args = parser.parse_args()
    
    # 检查输入文件是否存在
    if not os.path.exists(args.input_pdf):
        logger.error(f"输入文件不存在: {args.input_pdf}")
        return 1
    
    translator = PDFTranslator(
        base_url=args.base_url,
        model=args.model
    )
    
    try:
        output_path = await translator.translate_pdf(
            args.input_pdf,
            args.output,
            args.chunk_size,
            args.format,
        )
        logger.info(f"✓ 翻译完成！输出文件: {output_path}")
        return 0
    except Exception as e:
        logger.error(f"✗ 翻译失败: {e}", exc_info=True)
        return 1
    finally:
        await translator.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)

