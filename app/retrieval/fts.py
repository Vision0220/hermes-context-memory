"""FTS5 检索模块 — 全文搜索的辅助函数。"""

from __future__ import annotations

from typing import List

from app.storage import get_storage


def fts_search(query: str, limit: int = 20) -> List[dict]:
    """执行 FTS5 全文搜索。

    这是 search.py 中 Storage.search_fts 的便捷包装。
    """
    storage = get_storage()
    return storage.search_fts(query, limit=limit)
