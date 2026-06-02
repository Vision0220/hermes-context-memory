"""智能采集升级 — 数据模型测试。"""

import pytest
from app.models import RawEvent


class TestRawEventMonitorId:
    """测试 RawEvent 新增的 monitor_id 字段。"""

    def test_default_monitor_id(self):
        """默认 monitor_id 为 0。"""
        event = RawEvent(ts="2026-06-02T10:00:00", source="screenshot")
        assert event.monitor_id == 0

    def test_custom_monitor_id(self):
        """自定义 monitor_id。"""
        event = RawEvent(
            ts="2026-06-02T10:00:00",
            source="screenshot",
            monitor_id=2,
        )
        assert event.monitor_id == 2

    def test_monitor_id_in_dict(self):
        """monitor_id 包含在 model_dump 输出中。"""
        event = RawEvent(
            ts="2026-06-02T10:00:00",
            source="screenshot",
            monitor_id=1,
        )
        d = event.model_dump()
        assert "monitor_id" in d
        assert d["monitor_id"] == 1


class TestRawEventProcessingStatus:
    """测试处理状态字段。"""

    def test_default_processing_status(self):
        """默认处理状态为 pending。"""
        event = RawEvent(ts="2026-06-02T10:00:00", source="screenshot")
        assert event.processing_status == "pending"

    def test_processing_status_values(self):
        """测试各种处理状态。"""
        for status in ["pending", "processing", "completed", "failed", "skipped"]:
            event = RawEvent(
                ts="2026-06-02T10:00:00",
                source="screenshot",
                processing_status=status,
            )
            assert event.processing_status == status


class TestRawEventDimensions:
    """测试图片尺寸字段。"""

    def test_default_dimensions(self):
        """默认尺寸为 None。"""
        event = RawEvent(ts="2026-06-02T10:00:00", source="screenshot")
        assert event.image_width is None
        assert event.image_height is None

    def test_custom_dimensions(self):
        """自定义图片尺寸。"""
        event = RawEvent(
            ts="2026-06-02T10:00:00",
            source="screenshot",
            image_width=5120,
            image_height=2160,
        )
        assert event.image_width == 5120
        assert event.image_height == 2160
