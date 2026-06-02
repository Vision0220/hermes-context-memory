"""智能采集升级 — 配置模型测试。"""

import pytest
from app.config import AppConfig, CaptureConfig, VLMConfig, EmbeddingConfig


class TestCaptureConfigNew:
    """测试新增的采集配置字段。"""

    def test_default_per_monitor(self):
        """默认按屏幕独立截图。"""
        cfg = CaptureConfig()
        assert cfg.per_monitor is True

    def test_default_monitors_empty(self):
        """默认截取所有屏幕。"""
        cfg = CaptureConfig()
        assert cfg.monitors == []

    def test_default_vlm_max_width(self):
        """默认 VLM 最大宽度 2048。"""
        cfg = CaptureConfig()
        assert cfg.vlm_max_width == 2048

    def test_default_hash_max_width(self):
        """默认 hash 计算宽度 640。"""
        cfg = CaptureConfig()
        assert cfg.hash_max_width == 640

    def test_dedup_config_defaults(self):
        """去重配置默认值。"""
        cfg = CaptureConfig()
        assert cfg.dedup.hash_algorithm == "dhash"
        assert cfg.dedup.hash_threshold == 6
        assert cfg.dedup.ssim_threshold == 0.85
        assert cfg.dedup.thumbnail_size == [64, 36]

    def test_custom_dedup_config(self):
        """自定义去重配置。"""
        cfg = CaptureConfig(dedup={
            "hash_algorithm": "phash",
            "hash_threshold": 10,
        })
        assert cfg.dedup.hash_algorithm == "phash"
        assert cfg.dedup.hash_threshold == 10


class TestVLMConfigNew:
    """测试 VLM 配置新增字段。"""

    def test_default_timeout(self):
        """默认 VLM 超时 60 秒。"""
        cfg = VLMConfig()
        assert cfg.timeout == 60

    def test_default_retry_count(self):
        """默认重试 2 次。"""
        cfg = VLMConfig()
        assert cfg.retry_count == 2

    def test_default_max_tokens(self):
        """默认 max_tokens 1024。"""
        cfg = VLMConfig()
        assert cfg.max_tokens == 1024

    def test_default_temperature(self):
        """默认温度 0.1。"""
        cfg = VLMConfig()
        assert cfg.temperature == 0.1


class TestEmbeddingConfigNew:
    """测试 Embedding 配置新增字段。"""

    def test_default_timeout(self):
        """默认 Embedding 超时 30 秒。"""
        cfg = EmbeddingConfig()
        assert cfg.timeout == 30

    def test_default_retry_count(self):
        """默认重试 2 次。"""
        cfg = EmbeddingConfig()
        assert cfg.retry_count == 2


class TestAppConfigIntegration:
    """测试完整配置加载。"""

    def test_full_config_creation(self):
        """测试完整配置对象创建。"""
        cfg = AppConfig(
            capture=CaptureConfig(
                per_monitor=True,
                monitors=[1, 2],
                vlm_max_width=2048,
                hash_max_width=640,
            ),
            models={
                "vlm": {
                    "enabled": True,
                    "model": "qwen/test",
                    "timeout": 60,
                },
                "embedding": {
                    "enabled": True,
                    "model": "text-embedding-test",
                },
            },
        )
        assert cfg.capture.per_monitor is True
        assert cfg.capture.monitors == [1, 2]
        assert cfg.models.vlm.model == "qwen/test"
        assert cfg.models.embedding.model == "text-embedding-test"

    def test_config_yaml_roundtrip(self):
        """测试配置可以序列化和反序列化。"""
        cfg = AppConfig()
        data = cfg.model_dump()
        cfg2 = AppConfig(**data)
        assert cfg2.capture.per_monitor == cfg.capture.per_monitor
        assert cfg2.models.vlm.timeout == cfg.models.vlm.timeout
