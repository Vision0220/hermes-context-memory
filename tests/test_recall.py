"""检索层测试 — 测试上下文召回功能。"""

import tempfile
from pathlib import Path

import pytest

from app.config import AppConfig
from app.models import RawEvent, RecallRequest


@pytest.fixture
def storage_with_data():
    """创建含测试数据的临时数据库。"""
    from app.storage import Storage
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.sqlite"
        s = Storage(db_path=db_path)
        s.init_db()

        # 插入测试数据
        events = [
            RawEvent(
                ts="2026-06-02T09:00:00",
                source="screenshot",
                app_name="VSCode",
                window_title="main.py — Python Project",
                ocr_text="def hello_world(): print('hello')",
                vlm_summary="用户在 VSCode 中编写 Python 函数",
            ),
            RawEvent(
                ts="2026-06-02T09:30:00",
                source="screenshot",
                app_name="Chrome",
                window_title="GitHub - Hermes Project",
                url="https://github.com/hermes/project",
                domain="github.com",
                ocr_text="README.md",
                vlm_summary="用户在浏览 GitHub 上的 Hermes 项目",
            ),
            RawEvent(
                ts="2026-06-02T10:00:00",
                source="screenshot",
                app_name="Chrome",
                window_title="Stack Overflow - Python question",
                url="https://stackoverflow.com/questions/123",
                domain="stackoverflow.com",
                vlm_summary="用户在搜索 Python 错误解决方案",
            ),
            RawEvent(
                ts="2026-06-02T10:30:00",
                source="screenshot",
                app_name="1Password",
                sensitive=True,
            ),
        ]

        for event in events:
            s.insert_event(event)

        yield s
        s.close()


class TestRecallSearch:
    """测试检索功能。"""

    def test_basic_recall(self, storage_with_data):
        """测试基本检索。"""
        config = AppConfig()
        # 使用 monkeypatch 让 get_storage 返回测试实例
        import app.retrieval.search as search_mod
        original = search_mod.get_storage
        search_mod.get_storage = lambda: storage_with_data

        request = RecallRequest(
            query="Python",
            time_range="last_24h",
            top_k=5,
        )
        results = search_mod.search_context(request, config)

        search_mod.get_storage = original

        # 应该找到 Python 相关的结果
        assert len(results) > 0
        # 敏感记录不应出现在结果中
        for r in results:
            assert r.sensitive is False

    def test_app_filter(self, storage_with_data):
        """测试按应用过滤。"""
        config = AppConfig()
        import app.retrieval.search as search_mod
        original = search_mod.get_storage
        search_mod.get_storage = lambda: storage_with_data

        request = RecallRequest(
            query="project",
            time_range="last_24h",
            app_filter="Chrome",
            top_k=10,
        )
        results = search_mod.search_context(request, config)

        search_mod.get_storage = original

        # 只返回 Chrome 的结果
        for r in results:
            if r.app_name:
                assert "Chrome" in r.app_name

    def test_sensitive_excluded(self, storage_with_data):
        """测试敏感记录不返回。"""
        config = AppConfig()
        import app.retrieval.search as search_mod
        original = search_mod.get_storage
        search_mod.get_storage = lambda: storage_with_data

        request = RecallRequest(
            query="1Password",
            time_range="last_24h",
            top_k=10,
        )
        results = search_mod.search_context(request, config)

        search_mod.get_storage = original

        for r in results:
            assert r.sensitive is False
