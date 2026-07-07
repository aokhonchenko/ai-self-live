#!/usr/bin/env python3
"""
Тесты для src/tools/command_runner.py — инструмента запуска команд.

Запуск: python -m pytest tests/test_command_runner.py -v
    или: python tests/test_command_runner.py

Создан: сессия 37 (2026-07-06)
Цель: проверить запуск команд, обработку ошибок, таймауты, обёртки.
"""

import sys
import os
import tempfile
import time
from pathlib import Path

# Добавляем src/tools в путь для импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'tools'))

from command_runner import (
    CommandResult,
    run_command,
    run_pytest,
    run_python_script,
)


# ─── Тесты CommandResult ───────────────────────────────────────────

class TestCommandResult:
    """Тесты dataclass CommandResult."""

    def test_success_property(self):
        result = CommandResult(
            command='echo hello', returncode=0,
            stdout='hello\n', stderr='',
            cwd='/tmp', duration_sec=0.1
        )
        assert result.success is True
        assert result.timed_out is False

    def test_failure_property(self):
        result = CommandResult(
            command='false', returncode=1,
            stdout='', stderr='',
            cwd='/tmp', duration_sec=0.1
        )
        assert result.success is False

    def test_timed_out_property(self):
        result = CommandResult(
            command='sleep 10', returncode=-1,
            stdout='', stderr='timeout',
            cwd='/tmp', duration_sec=5.0
        )
        assert result.timed_out is True
        assert result.success is False

    def test_error_property(self):
        result = CommandResult(
            command='nonexistent', returncode=-1,
            stdout='', stderr='',
            cwd='/tmp', duration_sec=0.1,
            error='Команда не найдена'
        )
        assert result.success is False
        assert result.error is not None

    def test_summary_success(self):
        result = CommandResult(
            command='echo hi', returncode=0,
            stdout='hi\n', stderr='',
            cwd='/tmp', duration_sec=0.05
        )
        summary = result.summary()
        assert '✅' in summary
        assert 'Успешно' in summary

    def test_summary_failure(self):
        result = CommandResult(
            command='false', returncode=1,
            stdout='', stderr='error',
            cwd='/tmp', duration_sec=0.05
        )
        summary = result.summary()
        assert '❌' in summary
        assert 'Ошибка' in summary

    def test_summary_timeout(self):
        result = CommandResult(
            command='sleep 60', returncode=-1,
            stdout='', stderr='timeout',
            cwd='/tmp', duration_sec=5.0
        )
        summary = result.summary()
        assert '⏱' in summary
        assert 'Таймаут' in summary

    def test_summary_error(self):
        result = CommandResult(
            command='bad_cmd', returncode=-1,
            stdout='', stderr='',
            cwd='/tmp', duration_sec=0.1,
            error='Команда не найдена'
        )
        summary = result.summary()
        assert '❌' in summary
        assert 'Ошибка запуска' in summary

    def test_format_basic(self):
        result = CommandResult(
            command='echo hello', returncode=0,
            stdout='hello\n', stderr='',
            cwd='/tmp', duration_sec=0.1
        )
        formatted = result.format()
        assert 'echo hello' in formatted
        assert 'hello' in formatted
        assert 'Успешно' in formatted

    def test_format_truncates_long_output(self):
        long_stdout = '\n'.join(f'line {i}' for i in range(100))
        result = CommandResult(
            command='cat bigfile', returncode=0,
            stdout=long_stdout, stderr='',
            cwd='/tmp', duration_sec=0.1
        )
        formatted = result.format(max_lines=10)
        # Должно быть не больше 10 строк + заголовок
        stdout_section = formatted.split('## stdout')[1] if '## stdout' in formatted else ''
        code_lines = [l for l in stdout_section.split('\n') if l.strip() and not l.startswith('##') and not l.startswith('```')]
        assert len(code_lines) <= 12  # 10 строк + возможно заголовок


# ─── Тесты run_command ─────────────────────────────────────────────

