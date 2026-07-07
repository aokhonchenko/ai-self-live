#!/usr/bin/env python3
"""
Анализатор Python-кода проекта.

Анализирует модули: функции, классы, импорты, docstrings, сложность.
Генерирует компактный отчёт на русском языке.

Создан: сессия 26 (2026-07-06)
Цель: практический инструмент для понимания кодовой базы.

Использование:
    python code_analyzer.py [путь] [--json] [--verbose]

    путь — файл или директория (по умолчанию — текущая директория)
    --json — вывод в JSON
    --verbose — подробный отчёт
"""

import sys
import os
import ast
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional


@dataclass
class FuncInfo:
    """Информация о функции."""
    name: str
    line: int
    args: List[str]
    has_docstring: bool
    is_method: bool = False
    decorators: List[str] = field(default_factory=list)


@dataclass
class ClassInfo:
    """Информация о классе."""
    name: str
    line: int
    methods: List[FuncInfo]
    has_docstring: bool
    bases: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    """Информация об импорте."""
    module: str
    names: List[str]
    line: int
    is_from: bool = False


@dataclass
class FileAnalysis:
    """Результат анализа файла."""
    path: str
    lines: int
    functions: List[FuncInfo]
    classes: List[ClassInfo]
    imports: List[ImportInfo]
    has_docstring: bool
    top_level_assigns: int
    try_except_blocks: int
    error: Optional[str] = None


def analyze_file(filepath: str) -> FileAnalysis:
    """
    Анализирует один Python-файл.
    
    Returns:
        FileAnalysis с результатами.
    """
    path = Path(filepath)
    
    # Читаем файл
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
    except Exception as e:
        return FileAnalysis(
            path=str(path),
            lines=0,
            functions=[],
            classes=[],
            imports=[],
            has_docstring=False,
            top_level_assigns=0,
            try_except_blocks=0,
            error=str(e)
        )
    
    lines = len(source.splitlines())
    
    # Парсим AST
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        return FileAnalysis(
            path=str(path),
            lines=lines,
            functions=[],
            classes=[],
            imports=[],
            has_docstring=False,
            top_level_assigns=0,
            try_except_blocks=0,
            error=f"SyntaxError: {e}"
        )
    
    # Модульный docstring
    has_docstring = (ast.get_docstring(tree) is not None)
    
    functions = []
    classes = []
    imports = []
    top_level_assigns = 0
    try_except_blocks = 0
    
    for node in ast.iter_child_nodes(tree):
        # Функции верхнего уровня
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = _extract_func_info(node, is_method=False)
            functions.append(func)
        
        # Классы
        elif isinstance(node, ast.ClassDef):
            cls = _extract_class_info(node)
            classes.append(cls)
        
        # Импорты
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(
                    module=alias.name,
                    names=[alias.asname or alias.name],
                    line=node.lineno,
                    is_from=False
                ))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            names = [alias.name for alias in node.names]
            imports.append(ImportInfo(
                module=module,
                names=names,
                line=node.lineno,
                is_from=True
            ))
        
        # Присваивания верхнего уровня
        elif isinstance(node, ast.Assign):
            top_level_assigns += 1
        
        # Try/except
        elif isinstance(node, ast.Try):
            try_except_blocks += 1
    
    return FileAnalysis(
        path=str(path),
        lines=lines,
        functions=functions,
        classes=classes,
        imports=imports,
        has_docstring=has_docstring,
        top_level_assigns=top_level_assigns,
        try_except_blocks=try_except_blocks
    )


def _extract_func_info(node, is_method=False) -> FuncInfo:
    """Извлекает информацию о функции из AST-узла."""
    args = []
    for arg in node.args.args:
        args.append(arg.arg)
    
    decorators = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            decorators.append(ast.dump(dec))
    
    return FuncInfo(
        name=node.name,
        line=node.lineno,
        args=args,
        has_docstring=(ast.get_docstring(node) is not None),
        is_method=is_method,
        decorators=decorators
    )


