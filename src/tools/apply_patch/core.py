#!/usr/bin/env python3
"""
Инструмент частичных правок файлов (apply).

Позволяет вносить точечные изменения в файлы без перезаписи всего содержимого.
Поддерживает операции:
- Замена строки или блока строк по номеру
- Замена по регулярному выражению
- Вставка строк после/перед указанной строкой
- Удаление строк
- Замена секции markdown

Это решает проблему неоптимальной работы с моделью: вместо записи всего файла
целиком можно применить только нужное изменение.

Создан: сессия 35 (2026-07-06)
Цель: частичные правки файлов вместо полной перезаписи.

Использование:
    python apply_patch.py <путь> --replace <старое> <новое>
    python apply_patch.py <путь> --regex <pattern> <замена>
    python apply_patch.py <путь> --insert-after <строка> <текст>
    python apply_patch.py <путь> --insert-before <строка> <текст>
    python apply_patch.py <путь> --delete <строка>
    python apply_patch.py <путь> --delete-range <start> <end>
    python apply_patch.py <путь> --section <имя> <новое_содержимое>
    python apply_patch.py <путь> --dry-run  # показать изменения без записи
"""

import sys
import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class PatchResult:
    """Результат применения патча."""
    path: str
    applied: bool
    operation: str
    changes: int  # количество изменённых строк/блоков
    preview: str  # diff-подобный предпросмотр
    error: Optional[str] = None


def _read_file_lines(filepath: str) -> Tuple[List[str], Optional[str]]:
    """Читает файл и возвращает список строк."""
    path = Path(filepath)
    if not path.exists():
        return [], f"Файл не найден: {filepath}"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.readlines(), None
    except Exception as e:
        return [], str(e)


