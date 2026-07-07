"""Тесты для модуля scripts.external_projects."""

import stat
import shutil
from pathlib import Path

import pytest

from scripts import external_projects
from scripts.command_runners import CommandResult


class FakeRunner:
    """Фейковый раннер для git-команд."""

    def __init__(self, ignore_paths: set[str] | None = None):
        self.ignore_paths = ignore_paths or set()
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, args, cwd):
        self.calls.append((list(args), Path(cwd)))
        return CommandResult(0, "", "")


class TestIsGitIgnored:
    """Тесты для is_git_ignored."""

    def test_returns_true_when_git_check_ignore_says_ignored(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        path = root / "projects" / "ignored"
        path.mkdir(parents=True)

        def runner(args, cwd):
            self.calls = (list(args), Path(cwd))
            return CommandResult(0, "", "")

        self.calls = []
        result = external_projects.is_git_ignored(root, path, runner)
        assert result is True

    def test_returns_false_when_git_check_ignore_says_not_ignored(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        path = root / "projects" / "not-ignored"
        path.mkdir(parents=True)

        def runner(args, cwd):
            return CommandResult(1, "", "")

        result = external_projects.is_git_ignored(root, path, runner)
        assert result is False

    def test_returns_false_when_path_not_relative_to_root(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        # path outside root — relative_to will raise ValueError
        other = tmp_path / "other" / "project"
        other.mkdir(parents=True)

        runner = FakeRunner()
        result = external_projects.is_git_ignored(root, other, runner)
        assert result is False
        # runner should NOT be called since ValueError is caught
        assert runner.calls == []


class TestHasGitMetadata:
    """Тесты для has_git_metadata."""

    def test_returns_true_when_git_dir_exists(self, tmp_path):
        path = tmp_path / "project"
        path.mkdir()
        (path / ".git").mkdir()
        assert external_projects.has_git_metadata(path) is True

    def test_returns_false_when_no_git_dir(self, tmp_path):
        path = tmp_path / "project"
        path.mkdir()
        assert external_projects.has_git_metadata(path) is False


class TestExternalProjectDirs:
    """Тесты для external_project_dirs."""

    def test_returns_empty_when_projects_dir_missing(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        result = external_projects.external_project_dirs(root)
        assert result == []

    def test_returns_empty_when_projects_dir_empty(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        (root / "projects").mkdir()
        result = external_projects.external_project_dirs(root)
        assert result == []

    def test_includes_git_directories(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        projects = root / "projects"
        projects.mkdir()
        git_project = projects / "my-repo"
        git_project.mkdir()
        (git_project / ".git").mkdir()

        result = external_projects.external_project_dirs(root)
        assert len(result) == 1
        assert result[0] == git_project

    def test_includes_git_ignored_directories(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        projects = root / "projects"
        projects.mkdir()
        ignored_project = projects / "foundation-finance"
        ignored_project.mkdir()

        def runner(args, cwd):
            if list(args)[:3] == ["git", "check-ignore", "-q"] and args[3] == "projects/foundation-finance":
                return CommandResult(0, "", "")
            return CommandResult(1, "", "")

        result = external_projects.external_project_dirs(root, runner)
        assert len(result) == 1
        assert result[0] == ignored_project

    def test_excludes_non_directory_entries(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        projects = root / "projects"
        projects.mkdir()
        # Создаём файл в projects/ — он должен быть пропущен
        (projects / "readme.txt").write_text("hello", encoding="utf-8")
        # И директорию без .git
        (projects / "plain-dir").mkdir()

        result = external_projects.external_project_dirs(root)
        assert result == []

    def test_returns_sorted_by_name(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        projects = root / "projects"
        projects.mkdir()
        for name in ["z-project", "a-project", "m-project"]:
            d = projects / name
            d.mkdir()
            (d / ".git").mkdir()

        result = external_projects.external_project_dirs(root)
        names = [p.name for p in result]
        assert names == ["a-project", "m-project", "z-project"]


class TestIsIgnoredName:
    """Тесты для _is_ignored_name."""

    def test_returns_true_for_ignored_name(self):
        assert external_projects._is_ignored_name("__pycache__", {"__pycache__"}) is True

    def test_returns_false_for_non_ignored_name(self):
        assert external_projects._is_ignored_name("main.py", {"__pycache__"}) is False


class TestMakeWritable:
    """Тесты для _make_writable."""

    def test_makes_file_writable(self, tmp_path):
        path = tmp_path / "readonly.txt"
        path.write_text("data", encoding="utf-8")
        path.chmod(stat.S_IREAD)
        external_projects._make_writable(path)
        # Должно стать writable — можно записать
        path.write_text("new", encoding="utf-8")

    def test_handles_os_error_gracefully(self, monkeypatch, tmp_path):
        """OSError при chmod игнорируется."""
        path = tmp_path / "file.txt"
        path.write_text("data", encoding="utf-8")

        original_chmod = Path.chmod

        def fake_chmod(self, mode):
            raise OSError("simulated chmod failure")

        monkeypatch.setattr(Path, "chmod", fake_chmod)
        # Не должно выбросить исключение
        external_projects._make_writable(path)


class TestRemovePath:
    """Тесты для _remove_path."""

    def test_removes_file(self, tmp_path):
        path = tmp_path / "file.txt"
        path.write_text("data", encoding="utf-8")
        external_projects._remove_path(path)
        assert not path.exists()

    def test_removes_directory(self, tmp_path):
        d = tmp_path / "subdir"
        d.mkdir()
        (d / "nested.txt").write_text("data", encoding="utf-8")
        external_projects._remove_path(d)
        assert not d.exists()

    def test_removes_readonly_file(self, tmp_path):
        path = tmp_path / "readonly.txt"
        path.write_text("data", encoding="utf-8")
        path.chmod(stat.S_IREAD)
        external_projects._remove_path(path)
        assert not path.exists()


class TestCopyIntoExisting:
    """Тесты для _copy_into_existing."""

    def test_copies_files_from_source_to_target(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        (source / "file1.txt").write_text("content1", encoding="utf-8")
        (source / "file2.txt").write_text("content2", encoding="utf-8")

        external_projects._copy_into_existing(source, target)

        assert (target / "file1.txt").read_text(encoding="utf-8") == "content1"
        assert (target / "file2.txt").read_text(encoding="utf-8") == "content2"

    def test_removes_files_not_in_source(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        (source / "keep.txt").write_text("keep", encoding="utf-8")
        (target / "keep.txt").write_text("old keep", encoding="utf-8")
        (target / "remove.txt").write_text("old remove", encoding="utf-8")

        external_projects._copy_into_existing(source, target)

        assert (target / "keep.txt").read_text(encoding="utf-8") == "keep"
        assert not (target / "remove.txt").exists()

    def test_skips_ignored_names_in_source(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        (source / "file.txt").write_text("data", encoding="utf-8")
        (source / "__pycache__").mkdir()
        (source / "__pycache__" / "cache.pyc").write_text("bytecode", encoding="utf-8")

        external_projects._copy_into_existing(source, target)

        assert (target / "file.txt").exists()
        assert not (target / "__pycache__").exists()

    def test_skips_ignored_names_in_target(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        (source / "new.txt").write_text("new", encoding="utf-8")
        # .git в target должен быть проигнорирован и не удалён
        (target / ".git").mkdir()
        (target / ".git" / "config").write_text("git config", encoding="utf-8")

        external_projects._copy_into_existing(source, target)

        assert (target / ".git" / "config").read_text(encoding="utf-8") == "git config"

    def test_handles_destination_is_file_not_dir(self, tmp_path):
        """Ветка: destination существует как файл, а child — директория (строки 87-88)."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        # destination существует как файл
        (target / "subdir").write_text("I am a file", encoding="utf-8")
        # source имеет subdir как директорию
        (source / "subdir").mkdir()
        (source / "subdir" / "nested.txt").write_text("nested", encoding="utf-8")

        external_projects._copy_into_existing(source, target)

        # Файл должен быть удалён и заменён директорией
        assert (target / "subdir").is_dir()
        assert (target / "subdir" / "nested.txt").read_text(encoding="utf-8") == "nested"

    def test_handles_destination_is_dir_not_file(self, tmp_path):
        """Ветка: destination существует как директория, а child — файл (строка 92)."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        # destination существует как директория
        (target / "file.txt").mkdir()
        (target / "file.txt" / "old.txt").write_text("old", encoding="utf-8")
        # source имеет file.txt как файл
        (source / "file.txt").write_text("new", encoding="utf-8")

        external_projects._copy_into_existing(source, target)

        # Директория должна быть удалена и заменена файлом
        assert (target / "file.txt").is_file()
        assert (target / "file.txt").read_text(encoding="utf-8") == "new"

    def test_makes_writable_before_overwriting(self, tmp_path):
        """Ветка: _make_writable вызывается для существующего файла (строка 94)."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        dest = target / "file.txt"
        dest.write_text("old", encoding="utf-8")
        dest.chmod(stat.S_IREAD)
        (source / "file.txt").write_text("new", encoding="utf-8")

        external_projects._copy_into_existing(source, target)

        assert dest.read_text(encoding="utf-8") == "new"


class TestCopyExternalProject:
    """Тесты для copy_external_project."""

    def test_copies_tree_when_target_missing(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir(parents=True)
        (source / "a.txt").write_text("a", encoding="utf-8")
        sub = source / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("b", encoding="utf-8")

        external_projects.copy_external_project(source, target)

        assert (target / "a.txt").read_text(encoding="utf-8") == "a"
        assert (target / "sub" / "b.txt").read_text(encoding="utf-8") == "b"

    def test_copies_tree_when_target_exists(self, tmp_path):
        """Ветка: target существует как директория — вызывается _copy_into_existing (строки 103-105)."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir(parents=True)
        target.mkdir()
        (source / "new.txt").write_text("new", encoding="utf-8")
        (target / "old.txt").write_text("old", encoding="utf-8")

        external_projects.copy_external_project(source, target)

        assert (target / "new.txt").read_text(encoding="utf-8") == "new"
        assert not (target / "old.txt").exists()

    def test_raises_when_target_exists_as_file(self, tmp_path):
        """Ветка: target существует и не директория (строка 101)."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.write_text("I am a file", encoding="utf-8")

        with pytest.raises(
            external_projects.ExternalProjectError,
            match="target is not a directory",
        ):
            external_projects.copy_external_project(source, target)

    def test_ignores_patterns(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        (source / "keep.txt").write_text("keep", encoding="utf-8")
        (source / "__pycache__").mkdir()
        (source / "__pycache__" / "cache.pyc").write_text("bytecode", encoding="utf-8")
        (source / ".venv").mkdir()
        (source / ".venv" / "bin").mkdir()

        external_projects.copy_external_project(source, target)

        assert (target / "keep.txt").exists()
        assert not (target / "__pycache__").exists()
        assert not (target / ".venv").exists()

    def test_raises_on_copy_error(self, tmp_path, monkeypatch):
        """Ветка: OSError/shutil.Error при копировании (строки 107-108)."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        (source / "file.txt").write_text("data", encoding="utf-8")

        original_copytree = shutil.copytree

        def fake_copytree(*args, **kwargs):
            raise OSError("simulated copy error")

        monkeypatch.setattr(shutil, "copytree", fake_copytree)

        with pytest.raises(
            external_projects.ExternalProjectError,
            match="cannot replicate external project",
        ):
            external_projects.copy_external_project(source, target)


class TestReplicateExternalProjects:
    """Тесты для replicate_external_projects."""

    def test_replicates_all_external_projects(self, tmp_path):
        worktree = tmp_path / "worktree"
        root = tmp_path / "root"
        worktree.mkdir()
        root.mkdir()

        # Создаём структуру
        projects = worktree / "projects"
        projects.mkdir()
        ext = projects / "ext-project"
        ext.mkdir()
        (ext / ".git").mkdir()
        (ext / "data.txt").write_text("data", encoding="utf-8")

        def runner(args, cwd):
            return CommandResult(0, "", "")

        replicated = external_projects.replicate_external_projects(worktree, root, runner)

        assert replicated == [Path("projects/ext-project")]
        assert (root / "projects" / "ext-project" / "data.txt").read_text(encoding="utf-8") == "data"

    def test_returns_empty_list_when_no_external_projects(self, tmp_path):
        worktree = tmp_path / "worktree"
        root = tmp_path / "root"
        worktree.mkdir()
        root.mkdir()
        (worktree / "projects").mkdir()

        def runner(args, cwd):
            return CommandResult(0, "", "")

        replicated = external_projects.replicate_external_projects(worktree, root, runner)
        assert replicated == []
