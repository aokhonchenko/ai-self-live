import io

import pytest

from scripts import command_runners


def test_configure_utf8_stdio_reconfigures_available_streams(monkeypatch):
    calls = []

    class FakeStream:
        def reconfigure(self, encoding, errors):
            calls.append((encoding, errors))

    monkeypatch.setattr(command_runners.sys, "stdout", FakeStream())
    monkeypatch.setattr(command_runners.sys, "stderr", FakeStream())

    command_runners.configure_utf8_stdio()

    assert calls == [("utf-8", "replace"), ("utf-8", "replace")]

def test_streaming_runner_streams_output_and_sanitizes_env(monkeypatch, capsys, tmp_path):
    calls = []

    class FakeProcess:
        def __init__(self):
            self.stdout = io.StringIO("first line\nsecond line\n")

        def poll(self):
            return 0

        def wait(self):
            return 0

    def fake_popen(
        args,
        cwd,
        env,
        text,
        encoding,
        errors,
        stdout,
        stderr,
        bufsize,
    ):
        calls.append((args, cwd, env, text, encoding, errors, stdout, stderr, bufsize))
        return FakeProcess()

    monkeypatch.setenv("VIRTUAL_ENV", "C:/old/project/.venv")
    monkeypatch.setattr(command_runners.subprocess, "Popen", fake_popen)

    result = command_runners.streaming_runner(["cmd", "arg"], tmp_path)

    captured = capsys.readouterr()
    assert result == command_runners.CommandResult(0, "first line\nsecond line\n", "")
    assert "[cmd]" in captured.out
    assert "first line" in captured.out
    args, cwd, env, text, encoding, errors, stdout, stderr, bufsize = calls[0]
    assert args == ["cmd", "arg"]
    assert cwd == tmp_path
    assert "VIRTUAL_ENV" not in env
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert text is True
    assert encoding == "utf-8"
    assert errors == "replace"
    assert stdout is command_runners.subprocess.PIPE
    assert stderr is command_runners.subprocess.STDOUT
    assert bufsize == 1


def test_default_runner_uses_utf8_with_replacement(monkeypatch, tmp_path):
    calls = []

    class FakeCompleted:
        returncode = 0
        stdout = "готово\n"
        stderr = ""

    def fake_run(args, cwd, env, text, encoding, errors, capture_output):
        calls.append((args, cwd, env, text, encoding, errors, capture_output))
        return FakeCompleted()

    monkeypatch.setattr(command_runners.subprocess, "run", fake_run)

    result = command_runners.default_runner(["cmd"], tmp_path)

    assert result == command_runners.CommandResult(0, "готово\n", "")
    args, cwd, env, text, encoding, errors, capture_output = calls[0]
    assert args == ["cmd"]
    assert cwd == tmp_path
    assert text is True
    assert encoding == "utf-8"
    assert errors == "replace"
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert capture_output is True


def test_streaming_runner_reports_missing_stdout(monkeypatch, tmp_path):
    class FakeProcess:
        stdout = None

    def fake_popen(
        args,
        cwd,
        env,
        text,
        encoding,
        errors,
        stdout,
        stderr,
        bufsize,
    ):
        return FakeProcess()

    monkeypatch.setattr(command_runners.subprocess, "Popen", fake_popen)

    with pytest.raises(command_runners.CommandExecutionError, match="did not expose stdout"):
        command_runners.run_streaming_command(["cmd"], tmp_path)


def test_streaming_runner_prints_heartbeat_for_silent_process(monkeypatch, capsys, tmp_path):
    class FakeProcess:
        def __init__(self):
            self.stdout = io.StringIO("")
            self.poll_count = 0

        def poll(self):
            self.poll_count += 1
            if self.poll_count == 1:
                return None
            return 0

        def wait(self):
            return 0

    def fake_popen(
        args,
        cwd,
        env,
        text,
        encoding,
        errors,
        stdout,
        stderr,
        bufsize,
    ):
        return FakeProcess()

    times = iter([0.0, 31.0])
    monkeypatch.setattr(command_runners.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(command_runners.time, "monotonic", lambda: next(times))

    result = command_runners.run_streaming_command(["cmd"], tmp_path, heartbeat_seconds=30)

    captured = capsys.readouterr()
    assert result == command_runners.CommandResult(0, "", "")
    assert "[wait] command is still running" in captured.out
