#!/usr/bin/env python3
"""Run one autonomous session as an all-or-nothing Git transaction."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import run_session
from scripts.command_runners import (
    CommandExecutionError,
    CommandResult,
    default_runner,
    streaming_runner,
)
from scripts.external_projects import ExternalProjectError, replicate_external_projects
from scripts.run_snapshots import SnapshotError, preserve_session_snapshot

class TransactionError(RuntimeError):
    """Raised when a session cannot be applied atomically."""

CommandRunner = Callable[[Sequence[str], Path], CommandResult]

SENSITIVE_DIRS = {".git", ".pytest_cache", "__pycache__", ".venv", "runs"}
GENERATED_LONG_FILES = {"uv.lock", "poetry.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
HUMAN_INPUT_FILES = {"state/external_messages.md"}
SESSION_FAILURE_FILES = {"state/last_session.md", "state/session_failure_tail.txt"}

def diagnostic(message: str) -> None:
    """Выводит диагностическое сообщение с префиксом [session]."""
    print(f"[session] {message}", flush=True)

def command_failure_details(result: CommandResult, max_lines: int = 50) -> str:
    """Извлекает детали ошибки из результата команды, усечённые до max_lines строк.
    """
    details = (result.stderr or result.stdout).strip()
    if not details:
        return ""
    lines = details.splitlines()
    if len(lines) <= max_lines:
        return details
    tail = "\n".join(lines[-max_lines:])
    omitted = len(lines) - max_lines
    return f"... {omitted} earlier output lines omitted; tail follows ...\n{tail}"

def run_checked(
    runner: CommandRunner,
    args: Sequence[str],
    cwd: Path,
    action: str,
) -> CommandResult:
    """Выполняет команду через runner и raises TransactionError при ошибке.
    """
    result = runner(args, cwd)
    if result.returncode != 0:
        details = command_failure_details(result)
        if details:
            raise TransactionError(f"{action}: {details}")
        raise TransactionError(f"{action}: command failed with exit code {result.returncode}")
    return result

def git(runner: CommandRunner, root: Path, *args: str) -> CommandResult:
    """Обёртка над git через runner с проверкой ошибки."""
    return run_checked(runner, ["git", *args], root, f"git {' '.join(args)}")

def ensure_git_repo(root: Path, runner: CommandRunner = default_runner) -> None:
    """Проверяет, что root является корнем git-репозитория."""
    result = git(runner, root, "rev-parse", "--show-toplevel")
    repo_root = Path(result.stdout.strip()).resolve()
    if repo_root != root.resolve():
        raise TransactionError(f"expected git root {root}, got {repo_root}")

def ensure_clean_worktree(root: Path, runner: CommandRunner = default_runner) -> None:
    """Проверяет, что в основном worktree нет незакоммиченных изменений."""
    result = git(runner, root, "status", "--porcelain")
    if result.stdout.strip():
        raise TransactionError("main worktree must be clean before transactional session")

def parse_env_line(line: str) -> tuple[str, str] | None:
    """Парсит одну строку .env-файла, возвращая (key, value) или None.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").strip()
    if "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if not key:
        return None
    return key, value

def load_dotenv(path: Path) -> dict[str, str]:
    """Загружает переменные окружения из .env-файла, не перезаписывая существующие.
    """
    if not path.exists():
        return {}

    loaded: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        os.environ.setdefault(key, value)
        loaded[key] = os.environ[key]
    return loaded

def parse_porcelain_paths(status: str) -> list[tuple[str, str]]:
    """Парсит вывод `git status --porcelain` в список (code, path).
    """
    changes: list[tuple[str, str]] = []
    for line in status.splitlines():
        if not line:
            continue
        code = line[:2]
        path = line[3:].strip().strip('"')
        if " -> " in path:
            raise TransactionError("renamed files are not allowed as human input")
        changes.append((code, path.replace("\\", "/")))
    return changes

def is_human_input_change(code: str, path: str) -> bool:
    """Определяет, является ли изменение файлом человеческого ввода.
    """
    if "D" in code:
        return False
    if path in HUMAN_INPUT_FILES:
        return True
    if path in SESSION_FAILURE_FILES:
        return True
    return path.startswith("state/questions/") and path.endswith(".md")

