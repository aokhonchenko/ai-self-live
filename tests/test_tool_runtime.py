import subprocess
import sys
import time

from src.tools._runtime import command_result, subprocess_env


def test_subprocess_env_disables_interactive_git_prompts(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "C:/other/.venv")

    env = subprocess_env()

    assert "VIRTUAL_ENV" not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_EDITOR"] == "true"
    assert env["GCM_INTERACTIVE"] == "Never"


def test_command_result_timeout_kills_shell_child_process(tmp_path):
    marker = tmp_path / "child-survived.txt"
    child_code = (
        "import pathlib, time; "
        "time.sleep(2); "
        f"pathlib.Path({str(marker)!r}).write_text('alive', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(30)"
    )
    command = subprocess.list2cmdline([sys.executable, "-c", parent_code])

    result = command_result(command, tmp_path, 0.5, shell=True)
    time.sleep(3)

    assert result["returncode"] == -1
    assert result["timed_out"] is True
    assert "timed out" in result["stderr"]
    assert not marker.exists()
