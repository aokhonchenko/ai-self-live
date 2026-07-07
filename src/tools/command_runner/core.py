#!/usr/bin/env python3
"""
Инструмент для запуска shell-команд из агента.

Позволяет выполнять произвольные команды в shell, получать stdout/stderr
и код возврата. Это решает проблему отсутствия shell-инструмента у агента:
теперь можно запускать тесты, проверять изменения, собирать проекты и т.д.

Создан: сессия 37 (2026-07-06)
Цель: дать агенту возможность запускать команды (тесты, сборка, проверки).

Использование:
    python command_runner.py <команда> [аргументы...]
    python command_runner.py --cwd <директория> <команда>
    python command_runner.py --timeout <сек> <команда>
    python command_runner.py --no-capture  # вывод в реальном времени

Примеры:
    python command_runner.py python -m pytest tests/test_apply_patch.py -v
    python command_runner.py --cwd ../.. python -m pytest tests/
    python command_runner.py --timeout 30 python -m pytest
"""

import sys
import os
import shlex
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from datetime import datetime

from src.tools._runtime import ToolError, command_result as safe_command_result


@dataclass
class CommandResult:
    """Результат выполнения команды."""
    command: str
    returncode: int
    stdout: str
    stderr: str
    cwd: str
    duration_sec: float
    error: Optional[str] = None  # Ошибка запуска (если команду не удалось запустить)

    @property
    def success(self) -> bool:
        """True если команда завершилась успешно (код 0)."""
        return self.returncode == 0 and self.error is None

    @property
    def timed_out(self) -> bool:
        """True если команда была прервана по таймауту."""
        return self.returncode == -1

    def summary(self) -> str:
        """Краткая сводка результата."""
        if self.error:
            return f"❌ Ошибка запуска: {self.error}"
        if self.timed_out:
            return f"⏱ Таймаут ({self.duration_sec:.1f}с)"
        if self.success:
            return f"✅ Успешно (код {self.returncode}, {self.duration_sec:.2f}с)"
        return f"❌ Ошибка (код {self.returncode}, {self.duration_sec:.2f}с)"

    def format(self, max_lines: int = 50) -> str:
        """Форматирует результат для вывода."""
        lines = []
        lines.append(f"# Результат команды")
        lines.append(f"**Команда:** `{self.command}`")
        lines.append(f"**Директория:** `{self.cwd}`")
        lines.append(f"**Статус:** {self.summary()}")
        lines.append("")

        if self.stdout:
            stdout_lines = self.stdout.splitlines()
            truncated = len(stdout_lines) > max_lines
            if truncated:
                stdout_lines = stdout_lines[:max_lines]
            lines.append(f"## stdout ({len(stdout_lines)} строк{' +' if truncated else ''})")
            lines.append("")
            lines.append("```")
            lines.extend(stdout_lines)
            lines.append("```")
            lines.append("")

        if self.stderr:
            stderr_lines = self.stderr.splitlines()
            truncated = len(stderr_lines) > max_lines
            if truncated:
                stderr_lines = stderr_lines[:max_lines]
            lines.append(f"## stderr ({len(stderr_lines)} строк{' +' if truncated else ''})")
            lines.append("")
            lines.append("```")
            lines.extend(stderr_lines)
            lines.append("```")
            lines.append("")

        return "\n".join(lines)


def run_command(
    command: str,
    *args: str,
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
    capture_output: bool = True,
    shell: bool = False,
    env: Optional[dict] = None,
) -> CommandResult:
    """
    Запускает команду и возвращает результат.

    Args:
        command: команда (исполняемый файл или shell-команда если shell=True)
        *args: аргументы команды
        cwd: рабочая директория (по умолчанию текущая)
        timeout: таймаут в секундах (None = без таймаута)
        capture_output: захватывать stdout/stderr (иначе вывод в консоль)
        shell: запускать через shell (для пайпов, перенаправлений и т.д.)
        env: переменные окружения (дополняют текущие)

    Returns:
        CommandResult с результатом выполнения
    """
    import time

    start_time = time.time()
    cwd = cwd or os.getcwd()

    # Формируем команду
    if shell:
        cmd_str = command + (' ' + ' '.join(shlex.quote(a) for a in args) if args else '')
        cmd = cmd_str
    else:
        cmd = [command] + list(args)
        cmd_str = ' '.join(shlex.quote(str(p)) for p in cmd)

    # Формируем окружение
    cmd_env = os.environ.copy()
    if env:
        cmd_env.update(env)

    try:
        result = safe_command_result(
            cmd if shell else [command] + list(args),
            Path(cwd),
            timeout,
            shell=shell,
            env_overrides=env,
        )
        if not capture_output:
            if result.get("stdout"):
                print(result["stdout"], end="")
            if result.get("stderr"):
                print(result["stderr"], end="", file=sys.stderr)
        return CommandResult(
            command=cmd_str,
            returncode=result["returncode"],
            stdout=result.get("stdout", "") if capture_output else "",
            stderr=result.get("stderr", "") if capture_output else "",
            cwd=cwd,
            duration_sec=float(result.get("duration_seconds", time.time() - start_time)),
        )
    except ToolError as e:
        duration = time.time() - start_time
        return CommandResult(
            command=cmd_str,
            returncode=-1,
            stdout="",
            stderr="",
            cwd=cwd,
            duration_sec=duration,
            error=f"command not found: {command}" if "failed to start command" in str(e) else f"OS error: {e}",
        )