def checkpoint_human_input(root: Path, runner: CommandRunner = default_runner) -> bool:
    """Коммитит изменения человеческого ввода и возвращает True, если были изменения.
    """
    result = git(runner, root, "status", "--porcelain")
    changes = parse_porcelain_paths(result.stdout)
    if not changes:
        return False

    rejected = [path for code, path in changes if not is_human_input_change(code, path)]
    if rejected:
        joined = ", ".join(rejected)
        raise TransactionError(f"main worktree has non-human changes: {joined}")

    paths = [path for _, path in changes]
    git(runner, root, "add", "--", *paths)
    git(runner, root, "commit", "-m", "record human input before session")
    return True

def current_branch(root: Path, runner: CommandRunner = default_runner) -> str:
    """Возвращает имя текущей ветки в git-репозитории.
    """
    result = git(runner, root, "branch", "--show-current")
    branch = result.stdout.strip()
    if not branch:
        raise TransactionError("main worktree must be on a branch, not detached HEAD")
    return branch

def session_id(session: int) -> str:
    """Форматирует номер сессии как строку с ведущими нулями (0001, 0002, ...).
    """
    return f"{session:04d}"

@contextmanager
def lock_file(root: Path) -> Iterator[Path]:
    """Контекстный менеджер для блокировки сессии через .session.lock.

    Предотвращает параллельный запуск сессий. Возвращает путь к файлу блокировки.
    """
    lock_path = root / ".session.lock"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(lock_path, flags)
    except FileExistsError as exc:
        raise TransactionError(f"session lock already exists: {lock_path}") from exc

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\n")
        yield lock_path
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass

def default_runs_dir(root: Path) -> Path:
    """Возвращает стандартную директорию runs/ внутри корня проекта."""
    return root / "runs"

def create_worktree(
    root: Path,
    runs_dir: Path,
    session: int,
    runner: CommandRunner = default_runner,
) -> tuple[Path, str]:
    """Создаёт временный git worktree для сессии и возвращает (путь, имя_ветки).
    """
    sid = session_id(session)
    branch = f"session/{sid}"
    worktree = runs_dir / f"session-{sid}"
    if worktree.exists():
        raise TransactionError(f"worktree already exists: {worktree}")

    runs_dir.mkdir(parents=True, exist_ok=True)
    git(runner, root, "worktree", "add", "-b", branch, str(worktree), "HEAD")
    return worktree, branch

def remove_worktree_and_branch(
    root: Path,
    worktree: Path,
    branch: str,
    runner: CommandRunner = default_runner,
    force_branch: bool = True,
) -> None:
    """Удаляет временный worktree и ветку сессии.
    """
    runner(["git", "worktree", "remove", "--force", str(worktree)], root)
    delete_flag = "-D" if force_branch else "-d"
    runner(["git", "branch", delete_flag, branch], root)
    try:
        worktree.parent.rmdir()
    except OSError:
        pass

def tail_lines(text: str, max_lines: int = 50) -> str:
    """Возвращает последние max_lines строк текста.
    """
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[-max_lines:])


def record_interrupted_session(root: Path, details: str) -> Path:
    """Записывает детали прерванной сессии в state/session_failure_tail.txt.
    """
    state_dir = root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    failure_path = state_dir / "session_failure_tail.txt"
    tail = tail_lines(details.strip() or "нет диагностического вывода", max_lines=50)
    failure_path.write_text(f"{tail}\n", encoding="utf-8")

    last_session_path = state_dir / "last_session.md"
    previous = last_session_path.read_text(encoding="utf-8") if last_session_path.exists() else ""
    separator = "\n\n" if previous.strip() else ""
    last_session_path.write_text(
        f"{previous}{separator}"
        "## Сессия была прервана\n\n"
        "Сессия была прервана. Последние 50 строк сохранены в "
        "`state/session_failure_tail.txt`.\n",
        encoding="utf-8",
    )
    return failure_path

def run_inner_session(
    worktree: Path,
    agent_command: str,
    runner: CommandRunner = default_runner,
) -> None:
    """Запускает агента в временном worktree через run_agent.py.
    """
    script = worktree / "scripts" / "run_session.py"
    args = [sys.executable, str(script), "--agent-command", agent_command]
    result = runner(args, worktree)
    if result.returncode != 0:
        details = command_failure_details(result)
        raise TransactionError(f"agent session failed: {details or 'see streamed output above'}")

