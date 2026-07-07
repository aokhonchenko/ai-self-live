"""Agent wrapper for the legacy reader tool."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.tools._runtime import ToolError, safe_path
from src.tools.reader import core


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "reader",
            "description": "Read focused slices of a file: lines, head, tail, function, class, pattern, markdown section, or file info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["lines", "head", "tail", "func", "class", "pattern", "section", "info"]},
                    "path": {"type": "string"},
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "n": {"type": "integer"},
                    "name": {"type": "string"},
                    "pattern": {"type": "string"},
                    "context": {"type": "integer"},
                },
                "required": ["mode", "path"],
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `reader(mode, path, ...)` - точечно читать файл: lines/head/tail/func/class/pattern/section/info."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    mode = str(arguments.get("mode", ""))
    path = str(safe_path(root, str(arguments.get("path", ""))))
    if mode == "lines":
        result = core.read_lines(path, int(arguments.get("start", 1)), int(arguments.get("end", 1)))
        return asdict(result)
    if mode == "head":
        return asdict(core.read_head(path, int(arguments.get("n", 30))))
    if mode == "tail":
        return asdict(core.read_tail(path, int(arguments.get("n", 30))))
    if mode == "func":
        return asdict(core.read_func(path, str(arguments.get("name", ""))))
    if mode == "class":
        return asdict(core.read_class(path, str(arguments.get("name", ""))))
    if mode == "pattern":
        return asdict(core.read_pattern(path, str(arguments.get("pattern", "")), int(arguments.get("context", 2))))
    if mode == "section":
        return asdict(core.read_section(path, str(arguments.get("name", ""))))
    if mode == "info":
        return core.read_file_info(path)
    raise ToolError(f"unknown reader mode: {mode}")