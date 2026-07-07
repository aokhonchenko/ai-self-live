"""run_command agent tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import command_result, safe_cwd, timeout_seconds


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command inside the session root and return captured output and return code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command line to execute through the platform shell."},
                    "cwd": {"type": "string", "description": "Optional working directory inside the session root."},
                    "timeout": {"type": "number", "description": "Timeout in seconds, max 300; defaults to 120."},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `run_command(command, cwd='.', timeout=120)` - запустить shell-команду внутри корня сессии и вернуть stdout/stderr/returncode."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command", "")).strip()
    if not command:
        from src.tools._runtime import ToolError

        raise ToolError("command must be non-empty")
    cwd = safe_cwd(root, arguments.get("cwd"))
    timeout = timeout_seconds(arguments.get("timeout"), default=120.0)
    return command_result(command, cwd, timeout, shell=True)