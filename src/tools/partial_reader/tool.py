"""Agent wrapper for the legacy partial_reader tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import ToolError, safe_path
from src.tools.partial_reader import core


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "partial_reader",
            "description": "Read compact parts of a text file: head, headers, markdown section, summary, or file info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["head", "headers", "section", "summary", "info"]},
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
    return "- `partial_reader(mode, path, ...)` - компактно читать head/headers/section/summary/info."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    mode = str(arguments.get("mode", ""))
    requested_path = str(arguments.get("path", ""))
    resolved_path = safe_path(root, requested_path)
    path = str(resolved_path)
    if resolved_path.is_dir() and mode != "info":
        raise ToolError(f"path is a directory; use mode='info' first: {requested_path}")
    try:
        if mode == "head":
            content = core.read_head(path, int(arguments.get("n", 30)))
        elif mode == "headers":
            content = core.read_headers(path)
        elif mode == "section":
            content = core.read_section(path, str(arguments.get("section_name", "")))
        elif mode == "summary":
            content = core.read_summary(path, int(arguments.get("context_lines", 2)))
        elif mode == "info":
            content = core.get_file_info(path)
        else:
            raise ToolError(f"unknown partial_reader mode: {mode}")
    except UnicodeDecodeError as exc:
        raise ToolError(f"path is not valid UTF-8 text: {requested_path}") from exc
    except OSError as exc:
        raise ToolError(f"cannot read path {requested_path}: {exc}") from exc
    return {"path": requested_path, "mode": mode, "content": content}
