"""read_lines agent tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import ToolError, safe_path


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "read_lines",
            "description": "Read a 1-based line range from a UTF-8 text file inside the session root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside the session root."},
                    "start_line": {"type": "integer", "description": "First line to read, 1-based."},
                    "line_count": {"type": "integer", "description": "Number of lines to read."},
                },
                "required": ["path", "start_line", "line_count"],
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `read_lines(path, start_line, line_count)` - прочитать диапазон строк с 1-based нумерацией."


def read_lines(root: Path, path: str, start_line: int, line_count: int) -> dict[str, Any]:
    if start_line < 1:
        raise ToolError("start_line must be at least 1")
    if line_count < 1:
        raise ToolError("line_count must be at least 1")
    target = safe_path(root, path)
    if not target.exists():
        raise ToolError(f"file does not exist: {path}")
    if not target.is_file():
        raise ToolError(f"path is not a file: {path}")

    lines = target.read_text(encoding="utf-8").splitlines()
    start_index = start_line - 1
    selected = lines[start_index : start_index + line_count]
    numbered = [f"{start_line + index}: {line}" for index, line in enumerate(selected)]
    return {
        "path": path,
        "start_line": start_line,
        "end_line": start_line + len(selected) - 1 if selected else start_line - 1,
        "total_lines": len(lines),
        "content": "\n".join(numbered),
    }


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return read_lines(
        root,
        str(arguments.get("path", "")),
        int(arguments.get("start_line", 1)),
        int(arguments.get("line_count", 1)),
    )