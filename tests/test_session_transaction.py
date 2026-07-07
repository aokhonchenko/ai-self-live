import shutil
from pathlib import Path

import pytest

from scripts import session_transaction


class FakeRunner:
    def __init__(
        self,
        root: Path,
        fail_agent: bool = False,
        fail_checks: bool = False,
        create_external_project: bool = False,
    ):
        self.root = root
        self.fail_agent = fail_agent
        self.fail_checks = fail_checks
        self.create_external_project = create_external_project
        self.commands = []
        self.worktree = None
        self.branch = None

    def __call__(self, args, cwd):
        args = list(args)
        cwd = Path(cwd)
        self.commands.append((args, cwd))

        if args[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return session_transaction.CommandResult(0, f"{self.root}\n", "")

        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return session_transaction.CommandResult(0, "abc123\n", "")

        if args[:3] == ["git", "status", "--porcelain"]:
            if cwd == self.root:
                return session_transaction.CommandResult(0, "", "")
            return session_transaction.CommandResult(0, " M logs/history.md\n", "")

        if args[:3] == ["git", "branch", "--show-current"]:
            return session_transaction.CommandResult(0, "main\n", "")

        if args[:3] == ["git", "check-ignore", "-q"]:
            ignored = len(args) >= 4 and args[3] == "projects/foundation-finance"
            return session_transaction.CommandResult(0 if ignored else 1, "", "")

        if args[:3] == ["git", "worktree", "add"]:
            self.branch = args[4]
            self.worktree = Path(args[5])
            shutil.copytree(self.root, self.worktree, ignore=shutil.ignore_patterns(".git", ".session.lock"))
            return session_transaction.CommandResult(0, "", "")

        if args[:3] == ["git", "worktree", "remove"]:
            target = Path(args[-1])
            if target.exists():
                shutil.rmtree(target)
            return session_transaction.CommandResult(0, "", "")

        if args[:2] == ["git", "branch"]:
            return session_transaction.CommandResult(0, "", "")

        if args[:3] == ["git", "add", "-A"]:
            return session_transaction.CommandResult(0, "", "")

        if args[:3] == ["git", "commit", "-m"]:
            return session_transaction.CommandResult(0, "committed\n", "")

        if args[:3] == ["git", "merge", "--ff-only"]:
            return session_transaction.CommandResult(0, "merged\n", "")

        if args[0].endswith("python") or args[0].endswith("python.exe"):
            if len(args) >= 3 and args[2] == "pytest":
                if self.fail_checks:
                    return session_transaction.CommandResult(1, "", "tests failed")
                return session_transaction.CommandResult(0, "tests ok", "")
            if self.fail_agent:
                return session_transaction.CommandResult(7, "", "agent failed")
            (cwd / "state").mkdir(exist_ok=True)
            (cwd / "logs").mkdir(exist_ok=True)
            (cwd / "state" / "last_session.md").write_text("done\n", encoding="utf-8")
            (cwd / "logs" / "history.md").write_text("done\n", encoding="utf-8")
            if self.create_external_project:
                project = cwd / "projects" / "foundation-finance"
                project.mkdir(parents=True, exist_ok=True)
                (project / ".git").mkdir(exist_ok=True)
                (project / "README.md").write_text("created\n", encoding="utf-8")
            return session_transaction.CommandResult(0, "agent ok", "")

        return session_transaction.CommandResult(0, "", "")


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "pet"
    root.mkdir()
    (root / "scripts").mkdir()
    (root / "state").mkdir()
    (root / "logs").mkdir()
    (root / "scripts" / "run_session.py").write_text("", encoding="utf-8")
    (root / "state" / "session_counter.txt").write_text("3\n", encoding="utf-8")
    (root / "state" / "last_session.md").write_text("previous\n", encoding="utf-8")
    (root / "logs" / "history.md").write_text("history\n", encoding="utf-8")
    return root


def test_lock_file_creates_and_removes_lock(tmp_path):
    with session_transaction.lock_file(tmp_path) as lock_path:
        assert lock_path.exists()
        assert "pid=" in lock_path.read_text(encoding="utf-8")

    assert not (tmp_path / ".session.lock").exists()


def test_lock_file_rejects_existing_lock(tmp_path):
    (tmp_path / ".session.lock").write_text("pid=1\n", encoding="utf-8")

    with pytest.raises(session_transaction.TransactionError, match="session lock already exists"):
        with session_transaction.lock_file(tmp_path):
            pass


def test_ensure_git_repo_rejects_nested_repository(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    def runner(args, cwd):
        return session_transaction.CommandResult(0, f"{tmp_path}\n", "")

    with pytest.raises(session_transaction.TransactionError, match="expected git root"):
        session_transaction.ensure_git_repo(root, runner)


def test_file_size_policy_fails_for_large_text_file(tmp_path):
    path = tmp_path / "large.md"
    path.write_text("x\n" * 501, encoding="utf-8")

    with pytest.raises(session_transaction.TransactionError, match="must be decomposed"):
        session_transaction.ensure_file_size_policy(tmp_path, max_lines=500)


def test_archive_last_session_copies_current_last_session(tmp_path):
    worktree = tmp_path / "worktree"
    (worktree / "state").mkdir(parents=True)
    (worktree / "state" / "last_session.md").write_text("итог\n", encoding="utf-8")

    archived = session_transaction.archive_last_session(worktree, 7)

    assert archived == worktree / ".sessions" / "session-0007.md"
    assert archived.read_text(encoding="utf-8") == "итог\n"

def test_run_transaction_applies_successful_session(tmp_path):
    root = make_root(tmp_path)
    runs_dir = tmp_path / "runs"
    runner = FakeRunner(root)

    commit = session_transaction.run_transaction(
        root=root,
        agent_command="agent --ok",
        runs_dir=runs_dir,
        runner=runner,
    )

    assert commit == "abc123"
    commands = [command for command, _ in runner.commands]
    assert ["git", "merge", "--ff-only", "session/0003"] in commands
    assert ["git", "branch", "-d", "session/0003"] in commands
    assert not (runs_dir / "session-0003").exists()
    assert (runs_dir / "snapshots" / "session-0003-applied").exists()
    archived = runs_dir / "snapshots" / "session-0003-applied" / ".sessions" / "session-0003.md"
    assert archived.read_text(encoding="utf-8") == "done\n"


def test_run_transaction_rolls_back_failed_agent(tmp_path):
    root = make_root(tmp_path)
    runs_dir = tmp_path / "runs"
    runner = FakeRunner(root, fail_agent=True)

    with pytest.raises(session_transaction.TransactionError, match="agent session failed"):
        session_transaction.run_transaction(
            root=root,
            agent_command="agent --fail",
            runs_dir=runs_dir,
            runner=runner,
        )

    commands = [command for command, _ in runner.commands]
    assert ["git", "merge", "--ff-only", "session/0003"] not in commands
    assert ["git", "branch", "-D", "session/0003"] in commands
    assert not (runs_dir / "session-0003").exists()
    assert (runs_dir / "snapshots" / "session-0003-failed").exists()
    assert (root / "state" / "session_failure_tail.txt").read_text(encoding="utf-8") == (
        "agent session failed: agent failed\n"
    )
    last_session = (root / "state" / "last_session.md").read_text(encoding="utf-8")
    assert "Сессия была прервана" in last_session
    assert "state/session_failure_tail.txt" in last_session


def test_run_transaction_uses_default_agent_command(tmp_path):
    root = make_root(tmp_path)
    runs_dir = tmp_path / "runs"
    runner = FakeRunner(root)

    commit = session_transaction.run_transaction(
        root=root,
        agent_command="",
        runs_dir=runs_dir,
        runner=runner,
    )

    assert commit == "abc123"
    commands = [command for command, _ in runner.commands]
    agent_commands = [command for command in commands if "run_agent.py" in " ".join(command)]
    assert agent_commands


def test_main_returns_one_on_transaction_error(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        session_transaction.sys,
        "argv",
        ["session_transaction.py", "--root", str(tmp_path)],
    )

    result = session_transaction.main()

    captured = capsys.readouterr()
    assert result == 1
    assert "Transaction failed" in captured.err


def test_default_runner_wraps_subprocess_result(monkeypatch, tmp_path):
    class Completed:
        returncode = 2
        stdout = "out"
        stderr = "err"

    calls = []

    def fake_run(args, cwd, env, text, encoding, errors, capture_output):
        calls.append((args, cwd, env, text, encoding, errors, capture_output))
        return Completed()

    monkeypatch.setenv("VIRTUAL_ENV", "C:/old/project/.venv")
    from scripts import command_runners

    monkeypatch.setattr(command_runners.subprocess, "run", fake_run)

    result = session_transaction.default_runner(["cmd"], tmp_path)

    assert result == session_transaction.CommandResult(2, "out", "err")
    args, cwd, env, text, encoding, errors, capture_output = calls[0]
    assert args == ["cmd"]
    assert cwd == tmp_path
    assert "VIRTUAL_ENV" not in env
    assert text is True
    assert encoding == "utf-8"
    assert errors == "replace"
    assert capture_output is True




def test_record_interrupted_session_writes_only_last_50_lines(tmp_path):
    root = make_root(tmp_path)
    details = "\n".join(f"line {number}" for number in range(75))

    path = session_transaction.record_interrupted_session(root, details)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 50
    assert lines[0] == "line 25"
    assert lines[-1] == "line 74"
    assert "state/session_failure_tail.txt" in (root / "state" / "last_session.md").read_text(encoding="utf-8")

def test_command_failure_details_keeps_tail_for_long_output():
    result = session_transaction.CommandResult(1, "\n".join(str(i) for i in range(50)), "")

    details = session_transaction.command_failure_details(result, max_lines=3)

    assert "47" in details
    assert "49" in details
    assert "earlier output lines omitted" in details
    assert "0\n" not in details

def test_run_checked_reports_failure_details(tmp_path):
    def runner(args, cwd):
        return session_transaction.CommandResult(9, "", "bad things")

    with pytest.raises(session_transaction.TransactionError, match="bad things"):
        session_transaction.run_checked(runner, ["cmd"], tmp_path, "doing work")


def test_run_checked_reports_exit_code_without_details(tmp_path):
    def runner(args, cwd):
        return session_transaction.CommandResult(9, "", "")

    with pytest.raises(session_transaction.TransactionError, match="exit code 9"):
        session_transaction.run_checked(runner, ["cmd"], tmp_path, "doing work")


def test_ensure_clean_worktree_rejects_dirty_status(tmp_path):
    def runner(args, cwd):
        if args[:3] == ["git", "status", "--porcelain"]:
            return session_transaction.CommandResult(0, " M file.txt\n", "")
        return session_transaction.CommandResult(0, "", "")

    with pytest.raises(session_transaction.TransactionError, match="must be clean"):
        session_transaction.ensure_clean_worktree(tmp_path, runner)


def test_current_branch_rejects_detached_head(tmp_path):
    def runner(args, cwd):
        return session_transaction.CommandResult(0, "\n", "")

    with pytest.raises(session_transaction.TransactionError, match="not detached HEAD"):
        session_transaction.current_branch(tmp_path, runner)


def test_lock_file_tolerates_missing_lock_during_cleanup(tmp_path):
    with session_transaction.lock_file(tmp_path) as lock_path:
        lock_path.unlink()

    assert not (tmp_path / ".session.lock").exists()


def test_default_runs_dir_is_inside_root(tmp_path):
    root = tmp_path / "pet"

    assert session_transaction.default_runs_dir(root) == root / "runs"


def test_create_worktree_rejects_existing_directory(tmp_path):
    root = tmp_path / "pet"
    runs_dir = tmp_path / "runs"
    (runs_dir / "session-0004").mkdir(parents=True)

    with pytest.raises(session_transaction.TransactionError, match="already exists"):
        session_transaction.create_worktree(root, runs_dir, 4)


def test_run_checks_reports_failure(tmp_path):
    def runner(args, cwd):
        return session_transaction.CommandResult(1, "", "check failed")

    with pytest.raises(session_transaction.TransactionError, match="check failed"):
        session_transaction.run_checks(tmp_path, ["check"], runner)


def test_required_session_files_reports_missing_files(tmp_path):
    with pytest.raises(session_transaction.TransactionError, match="required session files"):
        session_transaction.ensure_required_session_files(tmp_path)


def test_find_oversized_files_skips_binary_and_sensitive_dirs(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "huge.txt").write_text("x\n" * 600, encoding="utf-8")
    (tmp_path / "runs" / "session-0001").mkdir(parents=True)
    (tmp_path / "runs" / "session-0001" / "huge.txt").write_text("x\n" * 600, encoding="utf-8")
    (tmp_path / "bad.bin").write_bytes(b"\xff\xfe\xfd")

    assert session_transaction.find_oversized_files(tmp_path, max_lines=1) == []


def test_ensure_session_changed_worktree_rejects_empty_status(tmp_path):
    def runner(args, cwd):
        return session_transaction.CommandResult(0, "", "")

    with pytest.raises(session_transaction.TransactionError, match="produced no"):
        session_transaction.ensure_session_changed_worktree(tmp_path, runner)


def test_commit_and_apply_session_issue_git_commands(tmp_path):
    commands = []

    def runner(args, cwd):
        commands.append(list(args))
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return session_transaction.CommandResult(0, "deadbeef\n", "")
        return session_transaction.CommandResult(0, "", "")

    commit = session_transaction.commit_session(tmp_path, 12, runner)
    session_transaction.apply_session_commit(tmp_path, "session/0012", runner)

    assert commit == "deadbeef"
    assert ["git", "add", "-A"] in commands
    assert ["git", "commit", "-m", "session 0012"] in commands
    assert ["git", "merge", "--ff-only", "session/0012"] in commands


def test_main_returns_zero_on_success(monkeypatch, capsys, tmp_path):
    def fake_transaction(root, agent_command, runs_dir, check_command, runner):
        assert root == tmp_path
        assert agent_command == "agent"
        assert runs_dir == tmp_path / "runs"
        assert check_command == ["check"]
        assert runner is session_transaction.streaming_runner
        return "cafebabe"

    monkeypatch.setattr(session_transaction, "run_transaction", fake_transaction)
    monkeypatch.setattr(
        session_transaction.sys,
        "argv",
        [
            "session_transaction.py",
            "--root",
            str(tmp_path),
            "--agent-command",
            "agent",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--check-command",
            "check",
        ],
    )

    result = session_transaction.main()

    captured = capsys.readouterr()
    assert result == 0
    assert "Transaction applied: cafebabe" in captured.out


def test_run_transaction_records_failed_checks_without_repair(tmp_path):
    root = make_root(tmp_path)
    runs_dir = tmp_path / "runs"
    runner = FakeRunner(root, fail_checks=True)

    with pytest.raises(session_transaction.TransactionError, match="checks failed"):
        session_transaction.run_transaction(
            root=root,
            agent_command="agent --ok",
            runs_dir=runs_dir,
            runner=runner,
        )

    commands = [command for command, _ in runner.commands]
    agent_runs = [command for command in commands if "run_session.py" in " ".join(command)]
    assert len(agent_runs) == 1
    obsolete_failure_context = root / "state" / ("check_" + "failure.md")
    assert not obsolete_failure_context.exists()
    assert (root / "state" / "session_failure_tail.txt").read_text(encoding="utf-8") == (
        "checks failed: tests failed\n"
    )


def test_parse_porcelain_paths_normalizes_paths():
    changes = session_transaction.parse_porcelain_paths(
        " M state/external_messages.md\n?? state\\questions\\0001-topic.md\n"
    )

    assert changes == [
        (" M", "state/external_messages.md"),
        ("??", "state/questions/0001-topic.md"),
    ]


def test_parse_porcelain_paths_rejects_renames():
    with pytest.raises(session_transaction.TransactionError, match="renamed files"):
        session_transaction.parse_porcelain_paths("R  old.md -> new.md\n")


def test_is_human_input_change_allows_creator_inputs_and_failure_diagnostics():
    assert session_transaction.is_human_input_change(" M", "state/external_messages.md")
    assert session_transaction.is_human_input_change("??", "state/external_messages.md")
    assert session_transaction.is_human_input_change(" M", "state/questions/0001-topic.md")
    assert session_transaction.is_human_input_change(" M", "state/last_session.md")
    assert session_transaction.is_human_input_change("??", "state/session_failure_tail.txt")
    assert not session_transaction.is_human_input_change(" D", "state/questions/0001-topic.md")
    assert not session_transaction.is_human_input_change(" M", "scripts/run_session.py")


def test_checkpoint_human_input_commits_allowed_changes(tmp_path):
    commands = []

    def runner(args, cwd):
        args = list(args)
        commands.append(args)
        if args[:3] == ["git", "status", "--porcelain"]:
            return session_transaction.CommandResult(
                0,
                " M state/external_messages.md\n?? state/questions/0001-topic.md\n M state/last_session.md\n?? state/session_failure_tail.txt\n",
                "",
            )
        return session_transaction.CommandResult(0, "", "")

    changed = session_transaction.checkpoint_human_input(tmp_path, runner)

    assert changed is True
    assert [
        "git",
        "add",
        "--",
        "state/external_messages.md",
        "state/questions/0001-topic.md",
        "state/last_session.md",
        "state/session_failure_tail.txt",
    ] in commands
    assert ["git", "commit", "-m", "record human input before session"] in commands


def test_checkpoint_human_input_returns_false_for_clean_tree(tmp_path):
    def runner(args, cwd):
        return session_transaction.CommandResult(0, "", "")

    assert session_transaction.checkpoint_human_input(tmp_path, runner) is False


def test_checkpoint_human_input_rejects_other_changes(tmp_path):
    def runner(args, cwd):
        if list(args)[:3] == ["git", "status", "--porcelain"]:
            return session_transaction.CommandResult(0, " M scripts/run_session.py\n", "")
        return session_transaction.CommandResult(0, "", "")

    with pytest.raises(session_transaction.TransactionError, match="non-human changes"):
        session_transaction.checkpoint_human_input(tmp_path, runner)


def test_parse_env_line_handles_comments_exports_and_quotes():
    assert session_transaction.parse_env_line("# comment") is None
    assert session_transaction.parse_env_line("") is None
    assert session_transaction.parse_env_line("export AI_API_KEY='secret'") == ("AI_API_KEY", "secret")
    assert session_transaction.parse_env_line('AI_BASE_URL="https://example/v1"') == (
        "AI_BASE_URL",
        "https://example/v1",
    )


def test_load_dotenv_sets_missing_values_without_overriding(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("AI_API_KEY=file-secret\nAI_BASE_URL=https://example/v1\n", encoding="utf-8")
    monkeypatch.setenv("AI_API_KEY", "existing-secret")
    monkeypatch.delenv("AI_BASE_URL", raising=False)

    loaded = session_transaction.load_dotenv(env_path)

    assert loaded == {
        "AI_API_KEY": "existing-secret",
        "AI_BASE_URL": "https://example/v1",
    }
    assert session_transaction.os.environ["AI_API_KEY"] == "existing-secret"
    assert session_transaction.os.environ["AI_BASE_URL"] == "https://example/v1"


def test_default_agent_command_uses_local_agent():
    command = session_transaction.default_agent_command()

    assert "uv run python scripts/run_agent.py" in command
    assert "{ROOT}" in command
    assert "{PROMPT_FILE}" in command

def test_find_oversized_files_skips_generated_lockfiles(tmp_path):
    (tmp_path / "uv.lock").write_text("x\n" * 1000, encoding="utf-8")

    assert session_transaction.find_oversized_files(tmp_path, max_lines=500) == []
    

def test_parse_env_line_rejects_line_without_equals():
    assert session_transaction.parse_env_line("just_a_word") is None


def test_parse_env_line_rejects_empty_key():
    assert session_transaction.parse_env_line(" = value") is None


def test_load_dotenv_returns_empty_for_missing_file(tmp_path):
    loaded = session_transaction.load_dotenv(tmp_path / "no_such_file.env")
    assert loaded == {}


def test_find_oversized_files_returns_empty_when_all_files_under_limit(tmp_path):
    (tmp_path / "small.txt").write_text("x\n" * 10, encoding="utf-8")
    assert session_transaction.find_oversized_files(tmp_path, max_lines=500) == []


def test_find_oversized_files_includes_file_over_limit(tmp_path):
    (tmp_path / "large.txt").write_text("x\n" * 501, encoding="utf-8")
    result = session_transaction.find_oversized_files(tmp_path, max_lines=500)
    assert len(result) == 1
    assert result[0].name == "large.txt"


def test_find_oversized_files_skips_unicode_decode_error(tmp_path):
    (tmp_path / "binary.bin").write_bytes(b"\x80\x81\x82\x83")
    assert session_transaction.find_oversized_files(tmp_path, max_lines=500) == []


def test_parse_porcelain_paths_skips_empty_lines():
    changes = session_transaction.parse_porcelain_paths(" M file.txt\n\n?? new.md\n")
    assert len(changes) == 2
    assert changes[0] == (" M", "file.txt")
    assert changes[1] == ("??", "new.md")


def test_tail_lines_returns_full_text_when_under_limit():
    text = "line1\nline2\nline3"
    assert session_transaction.tail_lines(text, max_lines=10) == text


def test_tail_lines_returns_last_n_lines_when_over_limit():
    lines = "\n".join(f"line {i}" for i in range(100))
    result = session_transaction.tail_lines(lines, max_lines=5)
    assert result.count("\n") == 4
    assert "line 96" in result
    assert "line 99" in result


def test_load_dotenv_ignores_blank_and_comment_lines(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("# comment\n\nAI_KEY=value\n", encoding="utf-8")
    loaded = session_transaction.load_dotenv(env_path)
    assert loaded == {"AI_KEY": "value"}


