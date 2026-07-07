"""Agent wrapper for the legacy self_review tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import safe_path
from src.tools.self_review import core


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "self_review",
            "description": "Analyze session history and produce a self-review report.",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_path": {"type": "string"},
                    "last_session_path": {"type": "string"},
                    "format": {"type": "string", "enum": ["text", "json"]},
                },
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `self_review(history_path='logs/history.md', last_session_path='state/last_session.md')` - проанализировать историю и качество работы агента."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    history = safe_path(root, str(arguments.get("history_path") or "logs/history.md"))
    last_session = safe_path(root, str(arguments.get("last_session_path") or "state/last_session.md"))
    report = core.run_self_review(str(history), str(last_session))
    if str(arguments.get("format") or "text") == "json":
        return {"report": report.__dict__}
    return {"content": core.format_report(report)}