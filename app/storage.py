"""存储层 — SQLite 数据库管理，含 FTS5 全文检索和 sqlite-vec 向量检索。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from app.config import DATA_DIR

DB_PATH = DATA_DIR / "context.sqlite"

# ── SQL 建表语句 ────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS raw_events (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    source TEXT NOT NULL,
    app_name TEXT,
    process_name TEXT,
    window_title TEXT,
    url TEXT,
    domain TEXT,
    screenshot_path TEXT,
    image_hash TEXT,
    duplicate_of TEXT,
    ocr_text TEXT,
    vlm_summary TEXT,
    vlm_json TEXT,
    sensitive INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS browser_events (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    browser TEXT,
    url TEXT,
    domain TEXT,
    title TEXT,
    tab_id TEXT,
    window_id TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_sessions (
    id TEXT PRIMARY KEY,
    ts_start TEXT NOT NULL,
    ts_end TEXT NOT NULL,
    topic TEXT,
    apps TEXT,
    urls TEXT,
    summary TEXT,
    evidence_event_ids TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recall_chunks (
    id TEXT PRIMARY KEY,
    event_id TEXT,
    session_id TEXT,
    chunk_text TEXT,
    embedding_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS config_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);
"""

# FTS5 虚拟表 — 用于全文检索
_FTS5_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    id UNINDEXED,
    ts UNINDEXED,
    app_name,
    window_title,
    url,
    domain,
    ocr_text,
    vlm_summary,
    content='raw_events',
    content_rowid='rowid'
);

-- 插入触发器
CREATE TRIGGER IF NOT EXISTS raw_events_ai AFTER INSERT ON raw_events BEGIN
    INSERT INTO events_fts(rowid, id, ts, app_name, window_title, url, domain, ocr_text, vlm_summary)
    VALUES (NEW.rowid, NEW.id, NEW.ts, NEW.app_name, NEW.window_title, NEW.url, NEW.domain, NEW.ocr_text, NEW.vlm_summary);
END;

CREATE TRIGGER IF NOT EXISTS raw_events_ad AFTER DELETE ON raw_events BEGIN
    INSERT INTO events_fts(events_fts, rowid, id, ts, app_name, window_title, url, domain, ocr_text, vlm_summary)
    VALUES ('delete', OLD.rowid, OLD.id, OLD.ts, OLD.app_name, OLD.window_title, OLD.url, OLD.domain, OLD.ocr_text, OLD.vlm_summary);
