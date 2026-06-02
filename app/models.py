"""数据模型定义 — Pydantic schemas 用于 API 请求/响应和内部数据表示。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


def _uuid() -> str:
    return uuid.uuid4().hex[:16]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── 原始事件 ────────────────────────────────────────────────────

class RawEvent(BaseModel):
    """一次截图/浏览器/窗口事件的完整记录。"""
    id: str = Field(default_factory=_uuid)
    ts: str
    source: str  # screenshot / browser / window / system
    app_name: Optional[str] = None
    process_name: Optional[str] = None
    window_title: Optional[str] = None
    url: Optional[str] = None
    domain: Optional[str] = None
    screenshot_path: Optional[str] = None
    image_hash: Optional[str] = None
    duplicate_of: Optional[str] = None
    ocr_text: Optional[str] = None
    vlm_summary: Optional[str] = None
    vlm_json: Optional[str] = None
    sensitive: bool = False
    created_at: str = Field(default_factory=_now_iso)
    # 新增字段
    monitor_id: int = 0
    processing_status: str = "pending"  # pending / processing / completed / failed / skipped
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    reused_from_event_id: Optional[str] = None
    skip_reason: Optional[str] = None


# ── 浏览器事件 ──────────────────────────────────────────────────

class BrowserEvent(BaseModel):
    """浏览器扩展上报的 tab 事件。"""
    id: str = Field(default_factory=_uuid)
    ts: str
    browser: str = "chrome"
    url: str
    domain: Optional[str] = None
    title: str = ""
    tab_id: Optional[str] = None
    window_id: Optional[str] = None
    active: bool = True
    created_at: str = Field(default_factory=_now_iso)


# ── 活动会话 ────────────────────────────────────────────────────

class ActivitySession(BaseModel):
    """聚合后的活动会话（多个相近事件合并）。"""
    id: str = Field(default_factory=_uuid)
    ts_start: str
    ts_end: str
    topic: Optional[str] = None
    apps: Optional[str] = None  # JSON 数组字符串
    urls: Optional[str] = None  # JSON 数组字符串
    summary: Optional[str] = None
    evidence_event_ids: Optional[str] = None  # JSON 数组字符串
    created_at: str = Field(default_factory=_now_iso)


# ── 检索结果 ────────────────────────────────────────────────────

class RecallResult(BaseModel):
    """单条检索结果。"""
    score: float
    ts: str
    app_name: Optional[str] = None
    window_title: Optional[str] = None
    url: Optional[str] = None
    summary: Optional[str] = None
    evidence_type: str = "screenshot"  # screenshot / browser / session
    screenshot_path: Optional[str] = None
    sensitive: bool = False


class RecallResponse(BaseModel):
    """POST /api/recall 的响应。"""
    query: str
    results: List[RecallResult]


# ── API 请求 ────────────────────────────────────────────────────

class RecallRequest(BaseModel):
    query: str
    time_range: str = "last_24h"
    app_filter: Optional[str] = None
    domain_filter: Optional[str] = None
    top_k: int = 8
    include_screenshots: bool = False


class ForgetRequest(BaseModel):
    time_range: Optional[str] = None
    app_name: Optional[str] = None
    domain: Optional[str] = None


# ── VLM 输出 ────────────────────────────────────────────────────

class VLMSummary(BaseModel):
    """VLM 分析截图后的结构化输出。"""
    app_or_website: str = ""
    page_title_or_document: str = ""
    visible_task: str = ""
    key_entities: List[str] = Field(default_factory=list)
    possible_intent: str = ""
    useful_facts: List[str] = Field(default_factory=list)
    sensitive_content: bool = False
    summary_zh: str = ""


# ── 健康检查 ────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    database: str = "unknown"
    capture_active: bool = False
    vlm_available: bool = False
    embedding_available: bool = False
    total_events: int = 0
    total_sessions: int = 0
