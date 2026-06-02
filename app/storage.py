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
    created_at TEXT NOT NULL,
    monitor_id INTEGER DEFAULT 0,
    processing_status TEXT DEFAULT 'pending',
    image_width INTEGER,
    image_height INTEGER,
    reused_from_event_id TEXT,
    skip_reason TEXT
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

CREATE TABLE IF NOT EXISTS screenshot_tiles (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    monitor_id INTEGER DEFAULT 0,
    tile_id INTEGER DEFAULT 0,
    tile_row INTEGER,
    tile_col INTEGER,
    x INTEGER DEFAULT 0,
    y INTEGER DEFAULT 0,
    width INTEGER DEFAULT 0,
    height INTEGER DEFAULT 0,
    tile_path TEXT,
    tile_hash TEXT,
    changed INTEGER DEFAULT 0,
    changed_score REAL DEFAULT 0.0,
    text_density REAL DEFAULT 0.0,
    ocr_text TEXT,
    vlm_summary TEXT,
    reused_from_tile_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduler_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    interval_seconds REAL,
    idle_level TEXT,
    queue_depth INTEGER,
    queue_pressure REAL,
    captures_total INTEGER DEFAULT 0,
    duplicates_skipped INTEGER DEFAULT 0,
    vlm_processed INTEGER DEFAULT 0,
    vlm_failed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS model_status (
    model_type TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 0,
    base_url TEXT,
    model_name TEXT,
    status TEXT DEFAULT 'unknown',
    last_warmup_ts TEXT,
    warmup_latency_ms INTEGER,
    last_error TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS event_vectors (
    event_id TEXT PRIMARY KEY,
    embedding BLOB
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
        """初始化数据库表结构，含自动迁移。"""
        conn = self.connect()
        conn.executescript(_SCHEMA_SQL)
        try:
            conn.executescript(_FTS5_SQL)
        except sqlite3.OperationalError:
            pass
        # 自动迁移：为已有表添加新列（IF NOT EXISTS 不支持，用 try/except）
        _migrations = [
            "ALTER TABLE raw_events ADD COLUMN monitor_id INTEGER DEFAULT 0",
            "ALTER TABLE raw_events ADD COLUMN processing_status TEXT DEFAULT 'pending'",
            "ALTER TABLE raw_events ADD COLUMN image_width INTEGER",
            "ALTER TABLE raw_events ADD COLUMN image_height INTEGER",
            "ALTER TABLE raw_events ADD COLUMN reused_from_event_id TEXT",
            "ALTER TABLE raw_events ADD COLUMN skip_reason TEXT",
            "ALTER TABLE screenshot_tiles ADD COLUMN monitor_id INTEGER DEFAULT 0",
            "ALTER TABLE screenshot_tiles ADD COLUMN tile_id INTEGER DEFAULT 0",
            "ALTER TABLE screenshot_tiles ADD COLUMN x INTEGER DEFAULT 0",
            "ALTER TABLE screenshot_tiles ADD COLUMN y INTEGER DEFAULT 0",
            "ALTER TABLE screenshot_tiles ADD COLUMN width INTEGER DEFAULT 0",
            "ALTER TABLE screenshot_tiles ADD COLUMN height INTEGER DEFAULT 0",
            "ALTER TABLE screenshot_tiles ADD COLUMN changed_score REAL DEFAULT 0.0",
            "ALTER TABLE screenshot_tiles ADD COLUMN ocr_text TEXT",
            "ALTER TABLE screenshot_tiles ADD COLUMN reused_from_tile_id INTEGER",
        ]
        for sql in _migrations:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # 列已存在
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
        # 为新字段提供默认值（兼容旧数据）
        d.setdefault("monitor_id", 0)
        d.setdefault("processing_status", "pending")
        d.setdefault("image_width", None)
        d.setdefault("image_height", None)
        d.setdefault("reused_from_event_id", None)
        d.setdefault("skip_reason", None)
        conn.execute(
            """INSERT OR REPLACE INTO raw_events
               (id, ts, source, app_name, process_name, window_title, url, domain,
                screenshot_path, image_hash, duplicate_of, ocr_text, vlm_summary,
                vlm_json, sensitive, created_at, monitor_id, processing_status,
                image_width, image_height, reused_from_event_id, skip_reason)
               VALUES (:id, :ts, :source, :app_name, :process_name, :window_title,
                       :url, :domain, :screenshot_path, :image_hash, :duplicate_of,
                       :ocr_text, :vlm_summary, :vlm_json, :sensitive, :created_at,
                       :monitor_id, :processing_status, :image_width, :image_height,
                       :reused_from_event_id, :skip_reason)""",
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

    def update_event_fields(self, event_id: str, fields: dict) -> bool:
        """更新事件的部分字段（用于 VLM/Embedding 处理完成后回写）。"""
        conn = self.connect()
        if not fields:
            return False
        set_parts = [f"{k} = ?" for k in fields]
        values = list(fields.values()) + [event_id]
        conn.execute(
            f"UPDATE raw_events SET {', '.join(set_parts)} WHERE id = ?",
            values,
        )
        conn.commit()
        return True

    def get_pending_events(self, limit: int = 10) -> List[dict]:
        """获取待处理的事件（用于 VLM/Embedding 异步处理）。"""
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM raw_events WHERE processing_status = 'pending' AND sensitive = 0 ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def insert_tile(self, tile_data: dict) -> str:
        """插入一条瓦片记录。"""
        conn = self.connect()
        from datetime import datetime
        tile_data.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
        tile_data.setdefault("monitor_id", 0)
        tile_data.setdefault("tile_id", 0)
        tile_data.setdefault("x", 0)
        tile_data.setdefault("y", 0)
        tile_data.setdefault("width", 0)
        tile_data.setdefault("height", 0)
        tile_data.setdefault("changed_score", 0.0)
        tile_data.setdefault("ocr_text", None)
        tile_data.setdefault("reused_from_tile_id", None)
        conn.execute(
            """INSERT OR REPLACE INTO screenshot_tiles
               (id, event_id, monitor_id, tile_id, tile_row, tile_col,
                x, y, width, height, tile_path, tile_hash, changed, changed_score,
                text_density, ocr_text, vlm_summary, reused_from_tile_id, created_at)
               VALUES (:id, :event_id, :monitor_id, :tile_id, :tile_row, :tile_col,
                        :x, :y, :width, :height, :tile_path, :tile_hash, :changed,
                        :changed_score, :text_density, :ocr_text, :vlm_summary,
                        :reused_from_tile_id, :created_at)""",
            tile_data,
        )
        conn.commit()
        return tile_data.get("id", "")

    def persist_metrics(self, metrics_data: dict):
        """持久化调度器指标到 scheduler_metrics 表。"""
        conn = self.connect()
        from datetime import datetime
        conn.execute(
            """INSERT INTO scheduler_metrics
               (ts, interval_seconds, idle_level, queue_depth, queue_pressure,
                captures_total, duplicates_skipped, vlm_processed, vlm_failed)
               VALUES (:ts, :interval_seconds, :idle_level, :queue_depth, :queue_pressure,
                        :captures_total, :duplicates_skipped, :vlm_processed, :vlm_failed)""",
            {
                "ts": metrics_data.get("ts", datetime.now().isoformat(timespec="seconds")),
                "interval_seconds": metrics_data.get("current_interval", 15.0),
                "idle_level": metrics_data.get("idle_level", ""),
                "queue_depth": metrics_data.get("queue_depth", 0),
                "queue_pressure": metrics_data.get("queue_pressure", 0.0),
                "captures_total": metrics_data.get("captures_total", 0),
                "duplicates_skipped": metrics_data.get("duplicates_skipped", 0),
                "vlm_processed": metrics_data.get("vlm_processed", 0),
                "vlm_failed": metrics_data.get("vlm_failed", 0),
            },
        )
        conn.commit()

    def get_recent_sessions(self, minutes: int = 60) -> List[dict]:
        """获取最近的活动会话。"""
        conn = self.connect()
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
        rows = conn.execute(
            "SELECT * FROM activity_sessions WHERE ts_start >= ? ORDER BY ts_start DESC LIMIT 50",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]

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
        """FTS5 全文搜索。CJK 查询自动退化为关键词 LIKE 搜索。"""
        conn = self.connect()
        has_cjk = any('一' <= c <= '鿿' or '㐀' <= c <= '䶿' for c in query)

        if not has_cjk:
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
                if rows:
                    return [dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass

        # CJK 关键词提取：2-gram 分词 + 去停用词
        if has_cjk:
            keywords = self._extract_cjk_keywords(query)
        else:
            keywords = [query]

        if not keywords:
            return []

        # 对每个关键词做 LIKE 搜索，合并去重，按匹配数排序
        seen = {}
        for kw in keywords:
            if len(kw) < 1:
                continue
            rows = conn.execute(
                """SELECT * FROM raw_events
                   WHERE app_name LIKE ? OR window_title LIKE ? OR url LIKE ?
                      OR ocr_text LIKE ? OR vlm_summary LIKE ?
                   ORDER BY ts DESC LIMIT ?""",
                (f"%{kw}%",) * 5 + (limit,),
            ).fetchall()
            for r in rows:
                r = dict(r)
                rid = r.get("id", "")
                if rid not in seen:
                    seen[rid] = {"row": r, "hits": 0}
                seen[rid]["hits"] += 1

            # 搜索浏览器事件
            browser_rows = conn.execute(
                """SELECT id, ts, browser as app_name, title as window_title, url, domain,
                          'browser' as source, created_at
                   FROM browser_events
                   WHERE title LIKE ? OR url LIKE ? OR domain LIKE ?
                   ORDER BY ts DESC LIMIT ?""",
                (f"%{kw}%",) * 3 + (limit,),
            ).fetchall()
            for r in browser_rows:
                r = dict(r)
                rid = r.get("id", "")
                if rid not in seen:
                    seen[rid] = {"row": r, "hits": 0}
                seen[rid]["hits"] += 1

            # 搜索 recall_chunks（包含中文摘要）
            chunk_rows = conn.execute(
                """SELECT rc.event_id, re.ts, re.app_name, re.window_title, re.url,
                          re.domain, re.screenshot_path, re.image_hash, re.duplicate_of,
                          re.ocr_text, rc.chunk_text as vlm_summary, re.vlm_json,
                          re.sensitive, re.created_at, re.monitor_id,
                          re.processing_status, re.image_width, re.image_height,
                          re.reused_from_event_id, re.skip_reason, re.source
                   FROM recall_chunks rc
                   LEFT JOIN raw_events re ON rc.event_id = re.id
                   WHERE rc.chunk_text LIKE ?
                   ORDER BY re.ts DESC LIMIT ?""",
                (f"%{kw}%", limit),
            ).fetchall()
            for r in chunk_rows:
                r = dict(r)
                rid = r.get("event_id", "") or r.get("id", "")
                if rid and rid not in seen:
                    seen[rid] = {"row": r, "hits": 0}
                if rid:
                    seen[rid]["hits"] += 1

        # 按匹配关键词数降序排列
        results = sorted(seen.values(), key=lambda x: x["hits"], reverse=True)
        return [r["row"] for r in results[:limit]]

    def _extract_cjk_keywords(self, query: str) -> List[str]:
        """从 CJK 查询中提取关键词（2-gram + 拉丁词 + 去停用词）。"""
        stops = set("的了是在有不人大中上为这个们这来和到说就也出会能对可你着"
                     "那得地而过子下么她好将把当只与让给被又从去已经"
                     "刚才什么哪个怎我")

        # 提取拉丁词（英文/数字）
        import re
        latin_words = re.findall(r'[A-Za-z0-9]{2,}', query)

        # 提取连续 CJK 字符
        cjk_chars = [c for c in query if '一' <= c <= '鿿' or '㐀' <= c <= '䶿']
        if not cjk_chars and not latin_words:
            return [query]

        # CJK 2-gram
        bigrams = set()
        for i in range(len(cjk_chars) - 1):
            bg = cjk_chars[i] + cjk_chars[i + 1]
            if bg not in stops and not all(c in stops for c in bg):
                bigrams.add(bg)

        # CJK 单字符（非停用）
        singles = {c for c in cjk_chars if c not in stops}

        # 合并：拉丁词 + bigrams + singles
        keywords = latin_words + list(bigrams) + list(singles)
        return keywords[:15]

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
