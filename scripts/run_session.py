#!/usr/bin/env python3
"""Cross-platform runner for one autonomous experiment session."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_OVERRIDE: Path | None = None


def read_text_or_default(path: Path, default: str) -> str:
    """Read a file's content or return a default string if the file is missing."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return default


def read_counter(path: Path) -> int:
    """Read the session counter from a file, returning 1 if missing or invalid."""
    if not path.exists():
        return 1

    raw = path.read_text(encoding="utf-8").strip()
    if raw.isdigit():
        return int(raw)

    return 1


def read_questions(root: Path) -> str:
    """Read all question files from state/questions/ and concatenate them."""
    questions_dir = root / "state" / "questions"
    if not questions_dir.exists():
        return "_Вопросов создателю пока нет._\n"

    question_files = sorted(
        path
        for path in questions_dir.glob("*.md")
        if path.is_file() and path.name != "README.md"
    )
    if not question_files:
        return "_Вопросов создателю пока нет._\n"

    parts = []
    for path in question_files:
        content = path.read_text(encoding="utf-8")
        parts.append(f"## {path.name}\n\n{content}")
    return "\n\n".join(parts)


def build_prompt(root: Path, session: int) -> str:
    """Assemble the full session prompt from state files and system prompt."""
    state_dir = root / "state"
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")

    system_prompt = read_text_or_default(
        root / "SYSTEM_PROMPT.md",
        "# Системный промпт отсутствует.\n",
    )
    last_session = read_text_or_default(
        state_dir / "last_session.md",
        "_Предыдущих сообщений нет._\n",
    )
    current_plan = read_text_or_default(
        state_dir / "current_plan.md",
        "_Текущий план пока не задан._\n",
    )
    external_messages = read_text_or_default(
        state_dir / "external_messages.md",
        "_Внешних сообщений нет._\n",
    )
    sleep_state = read_text_or_default(
        state_dir / "sleep" / "last_sleep.md",
        "_Сон ещё не выполнялся._\n",
    )
    questions = read_questions(root)

    return f"""# Активный промпт сессии {session}

Время сборки промпта: {now}
Корень эксперимента: {root}

---

{system_prompt}

---

# state/last_session.md

{last_session}

---

# state/current_plan.md

{current_plan}

---

# state/external_messages.md

{external_messages}

---

# state/questions/

{questions}

---

# state/sleep/last_sleep.md

{sleep_state}

---

# Инструкция на эту сессию

Ты находишься в сессии {session}. Работай в корне эксперимента: `{root}`.

Самостоятельно выбери и сделай один осмысленный шаг. Ты можешь создать артефакт, начать или улучшить проект в своей директории, улучшить инструменты агента, навести порядок в памяти или выбрать сон. Все пользовательские артефакты пиши на русском языке.

Перед завершением обязательно обнови:

1. `state/last_session.md`
2. `logs/history.md`

Если ты меняешь план, обнови `state/current_plan.md`.
"""


def expand_command(command: str, root: Path, prompt_file: Path, session: int) -> str:
    """Replace {PROMPT_FILE}, {ROOT}, {SESSION} placeholders in a command string."""
    return (
        command.replace("{PROMPT_FILE}", str(prompt_file))
        .replace("{ROOT}", str(root))
        .replace("{SESSION}", str(session))
    )


def agent_environment() -> dict[str, str]:
    """Build an environment dict for agent subprocesses with UTF-8 and no buffering."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def run_agent_command(command: str, root: Path) -> int:
    """Run the agent command as a subprocess and return its exit code."""
    completed = subprocess.run(
        command,
        cwd=root,
        shell=True,
        env=agent_environment(),
    )
    return completed.returncode


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the session prompt builder."""
    parser = argparse.ArgumentParser(
        description="Prepare a session prompt and optionally run an agent command."
    )
    parser.add_argument(
        "--agent-command",
        default=os.environ.get("AI_AGENT_COMMAND", ""),
        help="Command used to run the agent. Supports {PROMPT_FILE}, {ROOT}, {SESSION}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print the prompt path without incrementing the session counter.",
    )
    parser.add_argument(
        "--print-prompt",
        action="store_true",
        help="Print the prepared prompt to stdout.",
    )
    return parser.parse_args()


def project_root() -> Path:
    """Return the project root directory, respecting ROOT_OVERRIDE for tests."""
    if ROOT_OVERRIDE is not None:
        return ROOT_OVERRIDE
    return Path(__file__).resolve().parents[1]


def main() -> int:
    """Entry point: build prompt, update counter, optionally run agent command."""
    args = parse_args()
    root = project_root()
    state_dir = root / "state"
    logs_dir = root / "logs"

    for directory in (
        state_dir,
        logs_dir,
        root / "knowledge",
        root / "projects",
        root / "tools",
        state_dir / "questions",
        state_dir / "sleep",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    counter_path = state_dir / "session_counter.txt"
    session = read_counter(counter_path)
    prompt = build_prompt(root, session)
    active_prompt_path = state_dir / "active_prompt.md"
    active_prompt_path.write_text(prompt, encoding="utf-8")

    if args.print_prompt:
        print(prompt, flush=True)

    if args.dry_run:
        print(f"Собран промпт для сессии {session}: {active_prompt_path}", flush=True)
        print("Dry-run не увеличивает счётчик сессий и не запускает агента.", flush=True)
        return 0

    counter_path.write_text(f"{session + 1}\n", encoding="utf-8")

    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    history_path = logs_dir / "history.md"
    mode = "agent command" if args.agent_command.strip() else "command missing"
    with history_path.open("a", encoding="utf-8") as history:
        history.write(
            f"\n## Сессия {session} - prompt prepared\n\n"
            f"- Время: {now}\n"
            f"- Активный промпт: `state/active_prompt.md`\n"
            f"- Режим: {mode}\n"
        )

    if not args.agent_command.strip():
        print(f"Собран промпт для сессии {session}: {active_prompt_path}", flush=True)
        print("Для запуска агента задайте AI_AGENT_COMMAND или --agent-command.", flush=True)
        return 0

    expanded_command = expand_command(
        args.agent_command,
        root=root,
        prompt_file=active_prompt_path,
        session=session,
    )

    print(f"Запускаю сессию {session}...", flush=True)
    print(expanded_command, flush=True)

    return run_agent_command(expanded_command, root)


if __name__ == "__main__":
    sys.exit(main())
