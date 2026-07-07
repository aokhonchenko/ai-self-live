#!/usr/bin/env python3
"""
Тесты для src/tools/partial_reader.py — инструмент частичного чтения.

Запуск: python -m pytest tests/test_partial_reader.py -v

Создан: сессия 31 (2026-07-06)
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'tools'))

from partial_reader import (
    read_head, read_headers, read_section, read_summary, get_file_info
)


# ─── Вспомогательные функции ───────────────────────────────────────

def _make_temp_file(content: str, suffix: str = '.md') -> str:
    """Создаёт временный файл с заданным содержимым."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


SAMPLE_MD = """\
# Первая секция
Текст первой секции.
Ещё строка.

## Подсекция
Текст подсекции.

# Вторая секция
Текст второй секции.

### Глубокая подсекция
Глубокий текст.
"""


# ─── Тесты read_head ───────────────────────────────────────────────

class TestReadHead:
    """Тесты чтения первых N строк."""

    def test_reads_first_n_lines(self):
        content = "line1\nline2\nline3\nline4\nline5\n"
        path = _make_temp_file(content)
        try:
            result = read_head(path, 3)
            lines = result.rstrip('\n').split('\n')
            assert len(lines) == 3
            assert lines[0] == "line1"
            assert lines[2] == "line3"
        finally:
            os.unlink(path)

    def test_default_30_lines(self):
        content = "\n".join(f"line{i}" for i in range(50)) + "\n"
        path = _make_temp_file(content)
        try:
            result = read_head(path)
            lines = [l for l in result.split('\n') if l]
            assert len(lines) == 30
        finally:
            os.unlink(path)

    def test_file_shorter_than_n(self):
        content = "only one line\n"
        path = _make_temp_file(content)
        try:
            result = read_head(path, 100)
            assert "only one line" in result
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = _make_temp_file("")
        try:
            result = read_head(path, 10)
            assert result == ""
        finally:
            os.unlink(path)

    def test_zero_lines(self):
        content = "something\n"
        path = _make_temp_file(content)
        try:
            result = read_head(path, 0)
            assert result == ""
        finally:
            os.unlink(path)


# ─── Тесты read_headers ────────────────────────────────────────────

class TestReadHeaders:
    """Тесты чтения только заголовков markdown (# и ##)."""

    def test_extracts_h1_and_h2(self):
        path = _make_temp_file(SAMPLE_MD)
        try:
            result = read_headers(path)
            assert "# Первая секция" in result
            assert "## Подсекция" in result
            assert "# Вторая секция" in result
            assert "### Глубокая подсекция" in result
            assert "Текст первой секции" not in result
            assert "Текст подсекции" not in result
        finally:
            os.unlink(path)

    def test_no_headers(self):
        content = "just plain text\nno headers here\n"
        path = _make_temp_file(content)
        try:
            result = read_headers(path)
            assert result == ""
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = _make_temp_file("")
        try:
            result = read_headers(path)
            assert result == ""
        finally:
            os.unlink(path)

    def test_all_header_levels(self):
        content = "# H1\n## H2\n### H3\n#### H4\n"
        path = _make_temp_file(content)
        try:
            result = read_headers(path)
            lines = result.split('\n')
            assert len(lines) == 4
        finally:
            os.unlink(path)


# ─── Тесты read_section ────────────────────────────────────────────

