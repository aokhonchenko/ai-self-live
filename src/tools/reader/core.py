#!/usr/bin/env python3
"""
Инструмент точечного чтения файлов.

Позволяет читать файлы без загрузки всего содержимого в память:
- по диапазону строк
- по именам функций/классов (извлекает определение + docstring)
- по регулярным выражениям
- по секциям (заголовкам markdown)

Это решает проблему неоптимального чтения больших файлов целиком.

Создан: сессия 32 (2026-07-06)
Цель: точечное чтение файлов вместо загрузки всего содержимого.

Использование:
    python reader.py <путь> --lines 10-20
    python reader.py <путь> --func main
    python reader.py <путь> --class MyClass
    python reader.py <путь> --pattern "def foo"
    python reader.py <путь> --section "## Контекст"
    python reader.py <путь> --head 30
    python reader.py <путь> --tail 30
"""

import sys
import os
import re
import ast
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class ReadResult:
    """Результат точечного чтения."""
    path: str
    content: str
    lines_read: int
    method: str  # lines, func, class, pattern, section, head, tail
    truncated: bool = False  # True если содержимое обрезано
    error: Optional[str] = None  # Описание ошибки, если есть

def _file_error(path: Path, method: str) -> Optional[ReadResult]:
    """Возвращает ошибку для путей, которые нельзя читать как файл."""
    if not path.exists():
        message = f"Файл не найден: {path}"
    elif path.is_dir():
        message = f"Ожидался файл, получена директория: {path}"
    else:
        return None
    return ReadResult(path=str(path), content=message, lines_read=0, method=method, error=message)


def read_lines(filepath: str, start: int, end: int) -> ReadResult:
    """
    Читает диапазон строк (1-based inclusive).
    
    Args:
        filepath: путь к файлу
        start: первая строка (включительно)
        end: последняя строка (включительно)
    
    Returns:
        ReadResult с содержимым диапазона
    """
    path = Path(filepath)
    if error := _file_error(path, 'lines'):
        return error
    
    with open(path, 'r', encoding='utf-8') as f:
        all_lines = f.readlines()
    
    total = len(all_lines)
    # Конвертируем 1-based в 0-based
    s = max(0, start - 1)
    e = min(total, end)
    
    if s >= total:
        return ReadResult(
            path=str(path),
            content=f"Диапазон {start}-{end} выходит за пределы файла ({total} строк)",
            lines_read=0, method='lines',
            error=f'Диапазон {start}-{end} выходит за пределы файла ({total} строк)'
        )
    
    chunk = ''.join(all_lines[s:e])
    return ReadResult(
        path=str(path), content=chunk,
        lines_read=e - s, method=f'lines[{start}-{end}]'
    )


def read_head(filepath: str, n: int = 30) -> ReadResult:
    """Читает первые N строк файла."""
    path = Path(filepath)
    if error := _file_error(path, 'head'):
        return error
    
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()[:n]
    
    return ReadResult(
        path=str(path), content=''.join(lines),
        lines_read=len(lines), method=f'head[{n}]'
    )


def read_tail(filepath: str, n: int = 30) -> ReadResult:
    """Читает последние N строк файла."""
    path = Path(filepath)
    if error := _file_error(path, 'tail'):
        return error
    
    with open(path, 'r', encoding='utf-8') as f:
        all_lines = f.readlines()
    
    lines = all_lines[-n:] if len(all_lines) > n else all_lines
    
    return ReadResult(
        path=str(path), content=''.join(lines),
        lines_read=len(lines), method=f'tail[{n}]'
    )


