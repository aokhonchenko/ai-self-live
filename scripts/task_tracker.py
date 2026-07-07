"""Модуль трекера задач для автономного агента.

Позволяет создавать, обновлять, закрывать и просматривать задачи
в формате markdown-файлов в директории state/tasks/.

Каждая задача — отдельный markdown-файл с метаданными в YAML-подобном
заголовке и телом задачи.

Пример файла задачи:

    # Задача: короткое описание

    Статус: open
    Приоритет: medium
    Создана: 2026-07-08
    Обновлено: 2026-07-08

    ## Описание

    Текст задачи.

    ## Решение

    _Заполняется при выполнении._
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class TaskError(RuntimeError):
    """Ошибка трекера задач."""


# Регулярное выражение для парсинга метаданных из заголовка файла
META_PATTERN = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)

# Допустимые статусы
VALID_STATUSES = {"open", "in_progress", "closed", "archived"}

# Допустимые приоритеты
VALID_PRIORITIES = {"low", "medium", "high", "critical"}


def tasks_dir(root: Path) -> Path:
    """Возвращает путь к директории задач."""
    return Path(root) / "state" / "tasks"


def today_str() -> str:
    """Возвращает текущую дату в формате YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def parse_meta(content: str) -> dict[str, str]:
    """Парсит метаданные из начала файла задачи.

    Метаданные находятся в начале файла в формате:
        Ключ: значение

    Возвращает словарь {ключ: значение}.
    """
    meta: dict[str, str] = {}
    for match in META_PATTERN.finditer(content):
        key = match.group(1).strip().lower()
        value = match.group(2).strip()
        meta[key] = value
    return meta


def task_title(content: str) -> str:
    """Извлекает заголовок задачи из первого маркдаун-заголовка.
    
    Убирает префикс 'Задача: ' если он есть.
    """
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            text = stripped[2:].strip()
            # Убираем префикс "Задача: " если есть
            for prefix in ("Задача: ", "Task: "):
                if text.startswith(prefix):
                    text = text[len(prefix):]
            return text
    return ""


def task_status(content: str) -> str:
    """Извлекает статус задачи из метаданных."""
    meta = parse_meta(content)
    return meta.get("статус", meta.get("status", "open"))


def task_priority(content: str) -> str:
    """Извлекает приоритет задачи из метаданных."""
    meta = parse_meta(content)
    return meta.get("приоритет", meta.get("priority", "medium"))


def task_created(content: str) -> str:
    """Извлекает дату создания задачи."""
    meta = parse_meta(content)
    return meta.get("создана", meta.get("created", ""))


def task_updated(content: str) -> str:
    """Извлекает дату последнего обновления задачи."""
    meta = parse_meta(content)
    return meta.get("обновлено", meta.get("updated", ""))


def task_body(content: str) -> str:
    """Извлекает тело задачи (всё после блока метаданных).
    
    Тело начинается после первого маркдаун-заголовка второго уровня (##).
    Если такого нет — после блока метаданных (строки вида "Ключ: значение").
    """
    lines = content.splitlines()
    
    # Сначала ищем первый ## заголовок
    for i, line in enumerate(lines):
        if line.strip().startswith("## "):
            # Тело — всё после этого заголовка
            body_lines = lines[i + 1:]
            # Пропускаем пустые строки в начале
            while body_lines and body_lines[0].strip() == "":
                body_lines = body_lines[1:]
            return "\n".join(body_lines).strip()
    
    # Если нет ## заголовков, пропускаем метаданные
    # Метаданные — строки вида "Ключ: значение" в начале файла
    # Пропускаем первую строку (заголовок # ...)
    body_lines: list[str] = []
    past_meta = False
    for idx, line in enumerate(lines):
        if idx == 0:
            # Пропускаем первую строку (заголовок)
            continue
        stripped = line.strip()
        if not past_meta:
            # Проверяем, является ли строка метаданными
            if META_PATTERN.match(stripped):
                continue
            # Пустая строка — возможный разделитель
            if stripped == "":
                past_meta = True
                continue
            # Если не метаданные и не пустая — это тело
            past_meta = True
        # Проверяем, является ли строка метаданными (даже после пустой строки)
        if META_PATTERN.match(stripped):
            continue
        body_lines.append(line)
    
    # Пропускаем пустые строки в начале тела
    while body_lines and body_lines[0].strip() == "":
        body_lines = body_lines[1:]
    return "\n".join(body_lines).strip()


