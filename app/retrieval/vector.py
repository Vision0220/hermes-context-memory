"""向量检索模块 — 基于 sqlite-vec 的向量相似度搜索。

当 sqlite-vec 不可用时，所有向量操作静默退化。
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# sqlite-vec 是否可用的全局标记
_vec_available: Optional[bool] = None


def is_vector_available() -> bool:
    """检查 sqlite-vec 是否可用。"""
    global _vec_available
    if _vec_available is None:
        try:
            import sqlite_vec
            _vec_available = True
        except ImportError:
            _vec_available = False
            logger.info("sqlite-vec 不可用，向量检索已禁用。所有检索退化为 FTS5。")
    return _vec_available


def init_vector_table(conn) -> bool:
    """在 SQLite 连接中初始化向量表。

    Returns:
        True 如果成功初始化。
    """
    if not is_vector_available():
        return False

    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        # 创建向量表（384 维对应 all-MiniLM-L6-v2，使用动态维度更灵活）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS event_vectors (
                event_id TEXT PRIMARY KEY,
                embedding BLOB
            )
        """)
        conn.commit()
        return True
    except Exception as e:
        logger.warning(f"初始化向量表失败: {e}")
        return False


def store_embedding(conn, event_id: str, embedding: List[float]) -> bool:
    """存储事件的向量。"""
    if not is_vector_available():
        return False

    try:
        import sqlite_vec
        import struct
        # 将 float 列表转为二进制 blob
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        conn.execute(
            "INSERT OR REPLACE INTO event_vectors (event_id, embedding) VALUES (?, ?)",
            (event_id, blob),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.warning(f"存储向量失败: {e}")
        return False


def search_similar(conn, query_embedding: List[float], limit: int = 10) -> List[dict]:
    """向量相似度搜索。"""
    if not is_vector_available():
        return []

    try:
        import struct
        query_blob = struct.pack(f"{len(query_embedding)}f", *query_embedding)

        rows = conn.execute(
            """SELECT event_id, vec_distance_cosine(embedding, ?) as distance
               FROM event_vectors
               ORDER BY distance ASC
               LIMIT ?""",
            (query_blob, limit),
        ).fetchall()

        return [{"event_id": row[0], "distance": row[1]} for row in rows]
    except Exception as e:
        logger.warning(f"向量搜索失败: {e}")
        return []
