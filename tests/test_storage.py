"""存储层测试 — 测试 SQLite 数据库的 CRUD 操作。"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app.models import RawEvent, BrowserEvent, ActivitySession


@pytest.fixture
def storage():
    """创建临时数据库的 Storage 实例。"""
    from app.storage import Storage
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.sqlite"
        s = Storage(db_path=db_path)
        s.init_db()
        yield s
        s.close()


@pytest.fixture
def sample_event():
    """示例原始事件。"""
    now = datetime.now().isoformat(timespec="seconds")
    return RawEvent(
        ts=now,
        source="screenshot",
        app_name="VSCode",
        process_name="code.exe",
        window_title="test.py — Hermes",
        screenshot_path="/tmp/test.jpg",
        image_hash="abc123",
    )


@pytest.fixture
def sample_browser_event():
    """示例浏览器事件。"""
    return BrowserEvent(
        ts="2026-06-02T10:01:00",
        browser="chrome",
        url="https://github.com/example/repo",
        domain="github.com",
        title="GitHub - example/repo",
        tab_id="123",
        window_id="1",
        active=True,
    )


class TestRawEvents:
    """测试原始事件的 CRUD。"""

    def test_insert_and_get(self, storage, sample_event):
        """测试插入事件后能检索到。"""
        event_id = storage.insert_event(sample_event)
        assert event_id == sample_event.id

        events = storage.get_recent_events(minutes=60)
        assert len(events) == 1
        assert events[0]["app_name"] == "VSCode"

    def test_insert_multiple(self, storage):
        """测试插入多条事件。"""
        for i in range(5):
            event = RawEvent(
                ts=f"2026-06-02T10:{i:02d}:00",
                source="screenshot",
                app_name=f"App{i}",
            )
            storage.insert_event(event)

        events = storage.get_recent_events(minutes=1440)
        assert len(events) == 5

    def test_count_events(self, storage, sample_event):
        """测试事件计数。"""
        assert storage.count_events() == 0
        storage.insert_event(sample_event)
        assert storage.count_events() == 1


class TestBrowserEvents:
    """测试浏览器事件。"""

    def test_insert_browser_event(self, storage, sample_browser_event):
        """测试插入浏览器事件。"""
        event_id = storage.insert_browser_event(sample_browser_event)
        assert event_id == sample_browser_event.id


class TestSessions:
    """测试活动会话。"""

    def test_insert_session(self, storage):
        """测试插入活动会话。"""
        session = ActivitySession(
            ts_start="2026-06-02T10:00:00",
            ts_end="2026-06-02T10:30:00",
            topic="Python 开发",
            apps='["VSCode", "Chrome"]',
            summary="在 VSCode 中编写 Python 代码",
        )
        session_id = storage.insert_session(session)
        assert session_id == session.id
        assert storage.count_sessions() == 1


class TestFTS:
    """测试 FTS5 全文搜索。"""

    def test_fts_search(self, storage):
        """测试全文搜索。"""
        event = RawEvent(
            ts="2026-06-02T10:00:00",
            source="screenshot",
            app_name="VSCode",
            window_title="main.py — Python Project",
        )
        storage.insert_event(event)

        results = storage.search_fts("Python")
        assert len(results) >= 1

    def test_fts_no_match(self, storage):
        """测试无匹配的搜索。"""
        event = RawEvent(
            ts="2026-06-02T10:00:00",
            source="screenshot",
            app_name="VSCode",
        )
        storage.insert_event(event)
        # 即使无匹配也不应报错
        results = storage.search_fts("不存在的关键词")
        assert isinstance(results, list)


class TestDelete:
    """测试事件删除。"""

    def test_delete_by_app(self, storage):
        """测试按应用名删除。"""
        for app in ["VSCode", "Chrome", "VSCode"]:
            event = RawEvent(
                ts="2026-06-02T10:00:00",
                source="screenshot",
                app_name=app,
            )
            storage.insert_event(event)

        deleted = storage.delete_events({"app_name": "VSCode"})
        assert deleted == 2
        assert storage.count_events() == 1