def create_task(
    root: Path,
    title: str,
    description: str = "",
    priority: str = "medium",
    status: str = "open",
) -> Path:
    """Создаёт новую задачу в директории state/tasks/.

    Возвращает путь к созданному файлу задачи.
    Имя файла генерируется из заголовка (slug).
    """
    if status not in VALID_STATUSES:
        raise TaskError(f"Недопустимый статус: {status}. Допустимые: {VALID_STATUSES}")
    if priority not in VALID_PRIORITIES:
        raise TaskError(f"Недопустимый приоритет: {priority}. Допустимые: {VALID_PRIORITIES}")

    task_dir = tasks_dir(root)
    task_dir.mkdir(parents=True, exist_ok=True)

    # Генерируем slug из заголовка
    slug = _title_to_slug(title)
    task_file = task_dir / f"{slug}.md"

    if task_file.exists():
        raise TaskError(f"Задача уже существует: {task_file.name}")

    now = today_str()
    content = f"""# Задача: {title}

Статус: {status}
Приоритет: {priority}
Создана: {now}
Обновлено: {now}

## Описание

{description}
"""
    task_file.write_text(content, encoding="utf-8")
    return task_file


def update_task(
    root: Path,
    title: str,
    *,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    note: Optional[str] = None,
) -> Path:
    """Обновляет существующую задачу.

    Можно обновить статус, приоритет или добавить заметку.
    Возвращает путь к файлу задачи.
    """
    task_dir = tasks_dir(root)
    slug = _title_to_slug(title)
    task_file = task_dir / f"{slug}.md"

    if not task_file.exists():
        raise TaskError(f"Задача не найдена: {title}")

    content = task_file.read_text(encoding="utf-8")
    meta = parse_meta(content)

    if status is not None:
        if status not in VALID_STATUSES:
            raise TaskError(f"Недопустимый статус: {status}")
        if "статус" in meta:
            content = content.replace(
                f"Статус: {meta['статус']}", f"Статус: {status}"
            )
        elif "status" in meta:
            content = content.replace(
                f"Status: {meta['status']}", f"Status: {status}"
            )
        else:
            # Добавляем статус после заголовка
            content = content.replace(
                "# Задача: ",
                "# Задача: ",
                1,
            )
            # Вставляем статус после заголовка
            idx = content.index("\n")
            content = content[:idx] + f"\nСтатус: {status}" + content[idx:]

    if priority is not None:
        if priority not in VALID_PRIORITIES:
            raise TaskError(f"Недопустимый приоритет: {priority}")
        if "приоритет" in meta:
            content = content.replace(
                f"Приоритет: {meta['приоритет']}", f"Приоритет: {priority}"
            )
        elif "priority" in meta:
            content = content.replace(
                f"Priority: {meta['priority']}", f"Priority: {priority}"
            )

    if note is not None:
        now = today_str()
        if "обновлено" in meta:
            content = content.replace(
                f"Обновлено: {meta['обновлено']}", f"Обновлено: {now}"
            )
        elif "updated" in meta:
            content = content.replace(
                f"Updated: {meta['updated']}", f"Updated: {now}"
            )
        else:
            idx = content.index("\n")
            content = content[:idx] + f"\nОбновлено: {now}" + content[idx:]

        # Добавляем заметку в тело — ищем последний ## заголовок или конец файла
        body = task_body(content)
        if body:
            # Находим позицию тела в контенте
            body_start = content.index("\n\n") + 2
            # Пропускаем метаданные
            for line in content[body_start:].split("\n"):
                if META_PATTERN.match(line.strip()):
                    body_start += len(line) + 1
                else:
                    break
            # Находим начало реального тела (после ## заголовка или после метаданных)
            body_content = content[body_start:]
            # Ищем первый ## заголовок
            for i, line in enumerate(body_content.split("\n")):
                if line.strip().startswith("## "):
                    body_start = body_start + sum(len(l) + 1 for l in body_content.split("\n")[:i])
                    break
            
            # Добавляем заметку в конец тела
            content = content.rstrip() + f"\n\n> {note}"
        else:
            # Тела нет — добавляем после метаданных
            content = content.rstrip() + f"\n\n> {note}"

    task_file.write_text(content, encoding="utf-8")
    return task_file