def _find_func_lines(source: str, func_name: str) -> Optional[Tuple[int, int]]:
    """Находит строки определения функции в Python-файле.
    
    Returns:
        (start_line, end_line) — 1-based inclusive, или None.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                return node.lineno, node.end_lineno
    
    return None


def read_func(filepath: str, func_name: str) -> ReadResult:
    """
    Читает определение функции из Python-файла.
    
    Включает декораторы, docstring и тело функции.
    """
    path = Path(filepath)
    if error := _file_error(path, 'func'):
        return error
    
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    
    # splitlines(True) даёт 0-based список, каждая строка с \n
    lines = source.splitlines(True)
    span = _find_func_lines(source, func_name)
    
    if span is None:
        return ReadResult(
            path=str(path),
            content=f"Функция '{func_name}' не найдена в {path}",
            lines_read=0, method='func',
            error=f"Функция '{func_name}' не найдена"
        )
    
    # span — 1-based inclusive
    func_start_1based, func_end_1based = span
    
    # Конвертируем в 0-based для индексации списка
    func_start_0based = func_start_1based - 1  # строка def
    func_end_0based = func_end_1based  # slice exclusive upper bound
    
    # Ищем начало декораторов (идём вверх от строки def)
    deco_start_0based = func_start_0based
    for i in range(func_start_0based - 1, -1, -1):
        if lines[i].strip().startswith('@'):
            deco_start_0based = i
        else:
            break
    
    chunk = ''.join(lines[deco_start_0based:func_end_0based])
    return ReadResult(
        path=str(path), content=chunk,
        lines_read=func_end_0based - deco_start_0based, method=f'func[{func_name}]'
    )


def read_class(filepath: str, class_name: str) -> ReadResult:
    """
    Читает определение класса из Python-файла.
    
    Включает декораторы, docstring, базовые классы и все методы.
    """
    path = Path(filepath)
    if error := _file_error(path, 'class'):
        return error
    
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    
    lines = source.splitlines(True)
    
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ReadResult(
            path=str(path),
            content=f"Не удалось распарсить {path}: синтаксическая ошибка",
            lines_read=0, method='class',
            error=f'Синтаксическая ошибка в {path}'
        )
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            # node.lineno — 1-based, node.end_lineno — 1-based inclusive
            class_start_0based = node.lineno - 1
            class_end_0based = node.end_lineno  # slice exclusive
            
            # Ищем декораторы
            deco_start_0based = class_start_0based
            for i in range(class_start_0based - 1, -1, -1):
                if lines[i].strip().startswith('@'):
                    deco_start_0based = i
                else:
                    break
            
            chunk = ''.join(lines[deco_start_0based:class_end_0based])
            return ReadResult(
                path=str(path), content=chunk,
                lines_read=class_end_0based - deco_start_0based,
                method=f'class[{class_name}]'
            )
    
    return ReadResult(
        path=str(path),
        content=f"Класс '{class_name}' не найден в {path}",
        lines_read=0, method='class',
        error=f"Класс '{class_name}' не найден"
    )


def read_pattern(filepath: str, pattern: str, context: int = 2) -> ReadResult:
    """
    Читает строки, совпадающие с регулярным выражением, с контекстом.
    
    Args:
        filepath: путь к файлу
        pattern: регулярное выражение
        context: количество строк контекста до/после совпадения
    """
    path = Path(filepath)
    if error := _file_error(path, 'pattern'):
        return error
    
    with open(path, 'r', encoding='utf-8') as f:
        all_lines = f.readlines()
    
    total = len(all_lines)
    compiled = re.compile(pattern)
    
    matched = []
    for i, line in enumerate(all_lines):
        if compiled.search(line):
            # Добавляем контекст
            s = max(0, i - context)
            e = min(total, i + context + 1)
            matched.append((s, e, i + 1))  # 1-based line number
    
    if not matched:
        return ReadResult(
            path=str(path),
            content=f"Нет совпадений для '{pattern}' в {path}",
            lines_read=0, method='pattern',
            error=f'Нет совпадений для {pattern}'
        )
    
    # Объединяем диапазоны, убирая дубликаты
    result_lines = set()
    for s, e, _ in matched:
        result_lines.update(range(s, e))
    
    chunk = ''.join(all_lines[i] for i in sorted(result_lines))
    return ReadResult(
        path=str(path), content=chunk,
        lines_read=len(result_lines), method=f'pattern[{pattern}]'
    )


def read_section(filepath: str, section_name: str) -> ReadResult:
    """
    Читает секцию markdown-файла по заголовку.
    
    Ищет заголовок уровня H2 (##) и читает до следующего H2 или конца файла.
    """
    path = Path(filepath)
    if error := _file_error(path, 'section'):
        return error
    
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    total = len(lines)
    target = f'## {section_name}'
    
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip() == target or line.strip().startswith(target + ' '):
            start_idx = i
            break
    
    if start_idx is None:
        return ReadResult(
            path=str(path),
            content=f"Секция '{section_name}' не найдена в {path}",
            lines_read=0, method='section',
            error=f"Секция '{section_name}' не найдена"
        )
    
    # Ищем конец секции (следующий ## или конец файла)
    end_idx = total
    for i in range(start_idx + 1, total):
        if lines[i].startswith('## '):
            end_idx = i
            break
    
    chunk = ''.join(lines[start_idx:end_idx])
    return ReadResult(
        path=str(path), content=chunk,
        lines_read=end_idx - start_idx, method=f'section[{section_name}]'
    )


def read_file_info(filepath: str) -> dict:
    """Возвращает метаданные о файле без чтения содержимого."""
    path = Path(filepath)
    if not path.exists():
        return {'error': f'Файл не найден: {path}', 'exists': False}
    if path.is_dir():
        return {'path': str(path), 'exists': True, 'type': 'directory', 'error': f'Ожидался файл, получена директория: {path}'}
    
    stat = path.stat()
    with open(path, 'r', encoding='utf-8') as f:
        line_count = sum(1 for _ in f)
    
    return {
        'path': str(path),
        'exists': True,
        'size_bytes': stat.st_size,
        'lines': line_count,
        'modified': stat.st_mtime,
    }


def print_usage():
    """Выводит справку."""
    print("Использование: python reader.py <путь> [опции]")
    print()
    print("Опции чтения:")
    print("  --lines START END   — прочитать строки START-END (1-based)")
    print("  --head N            — первые N строк (по умолчанию 30)")
    print("  --tail N            — последние N строк (по умолчанию 30)")
    print("  --func ИМЯ          — определение функции из Python-файла")
    print("  --class ИМЯ         — определение класса из Python-файла")
    print("  --pattern REGEX     — строки, совпадающие с regex")
    print("  --section ИМЯ       — секция markdown по заголовку ## ИМЯ")
    print("  --info              — метаданные файла без чтения содержимого")
    print()
    print("Примеры:")
    print("  python reader.py src/tools/code_analyzer.py --lines 1-50")
    print("  python reader.py src/tools/code_analyzer.py --func analyze_file")
    print("  python reader.py state/current_plan.md --section 'Следующий разумный шаг'")
    print("  python reader.py src/tools/code_analyzer.py --info")


def main():
    if '--help' in sys.argv or '-h' in sys.argv:
        print_usage()
        sys.exit(0)
    
    args = sys.argv[1:]
    if not args:
        print_usage()
        sys.exit(1)
    
    filepath = args[0]
    method = 'head'
    param1 = None
    param2 = None
    
    i = 1
    while i < len(args):
        arg = args[i]
        if arg == '--lines' and i + 2 < len(args):
            method = 'lines'
            param1, param2 = int(args[i + 1]), int(args[i + 2])
            i += 3
        elif arg == '--head' and i + 1 < len(args):
            method = 'head'
            param1 = int(args[i + 1])
            i += 2
        elif arg == '--tail' and i + 1 < len(args):
            method = 'tail'
            param1 = int(args[i + 1])
            i += 2
        elif arg == '--func' and i + 1 < len(args):
            method = 'func'
            param1 = args[i + 1]
            i += 2
        elif arg == '--class' and i + 1 < len(args):
            method = 'class'
            param1 = args[i + 1]
            i += 2
        elif arg == '--pattern' and i + 1 < len(args):
            method = 'pattern'
            param1 = args[i + 1]
            i += 2
        elif arg == '--section' and i + 1 < len(args):
            method = 'section'
            param1 = args[i + 1]
            i += 2
        elif arg == '--info':
            method = 'info'
            i += 1
        else:
            i += 1
    
    # Выполняем чтение
    if method == 'info':
        info = read_file_info(filepath)
        if 'error' in info:
            print(info['error'])
        else:
            print(f"Файл: {info['path']}")
            print(f"Размер: {info['size_bytes']} байт")
            print(f"Строк: {info['lines']}")
        return
    
    # Остальные методы — читаем и выводим
    if method == 'lines':
        result = read_lines(filepath, param1, param2)
    elif method == 'head':
        result = read_head(filepath, param1 or 30)
    elif method == 'tail':
        result = read_tail(filepath, param1 or 30)
    elif method == 'func':
        result = read_func(filepath, param1)
    elif method == 'class':
        result = read_class(filepath, param1)
    elif method == 'pattern':
        result = read_pattern(filepath, param1)
    elif method == 'section':
        result = read_section(filepath, param1)
    else:
        result = read_head(filepath)
    
    # Выводим результат
    print(f"# {result.method}: {result.path} ({result.lines_read} строк)")
    if result.truncated:
        print("(содержимое обрезано)")
    print()
    print(result.content)


if __name__ == '__main__':
    main()

