#!/usr/bin/env python3
"""
Тесты для src/tools/reader.py — инструмента точечного чтения файлов.

Запуск: python -m pytest tests/test_reader.py -v
    или: python tests/test_reader.py

Создан: сессия 32 (2026-07-06)
Цель: проверить точечное чтение (lines, head, tail, func, class, pattern, section).
"""

import sys
import os
import tempfile
import textwrap
from pathlib import Path

# Добавляем src в путь для импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'tools'))

from reader import (
    ReadResult,
    read_lines, read_head, read_tail,
    read_func, read_class,
    read_pattern, read_section,
    read_file_info,
)


# ─── Вспомогательные функции ───────────────────────────────────────

def _make_temp_file(content: str, suffix: str = '.py') -> str:
    """Создаёт временный файл с заданным содержимым."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def _make_temp_md(content: str) -> str:
    """Создаёт временный markdown-файл."""
    return _make_temp_file(content, suffix='.md')


# ─── Тесты read_lines ──────────────────────────────────────────────

class TestReadLines:
    """Тесты чтения по диапазону строк."""

    def test_basic_range(self):
        content = 'line1\nline2\nline3\nline4\nline5\n'
        path = _make_temp_file(content)
        try:
            result = read_lines(path, 2, 4)
            assert result.error is None
            assert result.lines_read == 3
            assert 'line2' in result.content
            assert 'line3' in result.content
            assert 'line4' in result.content
            assert 'line1' not in result.content
            assert 'line5' not in result.content
        finally:
            os.unlink(path)

    def test_out_of_range(self):
        content = 'a\nb\nc\n'
        path = _make_temp_file(content)
        try:
            result = read_lines(path, 10, 20)
            assert 'выходит за пределы' in result.content
            assert result.lines_read == 0
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        result = read_lines('/nonexistent/file.py', 1, 10)
        assert 'не найден' in result.content
        assert result.lines_read == 0

    def test_single_line(self):
        content = 'first\nsecond\nthird\n'
        path = _make_temp_file(content)
        try:
            result = read_lines(path, 2, 2)
            assert result.lines_read == 1
            assert 'second' in result.content
        finally:
            os.unlink(path)

    def test_method_label(self):
        content = 'x\ny\nz\n'
        path = _make_temp_file(content)
        try:
            result = read_lines(path, 1, 2)
            assert result.method == 'lines[1-2]'
        finally:
            os.unlink(path)


# ─── Тесты read_head / read_tail ──────────────────────────────────

class TestHeadTail:
    """Тесты чтения начала и конца файла."""

    def test_head_default(self):
        content = '\n'.join(f'line{i}' for i in range(1, 101)) + '\n'
        path = _make_temp_file(content)
        try:
            result = read_head(path)
            assert result.lines_read == 30
            assert 'line1' in result.content
            assert 'line30' in result.content
            assert 'line31' not in result.content
        finally:
            os.unlink(path)

    def test_head_custom(self):
        content = '\n'.join(f'line{i}' for i in range(1, 51)) + '\n'
        path = _make_temp_file(content)
        try:
            result = read_head(path, 10)
            assert result.lines_read == 10
            assert 'line10' in result.content
        finally:
            os.unlink(path)

    def test_tail_default(self):
        content = '\n'.join(f'line{i}' for i in range(1, 101)) + '\n'
        path = _make_temp_file(content)
        try:
            result = read_tail(path)
            assert result.lines_read == 30
            assert 'line71' in result.content
            assert 'line100' in result.content
            assert 'line70' not in result.content
        finally:
            os.unlink(path)

    def test_tail_custom(self):
        content = '\n'.join(f'line{i}' for i in range(1, 51)) + '\n'
        path = _make_temp_file(content)
        try:
            result = read_tail(path, 5)
            assert result.lines_read == 5
            assert 'line46' in result.content
            assert 'line50' in result.content
        finally:
            os.unlink(path)

    def test_small_file_head(self):
        content = 'a\nb\nc\n'
        path = _make_temp_file(content)
        try:
            result = read_head(path, 100)
            assert result.lines_read == 3
        finally:
            os.unlink(path)

    def test_small_file_tail(self):
        content = 'a\nb\nc\n'
        path = _make_temp_file(content)
        try:
            result = read_tail(path, 100)
            assert result.lines_read == 3
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        result = read_head('/nonexistent/file.py')
        assert 'не найден' in result.content
        result = read_tail('/nonexistent/file.py')
        assert 'не найден' in result.content


# ─── Тесты read_func ──────────────────────────────────────────────

class TestReadFunc:
    """Тесты чтения определений функций."""

    def test_simple_function(self):
        content = textwrap.dedent('''\
            def hello():
                """Привет."""
                print("hello")
        ''')
        path = _make_temp_file(content)
        try:
            result = read_func(path, 'hello')
            assert result.lines_read > 0
            assert 'def hello' in result.content
            assert 'Привет' in result.content
        finally:
            os.unlink(path)

    def test_function_not_found(self):
        content = 'def foo(): pass\n'
        path = _make_temp_file(content)
        try:
            result = read_func(path, 'bar')
            assert 'не найдена' in result.content
            assert result.lines_read == 0
        finally:
            os.unlink(path)

    def test_function_with_decorator(self):
        content = textwrap.dedent('''\
            @staticmethod
            def foo():
                """Статический метод."""
                pass
        ''')
        path = _make_temp_file(content)
        try:
            result = read_func(path, 'foo')
            assert '@staticmethod' in result.content
            assert 'def foo' in result.content
        finally:
            os.unlink(path)

    def test_async_function(self):
        content = textwrap.dedent('''\
            async def fetch(url):
                """Асинхронный запрос."""
                return None
        ''')
        path = _make_temp_file(content)
        try:
            result = read_func(path, 'fetch')
            assert 'async def fetch' in result.content
            assert 'url' in result.content
        finally:
            os.unlink(path)

    def test_method_in_class(self):
        content = textwrap.dedent('''\
            class MyClass:
                def method(self, x):
                    """Метод."""
                    return x
        ''')
        path = _make_temp_file(content)
        try:
            result = read_func(path, 'method')
            assert 'def method' in result.content
            assert 'self' in result.content
        finally:
            os.unlink(path)

    def test_method_label(self):
        content = 'def foo(): pass\n'
        path = _make_temp_file(content)
        try:
            result = read_func(path, 'foo')
            assert result.method == 'func[foo]'
        finally:
            os.unlink(path)


# ─── Тесты read_class ─────────────────────────────────────────────

class TestReadClass:
    """Тесты чтения определений классов."""

    def test_simple_class(self):
        content = textwrap.dedent('''\
            class MyClass:
                """Тестовый класс."""
                def __init__(self):
                    pass
        ''')
        path = _make_temp_file(content)
        try:
            result = read_class(path, 'MyClass')
            assert result.lines_read > 0
            assert 'class MyClass' in result.content
            assert 'Тестовый класс' in result.content
        finally:
            os.unlink(path)

    def test_class_not_found(self):
        content = 'class Foo: pass\n'
        path = _make_temp_file(content)
        try:
            result = read_class(path, 'Bar')
            assert 'не найден' in result.content
            assert result.lines_read == 0
        finally:
            os.unlink(path)

    def test_class_with_bases(self):
        content = textwrap.dedent('''\
            class Derived(Base, Mixin):
                """Наследуемый класс."""
                pass
        ''')
        path = _make_temp_file(content)
        try:
            result = read_class(path, 'Derived')
            assert 'class Derived(Base, Mixin)' in result.content
        finally:
            os.unlink(path)

    def test_class_with_decorator(self):
        content = textwrap.dedent('''\
            @dataclass
            class Point:
                x: int
                y: int
        ''')
        path = _make_temp_file(content)
        try:
            result = read_class(path, 'Point')
            assert '@dataclass' in result.content
            assert 'class Point' in result.content
        finally:
            os.unlink(path)

    def test_method_label(self):
        content = 'class Foo: pass\n'
        path = _make_temp_file(content)
        try:
            result = read_class(path, 'Foo')
            assert result.method == 'class[Foo]'
        finally:
            os.unlink(path)


# ─── Тесты read_pattern ───────────────────────────────────────────

class TestReadPattern:
    """Тесты чтения по регулярному выражению."""

    def test_basic_pattern(self):
        content = 'import os\nimport sys\nimport json\nfrom pathlib import Path\n'
        path = _make_temp_file(content)
        try:
            result = read_pattern(path, r'^import (os|sys)$')
            assert result.lines_read > 0
            assert 'import os' in result.content
            assert 'import sys' in result.content
        finally:
            os.unlink(path)

    def test_no_match(self):
        content = 'def foo(): pass\n'
        path = _make_temp_file(content)
        try:
            result = read_pattern(path, r'nonexistent_pattern_xyz')
            assert 'Нет совпадений' in result.content
            assert result.lines_read == 0
        finally:
            os.unlink(path)

    def test_with_context(self):
        content = textwrap.dedent('''\
            def foo():
                """Функция foo."""
                x = 1
                return x

            def bar():
                """Функция bar."""
                y = 2
                return y
        ''')
        path = _make_temp_file(content)
        try:
            result = read_pattern(path, r'"""Функция foo', context=1)
            assert 'def foo' in result.content
            assert 'x = 1' in result.content
        finally:
            os.unlink(path)