def run_checks(
    worktree: Path,
    check_command: Sequence[str],
    runner: CommandRunner = default_runner,
) -> None:
    """Запускает проверку (например pytest) в worktree и raises при ошибке.
    """
    result = runner(check_command, worktree)
    if result.returncode != 0:
        details = command_failure_details(result)
        raise TransactionError(f"checks failed: {details or 'see streamed output above'}")

def ensure_required_session_files(worktree: Path) -> None:
    """Проверяет наличие обязательных файлов сессии: last_session.md и history.md.
    """
    required = [
        worktree / "state" / "last_session.md",
        worktree / "logs" / "history.md",
    ]
    missing = [str(path.relative_to(worktree)) for path in required if not path.exists()]
    if missing:
        raise TransactionError(f"required session files are missing: {', '.join(missing)}")


def archive_last_session(worktree: Path, session: int) -> Path:
    """Копирует last_session.md в .sessions/session-{session_id}.md.
    """
    source = worktree / "state" / "last_session.md"
    target = worktree / ".sessions" / f"session-{session_id(session)}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target

def find_oversized_files(root: Path, max_lines: int = 500) -> list[Path]:
    """Находит файлы, превышающие max_lines строк, исключая чувствительные директории.
    """
    oversized: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SENSITIVE_DIRS for part in path.parts):
            continue
        if path.name in GENERATED_LONG_FILES:
            continue
        try:
            line_count = sum(1 for _ in path.open("r", encoding="utf-8"))
        except UnicodeDecodeError:
            continue
        if line_count > max_lines:
            oversized.append(path)
    return oversized

def ensure_file_size_policy(worktree: Path, max_lines: int = 500) -> None:
    """Проверяет, что ни один файл не превышает max_lines строк.
    """
    oversized = find_oversized_files(worktree, max_lines=max_lines)
    if oversized:
        relative = ", ".join(str(path.relative_to(worktree)) for path in oversized)
        raise TransactionError(f"files exceed {max_lines} lines and must be decomposed: {relative}")

def ensure_session_changed_worktree(
    worktree: Path,
    runner: CommandRunner = default_runner,
) -> None:
    """Проверяет, что сессия произвела хотя бы одно изменение в worktree.
    """
    result = git(runner, worktree, "status", "--porcelain")
    if not result.stdout.strip():
        raise TransactionError("session produced no tracked or untracked changes")

def commit_session(
    worktree: Path,
    session: int,
    runner: CommandRunner = default_runner,
) -> str:
    """Коммитит все изменения в worktree и возвращает хеш коммита.
    """
    git(runner, worktree, "add", "-A")
    git(runner, worktree, "commit", "-m", f"session {session_id(session)}")
    result = git(runner, worktree, "rev-parse", "HEAD")
    return result.stdout.strip()

def apply_session_commit(
    root: Path,
    branch: str,
    runner: CommandRunner = default_runner,
) -> None:
    """Сливает ветку сессии в основную ветку через fast-forward merge.
    """
    git(runner, root, "merge", "--ff-only", branch)

def default_agent_command() -> str:
    """Возвращает команду агента по умолчанию с подстановкой переменных ROOT и PROMPT_FILE.
    """
    return 'uv run python scripts/run_agent.py --root "{ROOT}" --prompt-file "{PROMPT_FILE}"'

