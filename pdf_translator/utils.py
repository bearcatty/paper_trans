from __future__ import annotations

import hashlib
import logging
import re

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
