"""replace_text agent tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import ToolError, safe_path


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "replace_text",
            "description": "Replace an exact text fragment in a UTF-8 file without rewriting the whole file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside the session root."},
                    "old": {"type": "string", "description": "Exact text fragment to replace."},
                    "new": {"type": "string", "description": "Replacement text."},
                    "expected_replacements": {
                        "type": "integer",
                        "description": "Required number of replacements; defaults to 1.",
                    },
                },
                "required": ["path", "old", "new"],
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `replace_text(path, old, new, expected_replacements=1)` - заменить точный фрагмент без полной перезаписи файла."


def replace_text(root: Path, path: str, old: str, new: str, expected_replacements: int = 1) -> dict[str, Any]:
    if not old:
        raise ToolError("old text must be non-empty")
    if expected_replacements < 1:
        raise ToolError("expected_replacements must be at least 1")
    target = safe_path(root, path)
    if not target.exists():
        raise ToolError(f"file does not exist: {path}")
    if not target.is_file():
        raise ToolError(f"path is not a file: {path}")

    content = target.read_text(encoding="utf-8")
    replacements = content.count(old)
    if replacements != expected_replacements:
        raise ToolError(f"expected {expected_replacements} replacement(s), found {replacements}: {path}")
    updated = content.replace(old, new, expected_replacements)
    target.write_text(updated, encoding="utf-8")
    return {"path": path, "replacements": replacements, "bytes": len(updated.encode("utf-8"))}


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return replace_text(
        root,
        str(arguments.get("path", "")),
        str(arguments.get("old", "")),
        str(arguments.get("new", "")),
        int(arguments.get("expected_replacements", 1)),
    )