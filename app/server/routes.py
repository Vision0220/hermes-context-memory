"""API 路由定义 — 所有 REST 端点。

采集循环含：多屏截图、级联去重、自适应频率、VLM/Embedding 异步处理。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Query

from app.config import AppConfig, load_config
from app.models import (
    BrowserEvent, RecallRequest, RecallResponse, RecallResult,
    ForgetRequest, HealthResponse, RawEvent,
)
from app.storage import get_storage
from app.privacy import PrivacyGuard
from app.retrieval.search import search_context
from app.capture.screen import capture_screen, capture_screens_multi, compute_image_hash
from app.capture.window import get_active_window
from app.capture.dedup import CascadeDeduplicator
from app.capture.browser import parse_browser_event
from app.capture.idle import get_idle_level, compute_adaptive_interval, IdleLevel

logger = logging.getLogger(__name__)

router = APIRouter()

# 全局状态
_deduplicator: Optional[CascadeDeduplicator] = None
_capture_active = False
_vlm_queue: Optional[asyncio.Queue] = None


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

    summary = {
        "time_range": f"最近 {minutes} 分钟",
        "total_events": len(events),
        "apps": list(set(e.get("app_name", "") for e in events if e.get("app_name"))),
        "events": events[:50],
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


# ── VLM 异步处理队列 ────────────────────────────────────────────

class _VLMTask:
    """VLM 处理任务。"""
    def __init__(self, event_id: str, screenshot_path: str,
                 app_name: str, window_title: str, monitor_id: int):
        self.event_id = event_id
        self.screenshot_path = screenshot_path
        self.app_name = app_name
        self.window_title = window_title
        self.monitor_id = monitor_id
        self.superseded = False


async def _vlm_worker(config: AppConfig):
    """VLM 后台处理工作线程。从队列取任务，调用 VLM 分析，更新 DB。"""
    storage = get_storage()

    while True:
        try:
            task: _VLMTask = await _vlm_queue.get()

            if task.superseded:
                _vlm_queue.task_done()
                continue

            # 标记为处理中
            storage.update_event_fields(task.event_id, {"processing_status": "processing"})

            # VLM 分析
            from app.processing.vlm import analyze_screenshot
            from pathlib import Path
            from app.processing.ocr import get_ocr_engine

            ocr_engine = get_ocr_engine("noop")
            ocr_text = ocr_engine.extract_text(Path(task.screenshot_path))

            vlm_result = await analyze_screenshot(
                Path(task.screenshot_path), config,
                task.app_name, task.window_title, ocr_text,
            )

            update_fields = {}
            if ocr_text:
                update_fields["ocr_text"] = ocr_text
            if vlm_result:
                update_fields["vlm_summary"] = vlm_result.summary_zh
                update_fields["vlm_json"] = vlm_result.model_dump_json()
            update_fields["processing_status"] = "completed"

            storage.update_event_fields(task.event_id, update_fields)

            # Embedding（如果可用）
            if config.models.embedding.enabled and vlm_result:
                from app.processing.embedding import get_embedding
                text = f"{task.app_name} {task.window_title} {vlm_result.summary_zh}"
                embedding = await get_embedding(text, config)
                if embedding:
                    from app.retrieval.vector import store_embedding
                    store_embedding(storage.connect(), task.event_id, embedding)

            logger.debug("VLM 处理完成: %s (%s)", task.event_id[:8], task.app_name)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("VLM 工作出错: %s", e, exc_info=True)
        finally:
            _vlm_queue.task_done()


def _enqueue_vlm(task: _VLMTask):
    """将 VLM 任务入队。队列满时标记旧任务为 superseded。"""
    if _vlm_queue is None:
        return

    # 队列满时丢弃最旧的
    if _vlm_queue.full():
        try:
            old_task: _VLMTask = _vlm_queue.get_nowait()
            old_task.superseded = True
            logger.debug("队列满，丢弃旧任务: %s", old_task.event_id[:8])
        except asyncio.QueueEmpty:
            pass

    _vlm_queue.put_nowait(task)


# ── 采集循环（智能版）────────────────────────────────────────

async def capture_loop(config: AppConfig):
    """智能采集循环：多屏截图 + 级联去重 + 自适应频率 + VLM 异步处理。"""
    global _capture_active, _deduplicator, _vlm_queue
    _capture_active = True

    storage = get_storage()
    privacy = PrivacyGuard(config)

    # 初始化级联去重器
    dedup_cfg = config.capture.dedup
    _deduplicator = CascadeDeduplicator(
        hash_algorithm=dedup_cfg.hash_algorithm,
        hash_threshold=dedup_cfg.hash_threshold,
        ssim_threshold=dedup_cfg.ssim_threshold,
        thumbnail_size=tuple(dedup_cfg.thumbnail_size),
    )

    # 初始化 VLM 队列
    if config.models.vlm.enabled:
        _vlm_queue = asyncio.Queue(maxsize=10)
        asyncio.create_task(_vlm_worker(config))

    base_interval = config.capture.interval_seconds
    logger.info("智能采集循环启动: interval=%ds, per_monitor=%s, vlm=%s",
                base_interval, config.capture.per_monitor, config.models.vlm.enabled)

    while True:
        try:
            # 计算自适应间隔
            idle_level = get_idle_level()

            # L4 屏幕锁定 → 长睡
            if idle_level == IdleLevel.L4_PAUSED:
                await asyncio.sleep(30)
                continue

            queue_pressure = 0.0
            if _vlm_queue and _vlm_queue.maxsize:
                queue_pressure = _vlm_queue.qsize() / _vlm_queue.maxsize

            interval = compute_adaptive_interval(base_interval, idle_level, queue_pressure)
            await asyncio.sleep(interval)

            # 获取窗口信息
            window_info = get_active_window()
            app_name = window_info.app_name if window_info else ""
            process_name = window_info.process_name if window_info else ""
            window_title = window_info.window_title if window_info else ""
            ts = datetime.now().isoformat(timespec="seconds")

            # 隐私检查
            if privacy.is_sensitive(app_name, window_title):
                event_data = privacy.create_sensitive_event(ts, app_name, window_title)
                event_data["source"] = "screenshot"
                event_data["process_name"] = process_name
                event = RawEvent(**event_data)
                storage.insert_event(event)
                continue

            # 多屏截图
            if config.capture.per_monitor:
                screenshots = capture_screens_multi(config)
            else:
                single = capture_screen(config)
                screenshots = [(0, single)] if single else []

            for monitor_id, screenshot_path in screenshots:
                if not screenshot_path:
                    continue

                # 级联去重
                dedup_result = _deduplicator.check(
                    screenshot_path,
                    app_name=app_name,
                    window_title=window_title,
                    monitor_id=monitor_id,
                )

                # 获取图片尺寸
                img_width, img_height = None, None
                try:
                    from PIL import Image
                    with Image.open(str(screenshot_path)) as img:
                        img_width, img_height = img.size
                except Exception:
                    pass

                event = RawEvent(
                    ts=ts,
                    source="screenshot",
                    app_name=app_name,
                    process_name=process_name,
                    window_title=window_title,
                    screenshot_path=str(screenshot_path),
                    image_hash=dedup_result.thumbnail_md5,
                    duplicate_of=dedup_result.stage if dedup_result.is_duplicate else None,
                    sensitive=False,
                    monitor_id=monitor_id,
                    image_width=img_width,
                    image_height=img_height,
                    processing_status="skipped" if dedup_result.is_duplicate else "pending",
                )
                event_id = storage.insert_event(event)

                if not dedup_result.is_duplicate:
                    # 提交 VLM 异步处理
                    if config.models.vlm.enabled and _vlm_queue:
                        _enqueue_vlm(_VLMTask(
                            event_id=event_id,
                            screenshot_path=str(screenshot_path),
                            app_name=app_name,
                            window_title=window_title,
                            monitor_id=monitor_id,
                        ))
                    logger.info("截图 [%d] %s | %s | dedup=%s",
                                monitor_id, screenshot_path.name, app_name, dedup_result.stage)
                else:
                    logger.debug("重复 [%d] %s | dedup=%s",
                                 monitor_id, screenshot_path.name, dedup_result.stage)

        except asyncio.CancelledError:
            logger.info("采集循环已停止")
            break
        except Exception as e:
            logger.error("采集循环出错: %s", e, exc_info=True)
            await asyncio.sleep(5)

    _capture_active = False
