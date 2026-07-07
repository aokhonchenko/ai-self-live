import stat
from pathlib import Path

import pytest

from scripts import external_projects, session_transaction
from test_session_transaction import FakeRunner, make_root


def test_external_project_dirs_include_nested_repos_and_ignored_dirs(tmp_path):
    root = make_root(tmp_path)
    nested = root / "projects" / "external-repo"
    ignored = root / "projects" / "foundation-finance"
    tracked = root / "projects" / "notes"
    (nested / ".git").mkdir(parents=True)
    ignored.mkdir(parents=True)
    tracked.mkdir(parents=True)

    def runner(args, cwd):
        if list(args)[:3] == ["git", "check-ignore", "-q"]:
            return session_transaction.CommandResult(0 if args[3] == "projects/foundation-finance" else 1, "", "")
        return session_transaction.CommandResult(0, "", "")

    result = external_projects.external_project_dirs(root, runner)

    assert [path.relative_to(root).as_posix() for path in result] == [
        "projects/external-repo",
        "projects/foundation-finance",
    ]


def test_replicate_external_projects_copies_ignored_project_without_tracking_it(tmp_path):
    main_parent = tmp_path / "main"
    worktree_parent = tmp_path / "worktree"
    main_parent.mkdir()
    worktree_parent.mkdir()
    root = make_root(main_parent)
    worktree = make_root(worktree_parent)
    project = worktree / "projects" / "foundation-finance"
    project.mkdir(parents=True)
    (project / "README.md").write_text("dashboard\n", encoding="utf-8")
    (project / ".git").mkdir()
    (project / "node_modules").mkdir()
    (project / "node_modules" / "large.txt").write_text("skip\n", encoding="utf-8")

    def runner(args, cwd):
        if list(args)[:3] == ["git", "check-ignore", "-q"]:
            return session_transaction.CommandResult(0 if args[3] == "projects/foundation-finance" else 1, "", "")
        return session_transaction.CommandResult(0, "", "")

    replicated = external_projects.replicate_external_projects(worktree, root, runner)

    assert replicated == [Path("projects/foundation-finance")]
    assert (root / "projects" / "foundation-finance" / "README.md").read_text(encoding="utf-8") == "dashboard\n"
    assert (root / "projects" / "foundation-finance" / ".git").exists()
    assert not (root / "projects" / "foundation-finance" / "node_modules").exists()


def test_run_transaction_replicates_external_projects_after_success(tmp_path):
    root = make_root(tmp_path)
    runs_dir = tmp_path / "runs"
    runner = FakeRunner(root, create_external_project=True)

    session_transaction.run_transaction(
        root=root,
        agent_command="agent --ok",
        runs_dir=runs_dir,
        runner=runner,
    )

    assert (root / "projects" / "foundation-finance" / "README.md").read_text(encoding="utf-8") == "created\n"
    assert (root / "projects" / "foundation-finance" / ".git").exists()


def test_copy_external_project_preserves_existing_git_metadata(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source_pack_dir = source / ".git" / "objects" / "pack"
    target_pack_dir = target / ".git" / "objects" / "pack"
    source_pack_dir.mkdir(parents=True)
    target_pack_dir.mkdir(parents=True)
    (source_pack_dir / "pack-demo.pack").write_text("source git data\n", encoding="utf-8")
    target_pack = target_pack_dir / "pack-demo.pack"
    target_pack.write_text("target git data\n", encoding="utf-8")
    target_pack.chmod(stat.S_IREAD)
    (source / "README.md").write_text("new content\n", encoding="utf-8")
    (target / "stale.md").write_text("old content\n", encoding="utf-8")

    try:
        external_projects.copy_external_project(source, target)
    finally:
        target_pack.chmod(stat.S_IWRITE | stat.S_IREAD)

    assert target_pack.read_text(encoding="utf-8") == "target git data\n"
    assert (target / "README.md").read_text(encoding="utf-8") == "new content\n"
    assert not (target / "stale.md").exists()


def test_run_transaction_rolls_back_main_merge_when_external_replication_fails(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    runs_dir = tmp_path / "runs"
    runner = FakeRunner(root)

    def fake_replicate(source, target, command_runner):
        if Path(target) == root:
            raise external_projects.ExternalProjectError("copy failed")
        return []

    monkeypatch.setattr(session_transaction, "replicate_external_projects", fake_replicate)

    with pytest.raises(external_projects.ExternalProjectError, match="copy failed"):
        session_transaction.run_transaction(
            root=root,
            agent_command="agent --ok",
            runs_dir=runs_dir,
            runner=runner,
        )

    commands = [command for command, _ in runner.commands]
    assert ["git", "merge", "--ff-only", "session/0003"] in commands
    assert ["git", "reset", "--hard", "abc123"] in commands
    assert ["git", "branch", "-D", "session/0003"] in commands
    assert (runs_dir / "snapshots" / "session-0003-failed").exists()
