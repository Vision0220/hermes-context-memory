"""会话聚合模块 — 将相近的事件聚合为 activity session。

默认聚合规则：相邻事件间隔 < 5 分钟 且 (app 相同 OR url 相同 OR window_title 相似)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import List, Optional

from app.models import ActivitySession


def _parse_ts(ts_str: str) -> Optional[datetime]:
    """解析 ISO 格式时间字符串。"""
    try:
        # 兼容多种 ISO 格式
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(ts_str, fmt)
            except ValueError:
                continue
        return None
    except Exception:
        return None


def _is_similar(a: str, b: str, threshold: float = 0.5) -> bool:
    """判断两个字符串是否相似。"""
    if not a or not b:
        return False
    a_lower = a.lower().strip()
    b_lower = b.lower().strip()
    if a_lower == b_lower:
        return True
    return SequenceMatcher(None, a_lower, b_lower).ratio() >= threshold


def sessionize_events(events: List[dict], gap_minutes: int = 5) -> List[ActivitySession]:
    """将事件列表聚合为活动会话。

    Args:
        events: 按时间排序的事件列表。
        gap_minutes: 聚合时间窗口（分钟）。

    Returns:
        聚合后的 ActivitySession 列表。
    """
    if not events:
        return []

    sessions: List[ActivitySession] = []
    current_group: List[dict] = [events[0]]

    for event in events[1:]:
        prev = current_group[-1]
        prev_ts = _parse_ts(prev.get("ts", ""))
        curr_ts = _parse_ts(event.get("ts", ""))

        if not prev_ts or not curr_ts:
            # 时间解析失败，强制开启新组
            if current_group:
                sessions.append(_create_session(current_group))
            current_group = [event]
            continue

        time_diff = abs((curr_ts - prev_ts).total_seconds() / 60)
        same_context = _same_context(prev, event)

        if time_diff <= gap_minutes and same_context:
            current_group.append(event)
        else:
            # 结束当前组，开始新组
            sessions.append(_create_session(current_group))
            current_group = [event]

    # 处理最后一组
    if current_group:
        sessions.append(_create_session(current_group))

    return sessions


def _same_context(a: dict, b: dict) -> bool:
    """判断两个事件是否属于同一上下文。"""
    # 应用名相同
    if a.get("app_name") and b.get("app_name"):
        if a["app_name"].lower() == b["app_name"].lower():
            return True
    # URL 域名相同
    if a.get("domain") and b.get("domain"):
        if a["domain"].lower() == b["domain"].lower():
            return True
    # 窗口标题相似
    if _is_similar(a.get("window_title", ""), b.get("window_title", "")):
        return True
    return False


def _create_session(events: List[dict]) -> ActivitySession:
    """从一组事件创建一个活动会话。"""
    if not events:
        raise ValueError("无法从空事件列表创建会话")

    ts_start = events[0].get("ts", "")
    ts_end = events[-1].get("ts", "")

    # 收集应用和 URL
    apps = list(set(e.get("app_name", "") for e in events if e.get("app_name")))
    urls = list(set(e.get("url", "") for e in events if e.get("url")))
    event_ids = [e.get("id", "") for e in events]

    # 生成会话主题（从窗口标题和 URL 中提取）
    topic = _infer_topic(events)

    # 生成摘要
    summary = _generate_summary(events, topic, apps, urls)

    return ActivitySession(
        ts_start=ts_start,
        ts_end=ts_end,
        topic=topic,
        apps=json.dumps(apps, ensure_ascii=False),
        urls=json.dumps(urls, ensure_ascii=False),
        summary=summary,
        evidence_event_ids=json.dumps(event_ids),
    )


def _infer_topic(events: List[dict]) -> str:
    """从事件列表推断会话主题。"""
    # 优先使用 VLM 摘要
    for e in events:
        vlm = e.get("vlm_summary")
        if vlm:
            return vlm[:100]

    # 其次使用窗口标题
    titles = [e.get("window_title", "") for e in events if e.get("window_title")]
    if titles:
        # 取最常见的标题
        from collections import Counter
        most_common = Counter(titles).most_common(1)[0][0]
        return most_common[:100]

    # 最后使用 URL
    urls = [e.get("url", "") for e in events if e.get("url")]
    if urls:
        return urls[0][:100]

    return "未知活动"


def _generate_summary(events: List[dict], topic: str, apps: List[str], urls: List[str]) -> str:
    """生成会话的文本摘要。"""
    parts = []
    if topic:
        parts.append(f"主题: {topic}")
    if apps:
        parts.append(f"应用: {', '.join(apps[:3])}")
    if urls:
        parts.append(f"访问: {', '.join(urls[:3])}")
    parts.append(f"事件数: {len(events)}")
    return " | ".join(parts)