def _extract_class_info(node) -> ClassInfo:
    """Извлекает информацию о классе из AST-узла."""
    methods = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_extract_func_info(item, is_method=True))
    
    bases = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            bases.append(base.id)
        elif isinstance(base, ast.Attribute):
            bases.append(f"{ast.unparse(base)}")
    
    decorators = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
    
    return ClassInfo(
        name=node.name,
        line=node.lineno,
        methods=methods,
        has_docstring=(ast.get_docstring(node) is not None),
        bases=bases,
        decorators=decorators
    )


def analyze_directory(dirpath: str, extensions=('.py',)) -> List[FileAnalysis]:
    """
    Рекурсивно анализирует директорию.
    
    Returns:
        Список FileAnalysis для каждого найденного файла.
    """
    results = []
    root = Path(dirpath)
    
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.suffix in extensions:
            # Пропускаем __pycache__ и .pyc
            if '__pycache__' in str(path):
                continue
            results.append(analyze_file(str(path)))
    
    return results


def format_report(analyses: List[FileAnalysis], verbose=False) -> str:
    """
    Форматирует отчёт на русском языке.
    
    Args:
        analyses: результаты анализа файлов
        verbose: подробный вывод
    
    Returns:
        str: текстовый отчёт
    """
    lines = []
    
    # Заголовок
    lines.append("# Отчёт анализа кодовой базы")
    lines.append("")
    lines.append(f"Проанализировано файлов: {len(analyses)}")
    lines.append("")
    
    # Сводка
    total_lines = sum(a.lines for a in analyses)
    total_funcs = sum(len(a.functions) for a in analyses)
    total_classes = sum(len(a.classes) for a in analyses)
    total_imports = sum(len(a.imports) for a in analyses)
    files_with_docstrings = sum(1 for a in analyses if a.has_docstring)
    files_with_errors = sum(1 for a in analyses if a.error)
    
    funcs_with_docstrings = sum(
        sum(1 for f in a.functions if f.has_docstring)
        for a in analyses
    )
    methods_with_docstrings = sum(
        sum(1 for m in c.methods if m.has_docstring)
        for a in analyses
        for c in a.classes
    )
    total_methods = sum(
        len(c.methods)
        for a in analyses
        for c in a.classes
    )
    
    lines.append("## Сводка")
    lines.append("")
    lines.append(f"| Метрика | Значение |")
    lines.append(f"|---------|----------|")
    lines.append(f"| Файлов | {len(analyses)} |")
    lines.append(f"| Строк кода | {total_lines} |")
    lines.append(f"| Функций | {total_funcs} |")
    lines.append(f"| Методов | {total_methods} |")
    lines.append(f"| Классов | {total_classes} |")
    lines.append(f"| Импортов | {total_imports} |")
    lines.append(f"| Файлов с docstring | {files_with_docstrings}/{len(analyses)} |")
    lines.append(f"| Функций с docstring | {funcs_with_docstrings}/{total_funcs} |")
    lines.append(f"| Методов с docstring | {methods_with_docstrings}/{total_methods} |")
    if files_with_errors:
        lines.append(f"| Файлов с ошибками | {files_with_errors} |")
    lines.append("")
    
    # Docstring coverage
    all_items = total_funcs + total_methods
    documented = funcs_with_docstrings + methods_with_docstrings
    if all_items > 0:
        coverage = documented / all_items * 100
        lines.append(f"**Покрытие docstrings:** {coverage:.0f}% ({documented}/{all_items})")
        lines.append("")
    
    # Детали по файлам
    lines.append("## Детали по файлам")
    lines.append("")
    
    for a in analyses:
        if a.error:
            lines.append(f"### {a.path}")
            lines.append(f"⚠️ Ошибка: {a.error}")
            lines.append("")
            continue
        
        lines.append(f"### {a.path}")
        lines.append(f"- Строк: {a.lines}")
        lines.append(f"- Docstring модуля: {'✅' if a.has_docstring else '❌'}")
        
        if a.functions:
            lines.append(f"- Функции ({len(a.functions)}):")
            for f in a.functions:
                doc = '✅' if f.has_docstring else '❌'
                args_str = ', '.join(f.args) if f.args else '—'
                lines.append(f"  - `{f.name}({args_str})` [{doc}] строка {f.line}")
        
        if a.classes:
            for c in a.classes:
                doc = '✅' if c.has_docstring else '❌'
                bases_str = f"({', '.join(c.bases)})" if c.bases else ''
                lines.append(f"- Класс `{c.name}{bases_str}` [{doc}] строка {c.line}")
                if c.methods:
                    for m in c.methods:
                        mdoc = '✅' if m.has_docstring else '❌'
                        args_str = ', '.join(m.args) if m.args else '—'
                        lines.append(f"  - `{m.name}({args_str})` [{mdoc}] строка {m.line}")
        
        if verbose and a.imports:
            lines.append(f"- Импорты ({len(a.imports)}):")
            for imp in a.imports:
                if imp.is_from:
                    names = ', '.join(imp.names)
                    lines.append(f"  - `from {imp.module} import {names}`")
                else:
                    lines.append(f"  - `import {imp.module}`")
        
        lines.append("")
    
    # Топ импортов
    import_counts = {}
    for a in analyses:
        for imp in a.imports:
            module = imp.module.split('.')[0] if imp.module else '?'
            import_counts[module] = import_counts.get(module, 0) + 1
    
    if import_counts:
        lines.append("## Частые импорты")
        lines.append("")
        for module, count in sorted(import_counts.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"- `{module}` — {count} раз")
        lines.append("")
    
    return '\n'.join(lines)


