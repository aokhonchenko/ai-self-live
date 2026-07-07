#!/usr/bin/env python3
"""Тесты для context_analyzer — анализатора контекста сессии."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.tools.context_analyzer import core


class TestEstimateTokens:
    """Тесты оценки количества токенов."""

    def test_empty_string(self) -> None:
        assert core.estimate_tokens("") == 0

    def test_short_text(self) -> None:
        # ~4 символа на токен
        text = "Привет мир"
        tokens = core.estimate_tokens(text)
        assert tokens > 0
        assert tokens <= len(text)

    def test_russian_text(self) -> None:
        text = "Это русский текст для проверки оценки токенов"
        tokens = core.estimate_tokens(text)
        assert tokens > 0

    def test_large_text(self) -> None:
        text = "x" * 10000
        tokens = core.estimate_tokens(text)
        assert tokens == 2500  # 10000 / 4


class TestExtractDate:
    """Тесты извлечения даты из контента."""

    def test_iso_date(self) -> None:
        content = "Дата: 2026-07-08"
        result = core.extract_date_from_content(content)
        assert result == datetime(2026, 7, 8)

    def test_date_in_heading(self) -> None:
        content = "# Изменение режима автономии (2026-07-07)"
        result = core.extract_date_from_content(content)
        assert result == datetime(2026, 7, 7)

    def test_date_in_session_line(self) -> None:
        content = "## Сессия 46 — сон\n\nДата: 2026-07-08"
        result = core.extract_date_from_content(content)
        assert result == datetime(2026, 7, 8)

    def test_no_date(self) -> None:
        content = "# Просто заголовок\n\nНикаких дат тут нет."
        result = core.extract_date_from_content(content)
        assert result is None

    def test_empty_content(self) -> None:
        result = core.extract_date_from_content("")
        assert result is None

    def test_multiple_dates_first_wins(self) -> None:
        content = "Дата: 2026-07-08\nАктуально на 2026-07-01"
        result = core.extract_date_from_content(content)
        assert result == datetime(2026, 7, 8)


class TestAnalyzeFileSection:
    """Тесты анализа одной секции."""

    def test_existing_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "test.md"
        file_path.write_text("# Заголовок\n\nТекст", encoding="utf-8")
        result = core.analyze_file_section(tmp_path, "test.md", "test")
        assert result["exists"] is True
        assert result["name"] == "test"
        assert result["lines"] > 0
        assert result["tokens"] > 0
        assert result["empty"] is False

    def test_missing_file(self, tmp_path: Path) -> None:
        result = core.analyze_file_section(tmp_path, "missing.md", "test")
        assert result["exists"] is False

    def test_empty_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "empty.md"
        file_path.write_text("", encoding="utf-8")
        result = core.analyze_file_section(tmp_path, "empty.md", "test")
        assert result["exists"] is True
        assert result["empty"] is True

    def test_headings_extracted(self, tmp_path: Path) -> None:
        file_path = tmp_path / "headings.md"
        file_path.write_text(
            "# H1\n## H2\n### H3\n",
            encoding="utf-8",
        )
        result = core.analyze_file_section(tmp_path, "headings.md", "test")
        assert len(result["headings"]) == 3
        assert result["headings"][0]["level"] == 1
        assert result["headings"][0]["text"] == "H1"
        assert result["headings"][2]["level"] == 3


class TestAnalyzeQuestionsDir:
    """Тесты анализа директории вопросов."""

    def test_no_questions_dir(self, tmp_path: Path) -> None:
        result = core.analyze_questions_dir(tmp_path)
        assert result["exists"] is False
        assert result["count"] == 0

    def test_with_questions(self, tmp_path: Path) -> None:
        qdir = tmp_path / "state" / "questions"
        qdir.mkdir(parents=True)

        open_q = qdir / "0001-test.md"
        open_q.write_text(
            "# Вопрос\n\nСтатус: open\nСессия: 0001\n\nТекст вопроса.",
            encoding="utf-8",
        )

        closed_q = qdir / "0002-test.md"
        closed_q.write_text(
            "# Вопрос\n\nСтатус: closed\nСессия: 0002\n\nОтвет: сделано.",
            encoding="utf-8",
        )

        result = core.analyze_questions_dir(tmp_path)
        assert result["exists"] is True
        assert result["count"] == 2
        assert result["open"] == 1
        assert result["answered"] == 1


class TestAnalyzeHistory:
    """Тесты анализа истории."""

    def test_no_history(self, tmp_path: Path) -> None:
        result = core.analyze_history(tmp_path)
        assert result["exists"] is False

    def test_with_history(self, tmp_path: Path) -> None:
        logs = tmp_path / "logs"
        logs.mkdir()
        history = logs / "history.md"
        history.write_text(
            "### Сессия 48 (2026-07-06) Добавлена цель\n### Сессия 49 (2026-07-07) Метрики\n",
            encoding="utf-8",
        )
        result = core.analyze_history(tmp_path)
        assert result["exists"] is True
        assert result["sessions_count"] == 2
        assert result["lines"] > 0


class TestGenerateRecommendations:
    """Тесты генерации рекомендаций."""

    def test_good_state(self) -> None:
        sections = [
            {"exists": True, "stale": False, "empty": False, "tokens": 500},
        ]
        recs = core.generate_recommendations(sections, 500, 0)
        assert any("✅" in r for r in recs)

    def test_warning_tokens(self) -> None:
        sections = [{"exists": True, "stale": False, "empty": False, "tokens": 10000}]
        recs = core.generate_recommendations(sections, 10000, 0)
        assert any("⚡" in r for r in recs)

    def test_critical_tokens(self) -> None:
        sections = [{"exists": True, "stale": False, "empty": False, "tokens": 20000}]
        recs = core.generate_recommendations(sections, 20000, 0)
        assert any("⚠️ КРИТИЧНО" in r for r in recs)

    def test_stale_sections(self) -> None:
        sections = [{"exists": True, "stale": True, "empty": False, "tokens": 100, "name": "old"}]
        recs = core.generate_recommendations(sections, 100, 0)
        assert any("📅" in r for r in recs)

    def test_empty_sections(self) -> None:
        sections = [{"exists": True, "stale": False, "empty": True, "tokens": 0, "name": "empty"}]
        recs = core.generate_recommendations(sections, 0, 0)
        assert any("🗑️" in r for r in recs)

    def test_open_questions(self) -> None:
        sections = [{"exists": True, "stale": False, "empty": False, "tokens": 100}]
        recs = core.generate_recommendations(sections, 100, 3)
        assert any("❓" in r for r in recs)


class TestFormatText:
    """Тесты текстового форматирования."""

    def test_basic_output(self) -> None:
        report = {
            "timestamp": "2026-07-08T00:00:00",
            "health": "good",
            "health_label": "Хорошо",
            "total_tokens": 1000,
            "total_chars": 4000,
            "total_lines": 50,
            "sections": [
                {
                    "name": "test",
                    "path": "test.md",
                    "exists": True,
                    "lines": 10,
                    "chars": 200,
                    "tokens": 50,
                    "date": None,
                    "stale": False,
                    "empty": False,
                    "headings": [],
                }
            ],
            "questions": {"exists": False, "count": 0, "open": 0},
            "history": {"exists": False},
            "sleep": {"exists": False},
            "recommendations": ["✅ Тест"],
        }
        output = core.format_text(report)
        assert "АНАЛИЗ КОНТЕКСТА" in output
        assert "Хорошо" in output
        assert "✅ Тест" in output


class TestFormatJson:
    """Тесты JSON-форматирования."""

    def test_json_serializable(self) -> None:
        report = {
            "timestamp": datetime(2026, 7, 8, 12, 0, 0),
            "health": "good",
            "total_tokens": 100,
            "sections": [],
            "questions": {"exists": False},
            "history": {"exists": False},
            "sleep": {"exists": False},
            "recommendations": [],
        }
        output = core.format_json(report)
        parsed = json.loads(output)
        assert parsed["timestamp"] == "2026-07-08T12:00:00"
        assert parsed["health"] == "good"


class TestAnalyze:
    """Интеграционный тест полного анализа."""

    def test_full_analysis(self, tmp_path: Path) -> None:
        # Создаём структуру проекта
        (tmp_path / "state").mkdir()
        (tmp_path / "logs").mkdir()

        last = tmp_path / "state" / "last_session.md"
        last.write_text("# Сессия 49\n\nТекст сессии.", encoding="utf-8")

        plan = tmp_path / "state" / "current_plan.md"
        plan.write_text("# План\n\nДата: 2026-07-08\n\nРаботаем.", encoding="utf-8")

        ext = tmp_path / "state" / "external_messages.md"
        ext.write_text("# Сообщения\n\nДата: 2026-07-08", encoding="utf-8")

        report = core.analyze(tmp_path)

        assert report["health"] in ("good", "warning", "critical")
        assert report["total_tokens"] > 0
        assert len(report["sections"]) == 3
        assert report["sections"][0]["name"] == "last_session"
        assert report["sections"][1]["name"] == "current_plan"
        assert report["sections"][2]["name"] == "external_messages"
        assert isinstance(report["recommendations"], list)


class TestToolWrapper:
    """Тесты обёртки tool.py."""

    def test_schema_exists(self) -> None:
        from src.tools.context_analyzer.tool import schema

        s = schema()
        assert s["type"] == "function"
        assert s["function"]["name"] == "context_analyzer"
        assert "parameters" in s["function"]

    def test_passport_exists(self) -> None:
        from src.tools.context_analyzer.tool import passport

        p = passport()
        assert "context_analyzer" in p

    def test_handle_directory(self, tmp_path: Path) -> None:
        from src.tools.context_analyzer.tool import handle

        # Создаём минимальную структуру
        (tmp_path / "state").mkdir()
        (tmp_path / "state" / "last_session.md").write_text("# Тест", encoding="utf-8")
        (tmp_path / "state" / "current_plan.md").write_text("# План", encoding="utf-8")
        (tmp_path / "state" / "external_messages.md").write_text("# Сообщения", encoding="utf-8")

        result = handle(tmp_path, {"path": ".", "mode": "directory", "format": "json"})
        assert result["ok"] is True
        assert "content" in result

        data = json.loads(result["content"])
        assert "health" in data
        assert "sections" in data

    def test_handle_file(self, tmp_path: Path) -> None:
        from src.tools.context_analyzer.tool import handle

        test_file = tmp_path / "test.md"
        test_file.write_text("# Тест\n\nТекст", encoding="utf-8")

        result = handle(tmp_path, {"path": "test.md", "mode": "file", "format": "json"})
        assert result["ok"] is True
        data = json.loads(result["content"])
        assert data["path"] == str(test_file)
        assert data["lines"] > 0

    def test_handle_missing_file(self, tmp_path: Path) -> None:
        from src.tools.context_analyzer.tool import handle

        result = handle(tmp_path, {"path": "missing.md", "mode": "file", "format": "json"})
        assert result["ok"] is False
        assert "error" in result
        

class TestDetectDuplicates:
    """Тесты обнаружения дубликатов."""

    def test_no_duplicates(self) -> None:
        text = "line1\nline2\nline3\nline4\nline5"
        result = core.detect_duplicates(text)
        assert len(result) == 0

    def test_simple_duplicate(self) -> None:
        text = "line1\nline2\nline3\nline1\nline2\nline3"
        result = core.detect_duplicates(text)
        assert len(result) >= 1
        found = [d for d in result if d["line_count"] >= 3]
        assert len(found) >= 1
        assert found[0]["count"] == 2

    def test_empty_text(self) -> None:
        result = core.detect_duplicates("")
        assert result == []

    def test_single_line_repeated(self) -> None:
        text = "x\nx\nx\nx\nx"
        result = core.detect_duplicates(text, min_lines=1)
        assert len(result) >= 1

    def test_nested_duplicates_filtered(self) -> None:
        text = "a\nb\nc\nd\ne\na\nb\nc\nd\ne"
        result = core.detect_duplicates(text, min_lines=2)
        longest = max(result, key=lambda d: d["line_count"])
        assert longest["line_count"] >= 5


class TestAssessNoise:
    """Тесты оценки шумности."""

    def test_clean_text(self) -> None:
        text = "Привет мир\nЭто полезный текст\nЕщё одна строка"
        result = core.assess_noise(text)
        assert result["total_lines"] == 3
        assert result["noise_lines"] == 0
        assert result["noise_ratio"] == 0.0

    def test_text_with_empty_lines(self) -> None:
        text = "строка 1\n\n\nстрока 2\n\nстрока 3"
        result = core.assess_noise(text)
        assert result["total_lines"] == 6
        assert result["noise_lines"] >= 3
        assert result["noise_ratio"] > 0

    def test_text_with_separators(self) -> None:
        text = "---\n---\n---\nтекст"
        result = core.assess_noise(text)
        assert result["noise_lines"] >= 3

    def test_text_with_tables(self) -> None:
        text = "| a | b |\n|---|---|\n| 1 | 2 |\nтекст"
        result = core.assess_noise(text)
        assert result["noise_lines"] >= 3

    def test_empty_text(self) -> None:
        result = core.assess_noise("")
        assert result["total_lines"] == 0
        assert result["noise_ratio"] == 0.0

    def test_high_noise_ratio(self) -> None:
        lines = ["---"] * 10 + ["текст"]
        text = "\n".join(lines)
        result = core.assess_noise(text)
        assert result["noise_ratio"] > 0.8


class TestSuggestCompression:
    """Тесты рекомендаций по сжатию."""

    def test_no_suggestions(self) -> None:
        sections = [{"exists": True, "name": "test", "tokens": 100, "duplicate_count": 0, "noise_ratio": 0.1}]
        result = core.suggest_compression(sections, 100)
        assert result == []

    def test_large_section(self) -> None:
        sections = [{"exists": True, "name": "test", "tokens": 5000, "duplicate_count": 0, "noise_ratio": 0.1}]
        result = core.suggest_compression(sections, 5000)
        assert len(result) == 1
        assert "📦" in result[0]

    def test_duplicate_section(self) -> None:
        sections = [{"exists": True, "name": "test", "tokens": 100, "duplicate_count": 3, "duplicate_wasted_lines": 15, "noise_ratio": 0.1}]
        result = core.suggest_compression(sections, 100)
        assert len(result) == 1
        assert "🔁" in result[0]

    def test_noisy_section(self) -> None:
        sections = [{"exists": True, "name": "test", "tokens": 100, "duplicate_count": 0, "noise_ratio": 0.5}]
        result = core.suggest_compression(sections, 100)
        assert len(result) == 1
        assert "🌫️" in result[0]

    def test_missing_section(self) -> None:
        sections = [{"exists": False}]
        result = core.suggest_compression(sections, 100)
        assert result == []


class TestRecommendationsWithNewFeatures:
    """Тесты рекомендаций с новыми функциями."""

    def test_duplicate_recommendation(self) -> None:
        sections = [{"exists": True, "name": "test", "stale": False, "empty": False, "tokens": 100, "duplicate_count": 2, "duplicate_wasted_lines": 10}]
        recs = core.generate_recommendations(sections, 100, 0)
        assert any("🔁" in r for r in recs)

    def test_noise_recommendation(self) -> None:
        sections = [{"exists": True, "name": "test", "stale": False, "empty": False, "tokens": 100, "noise": {"noise_ratio": 0.5}}]
        recs = core.generate_recommendations(sections, 100, 0)
        assert any("🌫️" in r for r in recs)


class TestFormatTextWithNewFeatures:
    """Тесты текстового форматирования с новыми фичами."""

    def test_duplicate_flag_in_output(self) -> None:
        report = {
            "timestamp": "2026-07-08T00:00:00",
            "health": "good",
            "health_label": "Хорошо",
            "total_tokens": 100,
            "total_chars": 400,
            "total_lines": 20,
            "sections": [
                {
                    "name": "test",
                    "path": "test.md",
                    "exists": True,
                    "lines": 10,
                    "chars": 200,
                    "tokens": 50,
                    "date": None,
                    "stale": False,
                    "empty": False,
                    "headings": [],
                    "duplicate_count": 2,
                    "duplicate_wasted_lines": 6,
                    "noise": {"noise_ratio": 0.1},
                }
            ],
            "questions": {"exists": False, "count": 0, "open": 0},
            "history": {"exists": False},
            "sleep": {"exists": False},
            "recommendations": [],
        }
        output = core.format_text(report)
        assert "🔁2" in output

    def test_noise_flag_in_output(self) -> None:
        report = {
            "timestamp": "2026-07-08T00:00:00",
            "health": "good",
            "health_label": "Хорошо",
            "total_tokens": 100,
            "total_chars": 400,
            "total_lines": 20,
            "sections": [
                {
                    "name": "test",
                    "path": "test.md",
                    "exists": True,
                    "lines": 10,
                    "chars": 200,
                    "tokens": 50,
                    "date": None,
                    "stale": False,
                    "empty": False,
                    "headings": [],
                    "duplicate_count": 0,
                    "duplicate_wasted_lines": 0,
                    "noise": {"noise_ratio": 0.5},
                }
            ],
            "questions": {"exists": False, "count": 0, "open": 0},
            "history": {"exists": False},
            "sleep": {"exists": False},
            "recommendations": [],
        }
        output = core.format_text(report)
        assert "🌫️" in output
