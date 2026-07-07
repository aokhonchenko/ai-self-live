"""Agent wrapper for the legacy apply_patch tool."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.tools._runtime import ToolError, safe_path
from src.tools.apply_patch import core


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": "Apply targeted text edits to a file inside the session root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["replace", "regex", "insert_after", "insert_before", "delete", "delete_range", "replace_section", "append"]},
                    "path": {"type": "string"},
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                    "pattern": {"type": "string"},
                    "replacement": {"type": "string"},
                    "target": {"type": "string"},
                    "text": {"type": "string"},
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "section_name": {"type": "string"},
                    "count": {"type": "integer"},
                    "dry_run": {"type": "boolean"},
                },
                "required": ["operation", "path"],
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `apply_patch(operation, path, ...)` - точечно править файл: replace, regex, insert_after/before, delete, delete_range, replace_section."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    operation = str(arguments.get("operation", ""))
    path = str(safe_path(root, str(arguments.get("path", ""))))
    dry_run = bool(arguments.get("dry_run", False))
    if operation == "replace":
        result = core.replace_text(path, str(arguments.get("old", "")), str(arguments.get("new", "")), int(arguments.get("count", 1)), dry_run)
    elif operation == "regex":
        result = core.replace_regex(path, str(arguments.get("pattern", "")), str(arguments.get("replacement", "")), int(arguments.get("count", 0)), dry_run)
    elif operation == "insert_after":
        result = core.insert_after_line(path, str(arguments.get("target", "")), str(arguments.get("text", "")), dry_run)
    elif operation == "insert_before":
        result = core.insert_before_line(path, str(arguments.get("target", "")), str(arguments.get("text", "")), dry_run)
    elif operation == "delete":
        result = core.delete_lines(path, str(arguments.get("target", "")), dry_run)
    elif operation == "delete_range":
        result = core.delete_line_range(path, int(arguments.get("start", 1)), int(arguments.get("end", 1)), dry_run)
    elif operation == "replace_section":
        result = core.replace_section(path, str(arguments.get("section_name", "")), str(arguments.get("new", "")), dry_run)
    elif operation == "append":
        result = core.append_text(path, str(arguments.get("text", "")), dry_run)
    else:
        raise ToolError(f"unknown apply_patch operation: {operation}")
    return asdict(result)