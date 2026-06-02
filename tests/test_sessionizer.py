"""会话聚合测试 — 事件→活动会话合并。"""

import json
import tempfile
from pathlib import Path

import pytest

from app.models import RawEvent, ActivitySession
from app.processing.sessionizer import sessionize_events


class TestSessionizeEvents:
    """测试事件聚合为核心会话。"""

    def test_single_event_becomes_session(self):
        """单个事件应生成一个会话。"""
        events = [{"id": "1", "ts": "2026-06-02T10:00:00", "app_name": "Chrome", "window_title": "GitHub"}]
        sessions = sessionize_events(events)
        assert len(sessions) == 1
        assert sessions[0].ts_start == "2026-06-02T10:00:00"

    def test_same_app_merged(self):
        """同一应用的连续事件应合并为一个会话。"""
        events = [
            {"id": "1", "ts": "2026-06-02T10:00:00", "app_name": "Chrome", "window_title": "GitHub"},
            {"id": "2", "ts": "2026-06-02T10:02:00", "app_name": "Chrome", "window_title": "GitHub - repo"},
        ]
        sessions = sessionize_events(events)
        assert len(sessions) == 1
        assert sessions[0].ts_end == "2026-06-02T10:02:00"

    def test_different_app_separate_sessions(self):
        """不同应用的事件应分为不同会话。"""
        events = [
            {"id": "1", "ts": "2026-06-02T10:00:00", "app_name": "Chrome", "window_title": "GitHub"},
            {"id": "2", "ts": "2026-06-02T10:02:00", "app_name": "VSCode", "window_title": "main.py"},
        ]
        sessions = sessionize_events(events)
        assert len(sessions) == 2

    def test_time_gap_separates_sessions(self):
        """时间间隔超过阈值应分开。"""
        events = [
            {"id": "1", "ts": "2026-06-02T10:00:00", "app_name": "Chrome", "window_title": "GitHub"},
            {"id": "2", "ts": "2026-06-02T10:10:00", "app_name": "Chrome", "window_title": "GitHub"},
        ]
        sessions = sessionize_events(events, gap_minutes=5)
        assert len(sessions) == 2

    def test_empty_events(self):
        """空事件列表应返回空会话。"""
        sessions = sessionize_events([])
        assert len(sessions) == 0

    def test_session_contains_event_ids(self):
        """会话应包含关联的事件 ID。"""
        events = [
            {"id": "a1", "ts": "2026-06-02T10:00:00", "app_name": "Chrome", "window_title": "GitHub"},
            {"id": "a2", "ts": "2026-06-02T10:01:00", "app_name": "Chrome", "window_title": "GitHub"},
        ]
        sessions = sessionize_events(events)
        ids = json.loads(sessions[0].evidence_event_ids)
        assert "a1" in ids
        assert "a2" in ids


class TestSessionizerIntegration:
    """测试会话聚合与存储集成。"""

    def test_sessions_stored(self):
        """会话应能存入数据库。"""
        from app.storage import Storage
        with tempfile.TemporaryDirectory() as tmpdir:
            s = Storage(db_path=Path(tmpdir) / "test.sqlite")
            s.init_db()
            session = ActivitySession(
                ts_start="2026-06-02T10:00:00",
                ts_end="2026-06-02T10:30:00",
                topic="Python Development",
                apps='["VSCode", "Chrome"]',
                summary="Coding in VSCode",
            )
            sid = s.insert_session(session)
            assert sid is not None
            assert s.count_sessions() == 1
            s.close()
