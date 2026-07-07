"""run_pytest agent tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import command_result, normalize_args, python_executable, safe_cwd, timeout_seconds


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "run_pytest",
            "description": "Run pytest with the current Python executable inside the session root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "test_path": {"type": "string", "description": "Test file or directory; defaults to tests."},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "Extra pytest arguments."},
                    "cwd": {"type": "string", "description": "Optional working directory inside the session root."},
                    "timeout": {"type": "number", "description": "Timeout in seconds, max 300; defaults to 120."},
                },
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `run_pytest(test_path='tests', args=[], cwd='.', timeout=120)` - запустить pytest текущим Python внутри корня сессии."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    cwd = safe_cwd(root, arguments.get("cwd"))
    timeout = timeout_seconds(arguments.get("timeout"), default=120.0)
    test_path = str(arguments.get("test_path") or "tests")
    extra_args = normalize_args(arguments.get("args"), "args")
    command = [python_executable(), "-m", "pytest", test_path, *extra_args]
    return command_result(command, cwd, timeout)