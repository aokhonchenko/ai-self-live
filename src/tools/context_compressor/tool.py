"""Agent wrapper for the context_compressor tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import safe_path, ToolError
from src.tools.context_compressor import core


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "context_compressor",
            "description": (
                "Сжать файл памяти сессии: удалить дубликаты, старые записи сессий, "
                "шумные строки. Поддерживает dry-run для проверки без записи."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Путь к файлу для сжатия (относительно корня сессии).",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "Если True, только показать результат без записи.",
                    },
                    "keep_recent": {
                        "type": "integer",
                        "description": "Сколько последних сессий оставить (по умолчанию 5).",
                    },
                },
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `context_compressor(path, dry_run=False, keep_recent=5)` - сжать файл памяти сессии."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    """Обработать запрос на сжатие файла."""
    dry_run = bool(arguments.get("dry_run", False))
    keep_recent = int(arguments.get("keep_recent", 5))

    try:
        target_path = safe_path(root, arguments.get("path") or "state/last_session.md")
    except ToolError as exc:
        return {"ok": False, "error": str(exc)}

    if not target_path.exists():
        return {"ok": False, "error": f"Файл не найден: {target_path}"}

    try:
        text = target_path.read_text(encoding="utf-8")
        result = core.compress_last_session(text, keep_recent=keep_recent)
        output = core.format_compression_result(result)

        if not dry_run and result.compressed_lines < result.original_lines:
            target_path.write_text(result.compressed_text, encoding="utf-8")

        return {
            "ok": True,
            "path": str(target_path),
            "dry_run": dry_run,
            "content": output,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
