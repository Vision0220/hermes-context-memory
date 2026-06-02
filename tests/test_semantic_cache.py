"""语义缓存测试 — VLM 结果复用。"""

import pytest

from app.processing.semantic_cache import SemanticCache


@pytest.fixture
def cache():
    return SemanticCache(max_size=100, ttl_seconds=300)


class TestSemanticCache:
    """测试语义缓存核心功能。"""

    def test_cache_miss_first_time(self, cache):
        """首次查询应返回 miss。"""
        result = cache.lookup(
            app_name="Chrome",
            window_title="GitHub",
            url="https://github.com",
            thumbnail_md5="abc123",
        )
        assert result is None

    def test_cache_hit_same_context(self, cache):
        """相同上下文应返回 hit。"""
        cache.store(
            app_name="Chrome",
            window_title="GitHub",
            url="https://github.com",
            thumbnail_md5="abc123",
            vlm_summary="用户在浏览 GitHub",
            event_id="evt001",
        )
        result = cache.lookup(
            app_name="Chrome",
            window_title="GitHub",
            url="https://github.com",
            thumbnail_md5="abc123",
        )
        assert result is not None
        assert result.vlm_summary == "用户在浏览 GitHub"

    def test_cache_miss_different_app(self, cache):
        """不同应用应返回 miss。"""
        cache.store(
            app_name="Chrome",
            window_title="GitHub",
            url="https://github.com",
            thumbnail_md5="abc123",
            vlm_summary="GitHub",
            event_id="evt001",
        )
        result = cache.lookup(
            app_name="VSCode",
            window_title="GitHub",
            url="https://github.com",
            thumbnail_md5="abc123",
        )
        assert result is None

    def test_cache_miss_different_hash(self, cache):
        """不同内容哈希应返回 miss。"""
        cache.store(
            app_name="Chrome",
            window_title="GitHub",
            url="https://github.com",
            thumbnail_md5="abc123",
            vlm_summary="GitHub",
            event_id="evt001",
        )
        result = cache.lookup(
            app_name="Chrome",
            window_title="GitHub",
            url="https://github.com",
            thumbnail_md5="def456",
        )
        assert result is None

    def test_force_keyframe_on_app_switch(self, cache):
        """应用切换时应强制 keyframe（绕过缓存）。"""
        cache.store(
            app_name="Chrome",
            window_title="GitHub",
            url="https://github.com",
            thumbnail_md5="abc123",
            vlm_summary="GitHub",
            event_id="evt001",
        )
        # 应用切换 → 不查缓存
        should_skip = cache.should_skip_vlm(
            app_name="Chrome",
            prev_app_name="VSCode",
            window_title="GitHub",
            prev_window_title="main.py",
        )
        assert should_skip is False

    def test_skip_vlm_when_same_context(self, cache):
        """相同上下文 + 相同内容应跳过 VLM。"""
        cache.store(
            app_name="Chrome",
            window_title="GitHub",
            url="https://github.com",
            thumbnail_md5="abc123",
            vlm_summary="GitHub",
            event_id="evt001",
        )
        should_skip = cache.should_skip_vlm(
            app_name="Chrome",
            prev_app_name="Chrome",
            window_title="GitHub",
            prev_window_title="GitHub",
        )
        assert should_skip is True

    def test_cache_eviction(self, cache):
        """缓存满时应淘汰旧条目。"""
        small_cache = SemanticCache(max_size=2, ttl_seconds=300)
        small_cache.store(app_name="A", window_title="1", url="", thumbnail_md5="h1", vlm_summary="s1", event_id="e1")
        small_cache.store(app_name="A", window_title="2", url="", thumbnail_md5="h2", vlm_summary="s2", event_id="e2")
        small_cache.store(app_name="A", window_title="3", url="", thumbnail_md5="h3", vlm_summary="s3", event_id="e3")
        # 最旧的应被淘汰
        assert small_cache.lookup(app_name="A", window_title="1", url="", thumbnail_md5="h1") is None
        assert small_cache.lookup(app_name="A", window_title="3", url="", thumbnail_md5="h3") is not None

    def test_cache_stats(self, cache):
        """缓存应记录统计信息。"""
        cache.store(app_name="A", window_title="1", url="", thumbnail_md5="h1", vlm_summary="s1", event_id="e1")
        stats = cache.get_stats()
        assert stats["size"] == 1
        assert stats["hits"] == 0
        cache.lookup(app_name="A", window_title="1", url="", thumbnail_md5="h1")
        stats = cache.get_stats()
        assert stats["hits"] == 1
