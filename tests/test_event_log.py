"""Тесты для модуля структурированного логирования событий."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.event_log import (
    clear_events,
    event_count,
    event_path,
    event_summary,
    events_dir,
    events_since_session,
    last_event,
    read_events,
    write_event,
)


# === helpers ===


@pytest.fixture()
def tmp_project(tmp_path: Path):
    """Временная директория проекта с поддиректорией logs/events."""
    logs_dir = tmp_path / "logs" / "events"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


# === events_dir / event_path ===


class TestEventsDir:
    def test_returns_correct_path(self, tmp_project: Path):
        result = events_dir(tmp_project)
        assert result == tmp_project / "logs" / "events"

    def test_default_is_cwd(self):
        with patch("scripts.event_log.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/fake")
            result = events_dir()
            assert result == Path("/fake") / "logs" / "events"


class TestEventPath:
    def test_returns_jsonl_file(self, tmp_project: Path):
        result = event_path(events_dir(tmp_project))
        assert result == tmp_project / "logs" / "events" / "events.jsonl"

    def test_with_custom_events_root(self, tmp_project: Path):
        result = event_path(events_root=tmp_project)
        assert result == tmp_project / "events.jsonl"


# === write_event ===


class TestWriteEvent:
    def test_writes_single_event(self, tmp_project: Path):
        event = write_event("test_event", {"key": "value"}, tmp_project)
        assert event["type"] == "test_event"
        assert event["data"]["key"] == "value"
        assert "ts" in event

        path = event_path(events_dir(tmp_project))
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["type"] == "test_event"

    def test_writes_event_without_data(self, tmp_project: Path):
        write_event("empty_event", data=None, root=tmp_project)
        path = event_path(events_dir(tmp_project))
        parsed = json.loads(path.read_text(encoding="utf-8").strip())
        assert parsed["data"] == {}

    def test_creates_directory_if_missing(self, tmp_path: Path):
        # logs/events не существует
        project = tmp_path / "new_project"
        project.mkdir()
        write_event("test", {"x": 1}, project)
        path = event_path(events_dir(project))
        assert path.exists()

    def test_appends_multiple_events(self, tmp_project: Path):
        write_event("e1", {"n": 1}, tmp_project)
        write_event("e2", {"n": 2}, tmp_project)
        path = event_path(events_dir(tmp_project))
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    def test_event_has_utc_timestamp(self, tmp_project: Path):
        write_event("utc_test", {}, tmp_project)
        path = event_path(events_dir(tmp_project))
        parsed = json.loads(path.read_text(encoding="utf-8").strip())
        assert parsed["ts"].endswith("+00:00") or parsed["ts"].endswith("Z")


# === read_events ===


class TestReadEvents:
    def test_returns_empty_when_no_file(self, tmp_project: Path):
        result = read_events(root=tmp_project)
        assert result == []

    def test_returns_all_events(self, tmp_project: Path):
        write_event("a", {"v": 1}, tmp_project)
        write_event("b", {"v": 2}, tmp_project)
        result = read_events(root=tmp_project)
        assert len(result) == 2
        assert result[0]["type"] == "a"
        assert result[1]["type"] == "b"

    def test_filters_by_type(self, tmp_project: Path):
        write_event("keep", {}, tmp_project)
        write_event("skip", {}, tmp_project)
        write_event("keep", {}, tmp_project)
        result = read_events(event_type="keep", root=tmp_project)
        assert len(result) == 2
        assert all(e["type"] == "keep" for e in result)

    def test_filters_by_since(self, tmp_project: Path):
        # Записываем события напрямую, чтобы контролировать ts
        path = event_path(events_dir(tmp_project))
        path.write_text(
            '{"ts": "2025-01-01T00:00:00+00:00", "type": "old", "data": {}}\n'
            '{"ts": "2026-01-01T00:00:00+00:00", "type": "new", "data": {}}\n',
            encoding="utf-8",
        )
        result = read_events(since="2025-06-01T00:00:00+00:00", root=tmp_project)
        assert len(result) == 1
        assert result[0]["type"] == "new"

    def test_filters_by_until(self, tmp_project: Path):
        path = event_path(events_dir(tmp_project))
        path.write_text(
            '{"ts": "2025-01-01T00:00:00+00:00", "type": "old", "data": {}}\n'
            '{"ts": "2026-01-01T00:00:00+00:00", "type": "new", "data": {}}\n',
            encoding="utf-8",
        )
        result = read_events(until="2025-06-01T00:00:00+00:00", root=tmp_project)
        assert len(result) == 1
        assert result[0]["type"] == "old"

    def test_filters_by_type_and_since(self, tmp_project: Path):
        write_event("a", {}, tmp_project)
        write_event("b", {}, tmp_project)
        write_event("a", {}, tmp_project)
        result = read_events(event_type="a", root=tmp_project)
        assert len(result) == 2

    def test_skips_corrupt_lines(self, tmp_project: Path):
        path = event_path(events_dir(tmp_project))
        path.write_text('{"type": "good"}\nnot json\n{"type": "also_good"}\n', encoding="utf-8")
        result = read_events(root=tmp_project)
        assert len(result) == 2
        assert result[0]["type"] == "good"
        assert result[1]["type"] == "also_good"

    def test_empty_lines_ignored(self, tmp_project: Path):
        path = event_path(events_dir(tmp_project))
        path.write_text('{"type": "a"}\n\n\n{"type": "b"}\n', encoding="utf-8")
        result = read_events(root=tmp_project)
        assert len(result) == 2


# === event_count ===


class TestEventCount:
    def test_returns_zero_for_empty(self, tmp_project: Path):
        assert event_count(root=tmp_project) == 0

    def test_returns_total_count(self, tmp_project: Path):
        write_event("a", {}, tmp_project)
        write_event("b", {}, tmp_project)
        write_event("c", {}, tmp_project)
        assert event_count(root=tmp_project) == 3

    def test_returns_type_count(self, tmp_project: Path):
        write_event("x", {}, tmp_project)
        write_event("y", {}, tmp_project)
        write_event("x", {}, tmp_project)
        assert event_count(event_type="x", root=tmp_project) == 2
        assert event_count(event_type="y", root=tmp_project) == 1
        assert event_count(event_type="z", root=tmp_project) == 0


# === event_summary ===


class TestEventSummary:
    def test_returns_empty_for_no_events(self, tmp_project: Path):
        assert event_summary(root=tmp_project) == {}

    def test_counts_by_type(self, tmp_project: Path):
        write_event("start", {}, tmp_project)
        write_event("end", {}, tmp_project)
        write_event("start", {}, tmp_project)
        write_event("end", {}, tmp_project)
        write_event("start", {}, tmp_project)
        summary = event_summary(root=tmp_project)
        assert summary == {"start": 3, "end": 2}

    def test_unknown_type_for_missing_field(self, tmp_project: Path):
        path = event_path(events_dir(tmp_project))
        path.write_text('{"ts": "2025-01-01T00:00:00+00:00"}\n', encoding="utf-8")
        summary = event_summary(root=tmp_project)
        assert summary == {"unknown": 1}


# === clear_events ===


class TestClearEvents:
    def test_clears_all_events(self, tmp_project: Path):
        write_event("a", {}, tmp_project)
        write_event("b", {}, tmp_project)
        removed = clear_events(root=tmp_project)
        assert removed == 2
        assert event_count(root=tmp_project) == 0

    def test_returns_zero_when_empty(self, tmp_project: Path):
        removed = clear_events(root=tmp_project)
        assert removed == 0

    def test_removes_file(self, tmp_project: Path):
        write_event("a", {}, tmp_project)
        clear_events(root=tmp_project)
        path = event_path(events_dir(tmp_project))
        assert not path.exists()


# === last_event ===


class TestLastEvent:
    def test_returns_none_when_empty(self, tmp_project: Path):
        assert last_event(root=tmp_project) is None

    def test_returns_last_written(self, tmp_project: Path):
        write_event("first", {"n": 1}, tmp_project)
        write_event("second", {"n": 2}, tmp_project)
        write_event("third", {"n": 3}, tmp_project)
        result = last_event(root=tmp_project)
        assert result["type"] == "third"
        assert result["data"]["n"] == 3


# === events_since_session ===


class TestEventsSinceSession:
    def test_returns_empty_when_no_events(self, tmp_project: Path):
        result = events_since_session("session-0001", tmp_project)
        assert result == []

    def test_returns_empty_when_session_not_found(self, tmp_project: Path):
        write_event("other", {}, tmp_project)
        result = events_since_session("session-0001", tmp_project)
        assert result == []

    def test_returns_events_after_session(self, tmp_project: Path):
        path = event_path(events_dir(tmp_project))
        path.write_text(
            '{"ts": "2025-01-01T00:00:00+00:00", "type": "session_start", "data": {"session_id": "session-0040"}}\n'
            '{"ts": "2025-01-01T00:00:01+00:00", "type": "task_created", "data": {"task": "test"}}\n'
            '{"ts": "2025-01-01T00:00:02+00:00", "type": "session_end", "data": {}}\n',
            encoding="utf-8",
        )
        result = events_since_session("session-0040", tmp_project)
        assert len(result) == 2
        assert result[0]["type"] == "task_created"
        assert result[1]["type"] == "session_end"

    def test_returns_empty_for_same_session(self, tmp_project: Path):
        path = event_path(events_dir(tmp_project))
        path.write_text(
            '{"ts": "2025-01-01T00:00:00+00:00", "type": "session_start", "data": {"session_id": "session-0040"}}\n',
            encoding="utf-8",
        )
        result = events_since_session("session-0040", tmp_project)
        assert result == []

    def test_handles_multiple_sessions(self, tmp_project: Path):
        path = event_path(events_dir(tmp_project))
        path.write_text(
            '{"ts": "2025-01-01T00:00:00+00:00", "type": "session_start", "data": {"session_id": "session-0039"}}\n'
            '{"ts": "2025-01-01T00:00:01+00:00", "type": "task_a", "data": {}}\n'
            '{"ts": "2025-01-01T00:00:02+00:00", "type": "session_start", "data": {"session_id": "session-0040"}}\n'
            '{"ts": "2025-01-01T00:00:03+00:00", "type": "task_b", "data": {}}\n'
            '{"ts": "2025-01-01T00:00:04+00:00", "type": "session_end", "data": {}}\n',
            encoding="utf-8",
        )

        result_39 = events_since_session("session-0039", tmp_project)
        assert len(result_39) == 4  # task_a + session_start(40) + task_b + session_end

        result_40 = events_since_session("session-0040", tmp_project)
        assert len(result_40) == 2  # task_b + session_end
