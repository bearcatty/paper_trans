from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import List, Optional

import fitz
from .mcp_server import LMStudioClient

from .cache import TranslationCache
from .content import ContentExtractor
from .utils import compute_text_hash, english_char_ratio, sanitize_markdown_text, sanitize_text

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
DEFAULT_MODEL = os.getenv("LM_STUDIO_MODEL", "openai/gpt-oss-20b")

# 翻译配置
CHUNK_SIZE = 2000  # 每次翻译的字符数
MAX_TOKENS = 4000  # 最大token数
QA_MAX_ATTEMPTS = 3  # 质量检查最大尝试次数
MAX_ENGLISH_RATIO = 0.2  # 译文中英文字符占比阈值

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
        self.extractor = ContentExtractor()
    
    async def extract_content_from_pdf(self, pdf_path: str) -> List[dict]:
        """
        从PDF文件中提取内容块
        """
        logger.info(f"正在提取PDF内容: {pdf_path}")
        doc = fitz.open(pdf_path)
        pages_content = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = self.extractor.extract_page(page, page_num + 1)
            
            if blocks:
                # 将块转换为字典以便序列化和处理
                blocks_data = []
                for b in blocks:
                    block_dict = {
                        "text": b.text,
                        "type": b.block_type,
                        "bbox": b.bbox
                    }
                    if b.block_type == "image":
                        block_dict["image_data"] = b.image_data
                        block_dict["image_ext"] = b.image_ext
                    blocks_data.append(block_dict)

                pages_content.append(
                    {
                        "page_num": page_num + 1,
                        "blocks": blocks_data
                    }
                )
                logger.info(f"提取第 {page_num + 1} 页，共 {len(blocks)} 个内容块")
        
        doc.close()
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
5. 遇到 <<IMAGE_N>> 或 <<IMAGE_CLUSTER_N>> 等占位符时，请原样保留，不要翻译或修改它们
6. 仅输出翻译后的{self.target_lang}内容，不要重复原文或添加额外解释

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
    ) -> str:
        """
        翻译整个PDF文件
        
        Args:
            pdf_path: 输入PDF文件路径
            output_path: 输出Markdown文件路径，如果为None则自动生成
            chunk_size: 翻译块大小
            
        Returns:
            输出Markdown文件路径
        """
        # 生成输出路径
        if output_path is None:
            input_path = Path(pdf_path)
            output_path = str(input_path.parent / f"{input_path.stem}_translated.md")
        else:
            output_path_path = Path(output_path)
            if output_path_path.suffix.lower() != ".md":
                output_path = str(output_path_path.with_suffix(".md"))
        
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
            "output_format": "md",
        }
        self.cache = TranslationCache(cache_path)
        self.cache.initialize(cache_meta)

        # 翻译每一页
        translated_pages = []
        total_pages = len(pages_content)
        
        for idx, page in enumerate(pages_content, 1):
            page_num = page["page_num"]
            # 构建用于翻译的文本
            page_text_parts = []
            for block in page.get("blocks", []):
                if block["type"] == "text":
                    page_text_parts.append(block["text"])
                elif block["type"] == "image":
                    page_text_parts.append(block["text"])  # <<IMAGE_N>>
            
            text = "\n\n".join(page_text_parts)
            
            logger.info(f"正在翻译第 {page_num} 页 ({idx}/{total_pages})...")
            
            if not text.strip():
                logger.info(f"第 {page_num} 页无可翻译文本，跳过文本翻译，仅保留图像内容。")
                translated_pages.append(
                    {
                        "page_num": page_num,
                        "text": "",
                        "blocks": page.get("blocks", []),
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
                    "blocks": page.get("blocks", []),  # 保留原始blocks信息用于重建
                }
            )
        
        # 生成翻译后的Markdown
        logger.info(f"正在生成翻译后的Markdown: {output_path}")
        self.create_markdown_from_text(translated_pages, output_path)

        # 翻译完成后清理缓存
        if self.cache:
            self.cache.clear()
        
        logger.info(f"翻译完成！输出文件: {output_path}")
        return output_path
    

    
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
            blocks = page.get("blocks", [])
            
            lines.append(f"## 第 {page_num} 页")
            lines.append("")
            
            # 构建图像映射
            image_map = {}
            for block in blocks:
                if block["type"] == "image":
                    image_map[block["text"]] = block

            # 按占位符分割文本
            # BUG FIX: 支持 IMAGE_CLUSTER 占位符
            parts = re.split(r"(<<IMAGE(?:_CLUSTER)?_\d+>>)", text)
            
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                
                if part in image_map:
                    # 处理图像
                    img_block = image_map[part]
                    image_bytes = img_block.get("image_data")
                    if not image_bytes:
                        continue
                    
                    ext = img_block.get("image_ext", "png")
                    safe_ext = re.sub(r"[^A-Za-z0-9]", "", ext) or "png"
                    
                    # 从占位符中提取索引用于文件名
                    img_idx_match = re.search(r"(\d+)", part)
                    img_idx = img_idx_match.group(1) if img_idx_match else "unknown"
                    
                    # 如果是cluster，添加前缀区分
                    prefix = "cluster_" if "CLUSTER" in part else "img_"
                    
                    image_path = image_dir / f"page_{page_num}_{prefix}{img_idx}.{safe_ext}"
                    try:
                        with open(image_path, "wb") as f:
                            f.write(image_bytes)
                        rel_path = os.path.relpath(image_path, output_path_obj.parent)
                        lines.append(f"![第 {page_num} 页 图 {img_idx}]({rel_path})")
                        lines.append("")
                    except Exception as e:
                        logger.warning(f"写入图像失败: {e}")
                        continue
                else:
                    # 处理文本
                    for para in part.split("\n\n"):
                        sanitized_para = sanitize_text(para)
                        if sanitized_para:
                            lines.append(sanitized_para)
                            lines.append("")

        with open(output_path_obj, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).strip() + "\n")
        logger.info(f"Markdown文件已生成: {output_path}")

    async def close(self):
        """关闭客户端连接"""
        await self.client.close()