def run_transaction(
    root: Path,
    agent_command: str,
    runs_dir: Path | None = None,
    check_command: Sequence[str] | None = None,
    runner: CommandRunner = default_runner,
) -> str:
    """Выполняет полную транзакцию сессии: worktree → агент → проверка → merge.

    Возвращает хеш применённого коммита.
    """
    if not agent_command.strip():
        agent_command = default_agent_command()

    root = root.resolve()
    runs_dir = (runs_dir or default_runs_dir(root)).resolve()
    check_command = check_command or [sys.executable, "-m", "pytest"]

    diagnostic(f"root: {root}")
    diagnostic(f"runs dir: {runs_dir}")

    with lock_file(root):
        diagnostic("lock acquired")
        diagnostic("checking repository")
        ensure_git_repo(root, runner)

        loaded_env = load_dotenv(root / ".env")
        if loaded_env:
            diagnostic(f"loaded .env keys: {', '.join(sorted(loaded_env))}")
        else:
            diagnostic(".env not found or empty")

        diagnostic("checking human input changes")
        if checkpoint_human_input(root, runner):
            diagnostic("human input checkpoint committed")

        ensure_clean_worktree(root, runner)
        branch_name = current_branch(root, runner)
        diagnostic(f"main branch: {branch_name}")
        base_head = git(runner, root, "rev-parse", "HEAD").stdout.strip()

        session = run_session.read_counter(root / "state" / "session_counter.txt")
        diagnostic(f"session: {session_id(session)}")
        worktree: Path | None = None
        branch = ""
        applied = False
        merged = False

        try:
            diagnostic("creating temporary worktree")
            worktree, branch = create_worktree(root, runs_dir, session, runner)
            diagnostic(f"temporary branch: {branch}")

            diagnostic("seeding external project repositories")
            seeded_projects = replicate_external_projects(root, worktree, runner)
            if seeded_projects:
                joined = ", ".join(str(path) for path in seeded_projects)
                diagnostic(f"seeded external projects: {joined}")
            else:
                diagnostic("no external projects to seed")

            diagnostic("running agent session")
            run_inner_session(worktree, agent_command, runner)

            diagnostic("checking required session files")
            ensure_required_session_files(worktree)

            archived_last_session = archive_last_session(worktree, session)
            diagnostic(f"archived last session: {archived_last_session.relative_to(worktree)}")

            diagnostic("checking file size policy")
            ensure_file_size_policy(worktree)

            diagnostic("running validation checks")
            run_checks(worktree, check_command, runner)

            diagnostic("checking produced changes")
            ensure_session_changed_worktree(worktree, runner)

            diagnostic("committing session changes")
            commit_hash = commit_session(worktree, session, runner)

            diagnostic("applying session commit to main worktree")
            apply_session_commit(root, branch, runner)
            merged = True

            diagnostic("replicating external project repositories")
            replicated_projects = replicate_external_projects(worktree, root, runner)
            if replicated_projects:
                joined = ", ".join(str(path) for path in replicated_projects)
                diagnostic(f"replicated external projects: {joined}")
            else:
                diagnostic("no external projects to replicate")

            applied = True
            diagnostic(f"applied commit: {commit_hash}")
            return commit_hash
        except Exception as exc:
            if merged and not applied:
                diagnostic("rolling back main worktree to pre-session HEAD")
                git(runner, root, "reset", "--hard", base_head)
            failure_path = record_interrupted_session(root, str(exc))
            diagnostic(f"recorded interrupted session: {failure_path.relative_to(root)}")
            raise
        finally:
            if worktree is not None and branch:
                sid = session_id(session)
                status = "applied" if applied else "failed"
                try:
                    snapshot = preserve_session_snapshot(worktree, runs_dir, sid, applied)
                    diagnostic(f"preserved {status} session snapshot: {snapshot}")
                except SnapshotError as exc:
                    diagnostic(f"session snapshot was not preserved: {exc}")

                diagnostic("cleaning temporary worktree")
                remove_worktree_and_branch(
                    root,
                    worktree,
                    branch,
                    runner,
                    force_branch=not applied,
                )

def parse_args() -> argparse.Namespace:
    """Парсит аргументы командной строки для транзакционной сессии."""
    parser = argparse.ArgumentParser(
        description="Run one autonomous session in a temporary git worktree."
    )
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Main project root. Defaults to the parent of scripts/.",
    )
    parser.add_argument(
        "--agent-command",
        default=os.environ.get("AI_AGENT_COMMAND", ""),
        help="Agent command passed to scripts/run_session.py inside the worktree. Defaults to the local ai-lives agent.",
    )
    parser.add_argument(
        "--runs-dir",
        default="",
        help="Directory for temporary worktrees. Defaults to <root>/runs.",
    )
    parser.add_argument(
        "--check-command",
        nargs="+",
        default=[sys.executable, "-m", "pytest"],
        help="Command used to validate the worktree before applying changes.",
    )
    return parser.parse_args()

def main() -> int:
    """Точка входа для транзакционной сессии. Возвращает 0 при успехе, 1 при ошибке."""
    args = parse_args()
    root = Path(args.root)
    runs_dir = Path(args.runs_dir) if args.runs_dir else None

    try:
        commit_hash = run_transaction(
            root=root,
            agent_command=args.agent_command,
            runs_dir=runs_dir,
            check_command=args.check_command,
            runner=streaming_runner,
        )
    except (TransactionError, CommandExecutionError, ExternalProjectError) as exc:
        print(f"Transaction failed: {exc}", file=sys.stderr)
        return 1

    print(f"Transaction applied: {commit_hash}")
    return 0

if __name__ == "__main__":
    sys.exit(main())





