"""语义缓存 — VLM 结果复用，避免重复调用。

缓存键: domain + normalized_url + window_title + thumbnail_md5
当 app/window/title/hash 相同时，复用之前的 VLM 摘要和 embedding。
强制 keyframe: 应用切换、URL 变化、标题变化、首帧、手动截图。
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目。"""
    vlm_summary: str
    event_id: str
    created_at: float
    embedding: Optional[list] = None


class SemanticCache:
    """语义缓存 — 基于上下文信号复用 VLM 结果。"""

    def __init__(self, max_size: int = 500, ttl_seconds: int = 600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def _make_key(
        self,
        app_name: str,
        window_title: str,
        url: str,
        thumbnail_md5: str,
    ) -> str:
        """生成缓存键。"""
        raw = f"{app_name}|{window_title}|{url}|{thumbnail_md5}"
        return hashlib.md5(raw.encode()).hexdigest()

    def lookup(
        self,
        app_name: str,
        window_title: str,
        url: str,
        thumbnail_md5: str,
    ) -> Optional[CacheEntry]:
        """查找缓存。"""
        key = self._make_key(app_name, window_title, url, thumbnail_md5)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        # TTL 检查
        if time.time() - entry.created_at > self.ttl_seconds:
            del self._cache[key]
            self._misses += 1
            return None
        # 移到末尾（LRU）
        self._cache.move_to_end(key)
        self._hits += 1
        return entry

    def store(
        self,
        app_name: str,
        window_title: str,
        url: str,
        thumbnail_md5: str,
        vlm_summary: str,
        event_id: str,
        embedding: Optional[list] = None,
    ):
        """存储缓存条目。"""
        key = self._make_key(app_name, window_title, url, thumbnail_md5)
        self._cache[key] = CacheEntry(
            vlm_summary=vlm_summary,
            event_id=event_id,
            created_at=time.time(),
            embedding=embedding,
        )
        # 淘汰旧条目
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def should_skip_vlm(
        self,
        app_name: str,
        prev_app_name: Optional[str],
        window_title: str,
        prev_window_title: Optional[str],
        prev_thumbnail_md5: Optional[str] = None,
        current_thumbnail_md5: Optional[str] = None,
    ) -> bool:
        """判断是否应跳过 VLM 调用。

        跳过条件：应用和窗口标题相同 且 内容哈希相同。
        """
        # 应用切换 → 不跳过
        if prev_app_name and app_name != prev_app_name:
            return False
        # 标题变化 → 不跳过
        if prev_window_title and window_title != prev_window_title:
            return False
        # 哈希变化 → 不跳过
        if prev_thumbnail_md5 and current_thumbnail_md5 and prev_thumbnail_md5 != current_thumbnail_md5:
            return False
        # 全部相同 → 跳过
        if prev_app_name and prev_window_title:
            return True
        return False

    def get_stats(self) -> dict:
        """获取缓存统计。"""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / (self._hits + self._misses), 3) if (self._hits + self._misses) > 0 else 0.0,
        }

    def clear(self):
        """清空缓存。"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
