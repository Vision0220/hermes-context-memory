"""浏览器上下文采集 — 接收浏览器扩展上报的事件，提取域名。"""

from __future__ import annotations

from urllib.parse import urlparse
from typing import Optional


def extract_domain(url: str) -> Optional[str]:
    """从 URL 提取域名。"""
    try:
        parsed = urlparse(url)
        return parsed.netloc or None
    except Exception:
        return None


def parse_browser_event(data: dict) -> dict:
    """解析浏览器扩展上报的事件数据，补充 domain 字段。

    Args:
        data: 浏览器扩展 POST 的原始数据。

    Returns:
        规范化后的事件字典。
    """
    url = data.get("url", "")
    return {
        "ts": data.get("ts", ""),
        "browser": data.get("browser", "unknown"),
        "url": url,
        "domain": extract_domain(url),
        "title": data.get("title", ""),
        "tab_id": str(data.get("tab_id", "")),
        "window_id": str(data.get("window_id", "")),
        "active": data.get("active", True),
    }
