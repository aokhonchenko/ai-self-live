"""Tests for run_command, run_pytest, run_python_script tools."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.tools._runtime import ToolError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_tool(module_name: str):
    """Import a tool module by name from src.tools."""
    if module_name == "run_command":
        from src.tools.run_command import tool as mod
    elif module_name == "run_pytest":
        from src.tools.run_pytest import tool as mod
    elif module_name == "run_python_script":
        from src.tools.run_python_script import tool as mod
    else:
        raise ValueError(f"unknown tool: {module_name}")
    return mod


def _write_minimal_tool_dir(root: Path, tool_name: str) -> Path:
    """Create a minimal tool directory with tool.py and __init__.py."""
    tool_dir = root / "src" / "tools" / tool_name
    tool_dir.mkdir(parents=True, exist_ok=True)
    init = tool_dir / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")
    return tool_dir


# ---------------------------------------------------------------------------
# run_command — schema & passport
# ---------------------------------------------------------------------------

class TestRunCommandSchema:
    """Проверка схемы и паспорта run_command."""

    def test_schema_has_required_fields(self):
        mod = _load_tool("run_command")
        schema = mod.schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "run_command"
        params = schema["function"]["parameters"]["properties"]
        assert "command" in params
        assert params["command"]["type"] == "string"
        assert "cwd" in params
        assert "timeout" in params

    def test_schema_command_is_required(self):
        mod = _load_tool("run_command")
        schema = mod.schema()
        assert "command" in schema["function"]["parameters"]["required"]

    def test_passport_mentions_shell_command(self):
        mod = _load_tool("run_command")
        p = mod.passport()
        assert "run_command" in p
        assert "shell" in p.lower() or "команду" in p


# ---------------------------------------------------------------------------
# run_command — handle (actual execution)
# ---------------------------------------------------------------------------

class TestRunCommandHandle:
    """Проверка выполнения команд через run_command."""

    def test_echo_command_returns_output(self, tmp_path):
        mod = _load_tool("run_command")
        result = mod.handle(tmp_path, {"command": "echo hello"})
        assert result["returncode"] == 0
        assert "hello" in result["stdout"]

    def test_command_with_nonzero_returncode(self, tmp_path):
        mod = _load_tool("run_command")
        # cmd /c exit 42 on Windows
        exit_cmd = "cmd /c exit 42" if sys.platform == "win32" else "false"
        result = mod.handle(tmp_path, {"command": exit_cmd})
        assert result["returncode"] != 0

    def test_empty_command_raises_tool_error(self, tmp_path):
        mod = _load_tool("run_command")
        with pytest.raises(ToolError, match="command must be non-empty"):
            mod.handle(tmp_path, {"command": ""})

    def test_whitespace_only_command_raises_tool_error(self, tmp_path):
        mod = _load_tool("run_command")
        with pytest.raises(ToolError, match="command must be non-empty"):
            mod.handle(tmp_path, {"command": "   "})

    def test_command_with_custom_cwd(self, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        mod = _load_tool("run_command")
        # pwd / cd to show we're in subdir
        if sys.platform == "win32":
            cmd = "cd"
        else:
            cmd = "pwd"
        result = mod.handle(tmp_path, {"command": cmd, "cwd": "sub"})
        assert result["returncode"] == 0

    def test_command_timeout_raises_error(self, tmp_path):
        mod = _load_tool("run_command")
        # Use Python sleep for reliable cross-platform timeout
        if sys.platform == "win32":
            sleep_cmd = 'cmd /c python -c "import time; time.sleep(10)"'
        else:
            sleep_cmd = "python -c 'import time; time.sleep(10)'"
        result = mod.handle(tmp_path, {"command": sleep_cmd, "timeout": 0.1})
        assert result.get("timed_out") is True
        assert result["returncode"] == -1

    def test_command_returns_duration(self, tmp_path):
        mod = _load_tool("run_command")
        result = mod.handle(tmp_path, {"command": "echo done"})
        assert "duration_seconds" in result
        assert isinstance(result["duration_seconds"], float)
        assert result["duration_seconds"] > 0

    def test_command_output_truncation_flag(self, tmp_path):
        mod = _load_tool("run_command")
        # Generate a large output
        if sys.platform == "win32":
            cmd = 'cmd /c python -c "print(\'x\' * 30000)"'
        else:
            cmd = "python -c \"print('x' * 30000)\""
        result = mod.handle(tmp_path, {"command": cmd})
        assert result["stdout_truncated"] is True

    def test_stderr_is_captured(self, tmp_path):
        mod = _load_tool("run_command")
        if sys.platform == "win32":
            cmd = 'cmd /c python -c "import sys; sys.stderr.write(\'err\')"'
        else:
            cmd = "python -c \"import sys; sys.stderr.write('err')\""
        result = mod.handle(tmp_path, {"command": cmd})
        assert "err" in result["stderr"]


# ---------------------------------------------------------------------------
# run_pytest — schema & passport
# ---------------------------------------------------------------------------

class TestRunPytestSchema:
    """Проверка схемы и паспорта run_pytest."""

    def test_schema_has_required_fields(self):
        mod = _load_tool("run_pytest")
        schema = mod.schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "run_pytest"
        params = schema["function"]["parameters"]["properties"]
        assert "test_path" in params
        assert "args" in params
        assert "cwd" in params
        assert "timeout" in params

    def test_passport_mentions_pytest(self):
        mod = _load_tool("run_pytest")
        p = mod.passport()
        assert "run_pytest" in p
        assert "pytest" in p


# ---------------------------------------------------------------------------
# run_pytest — handle (actual execution)
# ---------------------------------------------------------------------------

class TestRunPytestHandle:
    """Проверка выполнения pytest через run_pytest."""

    def test_run_pytest_runs_a_simple_test(self, tmp_path):
        mod = _load_tool("run_pytest")
        # Create a simple test file
        test_file = tmp_path / "test_simple.py"
        test_file.write_text("def test_pass():\n    assert True\n", encoding="utf-8")
        result = mod.handle(tmp_path, {"test_path": str(test_file)})
        assert result["returncode"] == 0
        assert "1 passed" in result["stdout"]

    def test_run_pytest_fails_on_failing_test(self, tmp_path):
        mod = _load_tool("run_pytest")
        test_file = tmp_path / "test_fail.py"
        test_file.write_text("def test_fail():\n    assert False\n", encoding="utf-8")
        result = mod.handle(tmp_path, {"test_path": str(test_file)})
        assert result["returncode"] != 0
        assert "FAILED" in result["stdout"] or "failed" in result["stdout"].lower()

    def test_run_pytest_with_extra_args(self, tmp_path):
        mod = _load_tool("run_pytest")
        test_file = tmp_path / "test_simple.py"
        test_file.write_text("def test_pass():\n    assert True\n", encoding="utf-8")
        result = mod.handle(tmp_path, {"test_path": str(test_file), "args": ["-v"]})
        assert result["returncode"] == 0
        assert "test_simple.py::test_pass" in result["stdout"]

    def test_run_pytest_timeout(self, tmp_path):
        mod = _load_tool("run_pytest")
        test_file = tmp_path / "test_slow.py"
        if sys.platform == "win32":
            test_file.write_text(
                "import time\ndef test_slow():\n    time.sleep(10)\n",
                encoding="utf-8",
            )
        else:
            test_file.write_text(
                "import time\ndef test_slow():\n    time.sleep(10)\n",
                encoding="utf-8",
            )
        result = mod.handle(tmp_path, {"test_path": str(test_file), "timeout": 0.1})
        assert result.get("timed_out") is True


# ---------------------------------------------------------------------------
# run_python_script — schema & passport
# ---------------------------------------------------------------------------

class TestRunPythonScriptSchema:
    """Проверка схемы и паспорта run_python_script."""

    def test_schema_has_required_fields(self):
        mod = _load_tool("run_python_script")
        schema = mod.schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "run_python_script"
        params = schema["function"]["parameters"]["properties"]
        assert "script_path" in params
        assert "script_args" in params
        assert "cwd" in params
        assert "timeout" in params

    def test_schema_script_path_is_required(self):
        mod = _load_tool("run_python_script")
        schema = mod.schema()
        assert "script_path" in schema["function"]["parameters"]["required"]

    def test_passport_mentions_script(self):
        mod = _load_tool("run_python_script")
        p = mod.passport()
        assert "run_python_script" in p
        assert "скрипт" in p or "script" in p.lower()


# ---------------------------------------------------------------------------
# run_python_script — handle (actual execution)
# ---------------------------------------------------------------------------

class TestRunPythonScriptHandle:
    """Проверка выполнения Python-скриптов через run_python_script."""

    def test_run_script_executes_and_returns_output(self, tmp_path):
        mod = _load_tool("run_python_script")
        script = tmp_path / "hello.py"
        script.write_text('print("hello from script")\n', encoding="utf-8")
        result = mod.handle(tmp_path, {"script_path": "hello.py"})
        assert result["returncode"] == 0
        assert "hello from script" in result["stdout"]

    def test_run_script_with_arguments(self, tmp_path):
        mod = _load_tool("run_python_script")
        script = tmp_path / "args_script.py"
        script.write_text(
            "import sys; print(' '.join(sys.argv[1:]))\n",
            encoding="utf-8",
        )
        result = mod.handle(tmp_path, {
            "script_path": "args_script.py",
            "script_args": ["foo", "bar"],
        })
        assert result["returncode"] == 0
        assert "foo bar" in result["stdout"]

    def test_run_script_missing_file_raises_tool_error(self, tmp_path):
        mod = _load_tool("run_python_script")
        with pytest.raises(ToolError, match="script does not exist"):
            mod.handle(tmp_path, {"script_path": "missing.py"})

    def test_run_script_directory_raises_tool_error(self, tmp_path):
        mod = _load_tool("run_python_script")
        dir_path = tmp_path / "not_a_script"
        dir_path.mkdir()
        with pytest.raises(ToolError, match="script path is not a file"):
            mod.handle(tmp_path, {"script_path": "not_a_script"})

    def test_run_script_nonzero_exit_code(self, tmp_path):
        mod = _load_tool("run_python_script")
        script = tmp_path / "exit_script.py"
        script.write_text("import sys; sys.exit(42)\n", encoding="utf-8")
        result = mod.handle(tmp_path, {"script_path": "exit_script.py"})
        assert result["returncode"] == 42

    def test_run_script_timeout(self, tmp_path):
        mod = _load_tool("run_python_script")
        script = tmp_path / "slow_script.py"
        if sys.platform == "win32":
            script.write_text(
                "import time; time.sleep(10)\n",
                encoding="utf-8",
            )
        else:
            script.write_text(
                "import time; time.sleep(10)\n",
                encoding="utf-8",
            )
        result = mod.handle(tmp_path, {"script_path": "slow_script.py", "timeout": 0.1})
        assert result.get("timed_out") is True

    def test_run_script_empty_script_args(self, tmp_path):
        mod = _load_tool("run_python_script")
        script = tmp_path / "no_args.py"
        script.write_text('print("no args")\n', encoding="utf-8")
        result = mod.handle(tmp_path, {"script_path": "no_args.py", "script_args": []})
        assert result["returncode"] == 0
        assert "no args" in result["stdout"]

    def test_run_script_invalid_script_args_type_raises(self, tmp_path):
        mod = _load_tool("run_python_script")
        script = tmp_path / "hello.py"
        script.write_text('print("hi")\n', encoding="utf-8")
        with pytest.raises(ToolError, match="script_args must be an array"):
            mod.handle(tmp_path, {"script_path": "hello.py", "script_args": "not-a-list"})


# ---------------------------------------------------------------------------
# Cross-cutting: all three tools share command_result behavior
# ---------------------------------------------------------------------------

class TestSharedCommandResultBehavior:
    """Проверка, что все три инструмента корректно используют command_result."""

    def test_all_tools_include_duration(self, tmp_path):
        """Все три инструмента должны возвращать duration_seconds."""
        for name in ("run_command", "run_pytest", "run_python_script"):
            mod = _load_tool(name)
            if name == "run_command":
                result = mod.handle(tmp_path, {"command": "echo ok"})
            elif name == "run_pytest":
                tf = tmp_path / "test_dur.py"
                tf.write_text("def test_x(): pass\n", encoding="utf-8")
                result = mod.handle(tmp_path, {"test_path": str(tf)})
            else:
                sf = tmp_path / "dur.py"
                sf.write_text("pass\n", encoding="utf-8")
                result = mod.handle(tmp_path, {"script_path": "dur.py"})
            assert "duration_seconds" in result, f"{name} missing duration_seconds"
            assert isinstance(result["duration_seconds"], float)

    def test_all_tools_include_cwd_in_result(self, tmp_path):
        """Все три инструмента должны возвращать cwd."""
        for name in ("run_command", "run_pytest", "run_python_script"):
            mod = _load_tool(name)
            if name == "run_command":
                result = mod.handle(tmp_path, {"command": "echo ok"})
            elif name == "run_pytest":
                tf = tmp_path / "test_cwd.py"
                tf.write_text("def test_x(): pass\n", encoding="utf-8")
                result = mod.handle(tmp_path, {"test_path": str(tf)})
            else:
                sf = tmp_path / "cwd.py"
                sf.write_text("pass\n", encoding="utf-8")
                result = mod.handle(tmp_path, {"script_path": "cwd.py"})
            assert "cwd" in result, f"{name} missing cwd"
            assert isinstance(result["cwd"], str)

    def test_all_tools_include_returncode(self, tmp_path):
        """Все три инструмента должны возвращать returncode."""
        for name in ("run_command", "run_pytest", "run_python_script"):
            mod = _load_tool(name)
            if name == "run_command":
                result = mod.handle(tmp_path, {"command": "echo ok"})
            elif name == "run_pytest":
                tf = tmp_path / "test_rc.py"
                tf.write_text("def test_x(): pass\n", encoding="utf-8")
                result = mod.handle(tmp_path, {"test_path": str(tf)})
            else:
                sf = tmp_path / "rc.py"
                sf.write_text("pass\n", encoding="utf-8")
                result = mod.handle(tmp_path, {"script_path": "rc.py"})
            assert "returncode" in result, f"{name} missing returncode"
            assert isinstance(result["returncode"], int)
