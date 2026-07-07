"""Configuration helpers for the session management server."""

from __future__ import annotations

import os
import random
from pathlib import Path

AUTO_SESSION_DEFAULT_MIN_DELAY_SECONDS = 5 * 60
AUTO_SESSION_DEFAULT_MAX_DELAY_SECONDS = 15 * 60


def parse_env_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    if line.startswith("export "):
        line = line[len("export "):].strip()
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if not key:
        return None
    return key, value


def load_server_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    loaded: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_env_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        os.environ.setdefault(key, value)
        loaded[key] = os.environ[key]
    return loaded


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return max(0, int(value))
    except ValueError:
        return default


def auto_session_delay_bounds() -> tuple[int, int]:
    min_seconds = env_int("AUTO_SESSION_MIN_DELAY_SECONDS", AUTO_SESSION_DEFAULT_MIN_DELAY_SECONDS)
    max_seconds = env_int("AUTO_SESSION_MAX_DELAY_SECONDS", AUTO_SESSION_DEFAULT_MAX_DELAY_SECONDS)
    if max_seconds < min_seconds:
        max_seconds = min_seconds
    return min_seconds, max_seconds


def auto_session_delay_seconds() -> int:
    min_seconds, max_seconds = auto_session_delay_bounds()
    return random.randint(min_seconds, max_seconds)
