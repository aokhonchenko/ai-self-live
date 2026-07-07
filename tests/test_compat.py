#!/usr/bin/env python3
"""
Тесты для src/tools/compat.py — fallback-функции чтения файлов.

Запуск: python -m pytest tests/test_compat.py -v

Создан: сессия 31 (2026-07-06)
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'tools'))

from compat import read_head, read_headers, read_section, read_summary


# ─── Вспомогательные функции ───────────────────────────────────────

def _make_temp_file(content: str) -> str:
    """Создаёт временный файл с заданным содержимым."""
    fd, path = tempfile.mkstemp(suffix='.md')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


# ─── Тесты read_head ───────────────────────────────────────────────

class TestReadHead:
    """Тесты чтения первых N строк."""

    def test_reads_first_n_lines(self):
        content = "line1\nline2\nline3\nline4\nline5\n"
        path = _make_temp_file(content)
        try:
            result = read_head(path, 3)
            assert result == "line1\nline2\nline3\n"
        finally:
            os.unlink(path)

    def test_default_30_lines(self):
        content = "\n".join(f"line{i}" for i in range(50)) + "\n"
        path = _make_temp_file(content)
        try:
            result = read_head(path)
            lines = result.split('\n')
            # 30 строк + пустая от последнего \n
            assert len([l for l in lines if l]) == 30
        finally:
            os.unlink(path)

    def test_file_shorter_than_n(self):
        content = "only one line\n"
        path = _make_temp_file(content)
        try:
            result = read_head(path, 100)
            assert result == "only one line\n"
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = _make_temp_file("")
        try:
            result = read_head(path, 10)
            assert result == ""
        finally:
            os.unlink(path)


# ─── Тесты read_headers ────────────────────────────────────────────

class TestReadHeaders:
    """Тесты чтения только заголовков markdown."""

    def test_extracts_headers(self):
        content = "# Title\nSome text\n## Subtitle\nMore text\n### Deep\n"
        path = _make_temp_file(content)
        try:
            result = read_headers(path)
            assert "# Title" in result
            assert "## Subtitle" in result
            assert "### Deep" in result
            assert "Some text" not in result
            assert "More text" not in result
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

    def test_only_hash_lines(self):
        content = "# A\n## B\n### C\n"
        path = _make_temp_file(content)
        try:
            result = read_headers(path)
            lines = result.split('\n')
            assert len(lines) == 3
        finally:
            os.unlink(path)


# ─── Тесты read_section ────────────────────────────────────────────

class TestReadSection:
    """Тесты чтения секции (fallback — читает весь файл)."""

    def test_reads_entire_file(self):
        content = "# Header\nSome content\n## Sub\nMore\n"
        path = _make_temp_file(content)
        try:
            result = read_section(path, "Header")
            assert result == content
        finally:
            os.unlink(path)

    def test_returns_full_content(self):
        content = "Line1\nLine2\nLine3\n"
        path = _make_temp_file(content)
        try:
            result = read_section(path, "anything")
            assert result == content
        finally:
            os.unlink(path)


# ─── Тесты read_summary ────────────────────────────────────────────

class TestReadSummary:
    """Тесты чтения краткой сводки (fallback — первые 50 строк)."""

    def test_returns_first_50_lines(self):
        content = "\n".join(f"line{i}" for i in range(100)) + "\n"
        path = _make_temp_file(content)
        try:
            result = read_summary(path)
            lines = [l for l in result.split('\n') if l]
            assert len(lines) == 50
        finally:
            os.unlink(path)

    def test_short_file(self):
        content = "short\nfile\n"
        path = _make_temp_file(content)
        try:
            result = read_summary(path)
            assert "short" in result
            assert "file" in result
        finally:
            os.unlink(path)


# ─── Запуск ────────────────────────────────────────────────────────

def run_tests():
    """Запуск тестов без pytest (fallback)."""
    test_classes = [TestReadHead, TestReadHeaders, TestReadSection, TestReadSummary]

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