def close_task(root: Path, title: str, resolution: str = "") -> Path:
    """Закрывает задачу со статусом closed."""
    now = today_str()
    task_dir = tasks_dir(root)
    slug = _title_to_slug(title)
    task_file = task_dir / f"{slug}.md"

    if not task_file.exists():
        raise TaskError(f"Задача не найдена: {title}")

    content = task_file.read_text(encoding="utf-8")
    meta = parse_meta(content)

    # Обновляем статус
    if "статус" in meta:
        content = content.replace(f"Статус: {meta['статус']}", "Статус: closed")
    elif "status" in meta:
        content = content.replace(f"Status: {meta['status']}", "Status: closed")

    # Обновляем дату
    if "обновлено" in meta:
        content = content.replace(f"Обновлено: {meta['обновлено']}", f"Обновлено: {now}")
    elif "updated" in meta:
        content = content.replace(f"Updated: {meta['updated']}", f"Updated: {now}")

    # Добавляем решение
    if resolution:
        body = task_body(content)
        if body:
            content = content.rstrip() + f"\n\n## Решение\n\n{resolution}"
        else:
            content = content.rstrip() + f"\n\n## Решение\n\n{resolution}"

    task_file.write_text(content, encoding="utf-8")
    return task_file


def list_tasks(
    root: Path,
    status: Optional[str] = None,
    priority: Optional[str] = None,
) -> list[dict]:
    """Возвращает список задач, отфильтрованных по статусу и/или приоритету.

    Каждая задача — словарь с полями:
    - title: заголовок
    - status: статус
    - priority: приоритет
    - created: дата создания
    - updated: дата обновления
    - path: путь к файлу
    """
    task_dir = tasks_dir(root)
    if not task_dir.exists():
        return []

    tasks: list[dict] = []
    for task_file in sorted(task_dir.glob("*.md")):
        content = task_file.read_text(encoding="utf-8")
        meta = parse_meta(content)
        title = task_title(content)

        task_status_val = meta.get("статус", meta.get("status", "open"))
        task_priority_val = meta.get("приоритет", meta.get("priority", "medium"))

        if status is not None and task_status_val != status:
            continue
        if priority is not None and task_priority_val != priority:
            continue

        tasks.append({
            "title": title,
            "status": task_status_val,
            "priority": task_priority_val,
            "created": meta.get("создана", meta.get("created", "")),
            "updated": meta.get("обновлено", meta.get("updated", "")),
            "path": str(task_file),
        })

    return tasks


def read_task(root: Path, title: str) -> dict:
    """Читает одну задачу по заголовку.

    Возвращает словарь с полями:
    - title, status, priority, created, updated, body, path
    """
    task_dir = tasks_dir(root)
    slug = _title_to_slug(title)
    task_file = task_dir / f"{slug}.md"

    if not task_file.exists():
        raise TaskError(f"Задача не найдена: {title}")

    content = task_file.read_text(encoding="utf-8")
    meta = parse_meta(content)

    return {
        "title": task_title(content),
        "status": meta.get("статус", meta.get("status", "open")),
        "priority": meta.get("приоритет", meta.get("priority", "medium")),
        "created": meta.get("создана", meta.get("created", "")),
        "updated": meta.get("обновлено", meta.get("updated", "")),
        "body": task_body(content),
        "path": str(task_file),
    }


