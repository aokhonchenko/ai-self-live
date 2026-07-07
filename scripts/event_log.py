"""Модуль структурированного логирования событий проекта.

Записывает события в журнал (JSONL-формат) с поддержкой поиска,
фильтрации по дате/типу и агрегации статистики.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def events_dir(root: Optional[Path] = None) -> Path:
    """Возвращает путь к директории журналов событий.

    Args:
        root: Корень проекта. По умолчанию — текущая рабочая директория.

    Returns:
        Путь к директории `logs/events/`.
    """
    base = root or Path.cwd()
    return base / "logs" / "events"


def event_path(events_root: Optional[Path] = None) -> Path:
    """Возвращает путь к файлу журнала событий.

    Файл создаётся в директории `logs/events/events.jsonl`.

    Args:
        events_root: Директория журналов. По умолчанию — events_dir().

    Returns:
        Путь к файлу `events.jsonl`.
    """
    base = events_root or events_dir()
    return base / "events.jsonl"


def write_event(
    event_type: str,
    data: Optional[Dict[str, Any]] = None,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Записывает одно событие в журнал.

    Каждое событие — JSON-объект с полями:
    - `ts`: ISO-метка времени (UTC)
    - `type`: тип события (например, "session_start", "task_created")
    - `data`: произвольные данные события

    Args:
        event_type: Строковый идентификатор типа события.
        data: Словарь с данными события. Может быть пустым.
        root: Корень проекта для определения пути к журналу.

    Returns:
        Записанный словарь события.
    """
    now = datetime.now(timezone.utc)
    event: Dict[str, Any] = {
        "ts": now.isoformat(),
        "type": event_type,
        "data": data or {},
    }
    path = event_path(events_dir(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read_events(
    event_type: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Читает события из журнала с фильтрацией.

    Args:
        event_type: Если задан, возвращает только события этого типа.
        since: ISO-дата (включительно). Возвращает события >= этой даты.
        until: ISO-дата (включительно). Возвращает события <= этой даты.
        root: Корень проекта для определения пути к журналу.

    Returns:
        Список отфильтрованных событий.
    """
    path = event_path(events_dir(root))
    if not path.exists():
        return []

    events: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event_type and event.get("type") != event_type:
                continue

            if since:
                if event.get("ts", "") < since:
                    continue
            if until:
                if event.get("ts", "") > until:
                    continue

            events.append(event)

    return events


def event_count(
    event_type: Optional[str] = None,
    root: Optional[Path] = None,
) -> int:
    """Возвращает количество событий в журнале.

    Args:
        event_type: Если задан, считает только события этого типа.
        root: Корень проекта.

    Returns:
        Количество событий.
    """
    return len(read_events(event_type=event_type, root=root))


def event_summary(root: Optional[Path] = None) -> Dict[str, int]:
    """Возвращает сводку по типам событий.

    Args:
        root: Корень проекта.

    Returns:
        Словарь {тип_события: количество}.
    """
    events = read_events(root=root)
    summary: Dict[str, int] = {}
    for event in events:
        etype = event.get("type", "unknown")
        summary[etype] = summary.get(etype, 0) + 1
    return summary


def clear_events(root: Optional[Path] = None) -> int:
    """Удаляет все события из журнала.

    Args:
        root: Корень проекта.

    Returns:
        Количество удалённых событий.
    """
    path = event_path(events_dir(root))
    if not path.exists():
        return 0
    events = read_events(root=root)
    count = len(events)
    path.unlink(missing_ok=True)
    return count


def last_event(root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Возвращает последнее событие из журнала.

    Args:
        root: Корень проекта.

    Returns:
        Словарь последнего события или None, если журнал пуст.
    """
    events = read_events(root=root)
    if not events:
        return None
    return events[-1]


def events_since_session(
    session_id: str,
    root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Возвращает события, записанные после указанной сессии.

    Ищет событие типа 'session_start' с matching session_id и
    возвращает все события, записанные после него.

    Args:
        session_id: Идентификатор сессии (например, 'session-0040').
        root: Корень проекта.

    Returns:
        Список событий, записанных после указанной сессии.
    """
    events = read_events(root=root)
    if not events:
        return []

    # Находим точку начала — событие session_start с данным session_id
    cutoff_ts: Optional[str] = None
    for event in events:
        if (
            event.get("type") == "session_start"
            and event.get("data", {}).get("session_id") == session_id
        ):
            cutoff_ts = event.get("ts")
            break

    if cutoff_ts is None:
        return []

    # Возвращаем события после cutoff_ts
    return [e for e in events if e.get("ts", "") > cutoff_ts]
