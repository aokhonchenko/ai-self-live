#!/usr/bin/env python3
"""
Тесты для src/tools/code_analyzer.py.

Первые тесты проекта ai-lives.
Запуск: python -m pytest tests/test_code_analyzer.py -v
    или: python tests/test_code_analyzer.py

Создан: сессия 29 (2026-07-06)
Исправлен: сессия 30 (2026-07-06) — тест self-analysis под реальную структуру
"""

import sys
import os
import json
import tempfile
import textwrap
from pathlib import Path

# Добавляем src в путь для импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'tools'))

from code_analyzer import (
    FuncInfo, ClassInfo, ImportInfo, FileAnalysis,
    analyze_file, analyze_directory, format_report, format_json,
    _extract_func_info, _extract_class_info,
)
import ast


# ─── Вспомогательные функции ───────────────────────────────────────

def _make_temp_file(content: str, suffix: str = '.py') -> str:
    """Создаёт временный файл с заданным содержимым."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def _make_temp_dir(files: dict) -> str:
    """Создаёт временную директорию с файлами {name: content}."""
    tmpdir = tempfile.mkdtemp()
    for name, content in files.items():
        filepath = os.path.join(tmpdir, name)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    return tmpdir


# ─── Тесты dataclass-ов ────────────────────────────────────────────

class TestDataclasses:
    """Проверка создания и базовых свойств dataclass."""

    def test_func_info_creation(self):
        fi = FuncInfo(name='foo', line=1, args=['a', 'b'], has_docstring=True)
        assert fi.name == 'foo'
        assert fi.line == 1
        assert fi.args == ['a', 'b']
        assert fi.has_docstring is True
        assert fi.is_method is False
        assert fi.decorators == []

    def test_class_info_creation(self):
        ci = ClassInfo(name='Bar', line=5, methods=[], has_docstring=False, bases=['Foo'])
        assert ci.name == 'Bar'
        assert ci.bases == ['Foo']
        assert ci.decorators == []

    def test_import_info_from(self):
        imp = ImportInfo(module='os.path', names=['join'], line=1, is_from=True)
        assert imp.is_from is True
        assert imp.module == 'os.path'

    def test_file_analysis_defaults(self):
        fa = FileAnalysis(
            path='test.py', lines=10, functions=[], classes=[],
            imports=[], has_docstring=True, top_level_assigns=0,
            try_except_blocks=0
        )
        assert fa.error is None


# ─── Тесты analyze_file ────────────────────────────────────────────

class TestAnalyzeFile:
    """Тесты анализа одного файла."""

    def test_simple_function(self):
        content = textwrap.dedent('''\
            def hello():
                """Приветствие."""
                print("hello")
        ''')
        path = _make_temp_file(content)
        try:
            result = analyze_file(path)
            assert result.error is None
            assert len(result.functions) == 1
            assert result.functions[0].name == 'hello'
            assert result.functions[0].has_docstring is True
            assert result.functions[0].args == []
            assert result.has_docstring is False  # у модуля нет docstring
        finally:
            os.unlink(path)

    def test_function_with_args(self):
        content = textwrap.dedent('''\
            def add(a, b, c=0):
                return a + b + c
        ''')
        path = _make_temp_file(content)
        try:
            result = analyze_file(path)
            assert len(result.functions) == 1
            assert result.functions[0].args == ['a', 'b', 'c']
            assert result.functions[0].has_docstring is False
        finally:
            os.unlink(path)

    def test_class_with_methods(self):
        content = textwrap.dedent('''\
            class MyClass(Base):
                """Тестовый класс."""
                def method_a(self, x):
                    return x
                def method_b(self):
                    pass
        ''')
        path = _make_temp_file(content)
        try:
            result = analyze_file(path)
            assert len(result.classes) == 1
            cls = result.classes[0]
            assert cls.name == 'MyClass'
            assert cls.has_docstring is True
            assert cls.bases == ['Base']
            assert len(cls.methods) == 2
            assert cls.methods[0].name == 'method_a'
            assert cls.methods[0].is_method is True
            assert cls.methods[0].args == ['self', 'x']
        finally:
            os.unlink(path)

    def test_imports(self):
        content = textwrap.dedent('''\
            import os
            import sys
            from pathlib import Path
            from json import dumps, loads
        ''')
        path = _make_temp_file(content)
        try:
            result = analyze_file(path)
            assert len(result.imports) == 4
            # import os
            assert result.imports[0].module == 'os'
            assert result.imports[0].is_from is False
            # from pathlib import Path
            assert result.imports[2].module == 'pathlib'
            assert result.imports[2].is_from is True
            assert 'Path' in result.imports[2].names
            # from json import dumps, loads
            assert result.imports[3].module == 'json'
            assert 'dumps' in result.imports[3].names
            assert 'loads' in result.imports[3].names
        finally:
            os.unlink(path)

    def test_module_docstring(self):
        content = textwrap.dedent('''\
            """Модульный docstring."""
            x = 1
        ''')
        path = _make_temp_file(content)
        try:
            result = analyze_file(path)
            assert result.has_docstring is True
            assert result.top_level_assigns == 1
        finally:
            os.unlink(path)

    def test_try_except_blocks(self):
        content = textwrap.dedent('''\
            try:
                x = 1
            except ValueError:
                pass
            try:
                y = 2
            except Exception:
                pass
        ''')
        path = _make_temp_file(content)
        try:
            result = analyze_file(path)
            assert result.try_except_blocks == 2
        finally:
            os.unlink(path)

    def test_syntax_error(self):
        content = 'def foo(:\n'  # синтаксическая ошибка
        path = _make_temp_file(content)
        try:
            result = analyze_file(path)
            assert result.error is not None
            assert 'SyntaxError' in result.error
            assert result.lines == 1
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        result = analyze_file('/nonexistent/path/file.py')
        assert result.error is not None
        assert result.lines == 0

    def test_line_count(self):
        content = 'x = 1\ny = 2\nz = 3\n'
        path = _make_temp_file(content)
        try:
            result = analyze_file(path)
            assert result.lines == 3
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = _make_temp_file('')
        try:
            result = analyze_file(path)
            assert result.error is None
            assert result.lines == 0
            assert result.functions == []
            assert result.classes == []
            assert result.imports == []
        finally:
            os.unlink(path)

    def test_decorators(self):
        content = textwrap.dedent('''\
            @staticmethod
            def foo():
                pass
        ''')
        path = _make_temp_file(content)
        try:
            result = analyze_file(path)
            assert len(result.functions) == 1
            assert 'staticmethod' in result.functions[0].decorators
        finally:
            os.unlink(path)

    def test_async_function(self):
        content = textwrap.dedent('''\
            async def fetch(url):
                """Асинхронный запрос."""
                pass
        ''')
        path = _make_temp_file(content)
        try:
            result = analyze_file(path)
            assert len(result.functions) == 1
            assert result.functions[0].name == 'fetch'
            assert result.functions[0].has_docstring is True
        finally:
            os.unlink(path)


# ─── Тесты analyze_directory ───────────────────────────────────────

class TestAnalyzeDirectory:
    """Тесты рекурсивного анализа директории."""

    def test_multiple_files(self):
        tmpdir = _make_temp_dir({
            'a.py': 'def foo(): pass\n',
            'b.py': 'class Bar: pass\n',
            'c.txt': 'not python\n',  # должно быть пропущено
        })
        try:
            results = analyze_directory(tmpdir)
            assert len(results) == 2
            paths = [r.path for r in results]
            assert any('a.py' in p for p in paths)
            assert any('b.py' in p for p in paths)
        finally:
            import shutil
            shutil.rmtree(tmpdir)

    def test_skips_pycache(self):
        tmpdir = tempfile.mkdtemp()
        try:
            # Обычный файл
            with open(os.path.join(tmpdir, 'ok.py'), 'w') as f:
                f.write('x = 1\n')
            # Файл в __pycache__
            pycache = os.path.join(tmpdir, '__pycache__')
            os.makedirs(pycache)
            with open(os.path.join(pycache, 'cached.py'), 'w') as f:
                f.write('y = 2\n')
            
            results = analyze_directory(tmpdir)
            assert len(results) == 1
            assert 'ok.py' in results[0].path
        finally:
            import shutil
            shutil.rmtree(tmpdir)

    def test_empty_directory(self):
        tmpdir = tempfile.mkdtemp()
        try:
            results = analyze_directory(tmpdir)
            assert results == []
        finally:
            import shutil
            shutil.rmtree(tmpdir)

    def test_nested_structure(self):
        tmpdir = _make_temp_dir({
            'top.py': 'x = 1\n',
            'sub/inner.py': 'def inner(): pass\n',
        })
        try:
            results = analyze_directory(tmpdir)
            assert len(results) == 2
        finally:
            import shutil
            shutil.rmtree(tmpdir)


# ─── Тесты format_report ───────────────────────────────────────────

class TestFormatReport:
    """Тесты форматирования отчёта."""

    def test_report_contains_summary(self):
        content = textwrap.dedent('''\
            """Модуль."""
            def foo():
                """Функция."""
                pass
        ''')
        path = _make_temp_file(content)
        try:
            analyses = [analyze_file(path)]
            report = format_report(analyses)
            assert '# Отчёт анализа кодовой базы' in report
            assert 'Проанализировано файлов: 1' in report
            assert '## Сводка' in report
            assert '## Детали по файлам' in report
        finally:
            os.unlink(path)

    def test_report_verbose_includes_imports(self):
        content = 'import os\nimport sys\n'
        path = _make_temp_file(content)
        try:
            analyses = [analyze_file(path)]
            report = format_report(analyses, verbose=True)
            assert 'Импорты' in report
            assert 'import os' in report
        finally:
            os.unlink(path)

    def test_report_error_file(self):
        content = 'def bad(:\n'
        path = _make_temp_file(content)
        try:
            analyses = [analyze_file(path)]
            report = format_report(analyses)
            assert '⚠️ Ошибка' in report
        finally:
            os.unlink(path)

    def test_report_docstring_coverage(self):
        content = textwrap.dedent('''\
            def documented():
                """Есть docstring."""
                pass
            def undocumented():
                pass
        ''')
        path = _make_temp_file(content)
        try:
            analyses = [analyze_file(path)]
            report = format_report(analyses)
            assert 'Покрытие docstrings:' in report
            assert '50%' in report  # 1 из 2
        finally:
            os.unlink(path)

    def test_report_empty(self):
        report = format_report([])
        assert 'Проанализировано файлов: 0' in report


# ─── Тесты format_json ─────────────────────────────────────────────

class TestFormatJson:
    """Тесты JSON-вывода."""

    def test_valid_json(self):
        content = 'def foo(): pass\n'
        path = _make_temp_file(content)
        try:
            analyses = [analyze_file(path)]
            json_str = format_json(analyses)
            data = json.loads(json_str)
            assert len(data) == 1
            assert data[0]['functions'] == 1
            assert data[0]['classes'] == 0
            assert data[0]['has_docstring'] is False
            assert 'error' not in data[0]
        finally:
            os.unlink(path)

    def test_json_with_error(self):
        content = 'def bad(:\n'
        path = _make_temp_file(content)
        try:
            analyses = [analyze_file(path)]
            json_str = format_json(analyses)
            data = json.loads(json_str)
            assert 'error' in data[0]
        finally:
            os.unlink(path)

    def test_json_empty(self):
        json_str = format_json([])
        data = json.loads(json_str)
        assert data == []


# ─── Тесты _extract_func_info и _extract_class_info ────────────────

class TestExtractors:
    """Тесты внутренних функций извлечения из AST."""

    def test_extract_func_info_basic(self):
        source = 'def foo(a, b):\n    pass\n'
        tree = ast.parse(source)
        node = tree.body[0]
        info = _extract_func_info(node)
        assert info.name == 'foo'
        assert info.args == ['a', 'b']
        assert info.has_docstring is False
        assert info.is_method is False
        assert info.line == 1

    def test_extract_class_info_with_bases(self):
        source = 'class MyClass(A, B):\n    def m(self): pass\n'
        tree = ast.parse(source)
        node = tree.body[0]
        info = _extract_class_info(node)
        assert info.name == 'MyClass'
        assert 'A' in info.bases
        assert 'B' in info.bases
        assert len(info.methods) == 1
        assert info.methods[0].name == 'm'
        assert info.methods[0].is_method is True


# ─── Интеграционный тест: сам анализатор ───────────────────────────

class TestSelfAnalysis:
    """Интеграционный тест: анализируем сам code_analyzer.py."""

    def test_analyze_self(self):
        analyzer_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'tools', 'code_analyzer.py'
        )
        if not os.path.exists(analyzer_path):
            return  # пропускаем, если файл не найден
        
        result = analyze_file(analyzer_path)
        assert result.error is None
        assert len(result.functions) > 0
        # В code_analyzer 4 dataclass-а: FuncInfo, ClassInfo, ImportInfo, FileAnalysis
        assert len(result.classes) == 4
        assert result.has_docstring is True
        # Проверяем, что все классы — dataclass-ы с декоратором @dataclass
        for cls in result.classes:
            assert 'dataclass' in cls.decorators, f"Класс {cls.name} без @dataclass"
        # Проверяем docstring-покрытие функций (все основные функции документированы)
        documented = sum(1 for f in result.functions if f.has_docstring)
        total = len(result.functions)
        assert documented / total >= 0.8, (
            f"Покрытие docstrings функций: {documented}/{total} "
            f"({documented/total*100:.0f}%), ожидалось >= 80%"
        )


# ─── Запуск ────────────────────────────────────────────────────────

def run_tests():
    """Запуск тестов без pytest (fallback)."""
    import traceback
    
    test_classes = [
        TestDataclasses, TestAnalyzeFile, TestAnalyzeDirectory,
        TestFormatReport, TestFormatJson, TestExtractors, TestSelfAnalysis,
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