def run_pytest(
    test_path: str = "tests/",
    *extra_args: str,
    cwd: Optional[str] = None,
    timeout: Optional[float] = 120.0,
    verbose: bool = True,
) -> CommandResult:
    """
    Удобная обёртка для запуска pytest.

    Args:
        test_path: путь к тестам (файл или директория)
        *extra_args: дополнительные аргументы pytest
        cwd: рабочая директория
        timeout: таймаут (по умолчанию 120с)
        verbose: флаг -v

    Returns:
        CommandResult с результатом
    """
    args = ["-m", "pytest", test_path]
    if verbose:
        args.append("-v")
    args.extend(extra_args)
    return run_command(
        sys.executable, *args,
        cwd=cwd,
        timeout=timeout,
    )


def run_python_script(
    script_path: str,
    *script_args: str,
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
) -> CommandResult:
    """
    Запускает Python-скрипт.

    Args:
        script_path: путь к скрипту
        *script_args: аргументы скрипта
        cwd: рабочая директория
        timeout: таймаут

    Returns:
        CommandResult с результатом
    """
    return run_command(
        sys.executable, script_path, *script_args,
        cwd=cwd,
        timeout=timeout,
    )


def run_make(
    target: str = "",
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
) -> CommandResult:
    """
    Запускает make.

    Args:
        target: цель make (по умолчанию default)
        cwd: рабочая директория
        timeout: таймаут

    Returns:
        CommandResult с результатом
    """
    args = ["make"]
    if target:
        args.append(target)
    return run_command(*args, cwd=cwd, timeout=timeout)


def run_docker_compose(
    action: str = "up",
    *extra_args: str,
    cwd: Optional[str] = None,
    timeout: Optional[float] = 300.0,
) -> CommandResult:
    """
    Запускает docker-compose.

    Args:
        action: действие (up, down, build, ps, logs и т.д.)
        *extra_args: дополнительные аргументы
        cwd: рабочая директория
        timeout: таймаут (по умолчанию 300с)

    Returns:
        CommandResult с результатом
    """
    return run_command(
        "docker-compose", action, *extra_args,
        cwd=cwd,
        timeout=timeout,
    )


def print_usage():
    """Выводит справку."""
    print("Использование: python command_runner.py [опции] <команда> [аргументы...]")
    print()
    print("Опции:")
    print("  --cwd <директория>     — рабочая директория (по умолчанию текущая)")
    print("  --timeout <сек>        — таймаут в секундах")
    print("  --no-capture           — вывод в реальном времени (не захватывать)")
    print("  --shell                — запускать через shell (для пайпов, >, |)")
    print("  --json                 — вывод результата в JSON")
    print("  --pytest <путь>        — запустить pytest (удобная обёртка)")
    print("  --script <путь>        — запустить Python-скрипт")
    print("  --help                 — эта справка")
    print()
    print("Примеры:")
    print("  python command_runner.py python -m pytest tests/")
    print("  python command_runner.py --cwd ../.. python -m pytest tests/")
    print("  python command_runner.py --timeout 30 python -m pytest tests/test_apply_patch.py -v")
    print("  python command_runner.py --pytest tests/test_apply_patch.py")
    print("  python command_runner.py --script src/tools/self_review.py --history logs/history.md")
    print("  python command_runner.py --shell 'ls -la | grep .py'")
    print("  python command_runner.py --json python -m pytest tests/")
    print()
    print("Как импорт в Python:")
    print("  from command_runner import run_command, run_pytest")
    print("  result = run_pytest('tests/test_apply_patch.py')")
    print("  print(result.summary())")


def main():
    if '--help' in sys.argv or '-h' in sys.argv:
        print_usage()
        sys.exit(0)

    args = sys.argv[1:]
    if not args:
        print_usage()
        sys.exit(1)

    # Парсим опции
    cwd = None
    timeout = None
    capture_output = True
    shell = False
    output_json = False
    use_pytest = False
    use_script = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '--cwd' and i + 1 < len(args):
            cwd = args[i + 1]
            i += 2
        elif arg == '--timeout' and i + 1 < len(args):
            timeout = float(args[i + 1])
            i += 2
        elif arg == '--no-capture':
            capture_output = False
            i += 1
        elif arg == '--shell':
            shell = True
            i += 1
        elif arg == '--json':
            output_json = True
            i += 1
        elif arg == '--pytest' and i + 1 < len(args):
            use_pytest = True
            # Следующий аргумент — путь к тестам
            test_path = args[i + 1]
            extra_args = args[i + 2:]
            result = run_pytest(test_path, *extra_args, cwd=cwd, timeout=timeout)
            _output_result(result, output_json)
            sys.exit(0 if result.success else 1)
        elif arg == '--script' and i + 1 < len(args):
            use_script = True
            script_path = args[i + 1]
            script_args = args[i + 2:]
            result = run_python_script(script_path, *script_args, cwd=cwd, timeout=timeout)
            _output_result(result, output_json)
            sys.exit(0 if result.success else 1)
        else:
            break

    # Оставшиеся аргументы — команда
    remaining = args[i:]
    if not remaining:
        print("Ошибка: не указана команда")
        print_usage()
        sys.exit(1)

    command = remaining[0]
    cmd_args = remaining[1:]

    result = run_command(
        command, *cmd_args,
        cwd=cwd,
        timeout=timeout,
        capture_output=capture_output,
        shell=shell,
    )

    _output_result(result, output_json)
    sys.exit(0 if result.success else 1)


def _output_result(result: CommandResult, as_json: bool):
    """Выводит результат в нужном формате."""
    if as_json:
        print(json.dumps({
            'command': result.command,
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'cwd': result.cwd,
            'duration_sec': result.duration_sec,
            'success': result.success,
            'error': result.error,
        }, ensure_ascii=False, indent=2))
    else:
        print(result.format())


if __name__ == '__main__':
    main()
