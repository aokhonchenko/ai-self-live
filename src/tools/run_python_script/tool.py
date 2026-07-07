"""run_python_script agent tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools._runtime import command_result, normalize_args, python_executable, safe_cwd, safe_path, timeout_seconds


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "run_python_script",
            "description": "Run a Python script from inside the session root with optional arguments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "script_path": {"type": "string", "description": "Relative path to a Python script inside the session root."},
                    "script_args": {"type": "array", "items": {"type": "string"}, "description": "Arguments passed to the script."},
                    "cwd": {"type": "string", "description": "Optional working directory inside the session root."},
                    "timeout": {"type": "number", "description": "Timeout in seconds, max 300; defaults to 120."},
                },
                "required": ["script_path"],
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `run_python_script(script_path, script_args=[], cwd='.', timeout=120)` - запустить Python-скрипт из корня сессии."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    script_path = str(arguments.get("script_path", ""))
    script = safe_path(root, script_path)
    if not script.exists():
        from src.tools._runtime import ToolError

        raise ToolError(f"script does not exist: {script_path}")
    if not script.is_file():
        from src.tools._runtime import ToolError

        raise ToolError(f"script path is not a file: {script_path}")
    cwd = safe_cwd(root, arguments.get("cwd"))
    timeout = timeout_seconds(arguments.get("timeout"), default=120.0)
    script_args = normalize_args(arguments.get("script_args"), "script_args")
    command = [python_executable(), str(script), *script_args]
    return command_result(command, cwd, timeout)