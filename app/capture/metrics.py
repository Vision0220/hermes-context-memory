"""调度器指标模块 — 记录采集循环的运行指标。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class MetricsSnapshot:
    """指标快照。"""
    captures_total: int = 0
    duplicates_skipped: int = 0
    vlm_processed: int = 0
    vlm_failed: int = 0
    embedding_processed: int = 0
    embedding_failed: int = 0
    queue_depth: int = 0
    queue_maxsize: int = 0
    queue_pressure: float = 0.0
    current_interval: float = 15.0
    idle_level: str = "L1_ACTIVE"
    skip_reasons: Dict[str, int] = field(default_factory=dict)
    avg_vlm_latency_ms: float = 0.0
    avg_embedding_latency_ms: float = 0.0
    ts: str = ""

    @property
    def skip_rate(self) -> float:
        """跳过率 = 跳过数 / (截图数 + 跳过数)。"""
        total = self.captures_total + self.duplicates_skipped
        return round(self.duplicates_skipped / total, 3) if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "captures_total": self.captures_total,
            "duplicates_skipped": self.duplicates_skipped,
            "skip_rate": self.skip_rate,
            "vlm_processed": self.vlm_processed,
            "vlm_failed": self.vlm_failed,
            "embedding_processed": self.embedding_processed,
            "avg_vlm_latency_ms": round(self.avg_vlm_latency_ms, 1),
            "avg_embedding_latency_ms": round(self.avg_embedding_latency_ms, 1),
            "queue_depth": self.queue_depth,
            "queue_maxsize": self.queue_maxsize,
            "queue_pressure": self.queue_pressure,
            "current_interval": self.current_interval,
            "idle_level": self.idle_level,
            "skip_reasons": self.skip_reasons,
            "ts": self.ts,
        }


class SchedulerMetrics:
    """调度器指标收集器。"""

    def __init__(self):
        self._captures = 0
        self._skips = 0
        self._skip_reasons: Dict[str, int] = {}
        self._vlm_ok = 0
        self._vlm_fail = 0
        self._vlm_latencies: list = []
        self._emb_ok = 0
        self._emb_fail = 0
        self._emb_latencies: list = []
        self._queue_depth = 0
        self._queue_maxsize = 0
        self._queue_pressure = 0.0
        self._current_interval = 15.0
        self._idle_level = "L1_ACTIVE"

    def record_capture(self):
        self._captures += 1

    def record_skip(self, reason: str):
        self._skips += 1
        self._skip_reasons[reason] = self._skip_reasons.get(reason, 0) + 1

    def record_vlm(self, latency_ms: float, success: bool):
        if success:
            self._vlm_ok += 1
            self._vlm_latencies.append(latency_ms)
            if len(self._vlm_latencies) > 100:
                self._vlm_latencies = self._vlm_latencies[-50:]
        else:
            self._vlm_fail += 1

    def record_embedding(self, latency_ms: float, success: bool):
        if success:
            self._emb_ok += 1
            self._emb_latencies.append(latency_ms)
            if len(self._emb_latencies) > 100:
                self._emb_latencies = self._emb_latencies[-50:]
        else:
            self._emb_fail += 1

    def update_queue(self, depth: int, maxsize: int, pressure: float):
        self._queue_depth = depth
        self._queue_maxsize = maxsize
        self._queue_pressure = pressure

    def update_interval(self, current: float, idle_level: str):
        self._current_interval = current
        self._idle_level = idle_level

    def snapshot(self) -> MetricsSnapshot:
        from datetime import datetime
        avg_vlm = sum(self._vlm_latencies) / len(self._vlm_latencies) if self._vlm_latencies else 0.0
        avg_emb = sum(self._emb_latencies) / len(self._emb_latencies) if self._emb_latencies else 0.0
        return MetricsSnapshot(
            captures_total=self._captures,
            duplicates_skipped=self._skips,
            vlm_processed=self._vlm_ok,
            vlm_failed=self._vlm_fail,
            embedding_processed=self._emb_ok,
            embedding_failed=self._emb_fail,
            queue_depth=self._queue_depth,
            queue_maxsize=self._queue_maxsize,
            queue_pressure=self._queue_pressure,
            current_interval=self._current_interval,
            idle_level=self._idle_level,
            skip_reasons=dict(self._skip_reasons),
            avg_vlm_latency_ms=avg_vlm,
            avg_embedding_latency_ms=avg_emb,
            ts=datetime.now().isoformat(timespec="seconds"),
        )
