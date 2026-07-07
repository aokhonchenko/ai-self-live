"""Agent wrapper for the legacy prompt_builder tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import safe_cwd
from src.tools.prompt_builder import core


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "prompt_builder",
            "description": "Build compact project context using optimized partial reads.",
            "parameters": {
                "type": "object",
                "properties": {
                    "root": {"type": "string", "description": "Optional root directory inside the session root."},
                    "format": {"type": "string", "enum": ["compact", "json", "stats"]},
                },
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `prompt_builder(root='.', format='compact|json|stats')` - собрать компактный контекст проекта."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    target_root = safe_cwd(root, arguments.get("root"))
    builder = core.PromptBuilder(target_root)
    output_format = str(arguments.get("format") or "compact")
    if output_format == "json":
        content = builder.format_json()
    elif output_format == "stats":
        content = builder.get_total_stats()
    else:
        content = builder.format_compact()
    return {"root": str(target_root), "format": output_format, "content": content}