# ─── Тесты read_section ───────────────────────────────────────────

class TestReadSection:
    """Тесты чтения секций markdown."""

    def test_basic_section(self):
        content = textwrap.dedent('''\
            # Заголовок

            ## Контекст

            Текст контекста.

            ## Задачи

            Список задач.
        ''')
        path = _make_temp_md(content)
        try:
            result = read_section(path, 'Контекст')
            assert result.lines_read > 0
            assert '## Контекст' in result.content
            assert 'Текст контекста' in result.content
            assert '## Задачи' not in result.content
        finally:
            os.unlink(path)

    def test_section_not_found(self):
        content = '## Секция1\n\nТекст\n'
        path = _make_temp_md(content)
        try:
            result = read_section(path, 'Секция2')
            assert 'не найдена' in result.content
            assert result.lines_read == 0
        finally:
            os.unlink(path)

    def test_section_with_subsections(self):
        content = textwrap.dedent('''\
            ## Главная

            Основной текст.

            ### Подсекция

            Подтекст.

            ## Другая

            Другой текст.
        ''')
        path = _make_temp_md(content)
        try:
            result = read_section(path, 'Главная')
            assert '## Главная' in result.content
            assert '### Подсекция' in result.content
            assert '## Другая' not in result.content
        finally:
            os.unlink(path)

    def test_last_section(self):
        content = textwrap.dedent('''\
            ## Первая

            Текст.

            ## Последняя

            Конечный текст.
        ''')
        path = _make_temp_md(content)
        try:
            result = read_section(path, 'Последняя')
            assert '## Последняя' in result.content
            assert 'Конечный текст' in result.content
        finally:
            os.unlink(path)


