"""Agent wrapper for the legacy command_runner tool."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.tools._runtime import ToolError, normalize_args, safe_cwd, timeout_seconds
from src.tools.command_runner import core


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "command_runner",
            "description": "Use the legacy command runner helpers: command, pytest, python script, make, or docker-compose.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["command", "pytest", "script", "make", "docker_compose"]},
                    "command": {"type": "string"},
                    "args": {"type": "array", "items": {"type": "string"}},
                    "test_path": {"type": "string"},
                    "script_path": {"type": "string"},
                    "target": {"type": "string"},
                    "action": {"type": "string"},
                    "cwd": {"type": "string"},
                    "timeout": {"type": "number"},
                    "shell": {"type": "boolean"},
                },
                "required": ["operation"],
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `command_runner(operation, ...)` - legacy runner для command/pytest/script/make/docker_compose внутри корня сессии."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    operation = str(arguments.get("operation", ""))
    cwd = str(safe_cwd(root, arguments.get("cwd")))
    timeout = timeout_seconds(arguments.get("timeout"), default=120.0)
    args = normalize_args(arguments.get("args"), "args")
    if operation == "command":
        command = str(arguments.get("command", "")).strip()
        if not command:
            raise ToolError("command must be non-empty")
        result = core.run_command(command, *args, cwd=cwd, timeout=timeout, shell=bool(arguments.get("shell", False)))
    elif operation == "pytest":
        result = core.run_pytest(str(arguments.get("test_path") or "tests/"), *args, cwd=cwd, timeout=timeout)
    elif operation == "script":
        result = core.run_python_script(str(arguments.get("script_path", "")), *args, cwd=cwd, timeout=timeout)
    elif operation == "make":
        result = core.run_make(str(arguments.get("target") or ""), cwd=cwd, timeout=timeout)
    elif operation == "docker_compose":
        result = core.run_docker_compose(str(arguments.get("action") or "ps"), *args, cwd=cwd, timeout=timeout)
    else:
        raise ToolError(f"unknown command_runner operation: {operation}")
    return asdict(result)