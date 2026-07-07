"""Тесты для инструмента write_file."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.tools.write_file.tool import write_file


class TestWriteFile:
    """Изолированные тесты write_file без обращения к файлам проекта."""

    @pytest.fixture()
    def tmp_root(self, tmp_path: Path) -> Path:
        """Временная директория для тестов."""
        return tmp_path

    def test_basic_write(self, tmp_root: Path) -> None:
        """Базовая запись файла."""
        result = write_file(tmp_root, "test.txt", "hello")
        assert result["path"] == "test.txt"
        assert result["bytes"] == 5
        assert (tmp_root / "test.txt").read_text(encoding="utf-8") == "hello"

    def test_write_creates_parent_dirs(self, tmp_root: Path) -> None:
        """Создание вложенных директорий."""
        result = write_file(tmp_root, "a/b/c/file.txt", "deep")
        assert result["bytes"] == 4
        assert (tmp_root / "a/b/c/file.txt").read_text(encoding="utf-8") == "deep"

    def test_write_empty_content(self, tmp_root: Path) -> None:
        """Запись пустого содержимого."""
        result = write_file(tmp_root, "empty.txt", "")
        assert result["bytes"] == 0
        assert (tmp_root / "empty.txt").read_text(encoding="utf-8") == ""

    def test_write_multiline(self, tmp_root: Path) -> None:
        """Запись многострочного текста."""
        content = "line1\nline2\nline3\n"
        result = write_file(tmp_root, "multi.txt", content)
        assert result["bytes"] == len(content.encode("utf-8"))
        assert (tmp_root / "multi.txt").read_text(encoding="utf-8") == content

    def test_write_unicode_content(self, tmp_root: Path) -> None:
        """Запись текста с Unicode-символами."""
        content = "Привет мир! 日本語テスト"
        result = write_file(tmp_root, "unicode.txt", content)
        assert (tmp_root / "unicode.txt").read_text(encoding="utf-8") == content
        # UTF-8 кодирует кириллицу и японский в несколько байт
        assert result["bytes"] > len(content)

    def test_write_overwrites_existing(self, tmp_root: Path) -> None:
        """Перезапись существующего файла."""
        write_file(tmp_root, "overwrite.txt", "first")
        write_file(tmp_root, "overwrite.txt", "second")
        assert (tmp_root / "overwrite.txt").read_text(encoding="utf-8") == "second"

    def test_write_bytes_count_utf8(self, tmp_root: Path) -> None:
        """Корректный подсчёт байт в UTF-8."""
        # Буква 'ё' в UTF-8 занимает 2 байта
        content = "ё"
        result = write_file(tmp_root, "bytes_test.txt", content)
        assert result["bytes"] == len(content.encode("utf-8"))
        assert result["bytes"] == 2

    def test_write_large_content(self, tmp_root: Path) -> None:
        """Запись большого содержимого."""
        content = "x" * 100_000
        result = write_file(tmp_root, "large.txt", content)
        assert result["bytes"] == 100_000
        assert (tmp_root / "large.txt").read_text(encoding="utf-8") == content

    def test_write_preserves_newlines(self, tmp_root: Path) -> None:
        """Запись текста с переводом строк — на Windows write_text
        использует текстовый режим по умолчанию, поэтому \n сохраняется.
        Проверяем, что файл читается корректно как текст."""
        content = "line1\nline2\n"
        result = write_file(tmp_root, "lf.txt", content)
        assert (tmp_root / "lf.txt").read_text(encoding="utf-8") == content

    def test_write_special_chars_in_path(self, tmp_root: Path) -> None:
        """Запись в файл с спецсимволами в имени."""
        result = write_file(tmp_root, "file-with_dots.txt", "data")
        assert result["bytes"] == 4
        assert (tmp_root / "file-with_dots.txt").read_text(encoding="utf-8") == "data"

    def test_write_result_structure(self, tmp_root: Path) -> None:
        """Результат содержит только ожидаемые ключи."""
        result = write_file(tmp_root, "struct.txt", "test")
        assert set(result.keys()) == {"path", "bytes"}
        assert result["path"] == "struct.txt"
        assert isinstance(result["bytes"], int)

    def test_write_handles_newline_at_end(self, tmp_root: Path) -> None:
        """Запись с переводом строки в конце."""
        content = "with newline\n"
        result = write_file(tmp_root, "newline.txt", content)
        assert result["bytes"] == len(content.encode("utf-8"))
        assert (tmp_root / "newline.txt").read_text(encoding="utf-8") == content
