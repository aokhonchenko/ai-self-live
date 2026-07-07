#!/usr/bin/env python3
"""
Анализатор контекста сессии.

Оценивает «здоровье» контекста агента:
- Размер текущего промпта в токенах (приблизительно)
- Свежесть секций (дата последнего обновления)
- Наличие устаревших или пустых секций
- Рекомендации по оптимизации

Создан: сессия 50 (2026-07-08)
Цель: помочь агенту и создателю оценивать качество контекста.

Использование:
    python -m src.tools.context_analyzer --root DIR
    python -m src.tools.context_analyzer --root DIR --format json
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Секции, которые анализатор проверяет по умолчанию
DEFAULT_SECTIONS = [
    ("last_session", "state/last_session.md"),
    ("current_plan", "state/current_plan.md"),
    ("external_messages", "state/external_messages.md"),
]

# Секции, которые могут существовать
OPTIONAL_SECTIONS = [
    ("questions", "state/questions"),
    ("history", "logs/history.md"),
    ("sleep", "state/sleep/last_sleep.md"),
]

# Пороги для оценки
TOKENS_WARNING = 8000    # предупреждение при > 8000 токенов
TOKENS_CRITICAL = 16000  # критично при > 16000 токенов
STALE_DAYS = 7           # секция считается устаревшей, если не обновлялась N дней


def estimate_tokens(text: str) -> int:
    """Приблизительная оценка количества токенов в тексте.

    Для русского/английского текста ~4 символа на токен — грубая оценка.
    """
    if not text:
        return 0
    return len(text) // 4


def detect_duplicates(text: str, min_lines: int = 3, min_matches: int = 2) -> list[dict[str, Any]]:
    """Обнаруживает повторяющиеся блоки строк в тексте.

    Разбивает текст на строки, ищет последовательности из min_lines и более
    одинаковых строк, которые встречаются min_matches и более раз.

    Args:
        text: входной текст.
        min_lines: минимальная длина дублирующегося блока в строках.
        min_matches: минимальное количество повторений блока.

    Returns:
        Список словарей с информацией о дубликатах:
        {'lines': [str], 'count': int, 'start': int, 'total_wasted_lines': int}
    """
    if not text:
        return []

    lines = text.splitlines()
    duplicates: list[dict[str, Any]] = []

    # Ищем повторяющиеся последовательности от min_lines до 10 строк
    for seq_len in range(min_lines, min(11, len(lines) // min_matches + 1)):
        seen: dict[tuple[str, ...], list[int]] = {}
        for i in range(len(lines) - seq_len + 1):
            key = tuple(lines[i:i + seq_len])
            if key not in seen:
                seen[key] = []
            seen[key].append(i)

        for key, positions in seen.items():
            if len(positions) >= min_matches:
                duplicates.append({
                    "lines": list(key),
                    "line_count": seq_len,
                    "count": len(positions),
                    "positions": positions,
                    "total_wasted_lines": seq_len * (len(positions) - 1),
                })

    # Убираем вложенные дубликаты: если блок A содержится в блоке B, оставляем только B
    # Сортируем по длине (самые длинные первыми)
    duplicates.sort(key=lambda d: d["line_count"], reverse=True)

    filtered: list[dict[str, Any]] = []
    for dup in duplicates:
        # Проверяем, не содержится ли этот дубликат уже в более длинном
        is_subset = False
        for kept in filtered:
            if dup["line_count"] < kept["line_count"]:
                # Проверяем, что все строки этого дубликата есть в kept
                if all(l in kept["lines"] for l in dup["lines"]):
                    is_subset = True
                    break
        if not is_subset:
            filtered.append(dup)

    return filtered


def assess_noise(text: str) -> dict[str, Any]:
    """Оценивает «шумность» текста.

    Шум — это строки, которые не несут смысловой нагрузки:
    - Пустые строки
    - Строки только из маркеров списков/заголовков (---, ===)
    - Повторяющиеся заголовки (#### и ниже)
    - Таблицы (строки с |)

    Args:
        text: входной текст.

    Returns:
        Словарь с метриками шумности.
    """
    if not text:
        return {
            "total_lines": 0,
            "noise_lines": 0,
            "noise_ratio": 0.0,
            "breakdown": {},
        }

    lines = text.splitlines()
    total = len(lines)

    empty = 0
    separators = 0
    deep_headings = 0
    table_rows = 0
    code_fence_lines = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            empty += 1
        elif stripped in ("---", "===") or re.match(r"^-{3,}$", stripped) or re.match(r"^={3,}$", stripped):
            separators += 1
        elif re.match(r"^#{5,}\\s+", line):
            deep_headings += 1
        elif stripped.startswith("|") and stripped.endswith("|"):
            table_rows += 1
        elif stripped in ("```", "```python", "```json", "```text"):
            code_fence_lines += 1

    noise = empty + separators + deep_headings + table_rows + code_fence_lines
    ratio = noise / total if total > 0 else 0.0

    return {
        "total_lines": total,
        "noise_lines": noise,
        "noise_ratio": round(ratio, 3),
        "breakdown": {
            "empty_lines": empty,
            "separators": separators,
            "deep_headings": deep_headings,
            "table_rows": table_rows,
            "code_fence_lines": code_fence_lines,
        },
    }


def suggest_compression(sections: list[dict[str, Any]], total_tokens: int) -> list[str]:
    """Генерирует рекомендации по сжатию контекста.

    Args:
        sections: список секций из analyze().
        total_tokens: общее количество токенов.

    Returns:
        Список строк-рекомендаций.
    """
    suggestions: list[str] = []

    for section in sections:
        if not section.get("exists"):
            continue

        name = section.get("name", "unknown")
        path = section.get("path", "")

        # Если секция очень большая — предлагаем сжать
        if section.get("tokens", 0) > 3000:
            suggestions.append(
                f"📦 {name} ({path}): {section['tokens']} токенов. "
                f"Рассмотрите сокращение — оставьте только последние 2-3 сессии."
            )

        # Если есть дубликаты
        if section.get("duplicate_count", 0) > 0:
            count = section["duplicate_count"]
            wasted = section.get("duplicate_wasted_lines", 0)
            suggestions.append(
                f"🔁 {name} ({path}): {count} дублирующихся блок(ов), "
                f"~{wasted} строк можно удалить."
            )

        # Если много шума
        if section.get("noise_ratio", 0.0) > 0.4:
            suggestions.append(
                f"🌫️ {name} ({path}): {section['noise_ratio']*100:.0f}% — много «шумных» строк "
                f"(пустые, разделители, таблицы). Можно сократить."
            )

    # Общая рекомендация по истории
    return suggestions


def extract_date_from_content(content: str) -> datetime | None:
    """Пытается извлечь дату из содержимого markdown-файла.

    Ищет паттерны:
    - YYYY-MM-DD
    - сессия NNNN
    - Дата: YYYY-MM-DD
    - Актуально на YYYY-MM-DD
    """
    patterns = [
        r"Дата:\s*(\d{4}-\d{2}-\d{2})",
        r"Актуально на\s*(\d{4}-\d{2}-\d{2})",
        r"Сессия\s+\d{4}\s*—\s*(\d{4}-\d{2}-\d{2})",
        r"\(сессия\s+\d+\s*\(?\s*(\d{4}-\d{2}-\d{2})\)?\)",
        r"(\d{4}-\d{2}-\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y-%m-%d")
            except ValueError:
                continue
    return None


def analyze_file_section(
    root: Path, rel_path: str, section_name: str
) -> dict[str, Any]:
    """Анализировать одну секцию контекста."""
    filepath = root / rel_path

    result: dict[str, Any] = {
        "name": section_name,
        "path": rel_path,
        "exists": False,
        "lines": 0,
        "chars": 0,
        "tokens": 0,
        "date": None,
        "stale": False,
        "empty": False,
        "headings": [],
    }

    if not filepath.exists():
        return result

    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        result["error"] = str(e)
        return result

    lines = content.splitlines()
    result["exists"] = True
    result["lines"] = len(lines)
    result["chars"] = len(content)
    result["tokens"] = estimate_tokens(content)
    result["date"] = extract_date_from_content(content)
    result["empty"] = len(content.strip()) == 0

    # Извлекаем заголовки
    for line in lines:
        heading_match = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            result["headings"].append({"level": level, "text": text})

    # Анализ дубликатов
    try:
        dups = detect_duplicates(content)
        result["duplicate_count"] = len(dups)
        result["duplicate_wasted_lines"] = sum(d["total_wasted_lines"] for d in dups)
        result["duplicates"] = [
            {"lines": d["lines"], "count": d["count"]}
            for d in dups[:5]
        ]
    except Exception:
        result["duplicate_count"] = 0
        result["duplicate_wasted_lines"] = 0

    # Анализ шумности
    try:
        result["noise"] = assess_noise(content)
    except Exception:
        result["noise"] = {"total_lines": 0, "noise_lines": 0, "noise_ratio": 0.0, "breakdown": {}}

    # Проверяем устаревание
    if result["date"]:
        now = datetime.now()
        age = now - result["date"]
        result["stale"] = age > timedelta(days=STALE_DAYS)
        result["age_days"] = age.days
    else:
        result["age_days"] = None

    return result


def analyze_questions_dir(root: Path) -> dict[str, Any]:
    """Анализировать директорию вопросов."""
    questions_dir = root / "state" / "questions"
    result: dict[str, Any] = {
        "name": "questions",
        "path": "state/questions",
        "exists": questions_dir.is_dir(),
        "count": 0,
        "open": 0,
        "answered": 0,
        "files": [],
    }

    if not result["exists"]:
        return result

    for f in sorted(questions_dir.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
            status = "open" if "Статус: open" in content else "closed"
            file_info = {
                "name": f.stem,
                "status": status,
                "lines": len(content.splitlines()),
            }
            result["files"].append(file_info)
            result["count"] += 1
            if status == "open":
                result["open"] += 1
            else:
                result["answered"] += 1
        except Exception:
            pass

    return result


def analyze_history(root: Path) -> dict[str, Any]:
    """Анализировать историю сессий."""
    history_path = root / "logs" / "history.md"
    result: dict[str, Any] = {
        "name": "history",
        "path": "logs/history.md",
        "exists": history_path.exists(),
        "lines": 0,
        "sessions_count": 0,
        "tokens": 0,
    }

    if not result["exists"]:
        return result

    try:
        content = history_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        result["lines"] = len(lines)
        result["tokens"] = estimate_tokens(content)
        # Считаем количество сессий по паттерну "### Сессия"
        result["sessions_count"] = len(
            [l for l in lines if re.match(r"^###\s+Сессия\s+\d+", l)]
        )
    except Exception:
        pass

    return result


def analyze_sleep(root: Path) -> dict[str, Any]:
    """Анализировать состояние сна."""
    sleep_path = root / "state" / "sleep" / "last_sleep.md"
    result: dict[str, Any] = {
        "name": "sleep",
        "path": "state/sleep/last_sleep.md",
        "exists": sleep_path.exists(),
        "lines": 0,
        "tokens": 0,
        "date": None,
    }

    if not result["exists"]:
        return result

    try:
        content = sleep_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        result["lines"] = len(lines)
        result["tokens"] = estimate_tokens(content)
        result["date"] = extract_date_from_content(content)
    except Exception:
        pass

    return result


def generate_recommendations(
    sections: list[dict[str, Any]],
    total_tokens: int,
    open_questions: int,
) -> list[str]:
    """Сгенерировать рекомендации на основе анализа."""
    recs: list[str] = []

    # Токены
    if total_tokens > TOKENS_CRITICAL:
        recs.append(
            f"⚠️ КРИТИЧНО: контекст ~{total_tokens} токенов. "
            "Рассмотрите очистку last_session.md и current_plan.md — "
            "оставьте только актуальное."
        )
    elif total_tokens > TOKENS_WARNING:
        recs.append(
            f"⚡ Предупреждение: контекст ~{total_tokens} токенов. "
            "Можно сократить, убрав устаревшие детали из last_session.md."
        )

    # Устаревшие секции
    stale_sections = [s for s in sections if s.get("stale")]
    if stale_sections:
        names = ", ".join(s["name"] for s in stale_sections)
        recs.append(
            f"📅 Устаревшие секции ({STALE_DAYS}+ дней): {names}. "
            "Обновите или очистите."
        )

    # Пустые секции
    empty_sections = [s for s in sections if s.get("empty")]
    if empty_sections:
        names = ", ".join(s["name"] for s in empty_sections)
        recs.append(
            f"🗑️ Пустые секции: {names}. Можно удалить."
        )

    # Дубликаты
    dup_sections = [s for s in sections if s.get("duplicate_count", 0) > 0]
    for s in dup_sections:
        count = s["duplicate_count"]
        wasted = s.get("duplicate_wasted_lines", 0)
        recs.append(
            f"🔁 {s['name']}: {count} дублирующихся блок(ов), "
            f"~{wasted} строк можно удалить."
        )

    # Шум
    noisy_sections = [s for s in sections if s.get("noise", {}).get("noise_ratio", 0) > 0.4]
    for s in noisy_sections:
        ratio = s["noise"]["noise_ratio"] * 100
        recs.append(
            f"🌫️ {s['name']}: {ratio:.0f}% шумных строк "
            f"(пустые, разделители, таблицы). Можно сократить."
        )

    # Вопросы
    if open_questions > 0:
        recs.append(
            f"❓ Есть {open_questions} открытых вопрос(ов). "
            "Учтите их в следующей сессии."
        )

    # Положительная обратная связь
    if total_tokens < TOKENS_WARNING and open_questions == 0 and not stale_sections:
        recs.append(
            "✅ Контекст в хорошем состоянии: компактный, свежий, без открытых вопросов."
        )

    return recs


def analyze(root: Path | str = ".") -> dict[str, Any]:
    """Полный анализ контекста сессии.

    Args:
        root: корневая директория проекта.

    Returns:
        Словарь с результатами анализа.
    """
    root = Path(root)
    now = datetime.now()

    # Основные секции
    sections: list[dict[str, Any]] = []
    total_tokens = 0

    for name, path in DEFAULT_SECTIONS:
        info = analyze_file_section(root, path, name)
        sections.append(info)
        if info["exists"]:
            total_tokens += info["tokens"]

    # Дополнительные секции
    questions_info = analyze_questions_dir(root)
    history_info = analyze_history(root)
    sleep_info = analyze_sleep(root)

    # Рекомендации
    recommendations = generate_recommendations(
        sections, total_tokens, questions_info.get("open", 0)
    )

    # Общая оценка
    if total_tokens < TOKENS_WARNING:
        health = "good"
        health_label = "Хорошо"
    elif total_tokens < TOKENS_CRITICAL:
        health = "warning"
        health_label = "Внимание"
    else:
        health = "critical"
        health_label = "Критично"

    return {
        "timestamp": now.isoformat(),
        "health": health,
        "health_label": health_label,
        "total_tokens": total_tokens,
        "total_chars": sum(s.get("chars", 0) for s in sections if s.get("exists")),
        "total_lines": sum(s.get("lines", 0) for s in sections if s.get("exists")),
        "sections": sections,
        "questions": questions_info,
        "history": history_info,
        "sleep": sleep_info,
        "recommendations": recommendations,
    }


def format_text(report: dict[str, Any]) -> str:
    """Форматировать отчёт в читаемый текст."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  АНАЛИЗ КОНТЕКСТА СЕССИИ")
    lines.append(f"  Собрано: {report['timestamp']}")
    lines.append("=" * 60)

    # Оценка здоровья
    health_icon = {"good": "✅", "warning": "⚡", "critical": "⚠️"}
    icon = health_icon.get(report["health"], "❓")
    lines.append(f"\n  Оценка: {icon} {report['health_label']}")
    lines.append(f"  Токенов: {report['total_tokens']} | "
                 f"Символов: {report['total_chars']} | "
                 f"Строк: {report['total_lines']}")

    # Секции
    lines.append("\n  --- Секции ---")
    for s in report["sections"]:
        if not s["exists"]:
            lines.append(f"  ❌ {s['name']} ({s['path']}) — не найден")
            continue
        date_str = s.get("date", datetime.now()).strftime("%Y-%m-%d") if s.get("date") else "—"
        stale_flag = " 📅" if s.get("stale") else ""
        empty_flag = " 🗑️" if s.get("empty") else ""
        dup_flag = ""
        if s.get("duplicate_count", 0) > 0:
            dup_flag = f" 🔁{s['duplicate_count']}"
        noise_info = s.get("noise", {})
        noise_flag = ""
        if noise_info.get("noise_ratio", 0) > 0.3:
            noise_flag = f" 🌫️{noise_info['noise_ratio']*100:.0f}%"
        lines.append(
            f"  ✅ {s['name']:20s} {s['tokens']:>5} ток.  "
            f"{s['lines']:>4} стр.  {date_str}{stale_flag}{empty_flag}{dup_flag}{noise_flag}"
        )

    # Вопросы
    q = report.get("questions", {})
    if q.get("exists"):
        lines.append(
            f"\n  --- Вопросы: {q['count']} всего, "
            f"{q['open']} открытых, {q['answered']} отвечено ---"
        )
        for f in q.get("files", []):
            status_icon = "🔵" if f["status"] == "open" else "🟢"
            lines.append(f"    {status_icon} {f['name']} ({f['lines']} стр.)")

    # История
    h = report.get("history", {})
    if h.get("exists"):
        lines.append(
            f"\n  --- История: {h['sessions_count']} сессий, "
            f"{h['lines']} стр., {h['tokens']} ток. ---"
        )

    # Рекомендации
    recs = report.get("recommendations", [])
    if recs:
        lines.append("\n  --- Рекомендации ---")
        for r in recs:
            lines.append(f"  {r}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def format_json(report: dict[str, Any]) -> str:
    """Форматировать отчёт в JSON."""
    class _Encoder(json.JSONEncoder):
        def default(self, o: Any) -> Any:
            if isinstance(o, datetime):
                return o.isoformat()
            return super().default(o)
    return json.dumps(report, ensure_ascii=False, indent=2, cls=_Encoder)


def main() -> None:
    """CLI-точка входа."""
    root = "."
    fmt = "text"

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--root" and i + 1 < len(sys.argv):
            root = sys.argv[i + 1]
            i += 2
        elif arg == "--json":
            fmt = "json"
            i += 1
        elif arg == "--text":
            fmt = "text"
            i += 1
        elif arg in ("--help", "-h"):
            print("Использование: python -m src.tools.context_analyzer [опции]")
            print()
            print("Опции:")
            print("  --root DIR   — корневая директория (по умолчанию .)")
            print("  --json       — вывод в JSON")
            print("  --text       — текстовый вывод (по умолчанию)")
            print("  --help       — справка")
            sys.exit(0)
        else:
            print(f"Неизвестный аргумент: {arg}")
            sys.exit(1)

    report = analyze(root)

    if fmt == "json":
        print(format_json(report))
    else:
        print(format_text(report))


if __name__ == "__main__":
    main()