class TestReadSection:
    """Тесты чтения конкретной секции по имени заголовка."""

    def test_reads_first_section(self):
        path = _make_temp_file(SAMPLE_MD)
        try:
            result = read_section(path, "первая секция")
            assert "# Первая секция" in result
            assert "Текст первой секции" in result
            assert "## Подсекция" in result
            assert "# Вторая секция" not in result
        finally:
            os.unlink(path)

    def test_reads_second_section(self):
        path = _make_temp_file(SAMPLE_MD)
        try:
            result = read_section(path, "вторая секция")
            assert "# Вторая секция" in result
            assert "Текст второй секции" in result
            assert "### Глубокая подсекция" in result
            assert "# Первая секция" not in result
        finally:
            os.unlink(path)

    def test_reads_subsection(self):
        path = _make_temp_file(SAMPLE_MD)
        try:
            result = read_section(path, "подсекция")
            assert "## Подсекция" in result
            assert "Текст подсекции" in result
            # Должна остановиться на # Вторая секция
            assert "# Вторая секция" not in result
        finally:
            os.unlink(path)

    def test_case_insensitive(self):
        path = _make_temp_file(SAMPLE_MD)
        try:
            result = read_section(path, "ПЕРВАЯ СЕКЦИЯ")
            assert "# Первая секция" in result
        finally:
            os.unlink(path)

    def test_section_not_found(self):
        path = _make_temp_file(SAMPLE_MD)
        try:
            result = read_section(path, "несуществующая секция")
            assert result == ""
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = _make_temp_file("")
        try:
            result = read_section(path, "anything")
            assert result == ""
        finally:
            os.unlink(path)


# ─── Тесты read_summary ────────────────────────────────────────────

class TestReadSummary:
    """Тесты краткой сводки: заголовки + первые строки после каждого."""

    def test_summary_structure(self):
        path = _make_temp_file(SAMPLE_MD)
        try:
            result = read_summary(path, context_lines=1)
            assert "# Первая секция" in result
            assert "Текст первой секции" in result
            assert "# Вторая секция" in result
            assert "Текст второй секции" in result
        finally:
            os.unlink(path)

    def test_context_lines_parameter(self):
        path = _make_temp_file(SAMPLE_MD)
        try:
            result_default = read_summary(path)  # default 2
            result_one = read_summary(path, context_lines=1)
            # Больше контекстных строк → больше текста
            assert len(result_default) >= len(result_one)
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = _make_temp_file("")
        try:
            result = read_summary(path)
            assert result == ""
        finally:
            os.unlink(path)

    def test_no_content_after_header(self):
        content = "# Empty Section\n# Another Section\n"
        path = _make_temp_file(content)
        try:
            result = read_summary(path)
            assert "# Empty Section" in result
            assert "# Another Section" in result
        finally:
            os.unlink(path)


# ─── Тесты get_file_info ───────────────────────────────────────────

class TestGetFileInfo:
    """Тесты информации о файле."""

    def test_info_contains_size_and_lines(self):
        content = "line1\nline2\nline3\n"
        path = _make_temp_file(content)
        try:
            result = get_file_info(path)
            assert "Файл:" in result
            assert "Размер:" in result
            assert "Строк:" in result
            assert "3" in result  # 3 строки
        finally:
            os.unlink(path)

    def test_info_kilobytes(self):
        content = "x" * 2000 + "\n"
        path = _make_temp_file(content)
        try:
            result = get_file_info(path)
            assert "КБ" in result
        finally:
            os.unlink(path)

    def test_info_bytes(self):
        content = "small\n"
        path = _make_temp_file(content)
        try:
            result = get_file_info(path)
            assert "байт" in result
            assert "КБ" not in result
        finally:
            os.unlink(path)


# ─── Запуск ────────────────────────────────────────────────────────

def run_tests():
    """Запуск тестов без pytest (fallback)."""
    test_classes = [
        TestReadHead, TestReadHeaders, TestReadSection,
        TestReadSummary, TestGetFileInfo,
    ]

    passed = 0
    failed = 0

    for cls in test_classes:
        instance = cls()
        for method_name in sorted(dir(instance)):
            if not method_name.startswith('test_'):
                continue
            method = getattr(instance, method_name)
            test_name = f"{cls.__name__}.{method_name}"
            try:
                method()
                passed += 1
                print(f"  ✅ {test_name}")
            except Exception as e:
                failed += 1
                print(f"  ❌ {test_name}: {e}")

    print(f"\n{'='*50}")
    print(f"Результат: {passed} прошли, {failed} упали")
    return failed == 0


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
