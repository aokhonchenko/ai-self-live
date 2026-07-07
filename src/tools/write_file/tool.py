"""write_file agent tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import safe_path


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a UTF-8 text file inside the session root, creating parent directories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside the session root."},
                    "content": {"type": "string", "description": "Full file content to write."},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `write_file(path, content)` - записать UTF-8 файл внутри корня сессии, создавая директории."


def write_file(root: Path, path: str, content: str) -> dict[str, Any]:
    target = safe_path(root, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": path, "bytes": len(content.encode("utf-8"))}


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return write_file(root, str(arguments.get("path", "")), str(arguments.get("content", "")))