def _write_file_lines(filepath: str, lines: List[str]) -> Optional[str]:
    """Записывает список строк в файл."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return None
    except Exception as e:
        return str(e)


def _make_preview(old_lines: List[str], new_lines: List[str],
                  context: int = 2) -> str:
    """Создаёт diff-подобный предпросмотр изменений."""
    result = []
    # Простой diff: показываем только изменённые строки с контекстом
    old_set = set(old_lines)
    new_set = set(new_lines)
    
    added = new_set - old_set
    removed = old_set - new_set
    
    if added:
        result.append("--- Добавлено:")
        for line in sorted(added):
            result.append(f"+ {line.rstrip()}")
    if removed:
        result.append("--- Удалено:")
        for line in sorted(removed):
            result.append(f"- {line.rstrip()}")
    
    return '\n'.join(result) if result else "(нет изменений)"


def replace_text(filepath: str, old_text: str, new_text: str,
                 count: int = 1, dry_run: bool = False) -> PatchResult:
    """
    Заменяет текст в файле (первое вхождение или все).
    
    Args:
        filepath: путь к файлу
        old_text: заменяемый текст
        new_text: новый текст
        count: количество замен (0 = все)
        dry_run: только показать изменения
    
    Returns:
        PatchResult с результатом
    """
    lines, error = _read_file_lines(filepath)
    if error:
        return PatchResult(
            path=filepath, applied=False, operation='replace',
            changes=0, preview='', error=error
        )
    
    content = ''.join(lines)
    if old_text not in content:
        return PatchResult(
            path=filepath, applied=False, operation='replace',
            changes=0, preview='',
            error=f"Текст не найден: {old_text[:50]}..."
        )
    
    if count == 1:
        new_content = content.replace(old_text, new_text, 1)
    else:
        new_content = content.replace(old_text, new_text)
    
    actual_changes = content.count(old_text) if count == 0 else min(count, content.count(old_text))
    
    if dry_run:
        preview = _make_preview(content.splitlines(True),
                                new_content.splitlines(True))
        return PatchResult(
            path=filepath, applied=True, operation='replace',
            changes=actual_changes, preview=preview
        )
    
    new_lines = new_content.splitlines(True)
    # splitlines(True) может убрать последнюю пустую строку
    if new_content.endswith('\n') and (not new_lines or not new_lines[-1].endswith('\n')):
        new_lines[-1] = new_lines[-1] + '\n'
    
    err = _write_file_lines(filepath, new_lines)
    if err:
        return PatchResult(
            path=filepath, applied=False, operation='replace',
            changes=0, preview='', error=err
        )
    
    return PatchResult(
        path=filepath, applied=True, operation='replace',
        changes=actual_changes,
        preview=f"Заменено {actual_changes} вхождений"
    )


def replace_regex(filepath: str, pattern: str, replacement: str,
                  count: int = 0, dry_run: bool = False,
                  flags: int = re.MULTILINE) -> PatchResult:
    """
    Заменяет текст по регулярному выражению.
    
    По умолчанию включает re.MULTILINE, чтобы ^ и $ работали
    на каждой строке, а не только в начале/конце всего текста.
    
    Args:
        filepath: путь к файлу
        pattern: регулярное выражение
        replacement: строка замены (может содержать \\1, \\2 и т.д.)
        count: количество замен (0 = все)
        dry_run: только показать изменения
        flags: флаги re (по умолчанию re.MULTILINE)
    """
    lines, error = _read_file_lines(filepath)
    if error:
        return PatchResult(
            path=filepath, applied=False, operation='regex',
            changes=0, preview='', error=error
        )
    
    content = ''.join(lines)
    try:
        compiled = re.compile(pattern, flags)
    except re.error as e:
        return PatchResult(
            path=filepath, applied=False, operation='regex',
            changes=0, preview='',
            error=f"Ошибка в регулярном выражении: {e}"
        )
    
    if not compiled.search(content):
        return PatchResult(
            path=filepath, applied=False, operation='regex',
            changes=0, preview='',
            error=f"Нет совпадений для: {pattern}"
        )
    
    if count == 0:
        new_content, actual_changes = compiled.subn(replacement, content)
    else:
        new_content, actual_changes = compiled.subn(replacement, content, count=count)
    
    if dry_run:
        preview = _make_preview(content.splitlines(True),
                                new_content.splitlines(True))
        return PatchResult(
            path=filepath, applied=True, operation='regex',
            changes=actual_changes, preview=preview
        )
    
    new_lines = new_content.splitlines(True)
    if new_content.endswith('\n') and (not new_lines or not new_lines[-1].endswith('\n')):
        new_lines[-1] = new_lines[-1] + '\n'
    
    err = _write_file_lines(filepath, new_lines)
    if err:
        return PatchResult(
            path=filepath, applied=False, operation='regex',
            changes=0, preview='', error=err
        )
    
    return PatchResult(
        path=filepath, applied=True, operation='regex',
        changes=actual_changes,
        preview=f"Заменено {actual_changes} вхождений по шаблону {pattern}"
    )


def insert_after_line(filepath: str, target: str, text: str,
                      dry_run: bool = False) -> PatchResult:
    """
    Вставляет текст после строки, содержащей target.
    
    Args:
        filepath: путь к файлу
        target: текст для поиска строки
        text: вставляемый текст (будет добавлен как новая строка)
        dry_run: только показать изменения
    """
    lines, error = _read_file_lines(filepath)
    if error:
        return PatchResult(
            path=filepath, applied=False, operation='insert_after',
            changes=0, preview='', error=error
        )
    
    found_idx = None
    for i, line in enumerate(lines):
        if target in line:
            found_idx = i
            break
    
    if found_idx is None:
        return PatchResult(
            path=filepath, applied=False, operation='insert_after',
            changes=0, preview='',
            error=f"Строка с '{target}' не найдена"
        )
    
    # Добавляем отступ как у целевой строки
    indent = len(lines[found_idx]) - len(lines[found_idx].lstrip())
    indented_text = ' ' * indent + text
    if not indented_text.endswith('\n'):
        indented_text += '\n'
    
    new_lines = lines[:found_idx + 1] + [indented_text] + lines[found_idx + 1:]
    
    if dry_run:
        preview = _make_preview(lines, new_lines)
        return PatchResult(
            path=filepath, applied=True, operation='insert_after',
            changes=1, preview=preview
        )
    
    err = _write_file_lines(filepath, new_lines)
    if err:
        return PatchResult(
            path=filepath, applied=False, operation='insert_after',
            changes=0, preview='', error=err
        )
    
    return PatchResult(
        path=filepath, applied=True, operation='insert_after',
        changes=1,
        preview=f"Вставлено после строки {found_idx + 1}: '{target}'"
    )


def insert_before_line(filepath: str, target: str, text: str,
                       dry_run: bool = False) -> PatchResult:
    """
    Вставляет текст перед строкой, содержащей target.
    """
    lines, error = _read_file_lines(filepath)
    if error:
        return PatchResult(
            path=filepath, applied=False, operation='insert_before',
            changes=0, preview='', error=error
        )
    
    found_idx = None
    for i, line in enumerate(lines):
        if target in line:
            found_idx = i
            break
    
    if found_idx is None:
        return PatchResult(
            path=filepath, applied=False, operation='insert_before',
            changes=0, preview='',
            error=f"Строка с '{target}' не найдена"
        )
    
    indent = len(lines[found_idx]) - len(lines[found_idx].lstrip())
    indented_text = ' ' * indent + text
    if not indented_text.endswith('\n'):
        indented_text += '\n'
    
    new_lines = lines[:found_idx] + [indented_text] + lines[found_idx:]
    
    if dry_run:
        preview = _make_preview(lines, new_lines)
        return PatchResult(
            path=filepath, applied=True, operation='insert_before',
            changes=1, preview=preview
        )
    
    err = _write_file_lines(filepath, new_lines)
    if err:
        return PatchResult(
            path=filepath, applied=False, operation='insert_before',
            changes=0, preview='', error=err
        )
    
    return PatchResult(
        path=filepath, applied=True, operation='insert_before',
        changes=1,
        preview=f"Вставлено перед строкой {found_idx + 1}: '{target}'"
    )


def delete_lines(filepath: str, target: str,
                 dry_run: bool = False) -> PatchResult:
    """
    Удаляет строки, содержащие target.
    
    Args:
        filepath: путь к файлу
        target: текст для поиска удаляемых строк
        dry_run: только показать изменения
    """
    lines, error = _read_file_lines(filepath)
    if error:
        return PatchResult(
            path=filepath, applied=False, operation='delete',
            changes=0, preview='', error=error
        )
    
    new_lines = [l for l in lines if target not in l]
    removed = len(lines) - len(new_lines)
    
    if removed == 0:
        return PatchResult(
            path=filepath, applied=False, operation='delete',
            changes=0, preview='',
            error=f"Строки с '{target}' не найдены"
        )
    
    if dry_run:
        preview = _make_preview(lines, new_lines)
        return PatchResult(
            path=filepath, applied=True, operation='delete',
            changes=removed, preview=preview
        )
    
    err = _write_file_lines(filepath, new_lines)
    if err:
        return PatchResult(
            path=filepath, applied=False, operation='delete',
            changes=0, preview='', error=err
        )
    
    return PatchResult(
        path=filepath, applied=True, operation='delete',
        changes=removed,
        preview=f"Удалено {removed} строк, содержащих '{target}'"
    )


def delete_line_range(filepath: str, start: int, end: int,
                      dry_run: bool = False) -> PatchResult:
    """
    Удаляет диапазон строк (1-based inclusive).
    
    Args:
        filepath: путь к файлу
        start: первая строка для удаления (1-based)
        end: последняя строка для удаления (1-based, включительно)
        dry_run: только показать изменения
    """
    lines, error = _read_file_lines(filepath)
    if error:
        return PatchResult(
            path=filepath, applied=False, operation='delete_range',
            changes=0, preview='', error=error
        )
    
    total = len(lines)
    s = max(0, start - 1)
    e = min(total, end)
    
    if s >= total or s >= e:
        return PatchResult(
            path=filepath, applied=False, operation='delete_range',
            changes=0, preview='',
            error=f"Диапазон {start}-{end} выходит за пределы файла ({total} строк)"
        )
    
    removed_lines = lines[s:e]
    new_lines = lines[:s] + lines[e:]
    
    if dry_run:
        preview = _make_preview(lines, new_lines)
        return PatchResult(
            path=filepath, applied=True, operation='delete_range',
            changes=len(removed_lines), preview=preview
        )
    
    err = _write_file_lines(filepath, new_lines)
    if err:
        return PatchResult(
            path=filepath, applied=False, operation='delete_range',
            changes=0, preview='', error=err
        )
    
    return PatchResult(
        path=filepath, applied=True, operation='delete_range',
        changes=len(removed_lines),
        preview=f"Удалены строки {start}-{end} ({len(removed_lines)} строк)"
    )




def replace_section(filepath: str, section_name: str, new_content: str,
                    dry_run: bool = False) -> PatchResult:
    """
    Заменяет содержимое секции markdown (## SectionName).
    
    Args:
        filepath: путь к markdown-файлу
        section_name: имя секции (без ##)
        new_content: новое содержимое секции (без заголовка)
        dry_run: только показать изменения
    """
    lines, error = _read_file_lines(filepath)
    if error:
        return PatchResult(
            path=filepath, applied=False, operation='section',
            changes=0, preview='', error=error
        )
    
    target = f'## {section_name}'
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip() == target or line.strip().startswith(target + ' '):
            start_idx = i
            break
    
    if start_idx is None:
        return PatchResult(
            path=filepath, applied=False, operation='section',
            changes=0, preview='',
            error=f"Секция '{section_name}' не найдена"
        )
    
    # Ищем конец секции
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith('## '):
            end_idx = i
            break
    
    # Формируем новое содержимое
    section_lines = [f'## {section_name}\n']
    if not new_content.endswith('\n'):
        new_content += '\n'
    section_lines.append(new_content)
    
    new_lines = lines[:start_idx] + section_lines + lines[end_idx:]
    
    if dry_run:
        preview = _make_preview(lines, new_lines)
        return PatchResult(
            path=filepath, applied=True, operation='section',
            changes=1, preview=preview
        )
    
    err = _write_file_lines(filepath, new_lines)
    if err:
        return PatchResult(
            path=filepath, applied=False, operation='section',
            changes=0, preview='', error=err
        )
    
    return PatchResult(
        path=filepath, applied=True, operation='section',
        changes=1,
        preview=f"Заменена секция '{section_name}'"
    )


def append_text(filepath: str, text: str, dry_run: bool = False) -> PatchResult:
    """
    Добавляет текст в конец файла.
    
    Args:
        filepath: путь к файлу
        text: добавляемый текст
        dry_run: только показать изменения
    """
    path = Path(filepath)
    if not path.exists():
        return PatchResult(
            path=filepath, applied=False, operation='append',
            changes=0, preview='', error=f"Файл не найден: {filepath}"
        )
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            existing = f.read()
    except Exception as e:
        return PatchResult(
            path=filepath, applied=False, operation='append',
            changes=0, preview='', error=str(e)
        )
    
    # Добавляем перенос строки если файл не пустой и не заканчивается на \n
    if existing and not existing.endswith('\n'):
        text = '\n' + text
    
    if not text.endswith('\n'):
        text += '\n'
    
    if dry_run:
        preview = f"+ {text.rstrip()}"
        return PatchResult(
            path=filepath, applied=True, operation='append',
            changes=1, preview=preview
        )
    
    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(text)
        return PatchResult(
            path=filepath, applied=True, operation='append',
            changes=1, preview=f"Добавлено {len(text.splitlines())} строк"
        )
    except Exception as e:
        return PatchResult(
            path=filepath, applied=False, operation='append',
            changes=0, preview='', error=str(e)
        )


def print_usage():
    """Выводит справку."""
    print("Использование: python apply_patch.py <путь> <операция> [параметры]")
    print()
    print("Операции:")
    print("  --replace <старый> <новый>     — замена текста (первое вхождение)")
    print("  --replace-all <старый> <новый> — замена текста (все вхождения)")
    print("  --regex <шаблон> <замена>      — замена по регулярному выражению")
    print("  --insert-after <текст> <строка> — вставка после строки")
    print("  --insert-before <текст> <строка> — вставка перед строкой")
    print("  --delete <текст>               — удаление строк, содержащих текст")
    print("  --delete-range <start> <end>   — удаление диапазона строк (1-based)")
    print("  --section <имя> <содержимое>   — замена секции markdown")
    print("  --append <текст>               — добавление текста в конец файла")
    print()
    print("Общие опции:")
    print("  --dry-run  — показать изменения без записи")
    print("  --help     — эта справка")
    print()
    print("Примеры:")
    print("  python apply_patch.py file.py --replace 'old_func' 'new_func'")
    print("  python apply_patch.py file.py --regex 'def (\\w+)' 'def renamed_\\1'")
    print("  python apply_patch.py file.py --insert-after 'import os' 'import sys'")
    print("  python apply_patch.py file.py --delete 'TODO'")
    print("  python apply_patch.py file.py --section 'Контекст' 'Новый текст'")
    print("  python apply_patch.py file.py --replace 'foo' 'bar' --dry-run")


def main():
    if '--help' in sys.argv or '-h' in sys.argv or len(sys.argv) < 3:
        print_usage()
        sys.exit(0 if '--help' in sys.argv or '-h' in sys.argv else 1)
    
    filepath = sys.argv[1]
    dry_run = '--dry-run' in sys.argv
    
    # Убираем --dry-run из аргументов для упрощения парсинга
    args = [a for a in sys.argv[2:] if a != '--dry-run']
    
    if not args:
        print("Ошибка: не указана операция")
        print_usage()
        sys.exit(1)
    
    operation = args[0]
    
    if operation == '--replace':
        if len(args) < 3:
            print("Ошибка: --replace требует <старый> <новый>")
            sys.exit(1)
        result = replace_text(filepath, args[1], args[2], count=1, dry_run=dry_run)
    
    elif operation == '--replace-all':
        if len(args) < 3:
            print("Ошибка: --replace-all требует <старый> <новый>")
            sys.exit(1)
        result = replace_text(filepath, args[1], args[2], count=0, dry_run=dry_run)
    
    elif operation == '--regex':
        if len(args) < 3:
            print("Ошибка: --regex требует <шаблон> <замена>")
            sys.exit(1)
        result = replace_regex(filepath, args[1], args[2], dry_run=dry_run)
    
    elif operation == '--insert-after':
        if len(args) < 3:
            print("Ошибка: --insert-after требует <текст> <строка>")
            sys.exit(1)
        result = insert_after_line(filepath, args[2], args[1], dry_run=dry_run)
    
    elif operation == '--insert-before':
        if len(args) < 3:
            print("Ошибка: --insert-before требует <текст> <строка>")
            sys.exit(1)
        result = insert_before_line(filepath, args[2], args[1], dry_run=dry_run)
    
    elif operation == '--delete':
        if len(args) < 2:
            print("Ошибка: --delete требует <текст>")
            sys.exit(1)
        result = delete_lines(filepath, args[1], dry_run=dry_run)
    
    elif operation == '--delete-range':
        if len(args) < 3:
            print("Ок, --delete-range требует <start> <end>")
            sys.exit(1)
        try:
            start, end = int(args[1]), int(args[2])
        except ValueError:
            print("Ошибка: start и end должны быть числами")
            sys.exit(1)
        result = delete_line_range(filepath, start, end, dry_run=dry_run)
    
    elif operation == '--section':
        if len(args) < 3:
            print("Ошибка: --section требует <имя> <содержимое>")
            sys.exit(1)
        result = replace_section(filepath, args[1], args[2], dry_run=dry_run)
    
    elif operation == '--append':
        if len(args) < 2:
            print("Ошибка: --append требует <текст>")
            sys.exit(1)
        result = append_text(filepath, args[1], dry_run=dry_run)
    
    else:
        print(f"Ошибка: неизвестная операция '{operation}'")
        print_usage()
        sys.exit(1)
    
    # Вывод результата
    if result.error:
        print(f"❌ {result.error}")
        sys.exit(1)
    
    if dry_run:
        print(f"🔍 Предпросмотр ({result.operation}):")
        print()
        print(result.preview)
    else:
        print(f"✅ {result.operation}: {result.changes} изменений")
        if result.preview:
            print(result.preview)


if __name__ == '__main__':
    main()
