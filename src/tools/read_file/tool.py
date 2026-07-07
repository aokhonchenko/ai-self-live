"""read_file agent tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import ToolError, safe_path


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file inside the session root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside the session root."},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `read_file(path)` - прочитать UTF-8 файл внутри корня сессии."


def read_file(root: Path, path: str) -> dict[str, Any]:
    target = safe_path(root, path)
    if not target.exists():
        raise ToolError(f"file does not exist: {path}")
    if not target.is_file():
        raise ToolError(f"path is not a file: {path}")
    return {"path": path, "content": target.read_text(encoding="utf-8")}


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return read_file(root, str(arguments.get("path", "")))