END;
"""


# ── 数据库管理类 ────────────────────────────────────────────────

class Storage:
    """SQLite 存储管理器。"""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """打开数据库连接。"""
        if self.conn is None:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
        return self.conn

    def close(self):
        """关闭数据库连接。"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def init_db(self):
        """初始化数据库表结构。"""
        conn = self.connect()
        conn.executescript(_SCHEMA_SQL)
        try:
            conn.executescript(_FTS5_SQL)
        except sqlite3.OperationalError:
            # FTS5 不可用时静默跳过（极少数环境）
            pass
        conn.commit()

    def get_status(self) -> dict:
        """获取数据库状态摘要。"""
        conn = self.connect()
        event_count = conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
        session_count = conn.execute("SELECT COUNT(*) FROM activity_sessions").fetchone()[0]
        browser_count = conn.execute("SELECT COUNT(*) FROM browser_events").fetchone()[0]
        return {
            "db_path": str(self.db_path),
            "raw_events": event_count,
            "activity_sessions": session_count,
            "browser_events": browser_count,
        }

    # ── raw_events CRUD ────────────────────────────────────────

    def insert_event(self, event) -> str:
        """插入一条原始事件。接受 RawEvent 或 dict。"""
        conn = self.connect()
        if hasattr(event, "model_dump"):
            d = event.model_dump()
        else:
            d = dict(event)
        conn.execute(
            """INSERT OR REPLACE INTO raw_events
               (id, ts, source, app_name, process_name, window_title, url, domain,
                screenshot_path, image_hash, duplicate_of, ocr_text, vlm_summary,
                vlm_json, sensitive, created_at)
               VALUES (:id, :ts, :source, :app_name, :process_name, :window_title,
                       :url, :domain, :screenshot_path, :image_hash, :duplicate_of,
                       :ocr_text, :vlm_summary, :vlm_json, :sensitive, :created_at)""",
            d,
        )
        conn.commit()
        return d["id"]

    def insert_browser_event(self, event) -> str:
        """插入一条浏览器事件。"""
        conn = self.connect()
        if hasattr(event, "model_dump"):
            d = event.model_dump()
        else:
            d = dict(event)
        conn.execute(
            """INSERT OR REPLACE INTO browser_events
               (id, ts, browser, url, domain, title, tab_id, window_id, active, created_at)
               VALUES (:id, :ts, :browser, :url, :domain, :title, :tab_id, :window_id, :active, :created_at)""",
            d,
        )
        conn.commit()
        return d["id"]

    def insert_session(self, session) -> str:
        """插入一条活动会话。"""
        conn = self.connect()
        if hasattr(session, "model_dump"):
            d = session.model_dump()
        else:
            d = dict(session)
        conn.execute(
            """INSERT OR REPLACE INTO activity_sessions
               (id, ts_start, ts_end, topic, apps, urls, summary, evidence_event_ids, created_at)
               VALUES (:id, :ts_start, :ts_end, :topic, :apps, :urls, :summary, :evidence_event_ids, :created_at)""",
            d,
        )
        conn.commit()
        return d["id"]

    def get_recent_events(self, minutes: int = 30) -> List[dict]:
        """获取最近 N 分钟的事件。"""
        conn = self.connect()
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
        rows = conn.execute(
            "SELECT * FROM raw_events WHERE ts >= ? ORDER BY ts DESC LIMIT 100",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_events_by_date(self, date: str) -> List[dict]:
        """获取指定日期的事件（date 格式 YYYY-MM-DD）。"""
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM raw_events WHERE ts LIKE ? ORDER BY ts ASC",
            (f"{date}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_sessions_by_date(self, date: str) -> List[dict]:
        """获取指定日期的会话。"""
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM activity_sessions WHERE ts_start LIKE ? ORDER BY ts_start ASC",
            (f"{date}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_fts(self, query: str, limit: int = 20) -> List[dict]:
        """FTS5 全文搜索。"""
        conn = self.connect()
        try:
            rows = conn.execute(
                """SELECT raw_events.*, rank
                   FROM events_fts
                   JOIN raw_events ON events_fts.id = raw_events.id
                   WHERE events_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            # FTS 不可用时，退化为 LIKE 搜索
            rows = conn.execute(
                """SELECT * FROM raw_events
                   WHERE app_name LIKE ? OR window_title LIKE ? OR url LIKE ?
                      OR ocr_text LIKE ? OR vlm_summary LIKE ?
                   ORDER BY ts DESC LIMIT ?""",
                (f"%{query}%",) * 5 + (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_events(self, conditions: dict) -> int:
        """按条件删除事件，返回删除数量。"""
        conn = self.connect()
        where_parts = []
        params = []

        if conditions.get("time_range"):
            from datetime import datetime, timedelta
            # 解析时间范围
            tr = conditions["time_range"]
            if tr.startswith("last_") and tr.endswith("d"):
                days = int(tr.replace("last_", "").replace("d", ""))
                cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
                where_parts.append("ts >= ?")
                params.append(cutoff)
            elif tr.startswith("last_") and tr.endswith("h"):
                hours = int(tr.replace("last_", "").replace("h", ""))
                cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
                where_parts.append("ts >= ?")
                params.append(cutoff)

        if conditions.get("app_name"):
            where_parts.append("app_name LIKE ?")
            params.append(f"%{conditions['app_name']}%")

        if conditions.get("domain"):
            where_parts.append("domain LIKE ?")
            params.append(f"%{conditions['domain']}%")

        if not where_parts:
            return 0

        where_sql = " AND ".join(where_parts)

        # 先收集要删除的截图路径
        rows = conn.execute(
            f"SELECT screenshot_path FROM raw_events WHERE {where_sql} AND screenshot_path IS NOT NULL",
            params,
        ).fetchall()
        screenshot_paths = [Path(r["screenshot_path"]) for r in rows if r["screenshot_path"]]

        # 删除数据库记录
        cursor = conn.execute(f"DELETE FROM raw_events WHERE {where_sql}", params)
        deleted = cursor.rowcount

        # 清理 recall_chunks
        conn.execute(
            f"DELETE FROM recall_chunks WHERE event_id IN (SELECT id FROM raw_events WHERE {where_sql})",
            params,
        )

        # 删除浏览器事件（如果有 domain 条件）
        if conditions.get("domain"):
            conn.execute(
                "DELETE FROM browser_events WHERE domain LIKE ?",
                (f"%{conditions['domain']}%",),
            )
        if conditions.get("time_range"):
            for part in where_parts:
                if "ts >=" in part:
                    conn.execute(f"DELETE FROM browser_events WHERE {part}", params[:1])

        conn.commit()

        # 删除本地截图文件
        deleted_files = 0
        for p in screenshot_paths:
            if p.exists():
                try:
                    p.unlink()
                    deleted_files += 1
                except OSError:
                    pass

        return deleted

    def count_events(self) -> int:
        """统计事件总数。"""
        conn = self.connect()
        return conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]

    def count_sessions(self) -> int:
        """统计会话总数。"""
        conn = self.connect()
        return conn.execute("SELECT COUNT(*) FROM activity_sessions").fetchone()[0]


# ── 全局单例 ────────────────────────────────────────────────────

_storage: Optional[Storage] = None


def get_storage() -> Storage:
    """获取全局 Storage 单例。"""
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage


def close_storage():
    """关闭全局 Storage。"""
    global _storage
    if _storage:
        _storage.close()
        _storage = None
