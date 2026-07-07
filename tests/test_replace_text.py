"""Тесты для инструмента replace_text."""

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.tools.replace_text.tool import replace_text, ToolError


class TestReplaceText:
    """Изолированные тесты replace_text без обращения к файлам проекта."""

    @pytest.fixture()
    def tmp_root(self, tmp_path: Path) -> Path:
        """Временная директория для тестов."""
        return tmp_path

    def test_basic_replacement(self, tmp_root: Path) -> None:
        """Одна замена по точному совпадению."""
        target = tmp_root / "test.txt"
        target.write_text("hello world", encoding="utf-8")

        result = replace_text(tmp_root, "test.txt", "hello", "goodbye")

        assert result["replacements"] == 1
        assert target.read_text(encoding="utf-8") == "goodbye world"

    def test_multiple_occurrences_with_count(self, tmp_root: Path) -> None:
        """Замена всех вхождений при expected_replacements > 1."""
        target = tmp_root / "test.txt"
        target.write_text("aaa aaa aaa", encoding="utf-8")

        result = replace_text(tmp_root, "test.txt", "aaa", "bbb", expected_replacements=3)

        assert result["replacements"] == 3
        assert target.read_text(encoding="utf-8") == "bbb bbb bbb"

    def test_expected_replacements_mismatch(self, tmp_root: Path) -> None:
        """Ошибка при несовпадении количества вхождений."""
        target = tmp_root / "test.txt"
        target.write_text("hello world hello", encoding="utf-8")

        with pytest.raises(ToolError, match="expected 1 replacement\\(s\\), found 2"):
            replace_text(tmp_root, "test.txt", "hello", "goodbye", expected_replacements=1)

    def test_empty_old_raises(self, tmp_root: Path) -> None:
        """Пустой old текст вызывает ошибку."""
        target = tmp_root / "test.txt"
        target.write_text("hello", encoding="utf-8")

        with pytest.raises(ToolError, match="old text must be non-empty"):
            replace_text(tmp_root, "test.txt", "", "world")

    def test_expected_replacements_less_than_one(self, tmp_root: Path) -> None:
        """expected_replacements < 1 вызывает ошибку."""
        target = tmp_root / "test.txt"
        target.write_text("hello", encoding="utf-8")

        with pytest.raises(ToolError, match="expected_replacements must be at least 1"):
            replace_text(tmp_root, "test.txt", "hello", "world", expected_replacements=0)

    def test_nonexistent_file(self, tmp_root: Path) -> None:
        """Ошибка при чтении несуществующего файла."""
        with pytest.raises(ToolError, match="file does not exist"):
            replace_text(tmp_root, "missing.txt", "a", "b")

    def test_path_is_directory(self, tmp_root: Path) -> None:
        """Ошибка при указании директории вместо файла."""
        target_dir = tmp_root / "subdir"
        target_dir.mkdir()

        with pytest.raises(ToolError, match="path is not a file"):
            replace_text(tmp_root, "subdir", "a", "b")

    def test_replacement_preserves_surrounding_text(self, tmp_root: Path) -> None:
        """Окружающий текст не меняется."""
        target = tmp_root / "test.txt"
        target.write_text("prefix hello suffix", encoding="utf-8")

        replace_text(tmp_root, "test.txt", "hello", "world")

        assert target.read_text(encoding="utf-8") == "prefix world suffix"

    def test_multiline_replacement(self, tmp_root: Path) -> None:
        """Замена многострочного текста."""
        target = tmp_root / "test.txt"
        target.write_text("line1\nold line\nline3", encoding="utf-8")

        replace_text(tmp_root, "test.txt", "old line", "new line")

        assert target.read_text(encoding="utf-8") == "line1\nnew line\nline3"

    def test_result_contains_bytes_count(self, tmp_root: Path) -> None:
        """Результат содержит корректное количество байт."""
        target = tmp_root / "test.txt"
        target.write_text("hello", encoding="utf-8")

        result = replace_text(tmp_root, "test.txt", "hello", "world")

        assert "bytes" in result
        assert result["bytes"] == len("world".encode("utf-8"))

    def test_special_characters(self, tmp_root: Path) -> None:
        """Замена текста с спецсимволами."""
        target = tmp_root / "test.txt"
        target.write_text("price: $100", encoding="utf-8")

        replace_text(tmp_root, "test.txt", "$100", "$200")

        assert target.read_text(encoding="utf-8") == "price: $200"

    def test_unicode_replacement(self, tmp_root: Path) -> None:
        """Замена текста с Unicode-символами."""
        target = tmp_root / "test.txt"
        target.write_text("Привет мир", encoding="utf-8")

        replace_text(tmp_root, "test.txt", "Привет", "Здравствуйте")

        assert target.read_text(encoding="utf-8") == "Здравствуйте мир"
