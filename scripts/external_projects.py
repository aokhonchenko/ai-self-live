"""Replication helpers for external project repositories under projects/."""

from __future__ import annotations

import shutil
import stat
from pathlib import Path
from typing import Callable, Sequence

from scripts.command_runners import CommandResult, default_runner


class ExternalProjectError(RuntimeError):
    """Raised when an external project cannot be replicated."""


CommandRunner = Callable[[Sequence[str], Path], CommandResult]

EXTERNAL_PROJECTS_DIR = "projects"
EXTERNAL_PROJECT_COPY_IGNORES = {"__pycache__", ".pytest_cache", ".venv", "node_modules", "target"}
EXISTING_PROJECT_COPY_IGNORES = EXTERNAL_PROJECT_COPY_IGNORES | {".git"}


def is_git_ignored(root: Path, path: Path, runner: CommandRunner = default_runner) -> bool:
    """Check whether a path is ignored by the gitignore rules in root."""
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    result = runner(["git", "check-ignore", "-q", relative], root)
    return result.returncode == 0


def has_git_metadata(path: Path) -> bool:
    """Return True if the path contains a .git directory."""
    return (path / ".git").exists()


def external_project_dirs(root: Path, runner: CommandRunner = default_runner) -> list[Path]:
    """Return subdirectories under projects/ that have git metadata or are git-ignored."""
    projects_dir = root / EXTERNAL_PROJECTS_DIR
    if not projects_dir.exists():
        return []
    candidates: list[Path] = []
    for path in sorted(projects_dir.iterdir(), key=lambda item: item.name):
        if not path.is_dir():
            continue
        if has_git_metadata(path) or is_git_ignored(root, path, runner):
            candidates.append(path)
    return candidates


def _is_ignored_name(name: str, ignores: set[str]) -> bool:
    """Check whether a file/directory name is in the ignore set."""
    return name in ignores


def _make_writable(path: Path) -> None:
    """Make a file or directory writable, silently ignoring errors."""
    try:
        path.chmod(path.stat().st_mode | stat.S_IWRITE)
    except OSError:
        pass


def _remove_path(path: Path) -> None:
    """Remove a file or directory, forcing write permissions if needed."""
    if path.is_dir():
        shutil.rmtree(path, onerror=lambda func, item, _exc: (_make_writable(Path(item)), func(item)))
        return
    _make_writable(path)
    path.unlink()


def _copy_into_existing(source: Path, target: Path) -> None:
    """Sync source into target directory, removing extra files in target."""
    target.mkdir(parents=True, exist_ok=True)
    source_names = {
        child.name
        for child in source.iterdir()
        if not _is_ignored_name(child.name, EXISTING_PROJECT_COPY_IGNORES)
    }
    for child in list(target.iterdir()):
        if _is_ignored_name(child.name, EXISTING_PROJECT_COPY_IGNORES):
            continue
        if child.name not in source_names:
            _remove_path(child)

    for child in source.iterdir():
        if _is_ignored_name(child.name, EXISTING_PROJECT_COPY_IGNORES):
            continue
        destination = target / child.name
        if child.is_dir():
            if destination.exists() and not destination.is_dir():
                _remove_path(destination)
            _copy_into_existing(child, destination)
            continue
        if destination.exists() and destination.is_dir():
            _remove_path(destination)
        if destination.exists():
            _make_writable(destination)
        shutil.copy2(child, destination)


def copy_external_project(source: Path, target: Path) -> None:
    """Copy an external project from source to target, syncing if target exists."""
    ignore = shutil.ignore_patterns(*EXTERNAL_PROJECT_COPY_IGNORES)
    if target.exists() and not target.is_dir():
        raise ExternalProjectError(f"external project target is not a directory: {target}")
    try:
        if target.exists():
            _copy_into_existing(source, target)
            return
        shutil.copytree(source, target, dirs_exist_ok=True, ignore=ignore)
    except (OSError, shutil.Error) as exc:
        raise ExternalProjectError(f"cannot replicate external project {source} to {target}: {exc}") from exc


def replicate_external_projects(
    worktree: Path,
    root: Path,
    runner: CommandRunner = default_runner,
) -> list[Path]:
    """Replicate external projects from worktree into root, returning relative paths."""
    replicated: list[Path] = []
    for source in external_project_dirs(worktree, runner):
        relative = source.relative_to(worktree)
        target = root / relative
        copy_external_project(source, target)
        replicated.append(relative)
    return replicated
