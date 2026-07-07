"""Agent wrapper for the context_analyzer tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import safe_cwd
from src.tools.context_analyzer import core


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "context_analyzer",
            "description": (
                "Анализировать состояние контекста сессии: оценить размер промпта в токенах, "
                "проверить свежесть секций, найти устаревшие или пустые данные, "
                "сгенерировать рекомендации по оптимизации."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Путь к корню проекта (относительно корня сессии).",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["file", "directory"],
                        "description": "Режим анализа: 'file' — анализ одного файла, 'directory' — полный анализ проекта.",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "json"],
                        "description": "Формат вывода: 'text' для чтения человеком, 'json' для программной обработки.",
                    },
                    "verbose": {
                        "type": "boolean",
                        "description": "Подробный режим: включает заголовки и детали секций.",
                    },
                },
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `context_analyzer(path, mode='file|directory', format='text|json')` - анализировать состояние контекста сессии."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    mode = str(arguments.get("mode") or "directory")
    output_format = str(arguments.get("format") or "text")
    verbose = bool(arguments.get("verbose", False))

    if mode == "file":
        # Для режима file используем safe_path (не safe_cwd)
        from src.tools._runtime import ToolError, safe_path

        try:
            target_path = safe_path(root, arguments.get("path") or ".")
        except ToolError as exc:
            return {"ok": False, "error": str(exc)}
        # Анализ одного файла
        filepath = target_path
        if not filepath.exists():
            return {"ok": False, "error": f"Файл не найден: {filepath}"}

        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception as e:
            return {"ok": False, "error": str(e)}

        from datetime import datetime

        tokens = core.estimate_tokens(content)
        date = core.extract_date_from_content(content)

        result = {
            "path": str(filepath),
            "exists": True,
            "lines": len(content.splitlines()),
            "chars": len(content),
            "tokens": tokens,
            "date": date.isoformat() if date else None,
            "stale": (
                (datetime.now() - date).days > core.STALE_DAYS if date else None
            ),
            "empty": len(content.strip()) == 0,
        }
        output = format_json_result(result) if output_format == "json" else format_text_result(result)

    else:
        # Полный анализ директории
        target_path = root
        report = core.analyze(target_path)
        if output_format == "json":
            output = core.format_json(report)
        else:
            output = core.format_text(report)

    return {"ok": True, "path": str(target_path), "mode": mode, "content": output}


def format_json_result(result: dict[str, Any]) -> str:
    """Сформатировать результат анализа файла в JSON."""
    import json
    return json.dumps(result, ensure_ascii=False, indent=2)


def format_text_result(result: dict[str, Any]) -> str:
    """Сформатировать результат анализа файла в текст."""
    lines: list[str] = []
    lines.append("=" * 50)
    lines.append(f"  Анализ: {result['path']}")
    lines.append("=" * 50)
    lines.append(f"  Строк: {result['lines']}")
    lines.append(f"  Символов: {result['chars']}")
    lines.append(f"  Токенов (~): {result['tokens']}")
    if result.get("date"):
        lines.append(f"  Дата: {result['date']}")
    if result.get("stale"):
        lines.append(f"  ⚠️ Устарел (>7 дней)")
    if result.get("empty"):
        lines.append(f"  🗑️ Пустой файл")
    lines.append("=" * 50)
    return "\n".join(lines)
