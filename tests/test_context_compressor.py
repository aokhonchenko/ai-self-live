"""Тесты для context_compressor."""

from __future__ import annotations

import pytest
from pathlib import Path

from src.tools.context_compressor import core


class TestDetectDuplicates:
    """Тесты detect_duplicates."""

    def test_no_duplicates(self):
        text = "line1\nline2\nline3\n"
        result = core.detect_duplicates(text)
        assert result["duplicate_count"] == 0
        assert result["duplicate_wasted_lines"] == 0

    def test_exact_duplicates(self):
        text = "dup1\ndup2\ndup3\nother\n" * 3
        result = core.detect_duplicates(text, min_lines=3, min_matches=2)
        assert result["duplicate_count"] >= 1
        assert result["duplicate_wasted_lines"] > 0

    def test_nested_duplicates(self):
        """Вложенные дубликаты: большой блок содержит маленький."""
        text = "a\nb\nc\nd\ne\n" * 3
        result = core.detect_duplicates(text, min_lines=3, min_matches=2)
        # Должны быть найдены дубликаты
        assert result["duplicate_count"] >= 1

    def test_min_matches_filter(self):
        """Блоки, встречающиеся только 1 раз, не считаются."""
        text = "unique1\nunique2\nunique3\n"
        result = core.detect_duplicates(text, min_matches=2)
        assert result["duplicate_count"] == 0

    def test_min_lines_filter(self):
        """Короткие блоки игнорируются."""
        text = "a\nb\n" * 10
        result = core.detect_duplicates(text, min_lines=5, min_matches=2)
        # a\nb\na\nb\na\nb\na\nb\na\nb\n содержит 5-строчные дубликаты,
        # поэтому здесь ожидаем >= 1
        assert result["duplicate_count"] >= 1


class TestAssessNoise:
    """Тесты assess_noise."""

    def test_clean_text(self):
        text = "line1\nline2\nline3\n"
        result = core.assess_noise(text)
        assert result["noise_lines"] == 0
        assert result["noise_ratio"] == 0.0

    def test_empty_lines(self):
        text = "line1\n\n\nline2\n\n"
        result = core.assess_noise(text)
        assert result["noise_lines"] >= 3
        assert result["noise_ratio"] > 0

    def test_triple_dashes(self):
        text = "line1\n---\nline2\n---\n"
        result = core.assess_noise(text)
        assert result["types"]["separator"] == 2

    def test_deep_headers(self):
        text = "line1\n##### deep\nline2\n"
        result = core.assess_noise(text)
        assert result["types"]["deep_header"] == 1

    def test_empty_text(self):
        result = core.assess_noise("")
        assert result["noise_lines"] == 0
        assert result["noise_ratio"] == 0.0

    def test_table_rows(self):
        text = "| col1 | col2 |\n| a | b |\n"
        result = core.assess_noise(text)
        assert result["types"]["table_row"] == 2


class TestSuggestCompression:
    """Тесты suggest_compression."""

    def test_small_file_no_recommendations(self):
        sections = [{"name": "small", "tokens": 100}]
        result = core.suggest_compression(sections, 100)
        assert result == []

    def test_large_file_recommends_compression(self):
        sections = [{"name": "big", "tokens": 30000}]
        result = core.suggest_compression(sections, 30000)
        assert len(result) > 0

    def test_with_duplicates_recommends_cleanup(self):
        sections = [{"name": "dup", "tokens": 1000, "duplicate_count": 5}]
        result = core.suggest_compression(sections, 1000)
        assert any("дубликатов" in r for r in result)

    def test_with_noise_recommends_cleanup(self):
        sections = [{"name": "noisy", "tokens": 1000, "noise": {"noise_ratio": 40}}]
        result = core.suggest_compression(sections, 1000)
        assert any("шума" in r for r in result)

    def test_empty_sections(self):
        result = core.suggest_compression([], 0)
        assert result == []


class TestExtractSessionBlocks:
    """Тесты extract_session_blocks."""

    def test_no_sessions(self):
        text = "# Заголовок\n\nТекст без сессий.\n"
        blocks = core.extract_session_blocks(text)
        assert len(blocks) == 0

    def test_single_session(self):
        text = "## Сессия 10\n\nДата: 2026-01-01\n\nТекст сессии.\n"
        blocks = core.extract_session_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["number"] == 10
        assert blocks[0]["date"] == "2026-01-01"

    def test_multiple_sessions(self):
        text = (
            "## Сессия 1\n\nДата: 2026-01-01\n\nТекст 1.\n\n"
            "## Сессия 2\n\nДата: 2026-01-02\n\nТекст 2.\n"
        )
        blocks = core.extract_session_blocks(text)
        assert len(blocks) == 2
        assert blocks[0]["number"] == 1
        assert blocks[1]["number"] == 2

    def test_session_without_date(self):
        text = "## Сессия 5\n\nПросто текст.\n"
        blocks = core.extract_session_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["number"] == 5
        assert blocks[0]["date"] is None