class TestRunCommand:
    """Тесты запуска команд."""

    def test_simple_command(self):
        """Запуск простой команды."""
        result = run_command(sys.executable, '-c', 'print("hello")')
        assert result.success is True
        assert 'hello' in result.stdout

    def test_command_with_args(self):
        """Команда с аргументами."""
        result = run_command(sys.executable, '-c', 'import sys; print(len(sys.argv))', 'a', 'b', 'c')
        assert result.success is True
        # argv[0] = -c, argv[1] = a, argv[2] = b, argv[3] = c → len = 4
        assert '4' in result.stdout.strip()

    def test_failing_command(self):
        """Команда с ненулевым кодом возврата."""
        result = run_command(sys.executable, '-c', 'exit(42)')
        assert result.success is False
        assert result.returncode == 42

    def test_nonexistent_command(self):
        """Несуществующая команда."""
        result = run_command('/nonexistent/command_xyz123')
        assert result.success is False
        assert result.error is not None
        assert 'не найдена' in result.error or 'not found' in result.error.lower()

    def test_timeout(self):
        """Таймаут команды."""
        result = run_command(sys.executable, '-c', 'import time; time.sleep(10)', timeout=0.5)
        assert result.timed_out is True
        assert result.returncode == -1

    def test_cwd(self):
        """Рабочая директория."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_command(sys.executable, '-c', 'import os; print(os.getcwd())', cwd=tmpdir)
            assert result.success is True
            assert tmpdir in result.stdout

    def test_shell_mode(self):
        """Запуск через shell."""
        result = run_command('echo', 'hello', 'world', shell=True)
        assert result.success is True
        assert 'hello world' in result.stdout

    def test_env_vars(self):
        """Переменные окружения."""
        result = run_command(
            sys.executable, '-c', 'import os; print(os.environ.get("TEST_VAR", "NOT_SET"))',
            env={'TEST_VAR': 'custom_value'}
        )
        assert result.success is True
        assert 'custom_value' in result.stdout

    def test_stderr_capture(self):
        """Захват stderr."""
        result = run_command(sys.executable, '-c', 'import sys; sys.stderr.write("error msg")')
        assert result.success is True
        assert 'error msg' in result.stderr

    def test_no_capture(self):
        """Без захвата вывода (просто проверяем, что не падает)."""
        result = run_command(sys.executable, '-c', 'print("no capture")', capture_output=False)
        # При no capture stdout будет пустым, но команда выполнится
        assert result.success is True


# ─── Тесты run_pytest ──────────────────────────────────────────────

class TestRunPytest:
    """Тесты обёртки pytest."""

    def test_run_pytest_on_self(self):
        """Запуск pytest на самом command_runner (должен пройти)."""
        # Создаём минимальный тест, который точно проходит
        test_code = """
def test_always_passes():
    assert 1 + 1 == 2
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, 'test_dummy.py')
            with open(test_file, 'w') as f:
                f.write(test_code)
            result = run_pytest(test_file, cwd=tmpdir, timeout=10)
            assert result.success is True
            assert '1 passed' in result.stdout

    def test_run_pytest_failing(self):
        """Запуск pytest на падающем тесте."""
        test_code = """
def test_always_fails():
    assert 1 + 1 == 3
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, 'test_fail.py')
            with open(test_file, 'w') as f:
                f.write(test_code)
            result = run_pytest(test_file, cwd=tmpdir, timeout=10)
            assert result.success is False
            assert '1 failed' in result.stdout

    def test_run_pytest_no_tests(self):
        """Запуск pytest без тестов."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_pytest(tmpdir, cwd=tmpdir, timeout=10)
            # pytest возвращает код 5 если тестов не найдено
            assert result.returncode == 5


# ─── Тесты run_python_script ───────────────────────────────────────

class TestRunPythonScript:
    """Тесты обёртки для Python-скриптов."""

    def test_run_script(self):
        """Запуск Python-скрипта."""
        script_code = 'print("script output")'
        with tempfile.TemporaryDirectory() as tmpdir:
            script_file = os.path.join(tmpdir, 'test_script.py')
            with open(script_file, 'w') as f:
                f.write(script_code)
            result = run_python_script(script_file, cwd=tmpdir)
            assert result.success is True
            assert 'script output' in result.stdout

    def test_run_script_with_args(self):
        """Запуск скрипта с аргументами."""
        script_code = 'import sys; print(" ".join(sys.argv[1:]))'
        with tempfile.TemporaryDirectory() as tmpdir:
            script_file = os.path.join(tmpdir, 'test_args.py')
            with open(script_file, 'w') as f:
                f.write(script_code)
            result = run_python_script(script_file, 'arg1', 'arg2', cwd=tmpdir)
            assert result.success is True
            assert 'arg1 arg2' in result.stdout

    def test_run_script_failing(self):
        """Запуск падающего скрипта."""
        script_code = 'raise RuntimeError("test error")'
        with tempfile.TemporaryDirectory() as tmpdir:
            script_file = os.path.join(tmpdir, 'test_fail.py')
            with open(script_file, 'w') as f:
                f.write(script_code)
            result = run_python_script(script_file, cwd=tmpdir)
            assert result.success is False
            assert result.returncode != 0


# ─── Запуск ────────────────────────────────────────────────────────

def run_tests():
    """Запуск тестов без pytest (fallback)."""
    test_classes = [
        TestCommandResult,
        TestRunCommand,
        TestRunPytest,
        TestRunPythonScript,
    ]

    passed = 0
    failed = 0
    errors = []

    for cls in test_classes:
        instance = cls()
        for method_name in sorted(dir(instance)):
            if not method_name.startswith('test_'):
                continue
            method = getattr(instance, method_name)
            test_name = f"{cls.__name__}.{method_name}"
            try:
                method()
                passed += 1
                print(f"  ✅ {test_name}")
            except Exception as e:
                failed += 1
                errors.append((test_name, e))
                print(f"  ❌ {test_name}: {e}")

    print(f"\n{'='*50}")
    print(f"Результат: {passed} прошли, {failed} упали")

    if errors:
        print(f"\nОшибки:")
        for name, err in errors:
            print(f"  {name}: {err}")

    return failed == 0


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
