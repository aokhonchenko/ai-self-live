#!/usr/bin/env python3
"""
Совместимость: общие fallback-функции для чтения файлов.

Используется как запасной вариант, если partial_reader недоступен.
Устраняет дублирование одинаковых fallback-функций в context.py и prompt_builder.py.

Создан: сессия 28 (2026-07-06)
Цель: устранить ~20 строк дублированного кода.
"""


def read_head(filepath: str, n: int = 30) -> str:
    """Читает первые N строк файла (fallback)."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return ''.join(f.readline() for _ in range(n))


def read_headers(filepath: str) -> str:
    """Читает только заголовки markdown (fallback)."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return '\n'.join(line.rstrip() for line in f if line.startswith('#'))


def read_section(filepath: str, section_name: str) -> str:
    """Читает весь файл (fallback — нет точечного парсинга)."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def read_summary(filepath: str, context_lines: int = 2) -> str:
    """Возвращает первые 50 строк (fallback)."""
    return read_head(filepath, 50)
