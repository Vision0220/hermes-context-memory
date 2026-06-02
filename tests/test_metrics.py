"""调度器指标测试。"""

import pytest

from app.capture.metrics import SchedulerMetrics, MetricsSnapshot


@pytest.fixture
def metrics():
    return SchedulerMetrics()


class TestSchedulerMetrics:
    """测试调度器指标记录。"""

    def test_record_capture(self, metrics):
        """记录一次截图。"""
        metrics.record_capture()
        metrics.record_capture()
        snap = metrics.snapshot()
        assert snap.captures_total == 2

    def test_record_duplicate(self, metrics):
        """记录一次去重跳过。"""
        metrics.record_skip("dhash")
        snap = metrics.snapshot()
        assert snap.duplicates_skipped == 1
        assert snap.skip_reasons["dhash"] == 1

    def test_record_vlm_call(self, metrics):
        """记录 VLM 调用。"""
        metrics.record_vlm(latency_ms=500, success=True)
        metrics.record_vlm(latency_ms=200, success=False)
        snap = metrics.snapshot()
        assert snap.vlm_processed == 1
        assert snap.vlm_failed == 1

    def test_record_embedding_call(self, metrics):
        """记录 Embedding 调用。"""
        metrics.record_embedding(latency_ms=100, success=True)
        snap = metrics.snapshot()
        assert snap.embedding_processed == 1

    def test_queue_metrics(self, metrics):
        """记录队列指标。"""
        metrics.update_queue(depth=5, maxsize=10, pressure=0.5)
        snap = metrics.snapshot()
        assert snap.queue_depth == 5
        assert snap.queue_pressure == 0.5

    def test_interval_metrics(self, metrics):
        """记录自适应间隔。"""
        metrics.update_interval(current=15.0, idle_level="L1_ACTIVE")
        snap = metrics.snapshot()
        assert snap.current_interval == 15.0
        assert snap.idle_level == "L1_ACTIVE"

    def test_skip_rate(self, metrics):
        """计算跳过率。"""
        metrics.record_capture()
        metrics.record_capture()
        metrics.record_skip("thumbnail_md5")
        metrics.record_skip("dhash")
        snap = metrics.snapshot()
        # 2 次截图 + 2 次跳过 = 4 次尝试, 跳过率 = 2/4 = 0.5
        assert snap.skip_rate == 0.5

    def test_snapshot_to_dict(self, metrics):
        """快照应能转为字典。"""
        metrics.record_capture()
        snap = metrics.snapshot()
        d = snap.to_dict()
        assert "captures_total" in d
        assert "queue_depth" in d
        assert "skip_rate" in d
