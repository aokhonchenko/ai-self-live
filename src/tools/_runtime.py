"""Shared helpers for directory-based agent tools."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence


class ToolError(RuntimeError):
    """Raised when a local tool call is invalid or unsafe."""


FORBIDDEN_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "runs"}
MAX_TIMEOUT_SECONDS = 300.0
MAX_OUTPUT_CHARS = 20000
PROCESS_KILL_GRACE_SECONDS = 5.0
NON_INTERACTIVE_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_EDITOR": "true",
    "VISUAL": "true",
    "EDITOR": "true",
    "GCM_INTERACTIVE": "Never",
}


def safe_path(root: Path, path: str) -> Path:
    if not path or path.strip() != path:
        raise ToolError("path must be a non-empty relative path without surrounding whitespace")
    requested = Path(path)
    if requested.is_absolute():
        raise ToolError("absolute paths are not allowed")
    if any(part in FORBIDDEN_PARTS for part in requested.parts):
        raise ToolError(f"path contains a forbidden part: {path}")
    resolved_root = root.resolve()
    resolved = (resolved_root / requested).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ToolError(f"path escapes the session root: {path}") from exc
    return resolved


def safe_cwd(root: Path, cwd: str | None) -> Path:
    resolved_root = root.resolve()
    if cwd is None or not str(cwd).strip():
        return resolved_root
    requested = Path(str(cwd))
    resolved = requested.resolve() if requested.is_absolute() else (resolved_root / requested).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ToolError(f"cwd escapes the session root: {cwd}") from exc
    if not resolved.exists():
        raise ToolError(f"cwd does not exist: {cwd}")
    if not resolved.is_dir():
        raise ToolError(f"cwd is not a directory: {cwd}")
    return resolved


def timeout_seconds(value: Any, default: float = 120.0) -> float:
    if value in (None, ""):
        return default
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"timeout must be a number: {value}") from exc
    if timeout <= 0:
        raise ToolError("timeout must be positive")
    if timeout > MAX_TIMEOUT_SECONDS:
        raise ToolError(f"timeout must be <= {int(MAX_TIMEOUT_SECONDS)} seconds")
    return timeout


def subprocess_env(overrides: dict[str, Any] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.update(NON_INTERACTIVE_ENV)
    if overrides:
        env.update({str(key): str(value) for key, value in overrides.items()})
    return env


def normalize_args(value: Any, field: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ToolError(f"{field} must be an array of strings")
    return [str(item) for item in value]


def trim_output(value: str | bytes | None) -> tuple[str, bool]:
    if value is None:
        text = ""
    elif isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = value
    if len(text) <= MAX_OUTPUT_CHARS:
        return text, False
    return text[:MAX_OUTPUT_CHARS], True


def _popen_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=PROCESS_KILL_GRACE_SECONDS,
                check=False,
            )
            return
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except OSError:
            pass
    try:
        process.kill()
    except OSError:
        pass


def _communicate_after_kill(process: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        return process.communicate(timeout=PROCESS_KILL_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
        return "", ""


def command_result(
    command: str | Sequence[str],
    cwd: Path,
    timeout: float | None,
    *,
    shell: bool = False,
    env_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    start = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=subprocess_env(env_overrides),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=shell,
            **_popen_kwargs(),
        )
    except OSError as exc:
        raise ToolError(f"failed to start command: {exc}") from exc

    timed_out = False
    try:
        stdout_raw, stderr_raw = process.communicate(timeout=timeout)
        returncode = process.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_tree(process)
        stdout_raw, stderr_raw = _communicate_after_kill(process)
        returncode = -1

    stdout, stdout_truncated = trim_output(stdout_raw)
    stderr, stderr_truncated = trim_output(stderr_raw)
    if timed_out and not stderr:
        stderr = f"command timed out after {timeout} seconds"
    payload = {
        "command": command if isinstance(command, str) else list(command),
        "cwd": str(cwd),
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "duration_seconds": round(time.monotonic() - start, 3),
    }
    if timed_out:
        payload["timed_out"] = True
    return payload


def python_executable() -> str:
    return sys.executable
