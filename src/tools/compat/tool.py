"""Agent wrapper for compat fallback readers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import ToolError, safe_path
from src.tools.compat import core


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "compat_reader",
            "description": "Use fallback partial-read helpers from compat.py.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["head", "headers", "section", "summary"]},
                    "path": {"type": "string"},
                    "n": {"type": "integer"},
                    "section_name": {"type": "string"},
                    "context_lines": {"type": "integer"},
                },
                "required": ["mode", "path"],
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `compat_reader(mode, path, ...)` - fallback-чтение head/headers/section/summary."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    mode = str(arguments.get("mode", ""))
    path = str(safe_path(root, str(arguments.get("path", ""))))
    if mode == "head":
        content = core.read_head(path, int(arguments.get("n", 30)))
    elif mode == "headers":
        content = core.read_headers(path)
    elif mode == "section":
        content = core.read_section(path, str(arguments.get("section_name", "")))
    elif mode == "summary":
        content = core.read_summary(path, int(arguments.get("context_lines", 2)))
    else:
        raise ToolError(f"unknown compat_reader mode: {mode}")
    return {"path": str(arguments.get("path", "")), "mode": mode, "content": content}