class TestCompressLastSession:
    """Тесты compress_last_session."""

    def test_remove_duplicate_failure_blocks(self):
        text = (
            "## Сессия была прервана\n\nСессия была прервана. "
            "Последние 50 строк сохранены в `state/session_failure_tail.txt`.\n\n"
            "## Сессия была прервана\n\nСессия была прервана. "
            "Последние 50 строк сохранены в `state/session_failure_tail.txt`.\n\n"
        )
        result = core.compress_last_session(text)
        assert result.removed_duplicates > 0

    def test_keep_recent_sessions(self):
        blocks = "\n".join(
            f"## Сессия {i}\n\nДата: 2026-01-{i+1:02d}\n\nТекст.\n" for i in range(1, 11)
        )
        result = core.compress_last_session(blocks, keep_recent=3)
        assert len(result.kept_sessions) == 3
        assert len(result.removed_sessions) == 7

    def test_remove_noise(self):
        text = "line1\n\n\n---\n\nline2\n##### deep\nline3\n"
        result = core.compress_last_session(text, remove_noise=True)
        assert result.removed_noise > 0

    def test_dry_run_no_change(self):
        text = "## Сессия 1\n\nТекст.\n"
        result = core.compress_last_session(text)
        assert result.original_lines > 0


class TestFormatCompressionResult:
    """Тесты форматирования результата."""

    def test_format_output_contains_key_info(self):
        result = core.CompressionResult(
            original_lines=100,
            compressed_lines=70,
            removed_lines=30,
            removed_duplicates=10,
            kept_sessions=["сессия 5", "сессия 6"],
        )
        output = core.format_compression_result(result)
        assert "100" in output
        assert "70" in output
        assert "30" in output
        assert "сессия 5" in output

    def test_format_empty_result(self):
        result = core.CompressionResult()
        output = core.format_compression_result(result)
        assert "=" * 50 in output


class TestCompressionResult:
    """Тесты CompressionResult."""

    def test_compression_ratio(self):
        result = core.CompressionResult(original_lines=100, removed_lines=30)
        assert result.compression_ratio == 0.3

    def test_compression_ratio_zero(self):
        result = core.CompressionResult()
        assert result.compression_ratio == 0.0

    def test_size_reduction_pct(self):
        result = core.CompressionResult(original_lines=100, compressed_lines=70)
        assert result.size_reduction_pct == 30.0

    def test_size_reduction_pct_zero(self):
        result = core.CompressionResult()
        assert result.size_reduction_pct == 0.0


class TestToolWrapper:
    """Тесты обёртки tool.py."""

    def test_schema_exists(self) -> None:
        from src.tools.context_compressor.tool import schema

        s = schema()
        assert s["type"] == "function"
        assert s["function"]["name"] == "context_compressor"
        assert "parameters" in s["function"]

    def test_passport_exists(self) -> None:
        from src.tools.context_compressor.tool import passport

        p = passport()
        assert "context_compressor" in p

    def test_handle_dry_run(self, tmp_path: Path) -> None:
        from src.tools.context_compressor.tool import handle

        test_file = tmp_path / "state" / "last_session.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(
            "# Сообщение\n\n## Сессия 1\n\nТекст.\n",
            encoding="utf-8",
        )

        result = handle(tmp_path, {"path": "state/last_session.md", "dry_run": True})
        assert result["ok"] is True
        assert result["dry_run"] is True
        assert "content" in result
        assert "Строк до" in result["content"]

    def test_handle_writes_compressed_text(self, tmp_path: Path) -> None:
        from src.tools.context_compressor.tool import handle

        # Создаём файл с дубликатами
        test_file = tmp_path / "state" / "last_session.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(
            "# Сообщение\n\n"
            "## Сессия была прервана\n\nСессия была прервана. "
            "Последние 50 строк сохранены в `state/session_failure_tail.txt`.\n\n"
            "## Сессия была прервана\n\nСессия была прервана. "
            "Последние 50 строк сохранены в `state/session_failure_tail.txt`.\n\n",
            encoding="utf-8",
        )

        original_content = test_file.read_text(encoding="utf-8")

        result = handle(tmp_path, {"path": "state/last_session.md", "dry_run": False})
        assert result["ok"] is True

        # Файл должен быть изменён (сжат)
        compressed_content = test_file.read_text(encoding="utf-8")
        assert len(compressed_content) < len(original_content)

    def test_handle_missing_file(self, tmp_path: Path) -> None:
        from src.tools.context_compressor.tool import handle

        result = handle(tmp_path, {"path": "missing.md", "dry_run": True})
        assert result["ok"] is False
        assert "error" in result

    def test_handle_default_path(self, tmp_path: Path) -> None:
        from src.tools.context_compressor.tool import handle

        test_file = tmp_path / "state" / "last_session.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# Тест\n\nТекст.\n", encoding="utf-8")

        # Без path — должен использовать state/last_session.md по умолчанию
        result = handle(tmp_path, {"dry_run": True})
        assert result["ok"] is True