def delete_task(root: Path, title: str) -> None:
    """Удаляет задачу по заголовку."""
    task_dir = tasks_dir(root)
    slug = _title_to_slug(title)
    task_file = task_dir / f"{slug}.md"

    if not task_file.exists():
        raise TaskError(f"Задача не найдена: {title}")

    task_file.unlink()


def _title_to_slug(title: str) -> str:
    """Конвертирует заголовок в slug для имени файла."""
    slug = title.lower()
    # Сначала заменяем пробелы на дефисы
    slug = re.sub(r"\s+", "-", slug)
    # Удаляем все символы, кроме букв, цифр и дефисов
    slug = re.sub(r"[^a-zа-яё0-9\-]", "", slug, flags=re.IGNORECASE)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    if not slug:
        slug = "untitled"
    return slug


def main() -> None:
    """CLI-точка входа для трекера задач."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Трекер задач для автономного агента")
    subparsers = parser.add_subparsers(dest="command")

    # create
    create_parser = subparsers.add_parser("create", help="Создать задачу")
    create_parser.add_argument("title", help="Заголовок задачи")
    create_parser.add_argument("--description", "-d", default="", help="Описание")
    create_parser.add_argument(
        "--priority", "-p", default="medium", choices=list(VALID_PRIORITIES)
    )
    create_parser.add_argument(
        "--status", "-s", default="open", choices=list(VALID_STATUSES)
    )

    # list
    list_parser = subparsers.add_parser("list", help="Список задач")
    list_parser.add_argument("--status", default=None, help="Фильтр по статусу")
    list_parser.add_argument("--priority", default=None, help="Фильтр по приоритету")

    # read
    read_parser = subparsers.add_parser("read", help="Прочитать задачу")
    read_parser.add_argument("title", help="Заголовок задачи")

    # update
    update_parser = subparsers.add_parser("update", help="Обновить задачу")
    update_parser.add_argument("title", help="Заголовок задачи")
    update_parser.add_argument("--status", default=None, choices=list(VALID_STATUSES))
    update_parser.add_argument("--priority", default=None, choices=list(VALID_PRIORITIES))
    update_parser.add_argument("--note", "-n", default=None, help="Заметка")

    # close
    close_parser = subparsers.add_parser("close", help="Закрыть задачу")
    close_parser.add_argument("title", help="Заголовок задачи")
    close_parser.add_argument("--resolution", "-r", default="", help="Решение")

    # delete
    delete_parser = subparsers.add_parser("delete", help="Удалить задачу")
    delete_parser.add_argument("title", help="Заголовок задачи")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    root = Path.cwd()

    if args.command == "create":
        path = create_task(
            root,
            args.title,
            description=args.description,
            priority=args.priority,
            status=args.status,
        )
        print(f"Создана задача: {path}")

    elif args.command == "list":
        tasks = list_tasks(root, status=args.status, priority=args.priority)
        if not tasks:
            print("Задач не найдено.")
            return
        for t in tasks:
            print(f"[{t['status']}] [{t['priority']}] {t['title']} (создана: {t['created']})")

    elif args.command == "read":
        try:
            task = read_task(root, args.title)
            print(f"Заголовок: {task['title']}")
            print(f"Статус: {task['status']}")
            print(f"Приоритет: {task['priority']}")
            print(f"Создана: {task['created']}")
            print(f"Обновлено: {task['updated']}")
            print(f"\nТело:\n{task['body']}")
        except TaskError as e:
            print(f"Ошибка: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "update":
        try:
            path = update_task(
                root,
                args.title,
                status=args.status,
                priority=args.priority,
                note=args.note,
            )
            print(f"Обновлена задача: {path}")
        except TaskError as e:
            print(f"Ошибка: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "close":
        try:
            path = close_task(root, args.title, resolution=args.resolution)
            print(f"Задача закрыта: {path}")
        except TaskError as e:
            print(f"Ошибка: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "delete":
        try:
            delete_task(root, args.title)
            print(f"Задача удалена: {args.title}")
        except TaskError as e:
            print(f"Ошибка: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
