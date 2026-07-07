#!/usr/bin/env python3
"""
Инструмент частичного чтения файлов.

Читает файлы точечно: заголовки, первые N строк,特定ные секции.
Экономит токены контекста, позволяя решить "читать ли файл" до фактического чтения.

Создан: сессия 21 (2026-07-06)
Фидбек: создатель указал на неоптимальность полного чтения файлов.

Использование:
    python partial_reader.py <файл> [режим] [параметры]

Режимы:
    head N      — первые N строк (по умолчанию 30)
    headers     — только заголовки markdown (# и ##)
    section X   — секция, содержащая X в заголовке
    summary     — краткая сводка: заголовки + первые строки каждой секции
"""

import sys
import os
from pathlib import Path


def read_head(filepath: str, n: int = 30) -> str:
    """Читает первые N строк файла."""
    lines = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= n:
                break
            lines.append(line)
    return ''.join(lines)


def read_headers(filepath: str) -> str:
    """Читает только заголовки markdown файла (# и ##)."""
    headers = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.rstrip()
            if stripped.startswith('#'):
                headers.append(stripped)
    return '\n'.join(headers)


def read_section(filepath: str, section_name: str) -> str:
    """Читает特定ную секцию по имени заголовка (регистронезависимо)."""
    section_lower = section_name.lower()
    result = []
    in_section = False
    section_level = 0

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.rstrip()
            
            # Нашли начало секции
            if stripped.startswith('#') and section_lower in stripped.lower():
                in_section = True
                section_level = len(stripped) - len(stripped.lstrip('#'))
                result.append(line)
                continue
            
            # Мы в секции
            if in_section:
                # Если встретили заголовок того же или более высокого уровня — конец секции
                if stripped.startswith('#'):
                    current_level = len(stripped) - len(stripped.lstrip('#'))
                    if current_level <= section_level:
                        break
                result.append(line)
    
    return ''.join(result)


def read_summary(filepath: str, context_lines: int = 2) -> str:
    """Краткая сводка: заголовки + первые строки после каждого заголовка."""
    sections = []
    current_header = None
    current_lines = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.rstrip()
            
            if stripped.startswith('#'):
                # Сохраняем предыдущую секцию
                if current_header:
                    sections.append((current_header, current_lines[:context_lines]))
                current_header = stripped
                current_lines = []
            elif current_header and stripped:
                current_lines.append(stripped)
        
        # Последняя секция
        if current_header:
            sections.append((current_header, current_lines[:context_lines]))
    
    # Формируем вывод
    result = []
    for header, lines in sections:
        result.append(header)
        for line in lines:
            result.append(f"  {line}")
        result.append("")
    
    return '\n'.join(result)


def _format_size(size: int) -> str:
    size_str = f"{size} \u0431\u0430\u0439\u0442"
    if size > 1024:
        size_str = f"{size / 1024:.1f} \u041a\u0411"
    return size_str


def get_file_info(filepath: str) -> str:
    """Returns compact information about a file or directory."""
    path = Path(filepath)
    if path.is_dir():
        entries = sorted(path.iterdir(), key=lambda item: item.name.lower())
        files = sum(1 for item in entries if item.is_file())
        directories = sum(1 for item in entries if item.is_dir())
        preview = entries[:50]
        result = [
            f"\u0414\u0438\u0440\u0435\u043a\u0442\u043e\u0440\u0438\u044f: {filepath}",
            f"\u042d\u043b\u0435\u043c\u0435\u043d\u0442\u043e\u0432: {len(entries)}",
            f"\u0414\u0438\u0440\u0435\u043a\u0442\u043e\u0440\u0438\u0439: {directories}",
            f"\u0424\u0430\u0439\u043b\u043e\u0432: {files}",
        ]
        if preview:
            result.append("\u0421\u043e\u0434\u0435\u0440\u0436\u0438\u043c\u043e\u0435:")
            for item in preview:
                suffix = "/" if item.is_dir() else ""
                result.append(f"- {item.name}{suffix}")
            if len(entries) > len(preview):
                result.append(f"... \u0435\u0449\u0451 {len(entries) - len(preview)}")
        return "\n".join(result)

    size = os.path.getsize(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        line_count = sum(1 for _ in f)

    return (
        f"\u0424\u0430\u0439\u043b: {filepath}\n"
        f"\u0420\u0430\u0437\u043c\u0435\u0440: {_format_size(size)}\n"
        f"\u0421\u0442\u0440\u043e\u043a: {line_count}"
    )


def print_usage():
    """Выводит справку по использованию."""
    print("Использование: python partial_reader.py <файл> [режим] [параметры]")
    print()
    print("Режимы:")
    print("  head N      — первые N строк (по умолчанию 30)")
    print("  headers     — только заголовки markdown (# и ##)")
    print("  section X   — секция, содержащая X в заголовке")
    print("  summary     — краткая сводка: заголовки + первые строки")
    print("  info        — информация о файле (размер, строки)")
    print()
    print("Примеры:")
    print("  python partial_reader.py knowledge/system_map.md head 20")
    print("  python partial_reader.py tasks/active.md headers")
    print("  python partial_reader.py state/current_plan.md section 'следующий'")


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    
    filepath = sys.argv[1]
    
    # Проверка существования файла
    if not os.path.exists(filepath):
        print(f"Ошибка: файл не найден: {filepath}")
        sys.exit(1)
    
    if not os.path.isfile(filepath):
        print(f"Ошибка: это не файл: {filepath}")
        sys.exit(1)
    
    # Режим по умолчанию
    mode = sys.argv[2] if len(sys.argv) > 2 else 'head'
    
    try:
        if mode == 'head':
            n = int(sys.argv[3]) if len(sys.argv) > 3 else 30
            print(read_head(filepath, n))
        
        elif mode == 'headers':
            print(read_headers(filepath))
        
        elif mode == 'section':
            if len(sys.argv) < 4:
                print("Ошибка: укажите имя секции")
                print("Пример: python partial_reader.py file.md section 'название'")
                sys.exit(1)
            section_name = sys.argv[3]
            result = read_section(filepath, section_name)
            if not result:
                print(f"Секция '{section_name}' не найдена в {filepath}")
                sys.exit(1)
            print(result)
        
        elif mode == 'summary':
            context_lines = int(sys.argv[3]) if len(sys.argv) > 3 else 2
            print(read_summary(filepath, context_lines))
        
        elif mode == 'info':
            print(get_file_info(filepath))
        
        else:
            print(f"Неизвестный режим: {mode}")
            print()
            print_usage()
            sys.exit(1)
    
    except UnicodeDecodeError:
        print(f"Ошибка: файл {filepath} не является UTF-8 текстом")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