def format_json(analyses: List[FileAnalysis]) -> str:
    """Форматирует результат в JSON."""
    data = []
    for a in analyses:
        item = {
            'path': a.path,
            'lines': a.lines,
            'has_docstring': a.has_docstring,
            'functions': len(a.functions),
            'classes': len(a.classes),
            'imports': len(a.imports),
            'top_level_assigns': a.top_level_assigns,
            'try_except_blocks': a.try_except_blocks,
        }
        if a.error:
            item['error'] = a.error
        data.append(item)
    
    return json.dumps(data, ensure_ascii=False, indent=2)


def print_usage():
    """Выводит справку."""
    print("Использование: python code_analyzer.py [путь] [--json] [--verbose]")
    print()
    print("Аргументы:")
    print("  путь      — файл или директория (по умолчанию — текущая)")
    print("  --json    — вывод в JSON")
    print("  --verbose — подробный отчёт с импортами")
    print()
    print("Примеры:")
    print("  python code_analyzer.py src/")
    print("  python code_analyzer.py src/tools/partial_reader.py --verbose")
    print("  python code_analyzer.py src/ --json > report.json")


def main():
    if '--help' in sys.argv or '-h' in sys.argv:
        print_usage()
        sys.exit(0)
    
    # Парсинг аргументов
    target = '.'
    output_json = False
    verbose = False
    
    for arg in sys.argv[1:]:
        if arg == '--json':
            output_json = True
        elif arg == '--verbose':
            verbose = True
        elif not arg.startswith('-'):
            target = arg
    
    # Анализ
    path = Path(target)
    
    if path.is_file():
        analyses = [analyze_file(str(path))]
    elif path.is_dir():
        analyses = analyze_directory(str(path))
    else:
        print(f"Ошибка: путь не найден: {target}")
        sys.exit(1)
    
    if not analyses:
        print("Python-файлы не найдены.")
        sys.exit(0)
    
    # Вывод
    if output_json:
        print(format_json(analyses))
    else:
        print(format_report(analyses, verbose=verbose))


if __name__ == '__main__':
    main()
