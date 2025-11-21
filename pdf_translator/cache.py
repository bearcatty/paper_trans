from __future__ import annotations

import json
import logging
import os
import time
from typing import Dict

logger = logging.getLogger(__name__)

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
