"""API 路由定义 — 所有 REST 端点。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from app.config import AppConfig, load_config
from app.models import (
    BrowserEvent, RecallRequest, RecallResponse, RecallResult,
    ForgetRequest, HealthResponse, RawEvent,
)
from app.storage import get_storage
from app.privacy import PrivacyGuard
from app.retrieval.search import search_context
from app.capture.screen import capture_screen, compute_image_hash
from app.capture.window import get_active_window
from app.capture.dedup import Deduplicator
from app.capture.browser import parse_browser_event

logger = logging.getLogger(__name__)

router = APIRouter()

# 全局去重器
_deduplicator = Deduplicator()
_capture_active = False


# ── 健康检查 ────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health():
    """服务健康检查。"""
    config = load_config()
    storage = get_storage()

    db_status = "ok"
    try:
        storage.get_status()
    except Exception:
        db_status = "error"

    return HealthResponse(
        status="ok",
        database=db_status,
        capture_active=_capture_active,
        vlm_available=config.models.vlm.enabled,
        embedding_available=config.models.embedding.enabled,
        total_events=storage.count_events(),
        total_sessions=storage.count_sessions(),
    )


# ── 浏览器事件接收 ──────────────────────────────────────────────

@router.post("/api/browser/events")
async def receive_browser_event(data: dict):
    """接收浏览器扩展上报的 tab 事件。"""
    config = load_config()
    storage = get_storage()
    privacy = PrivacyGuard(config)

    parsed = parse_browser_event(data)

    # 隐私检查
    if privacy.is_domain_excluded(parsed.get("domain"), parsed.get("url")):
        return {"status": "filtered", "reason": "domain_excluded"}

    event = BrowserEvent(**{k: v for k, v in parsed.items() if k in BrowserEvent.model_fields})
    event_id = storage.insert_browser_event(event)
    return {"status": "ok", "id": event_id}


# ── Recall 检索 ────────────────────────────────────────────────

@router.post("/api/recall", response_model=RecallResponse)
async def recall(request: RecallRequest):
    """语义检索本地上下文记忆。"""
    config = load_config()
    results = search_context(request, config)
    return RecallResponse(query=request.query, results=results)


# ── 最近活动 ────────────────────────────────────────────────────

@router.get("/api/recent")
async def recent(minutes: int = Query(30, ge=1, le=1440)):
    """获取最近 N 分钟的活动摘要。"""
    storage = get_storage()
    events = storage.get_recent_events(minutes)

    # 简单汇总
    summary = {
        "time_range": f"最近 {minutes} 分钟",
        "total_events": len(events),
        "apps": list(set(e.get("app_name", "") for e in events if e.get("app_name"))),
        "events": events[:50],  # 限制返回数量
    }
    return summary


# ── 时间线 ──────────────────────────────────────────────────────

@router.get("/api/timeline")
async def timeline(date: str = Query(..., description="日期，格式 YYYY-MM-DD")):
    """获取指定日期的活动时间线。"""
    storage = get_storage()
    events = storage.get_events_by_date(date)
    sessions = storage.get_sessions_by_date(date)

    return {
        "date": date,
        "total_events": len(events),
        "total_sessions": len(sessions),
        "events": events,
        "sessions": sessions,
    }


# ── 遗忘 ────────────────────────────────────────────────────────

@router.post("/api/forget")
async def forget(request: ForgetRequest):
    """删除指定条件的上下文记录和截图。"""
    storage = get_storage()
    conditions = {}
    if request.time_range:
        conditions["time_range"] = request.time_range
    if request.app_name:
        conditions["app_name"] = request.app_name
    if request.domain:
        conditions["domain"] = request.domain

    if not conditions:
        return {"status": "error", "message": "请至少指定一个删除条件"}

    deleted = storage.delete_events(conditions)
    return {"status": "ok", "deleted_count": deleted}


# ── 采集循环 ────────────────────────────────────────────────────

async def capture_loop(config: AppConfig):
    """后台截图采集循环。"""
    global _capture_active
    _capture_active = True
    storage = get_storage()
    privacy = PrivacyGuard(config)

    logger.info("采集循环启动")

    while True:
        try:
            await asyncio.sleep(config.capture.interval_seconds)

            # 获取当前窗口信息
            window_info = get_active_window()
            app_name = window_info.app_name if window_info else ""
            process_name = window_info.process_name if window_info else ""
            window_title = window_info.window_title if window_info else ""

            ts = datetime.now().isoformat(timespec="seconds")

            # 隐私检查
            if privacy.is_sensitive(app_name, window_title):
                # 敏感窗口 — 记录低细节事件，不保存截图
                event_data = privacy.create_sensitive_event(ts, app_name, window_title)
                event_data["source"] = "screenshot"
                event_data["process_name"] = process_name
                event = RawEvent(**event_data)
                storage.insert_event(event)
                logger.debug("敏感窗口已记录（不保存截图）: %s", app_name)
                continue

            # 截图
            screenshot_path = capture_screen(config)
            if not screenshot_path:
                continue

            # 计算哈希
            image_hash = compute_image_hash(screenshot_path)

            # 去重检查
            is_dup = _deduplicator.is_duplicate(image_hash)

            event = RawEvent(
                ts=ts,
                source="screenshot",
                app_name=app_name,
                process_name=process_name,
                window_title=window_title,
                screenshot_path=str(screenshot_path),
                image_hash=image_hash,
                duplicate_of="previous" if is_dup else None,
                sensitive=False,
            )
            storage.insert_event(event)

            if is_dup:
                logger.debug("重复截图，跳过处理: %s", screenshot_path.name)
            else:
                logger.info("截图已保存: %s (%s)", screenshot_path.name, app_name)

        except asyncio.CancelledError:
            logger.info("采集循环已停止")
            break
        except Exception as e:
            logger.error("采集循环出错: %s", e, exc_info=True)
            await asyncio.sleep(5)  # 出错后短暂等待

    _capture_active = False
