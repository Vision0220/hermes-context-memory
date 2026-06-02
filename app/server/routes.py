"""API 路由定义 — 所有 REST 端点。

采集循环含：多屏截图、级联去重、自适应频率、VLM/Embedding 异步处理。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

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


# ── 服务状态 ────────────────────────────────────────────────────

@router.get("/api/status")
async def api_status():
    """详细服务状态。"""
    config = load_config()
    storage = get_storage()
    db_status = storage.get_status()

    idle_level = "unknown"
    try:
        from app.capture.idle import get_idle_level
        idle_level = get_idle_level().name
    except Exception:
        pass

    queue_info = {"depth": 0, "maxsize": 0, "pressure": 0.0}
    if _vlm_queue and _vlm_queue.maxsize:
        queue_info = {
            "depth": _vlm_queue.qsize(),
            "maxsize": _vlm_queue.maxsize,
            "pressure": round(_vlm_queue.qsize() / _vlm_queue.maxsize, 2),
        }

    return {
        "status": "running",
        "version": "0.2.0",
        "capture_active": _capture_active,
        "idle_level": idle_level,
        "queue": queue_info,
        "database": db_status,
        "models": {
            "vlm": {"enabled": config.models.vlm.enabled, "model": config.models.vlm.model},
            "embedding": {"enabled": config.models.embedding.enabled, "model": config.models.embedding.model},
        },
    }


# ── 配置管理 ────────────────────────────────────────────────────

@router.get("/api/config")
async def get_config():
    """获取当前配置（隐藏敏感信息）。"""
    config = load_config()
    data = config.model_dump()
    # 脱敏 API key
    if data.get("models", {}).get("vlm", {}).get("api_key"):
        key = data["models"]["vlm"]["api_key"]
        data["models"]["vlm"]["api_key"] = key[:8] + "***" if len(key) > 8 else "***"
    if data.get("models", {}).get("embedding", {}).get("api_key"):
        key = data["models"]["embedding"]["api_key"]
        data["models"]["embedding"]["api_key"] = key[:8] + "***" if len(key) > 8 else "***"
    return data


@router.post("/api/config")
async def update_config(updates: dict):
    """更新运行时配置（写入 config.yaml）。"""
    import yaml
    from app.config import CONFIG_PATH
    config = load_config()
    data = config.model_dump()
    # 递归合并
    def _merge(base, override):
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                _merge(base[k], v)
            else:
                base[k] = v
    _merge(data, updates)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    return {"status": "ok", "message": "配置已更新，重启服务后生效"}


# ── 预热 ────────────────────────────────────────────────────────

@router.post("/api/warmup")
async def warmup():
    """手动触发 VLM/Embedding 预热。"""
    config = load_config()
    results = {}

    if config.models.vlm.enabled:
        from app.processing.vlm import warmup_vlm
        import time
        start = time.time()
        ok = await warmup_vlm(config)
        latency = int((time.time() - start) * 1000)
        results["vlm"] = {"ok": ok, "latency_ms": latency}

    if config.models.embedding.enabled:
        from app.processing.embedding import warmup_embedding
        import time
        start = time.time()
        ok = await warmup_embedding(config)
        latency = int((time.time() - start) * 1000)
        results["embedding"] = {"ok": ok, "latency_ms": latency}

    return {"status": "ok", "results": results}


# ── 单次截图 ────────────────────────────────────────────────────

@router.post("/api/capture-once")
async def api_capture_once():
    """手动触发一次截图采集。"""
    config = load_config()
    storage = get_storage()
    privacy = PrivacyGuard(config)

    from app.capture.screen import capture_screen, capture_screens_multi
    from app.capture.dedup import CascadeDeduplicator

    window_info = get_active_window()
    app_name = window_info.app_name if window_info else ""
    window_title = window_info.window_title if window_info else ""
    ts = datetime.now().isoformat(timespec="seconds")

    if privacy.is_sensitive(app_name, window_title):
        return {"status": "filtered", "reason": "sensitive"}

    dedup_cfg = config.capture.dedup
    dedup = CascadeDeduplicator(
        hash_algorithm=dedup_cfg.hash_algorithm,
        hash_threshold=dedup_cfg.hash_threshold,
        ssim_threshold=dedup_cfg.ssim_threshold,
        thumbnail_size=tuple(dedup_cfg.thumbnail_size),
    )

    if config.capture.per_monitor:
        screenshots = capture_screens_multi(config)
    else:
        single = capture_screen(config)
        screenshots = [(0, single)] if single else []

    results = []
    for monitor_id, path in screenshots:
        if not path:
            results.append({"monitor": monitor_id, "status": "failed"})
            continue
        dr = dedup.check(path, app_name=app_name, window_title=window_title, monitor_id=monitor_id)
        event = RawEvent(
            ts=ts, source="screenshot", app_name=app_name,
            window_title=window_title, screenshot_path=str(path),
            image_hash=dr.thumbnail_md5, duplicate_of=dr.stage if dr.is_duplicate else None,
            monitor_id=monitor_id, processing_status="skipped" if dr.is_duplicate else "pending",
        )
        eid = storage.insert_event(event)
        results.append({"monitor": monitor_id, "event_id": eid, "duplicate": dr.is_duplicate, "stage": dr.stage})

    return {"status": "ok", "screenshots": results}


# ── /ui 简易 Web 界面 ──────────────────────────────────────────

@router.get("/ui", response_class=HTMLResponse)
async def ui_page():
    """简易 Web 界面，展示服务状态、队列、配置。"""
    config = load_config()
    storage = get_storage()
    db = storage.get_status()
    vlm_key = config.models.vlm.api_key
    emb_key = config.models.embedding.api_key
    vlm_masked = (vlm_key[:8] + "***") if len(vlm_key) > 8 else "***"
    emb_masked = (emb_key[:8] + "***") if len(emb_key) > 8 else "***"
    queue_depth = _vlm_queue.qsize() if _vlm_queue else 0
    queue_max = _vlm_queue.maxsize if _vlm_queue else 0
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Hermes Context Memory</title>
<style>
body{{font-family:system-ui;max-width:900px;margin:40px auto;padding:0 20px;background:#0d1117;color:#c9d1d9}}
h1{{color:#58a6ff}}h2{{color:#79c0ff;margin-top:30px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin:10px 0}}
.status{{display:inline-block;padding:4px 12px;border-radius:12px;font-size:13px}}
.ok{{background:#238636}}.warn{{background:#9e6a03}}.err{{background:#da3633}}
table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:6px 10px;border-bottom:1px solid #30363d}}
button{{background:#238636;color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;margin:4px}}
button:hover{{background:#2ea043}}
pre{{background:#161b22;padding:12px;border-radius:6px;overflow-x:auto;font-size:13px}}
</style></head><body>
<h1>Hermes Context Memory</h1>
<div class="card">
<span class="status {'ok' if _capture_active else 'warn'}">{'Capturing' if _capture_active else 'Stopped'}</span>
&nbsp; DB: {db['raw_events']} events, {db['browser_events']} browser, {db['activity_sessions']} sessions
&nbsp; Queue: {queue_depth}/{queue_max}
</div>
<h2>Models</h2>
<div class="card"><table>
<tr><th>Model</th><th>Status</th><th>Model Name</th><th>API Key</th></tr>
<tr><td>VLM</td><td><span class="status {'ok' if config.models.vlm.enabled else 'err'}">{'Enabled' if config.models.vlm.enabled else 'Disabled'}</span></td>
<td>{config.models.vlm.model}</td><td>{vlm_masked}</td></tr>
<tr><td>Embedding</td><td><span class="status {'ok' if config.models.embedding.enabled else 'err'}">{'Enabled' if config.models.embedding.enabled else 'Disabled'}</span></td>
<td>{config.models.embedding.model}</td><td>{emb_masked}</td></tr>
</table></div>
<h2>Capture</h2>
<div class="card"><table>
<tr><td>Interval</td><td>{config.capture.interval_seconds}s</td></tr>
<tr><td>Per Monitor</td><td>{config.capture.per_monitor}</td></tr>
<tr><td>Max Width</td><td>{config.capture.max_width}px</td></tr>
<tr><td>VLM Max Width</td><td>{config.capture.vlm_max_width}px</td></tr>
<tr><td>Dedup</td><td>{config.capture.dedup.hash_algorithm} threshold={config.capture.dedup.hash_threshold}</td></tr>
</table></div>
<h2>Actions</h2>
<div class="card">
<button onclick="doAction('/api/capture-once','POST')">Capture Once</button>
<button onclick="doAction('/api/warmup','POST')">Warmup</button>
<button onclick="doAction('/api/status','GET')">Status</button>
<pre id="out">Click an action...</pre>
<script>
function doAction(url, method) {{
  fetch(url, {{method: method}})
    .then(function(r) {{ return r.json(); }})
    .then(function(d) {{ document.getElementById('out').textContent = JSON.stringify(d, null, 2); }})
    .catch(function(e) {{ document.getElementById('out').textContent = 'Error: ' + e; }});
}}
</script>
</div>
<h2>Privacy</h2>
<div class="card">
Excluded apps: {', '.join(config.privacy.excluded_apps[:5])}...<br>
Excluded domains: {', '.join(config.privacy.excluded_domains)}
</div>
</body></html>"""

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
