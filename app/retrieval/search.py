"""检索模块 — 统一检索接口，协调 FTS 和向量检索。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import List, Optional

from app.config import AppConfig
from app.models import RecallResult, RecallRequest
from app.storage import get_storage


def parse_time_range(time_range: str) -> Optional[str]:
    """解析时间范围字符串为 ISO 时间戳下限。

    支持格式：
      - "last_24h" — 最近 24 小时
      - "last_7d" — 最近 7 天
      - "last_30d" — 最近 30 天
      - "YYYY-MM-DD" — 特定日期
      - 任意 ISO 时间戳
    """
    now = datetime.now()

    if time_range == "last_24h":
        return (now - timedelta(hours=24)).isoformat(timespec="seconds")
    elif time_range == "last_7d":
        return (now - timedelta(days=7)).isoformat(timespec="seconds")
    elif time_range == "last_30d":
        return (now - timedelta(days=30)).isoformat(timespec="seconds")
    elif len(time_range) == 10 and time_range[4] == "-" and time_range[7] == "-":
        # YYYY-MM-DD 格式 — 返回当天开始
        return f"{time_range}T00:00:00"
    else:
        # 尝试直接作为 ISO 时间戳
        try:
            datetime.fromisoformat(time_range)
            return time_range
        except ValueError:
            # 默认最近 24 小时
            return (now - timedelta(hours=24)).isoformat(timespec="seconds")


def search_context(request: RecallRequest, config: AppConfig) -> List[RecallResult]:
    """执行上下文检索。

    优先使用 FTS5 全文检索（始终可用）。
    如果配置了向量检索且 embedding 可用，增加向量排序。
    """
    storage = get_storage()
    results: List[RecallResult] = []

    # 1. FTS5 检索
    if config.retrieval.use_fts_fallback:
        fts_results = storage.search_fts(request.query, limit=request.top_k * 2)
        for row in fts_results:
            # 应用时间范围过滤
            if request.time_range:
                cutoff = parse_time_range(request.time_range)
                if cutoff and (row.get("ts") or "") < cutoff:
                    continue

            # 应用过滤器
            if request.app_filter and request.app_filter.lower() not in (row.get("app_name") or "").lower():
                continue
            if request.domain_filter and request.domain_filter.lower() not in (row.get("domain") or "").lower():
                continue

            # 跳过敏感记录
            if row.get("sensitive"):
                continue

            # 构建摘要文本
            summary = row.get("vlm_summary") or row.get("ocr_text") or row.get("window_title") or ""

            results.append(RecallResult(
                score=0.8,  # FTS 默认分
                ts=row.get("ts", ""),
                app_name=row.get("app_name"),
                window_title=row.get("window_title"),
                url=row.get("url"),
                summary=summary[:200],
                evidence_type="screenshot" if row.get("screenshot_path") else "browser",
                screenshot_path=row.get("screenshot_path") if request.include_screenshots else None,
                sensitive=bool(row.get("sensitive")),
            ))

    # 2. 也搜索浏览器事件
    try:
        browser_results = _search_browser_events(request, storage)
        results.extend(browser_results)
    except Exception:
        pass

    # 3. 搜索会话
    try:
        session_results = _search_sessions(request, storage)
        results.extend(session_results)
    except Exception:
        pass

    # 去重并按分数排序
    seen_ts = set()
    unique_results = []
    for r in results:
        key = f"{r.ts}:{r.app_name}:{r.window_title}"
        if key not in seen_ts:
            seen_ts.add(key)
            unique_results.append(r)

    unique_results.sort(key=lambda r: r.score, reverse=True)
    return unique_results[:request.top_k]


def _search_browser_events(request: RecallRequest, storage) -> List[RecallResult]:
    """搜索浏览器事件。"""
    conn = storage.connect()
    cutoff = parse_time_range(request.time_range) if request.time_range else None

    conditions = ["1=1"]
    params = []

    if cutoff:
        conditions.append("ts >= ?")
        params.append(cutoff)

    if request.domain_filter:
        conditions.append("domain LIKE ?")
        params.append(f"%{request.domain_filter}%")

    # 文本匹配
    query_words = request.query.split()
    if query_words:
        text_conditions = []
        for word in query_words:
            text_conditions.append("(title LIKE ? OR url LIKE ?)")
            params.extend([f"%{word}%", f"%{word}%"])
        conditions.append(f"({' OR '.join(text_conditions)})")

    where_sql = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM browser_events WHERE {where_sql} ORDER BY ts DESC LIMIT ?",
        params + [request.top_k],
    ).fetchall()

    results = []
    for row in rows:
        row = dict(row)
        results.append(RecallResult(
            score=0.6,  # 浏览器事件分数略低
            ts=row.get("ts", ""),
            app_name=row.get("browser"),
            window_title=row.get("title"),
            url=row.get("url"),
            summary=row.get("title"),
            evidence_type="browser",
            sensitive=False,
        ))
    return results


def _search_sessions(request: RecallRequest, storage) -> List[RecallResult]:
    """搜索活动会话。"""
    conn = storage.connect()
    cutoff = parse_time_range(request.time_range) if request.time_range else None

    conditions = ["1=1"]
    params = []

    if cutoff:
        conditions.append("ts_start >= ?")
        params.append(cutoff)

    # 文本匹配
    query_words = request.query.split()
    if query_words:
        text_conditions = []
        for word in query_words:
            text_conditions.append("(topic LIKE ? OR summary LIKE ? OR apps LIKE ?)")
            params.extend([f"%{word}%"] * 3)
        conditions.append(f"({' OR '.join(text_conditions)})")

    where_sql = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM activity_sessions WHERE {where_sql} ORDER BY ts_start DESC LIMIT ?",
        params + [request.top_k],
    ).fetchall()

    results = []
    for row in rows:
        row = dict(row)
        results.append(RecallResult(
            score=0.7,
            ts=row.get("ts_start", ""),
            app_name=None,
            window_title=row.get("topic"),
            url=None,
            summary=row.get("summary"),
            evidence_type="session",
            sensitive=False,
        ))
    return results
