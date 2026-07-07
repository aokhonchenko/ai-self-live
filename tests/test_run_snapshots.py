from scripts import run_snapshots


def test_preserve_session_snapshot_copies_worktree_and_prunes_old_snapshots(tmp_path):
    runs_dir = tmp_path / "runs"
    source = tmp_path / "worktree"
    source.mkdir()
    (source / "state").mkdir()
    (source / "state" / "last_session.md").write_text("готово\n", encoding="utf-8")
    (source / ".git").write_text("gitdir: ignored\n", encoding="utf-8")
    snapshots = runs_dir / "snapshots"
    old_one = snapshots / "session-0001-applied"
    old_two = snapshots / "session-0002-failed"
    old_one.mkdir(parents=True)
    old_two.mkdir()
    (old_one / "old.md").write_text("1", encoding="utf-8")
    (old_two / "old.md").write_text("2", encoding="utf-8")

    target = run_snapshots.preserve_session_snapshot(source, runs_dir, "0003", applied=False)

    assert target == snapshots / "session-0003-failed"
    assert (target / "state" / "last_session.md").read_text(encoding="utf-8") == "готово\n"
    assert not (target / ".git").exists()
    assert "завершилась ошибкой" in (target / "RUN_SNAPSHOT.md").read_text(encoding="utf-8")
    assert not old_one.exists()
    assert old_two.exists()


def test_prune_snapshots_keeps_directory_when_keep_is_zero(tmp_path):
    snapshots = tmp_path / "snapshots"
    old = snapshots / "session-0001-applied"
    old.mkdir(parents=True)

    run_snapshots.prune_snapshots(snapshots, keep=0)

    assert old.exists()

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import run_snapshots


def test_preserve_session_snapshot_removes_existing_target(tmp_path):
    runs_dir = tmp_path / "runs"
    source = tmp_path / "worktree"
    source.mkdir()
    (source / "file.txt").write_text("new\\n", encoding="utf-8")
    snapshots = runs_dir / "snapshots"
    target = snapshots / "session-0003-applied"
    target.mkdir(parents=True)
    (target / "old.txt").write_text("old\\n", encoding="utf-8")

    result = run_snapshots.preserve_session_snapshot(source, runs_dir, "0003", applied=True)

    assert result == target
    assert (target / "file.txt").read_text(encoding="utf-8") == "new\\n"
    assert not (target / "old.txt").exists()
    assert "успешно применена" in (target / "RUN_SNAPSHOT.md").read_text(encoding="utf-8")


def test_preserve_session_snapshot_raises_on_copy_failure(tmp_path):
    runs_dir = tmp_path / "runs"
    source = tmp_path / "worktree"
    source.mkdir()

    with patch.object(shutil, "copytree", side_effect=PermissionError("denied")):
        with pytest.raises(run_snapshots.SnapshotError, match="cannot preserve session snapshot"):
            run_snapshots.preserve_session_snapshot(source, runs_dir, "0004", applied=True)


def test_snapshot_name_applied():
    name = run_snapshots.snapshot_name("0010", True)
    assert name == "session-0010-applied"


def test_snapshot_name_failed():
    name = run_snapshots.snapshot_name("0010", False)
    assert name == "session-0010-failed"


def test_snapshots_dir_returns_correct_path(tmp_path):
    result = run_snapshots.snapshots_dir(tmp_path)
    assert result == tmp_path / "snapshots"


def test_write_snapshot_metadata_applied(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    source = tmp_path / "source"
    run_snapshots.write_snapshot_metadata(target, "0020", True, source)
    content = (target / "RUN_SNAPSHOT.md").read_text(encoding="utf-8")
    assert "успешно применена" in content
    assert "`0020`" in content
    assert "`" + str(source) + "`" in content


def test_write_snapshot_metadata_failed(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    source = tmp_path / "source"
    run_snapshots.write_snapshot_metadata(target, "0021", False, source)
    content = (target / "RUN_SNAPSHOT.md").read_text(encoding="utf-8")
    assert "завершилась ошибкой" in content


def test_prune_snapshots_removes_oldest(tmp_path):
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    old = snapshots / "session-0001-applied"
    newer = snapshots / "session-0002-applied"
    old.mkdir()
    newer.mkdir()
    # Установим разные mtime
    old_stat = old.stat()
    import os
    os.utime(old, (old_stat.st_atime - 100, old_stat.st_mtime - 100))

    run_snapshots.prune_snapshots(snapshots, keep=1)

    assert not old.exists()
    assert newer.exists()


def test_prune_snapshots_empty_directory(tmp_path):
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    # Не должно вызвать ошибку
    run_snapshots.prune_snapshots(snapshots, keep=2)


def test_prune_snapshots_nonexistent_directory(tmp_path):
    snapshots = tmp_path / "nonexistent"
    run_snapshots.prune_snapshots(snapshots, keep=2)


def test_prune_snapshots_keep_all(tmp_path):
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    one = snapshots / "session-0001-applied"
    two = snapshots / "session-0002-applied"
    three = snapshots / "session-0003-applied"
    one.mkdir()
    two.mkdir()
    three.mkdir()

    run_snapshots.prune_snapshots(snapshots, keep=10)

    assert one.exists()
    assert two.exists()
    assert three.exists()
