"""MCP Server — 暴露上下文记忆工具给 Hermes Agent。

使用官方 MCP SDK (fastmcp) 实现。
工具：
  - recall_context: 语义检索上下文
  - get_recent_context: 获取最近活动
  - get_activity_timeline: 获取某天时间线
  - forget_context: 删除上下文记录
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "hermes-context-memory",
    description="本地上下文记忆服务 — 让 Agent 记住用户看过什么",
)


def _format_results(results: list, include_screenshots: bool = False) -> str:
    """格式化检索结果为 Agent 可读的文本。"""
    if not results:
        return "未找到相关上下文记录。"

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"--- 记录 {i} ---")
        lines.append(f"时间: {r.get('ts', '未知')}")
        lines.append(f"应用: {r.get('app_name') or '未知'}")
        lines.append(f"窗口标题: {r.get('window_title') or '未知'}")
        if r.get("url"):
            lines.append(f"URL: {r['url']}")
        if r.get("summary"):
            lines.append(f"摘要: {r['summary']}")
        lines.append(f"证据类型: {r.get('evidence_type', '未知')}")
        lines.append(f"敏感内容: {'是' if r.get('sensitive') else '否'}")
        if include_screenshots and r.get("screenshot_path"):
            lines.append(f"截图路径: {r['screenshot_path']}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def recall_context(
    query: str,
    time_range: str = "last_24h",
    top_k: int = 8,
    include_screenshots: bool = False,
) -> str:
    """根据语义查询本地屏幕/浏览器上下文记忆。

    Args:
        query: 查询内容，例如"我昨天看过 MineContext 吗"
        time_range: 时间范围，支持 last_24h, last_7d, last_30d, YYYY-MM-DD
        top_k: 返回结果数量
        include_screenshots: 是否包含截图路径

    Returns:
        格式化的上下文记录列表，包含时间、应用、窗口标题、URL、摘要。
    """
    try:
        from app.config import load_config
        from app.storage import Storage
        from app.models import RecallRequest
        from app.retrieval.search import search_context

        config = load_config()
        storage = Storage()
        storage.init_db()

        request = RecallRequest(
            query=query,
            time_range=time_range,
            top_k=top_k,
            include_screenshots=include_screenshots,
        )
        results = search_context(request, config)

        storage.close()

        # 转为字典列表
        result_dicts = [r.model_dump() for r in results]
        return _format_results(result_dicts, include_screenshots)

    except Exception as e:
        return f"检索失败: {e}"


@mcp.tool()
def get_recent_context(minutes: int = 30) -> str:
    """获取最近的活动上下文摘要。

    Args:
        minutes: 获取最近 N 分钟的活动，默认 30 分钟。

    Returns:
        最近活动的格式化摘要。
    """
    try:
        from app.storage import Storage

        storage = Storage()
        storage.init_db()
        events = storage.get_recent_events(minutes)
        storage.close()

        if not events:
            return f"最近 {minutes} 分钟内没有记录到活动。"

        # 按应用分组
        apps = {}
        for e in events:
            app_name = e.get("app_name") or "未知应用"
            if app_name not in apps:
                apps[app_name] = []
            apps[app_name].append(e)

        lines = [f"最近 {minutes} 分钟活动摘要（共 {len(events)} 条记录）：\n"]
        for app_name, app_events in apps.items():
            lines.append(f"【{app_name}】({len(app_events)} 条)")
            for e in app_events[:5]:  # 每个应用最多显示 5 条
                title = e.get("window_title", "")
                ts = e.get("ts", "")[:19]
                lines.append(f"  - [{ts}] {title}")
            if len(app_events) > 5:
                lines.append(f"  ... 还有 {len(app_events) - 5} 条")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return f"获取最近活动失败: {e}"


@mcp.tool()
def get_activity_timeline(date: str) -> str:
    """获取指定日期的活动时间线。

    Args:
        date: 日期，格式 YYYY-MM-DD，例如 "2026-06-01"

    Returns:
        该日期的时间线摘要。
    """
    try:
        from app.storage import Storage

        storage = Storage()
        storage.init_db()
        events = storage.get_events_by_date(date)
        sessions = storage.get_sessions_by_date(date)
        storage.close()

        lines = [f"📅 {date} 活动时间线\n"]

        if sessions:
            lines.append(f"== 活动会话 ({len(sessions)} 个) ==\n")
            for s in sessions:
                start = s.get("ts_start", "")[:19]
                end = s.get("ts_end", "")[:19]
                topic = s.get("topic", "未知")
                summary = s.get("summary", "")
                lines.append(f"  [{start} ~ {end}] {topic}")
                if summary:
                    lines.append(f"    {summary}")
                lines.append("")

        if events:
            lines.append(f"== 原始事件 ({len(events)} 条) ==\n")
            for e in events:
                ts = e.get("ts", "")[:19]
                app_name = e.get("app_name", "未知")
                title = e.get("window_title", "")
                sensitive = " 🔒" if e.get("sensitive") else ""
                lines.append(f"  [{ts}] {app_name}: {title}{sensitive}")

        if not events and not sessions:
            lines.append(f"日期 {date} 没有活动记录。")

        return "\n".join(lines)

    except Exception as e:
        return f"获取时间线失败: {e}"


@mcp.tool()
def forget_context(
    time_range: str = "",
    app_name: str = "",
    domain: str = "",
) -> str:
    """删除本地上下文记录和截图。

    Args:
        time_range: 时间范围，如 last_7d, last_30d
        app_name: 按应用名删除
        domain: 按域名删除
    """
    try:
        from app.storage import Storage

        if not time_range and not app_name and not domain:
            return "请至少指定一个删除条件: time_range, app_name, domain"

        storage = Storage()
        storage.init_db()

        conditions = {}
        if time_range:
            conditions["time_range"] = time_range
        if app_name:
            conditions["app_name"] = app_name
        if domain:
            conditions["domain"] = domain

        deleted = storage.delete_events(conditions)
        storage.close()

        return f"已删除 {deleted} 条记录及其关联截图。"

    except Exception as e:
        return f"删除失败: {e}"


def main():
    """启动 MCP Server。"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
