"""Preserve recent session worktree snapshots for debugging."""

from __future__ import annotations

import shutil
from pathlib import Path


RECENT_SNAPSHOT_COUNT = 2
SNAPSHOT_IGNORES = (".git", ".venv", "__pycache__", ".pytest_cache", "runs")


class SnapshotError(RuntimeError):
    """Raised when a session snapshot cannot be preserved."""


def snapshots_dir(runs_dir: Path) -> Path:
    """Return the path to the snapshots directory inside runs_dir."""
    return runs_dir / "snapshots"


def snapshot_name(session_id: str, applied: bool) -> str:
    """Generate a snapshot directory name from session id and status."""
    status = "applied" if applied else "failed"
    return f"session-{session_id}-{status}"


def write_snapshot_metadata(target: Path, session_id: str, applied: bool, source: Path) -> None:
    """Write a RUN_SNAPSHOT.md file describing the snapshot status."""
    status = "успешно применена" if applied else "завершилась ошибкой"
    metadata = (
        "# Снимок сессии\n\n"
        f"- Сессия: `{session_id}`\n"
        f"- Статус: {status}\n"
        f"- Исходный worktree: `{source}`\n\n"
        "Этот каталог является отладочным снимком. Он не участвует в Git worktree "
        "и может быть удалён после анализа.\n"
    )
    (target / "RUN_SNAPSHOT.md").write_text(metadata, encoding="utf-8")


def prune_snapshots(directory: Path, keep: int = RECENT_SNAPSHOT_COUNT) -> None:
    """Remove old snapshot directories, keeping only the most recent `keep`."""
    if keep < 1 or not directory.exists():
        return
    snapshots = [path for path in directory.iterdir() if path.is_dir() and path.name.startswith("session-")]
    snapshots.sort(key=lambda path: (path.stat().st_mtime, path.name))
    for old_snapshot in snapshots[:-keep]:
        shutil.rmtree(old_snapshot)


def preserve_session_snapshot(
    worktree: Path,
    runs_dir: Path,
    session_id: str,
    applied: bool,
    keep: int = RECENT_SNAPSHOT_COUNT,
) -> Path:
    """Copy a worktree to snapshots, write metadata, and prune old snapshots."""
    try:
        directory = snapshots_dir(runs_dir)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / snapshot_name(session_id, applied)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(
            worktree,
            target,
            ignore=shutil.ignore_patterns(*SNAPSHOT_IGNORES),
        )
        write_snapshot_metadata(target, session_id, applied, worktree)
        prune_snapshots(directory, keep=keep)
        return target
    except (OSError, shutil.Error) as exc:
        raise SnapshotError(f"cannot preserve session snapshot: {exc}") from exc