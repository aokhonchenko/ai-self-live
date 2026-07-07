
#!/usr/bin/env python3
"""
Тесты для src/tools/apply_patch.py — инструмента частичных правок.

Запуск: python -m pytest tests/test_apply_patch.py -v
    или: python tests/test_apply_patch.py

Создан: сессия 35 (2026-07-06)
Цель: проверить частичные правки (replace, regex, insert, delete, section).
"""

import sys
import os
import tempfile
import textwrap
from pathlib import Path

# Добавляем src/tools в путь для импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'tools'))

from apply_patch import (
    PatchResult,
    replace_text, replace_regex,
    insert_after_line, insert_before_line,
    delete_lines, delete_line_range,
    replace_section,
    append_text,
)


# ─── Вспомогательные функции ───────────────────────────────────────

def _make_temp_file(content: str, suffix: str = '.py') -> str:
    """Создаёт временный файл с заданным содержимым."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def _read_file(path: str) -> str:
    """Читает содержимое файла."""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


# ─── Тесты replace_text ────────────────────────────────────────────

class TestReplaceText:
    """Тесты замены текста."""

    def test_replace_first_occurrence(self):
        content = 'foo\nbar\nfoo\n'
        path = _make_temp_file(content)
        try:
            result = replace_text(path, 'foo', 'baz')
            assert result.applied is True
            assert result.changes == 1
            new_content = _read_file(path)
            assert new_content == 'baz\nbar\nfoo\n'
        finally:
            os.unlink(path)

    def test_replace_all(self):
        content = 'foo\nbar\nfoo\n'
        path = _make_temp_file(content)
        try:
            result = replace_text(path, 'foo', 'baz', count=0)
            assert result.applied is True
            assert result.changes == 2
            new_content = _read_file(path)
            assert new_content == 'baz\nbar\nbaz\n'
        finally:
            os.unlink(path)

    def test_replace_not_found(self):
        content = 'foo\nbar\n'
        path = _make_temp_file(content)
        try:
            result = replace_text(path, 'nonexistent', 'baz')
            assert result.applied is False
            assert result.error is not None
            assert 'не найден' in result.error
        finally:
            os.unlink(path)

    def test_replace_nonexistent_file(self):
        result = replace_text('/nonexistent/file.py', 'foo', 'bar')
        assert result.applied is False
        assert 'не найден' in result.error

    def test_replace_dry_run(self):
        content = 'foo\nbar\n'
        path = _make_temp_file(content)
        try:
            result = replace_text(path, 'foo', 'baz', dry_run=True)
            assert result.applied is True
            assert result.changes == 1
            # Файл не должен измениться
            new_content = _read_file(path)
            assert new_content == content
        finally:
            os.unlink(path)


# ─── Тесты replace_regex ───────────────────────────────────────────

class TestReplaceRegex:
    """Тесты замены по регулярному выражению."""

    def test_regex_basic(self):
        content = 'def foo():\n    pass\n'
        path = _make_temp_file(content)
        try:
            result = replace_regex(path, r'def (\w+)', r'def renamed_\1')
            assert result.applied is True
            assert result.changes == 1
            new_content = _read_file(path)
            assert 'def renamed_foo' in new_content
        finally:
            os.unlink(path)

    def test_regex_no_match(self):
        content = 'foo\nbar\n'
        path = _make_temp_file(content)
        try:
            result = replace_regex(path, r'def \w+', 'replaced')
            assert result.applied is False
            assert 'Нет совпадений' in result.error
        finally:
            os.unlink(path)

    def test_regex_invalid_pattern(self):
        content = 'foo\n'
        path = _make_temp_file(content)
        try:
            result = replace_regex(path, r'[invalid', 'replaced')
            assert result.applied is False
            assert 'Ошибка в регулярном выражении' in result.error
        finally:
            os.unlink(path)

    def test_regex_multiline(self):
        content = 'a=1\nb=2\na=3\n'
        path = _make_temp_file(content)
        try:
            result = replace_regex(path, r'^a=\d+', 'a=0')
            assert result.applied is True
            assert result.changes == 2
            new_content = _read_file(path)
            assert new_content == 'a=0\nb=2\na=0\n'
        finally:
            os.unlink(path)


# ─── Тесты insert_after_line / insert_before_line ──────────────────

class TestInsertAfter:
    """Тесты вставки после строки."""

    def test_insert_after_basic(self):
        content = 'import os\nimport sys\n'
        path = _make_temp_file(content)
        try:
            result = insert_after_line(path, 'import os', 'import json')
            assert result.applied is True
            new_content = _read_file(path)
            assert 'import os\nimport json\nimport sys' in new_content
        finally:
            os.unlink(path)

    def test_insert_after_not_found(self):
        content = 'foo\nbar\n'
        path = _make_temp_file(content)
        try:
            result = insert_after_line(path, 'nonexistent', 'new line')
            assert result.applied is False
            assert 'не найдена' in result.error
        finally:
            os.unlink(path)

    def test_insert_after_dry_run(self):
        content = 'foo\nbar\n'
        path = _make_temp_file(content)
        try:
            result = insert_after_line(path, 'foo', 'new line', dry_run=True)
            assert result.applied is True
            new_content = _read_file(path)
            assert new_content == content  # не изменился
        finally:
            os.unlink(path)


class TestInsertBefore:
    """Тесты вставки перед строкой."""

    def test_insert_before_basic(self):
        content = 'import os\nimport sys\n'
        path = _make_temp_file(content)
        try:
            result = insert_before_line(path, 'import sys', 'import json')
            assert result.applied is True
            new_content = _read_file(path)
            assert 'import os\nimport json\nimport sys' in new_content
        finally:
            os.unlink(path)

    def test_insert_before_not_found(self):
        content = 'foo\n'
        path = _make_temp_file(content)
        try:
            result = insert_before_line(path, 'nonexistent', 'new')
            assert result.applied is False
        finally:
            os.unlink(path)


# ─── Тесты delete_lines ────────────────────────────────────────────

class TestDeleteLines:
    """Тесты удаления строк."""

    def test_delete_basic(self):
        content = 'keep\nremove_this\nkeep\n'
        path = _make_temp_file(content)
        try:
            result = delete_lines(path, 'remove')
            assert result.applied is True
            assert result.changes == 1
            new_content = _read_file(path)
            assert new_content == 'keep\nkeep\n'
        finally:
            os.unlink(path)

    def test_delete_not_found(self):
        content = 'keep\nkeep\n'
        path = _make_temp_file(content)
        try:
            result = delete_lines(path, 'remove')
            assert result.applied is False
            assert 'не найдены' in result.error
        finally:
            os.unlink(path)

    def test_delete_multiple(self):
        content = 'a\nb\nc\nb\nd\n'
        path = _make_temp_file(content)
        try:
            result = delete_lines(path, 'b')
            assert result.applied is True
            assert result.changes == 2
            new_content = _read_file(path)
            assert new_content == 'a\nc\nd\n'
        finally:
            os.unlink(path)


# ─── Тесты delete_line_range ───────────────────────────────────────

class TestDeleteRange:
    """Тесты удаления диапазона строк."""

    def test_delete_range_basic(self):
        content = 'line1\nline2\nline3\nline4\nline5\n'
        path = _make_temp_file(content)
        try:
            result = delete_line_range(path, 2, 4)
            assert result.applied is True
            assert result.changes == 3
            new_content = _read_file(path)
            assert new_content == 'line1\nline5\n'
        finally:
            os.unlink(path)

    def test_delete_range_out_of_bounds(self):
        content = 'a\nb\nc\n'
        path = _make_temp_file(content)
        try:
            result = delete_line_range(path, 10, 20)
            assert result.applied is False
            assert 'выходит за пределы' in result.error
        finally:
            os.unlink(path)

    def test_delete_range_single_line(self):
        content = 'a\nb\nc\n'
        path = _make_temp_file(content)
        try:
            result = delete_line_range(path, 2, 2)
            assert result.applied is True
            assert result.changes == 1
            new_content = _read_file(path)
            assert new_content == 'a\nc\n'
        finally:
            os.unlink(path)


# ─── Тесты replace_section ─────────────────────────────────────────

class TestReplaceSection:
    """Тесты замены секции markdown."""

    def test_replace_section_basic(self):
        content = textwrap.dedent('''\
            # Title

            ## Old Section

            Old content here.

            ## Next Section

            More content.
        ''')
        path = _make_temp_file(content, suffix='.md')
        try:
            result = replace_section(path, 'Old Section', 'New content here.')
            assert result.applied is True
            new_content = _read_file(path)
            assert '## Old Section' in new_content
            assert 'New content here.' in new_content
            assert 'Old content here.' not in new_content
            assert '## Next Section' in new_content
        finally:
            os.unlink(path)

    def test_replace_section_not_found(self):
        content = '## Section1\n\nText\n'
        path = _make_temp_file(content, suffix='.md')
        try:
            result = replace_section(path, 'Nonexistent', 'New text')
            assert result.applied is False
            assert 'не найдена' in result.error
        finally:
            os.unlink(path)

    def test_replace_last_section(self):
        content = textwrap.dedent('''\
            ## First

            Text.

            ## Last

            Old last text.
        ''')
        path = _make_temp_file(content, suffix='.md')
        try:
            result = replace_section(path, 'Last', 'New last text.')
            assert result.applied is True
            new_content = _read_file(path)
            assert 'New last text.' in new_content
            assert 'Old last text.' not in new_content
        finally:
            os.unlink(path)


# ─── Тесты PatchResult ─────────────────────────────────────────────

class TestPatchResult:
    """Тесты dataclass PatchResult."""

    def test_creation(self):
        result = PatchResult(
            path='test.py', applied=True, operation='replace',
            changes=1, preview='+ new line'
        )
        assert result.path == 'test.py'
        assert result.applied is True
        assert result.operation == 'replace'
        assert result.changes == 1
        assert result.preview == '+ new line'
        assert result.error is None

    def test_with_error(self):
        result = PatchResult(
            path='test.py', applied=False, operation='replace',
            changes=0, preview='', error='File not found'
        )
        assert result.error == 'File not found'
        assert result.applied is False



# ─── Тесты append_text ─────────────────────────────────────────────

class TestAppendText:
    """Тесты добавления текста в конец файла."""

    def test_append_basic(self):
        content = 'line1\nline2\n'
        path = _make_temp_file(content)
        try:
            result = append_text(path, 'line3')
            assert result.applied is True
            assert result.changes == 1
            new_content = _read_file(path)
            assert new_content == 'line1\nline2\nline3\n'
        finally:
            os.unlink(path)

    def test_append_to_empty_file(self):
        content = ''
        path = _make_temp_file(content)
        try:
            result = append_text(path, 'first line')
            assert result.applied is True
            new_content = _read_file(path)
            assert new_content == 'first line\n'
        finally:
            os.unlink(path)

    def test_append_without_trailing_newline(self):
        content = 'line1\nline2'
        path = _make_temp_file(content)
        try:
            result = append_text(path, 'line3')
            assert result.applied is True
            new_content = _read_file(path)
            assert new_content == 'line1\nline2\nline3\n'
        finally:
            os.unlink(path)

    def test_append_nonexistent_file(self):
        result = append_text('/nonexistent/file.py', 'text')
        assert result.applied is False
        assert 'не найден' in result.error

    def test_append_dry_run(self):
        content = 'line1\n'
        path = _make_temp_file(content)
        try:
            result = append_text(path, 'line2', dry_run=True)
            assert result.applied is True
            new_content = _read_file(path)
            assert new_content == content  # не изменился
        finally:
            os.unlink(path)

    def test_append_multiline(self):
        content = 'line1\n'
        path = _make_temp_file(content)
        try:
            result = append_text(path, 'line2\nline3')
            assert result.applied is True
            new_content = _read_file(path)
            assert 'line2\nline3\n' in new_content
        finally:
            os.unlink(path)

# ─── Запуск ────────────────────────────────────────────────────────

def run_tests():
    """Запуск тестов без pytest (fallback)."""
    test_classes = [
        TestReplaceText, TestReplaceRegex,
        TestInsertAfter, TestInsertBefore,
        TestDeleteLines, TestDeleteRange,
        TestReplaceSection, TestAppendText, TestPatchResult,
    ]

    passed = 0
    failed = 0
    errors = []

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
                errors.append((test_name, e))
                print(f"  ❌ {test_name}: {e}")

    print(f"\n{'='*50}")
    print(f"Результат: {passed} прошли, {failed} упали")

    if errors:
        print(f"\nОшибки:")
        for name, err in errors:
            print(f"  {name}: {err}")

    return failed == 0


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