# ─── Тесты read_file_info ─────────────────────────────────────────

class TestReadFileInfo:
    """Тесты метаданных файла."""

    def test_existing_file(self):
        content = 'x = 1\ny = 2\nz = 3\n'
        path = _make_temp_file(content)
        try:
            info = read_file_info(path)
            assert info['exists'] is True
            assert info['lines'] == 3
            assert info['size_bytes'] > 0
            assert 'error' not in info
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        info = read_file_info('/nonexistent/file.py')
        assert info['exists'] is False
        assert 'error' in info


# ─── Тесты ReadResult ─────────────────────────────────────────────

class TestReadResult:
    """Тесты dataclass ReadResult."""

    def test_creation(self):
        result = ReadResult(
            path='test.py', content='hello',
            lines_read=1, method='head'
        )
        assert result.path == 'test.py'
        assert result.content == 'hello'
        assert result.lines_read == 1
        assert result.method == 'head'
        assert result.truncated is False

    def test_truncated_flag(self):
        result = ReadResult(
            path='test.py', content='hello',
            lines_read=1, method='head', truncated=True
        )
        assert result.truncated is True


# ─── Запуск ────────────────────────────────────────────────────────

def run_tests():
    """Запуск тестов без pytest (fallback)."""
    import traceback
    
    test_classes = [
        TestReadLines, TestHeadTail, TestReadFunc,
        TestReadClass, TestReadPattern, TestReadSection,
        TestReadFileInfo, TestReadResult,
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
