"""Agent wrapper for the legacy code_analyzer tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import ToolError, safe_path
from src.tools.code_analyzer import core


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "code_analyzer",
            "description": "Analyze a Python file or directory and return a text or JSON report.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "mode": {"type": "string", "enum": ["file", "directory"]},
                    "format": {"type": "string", "enum": ["text", "json"]},
                    "verbose": {"type": "boolean"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `code_analyzer(path, mode='file|directory', format='text|json')` - анализировать Python-файл или директорию."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    target = safe_path(root, str(arguments.get("path", "")))
    mode = str(arguments.get("mode") or ("directory" if target.is_dir() else "file"))
    output_format = str(arguments.get("format") or "text")
    verbose = bool(arguments.get("verbose", False))
    if mode == "file":
        analyses = [core.analyze_file(str(target))]
    elif mode == "directory":
        analyses = core.analyze_directory(str(target))
    else:
        raise ToolError(f"unknown code_analyzer mode: {mode}")
    content = core.format_json(analyses) if output_format == "json" else core.format_report(analyses, verbose=verbose)
    return {"path": str(arguments.get("path", "")), "mode": mode, "format": output_format, "content": content}