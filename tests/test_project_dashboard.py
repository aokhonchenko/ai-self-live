"""Тесты для scripts/project_dashboard.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from scripts.project_dashboard import (
    collect_script_stats,
    collect_state_stats,
    collect_test_stats,
    count_lines,
    dir_tree,
    generate_html,
    main,
    read_file_safe,
    read_history_summary,
)


# ── Утилиты ────────────────────────────────────────────────────────────────


class TestReadFileSafe:
    """Тесты read_file_safe."""

    def test_existing_file(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        assert read_file_safe(f) == "hello"

    def test_nonexistent_file(self, tmp_path: Path):
        f = tmp_path / "nope.txt"
        assert read_file_safe(f) == ""

    def test_binary_file(self, tmp_path: Path):
        f = tmp_path / "bin.dat"
        f.write_bytes(b"\x00\x01\x02")
        # с errors="replace" бинарные данные читаются без ошибки
        result = read_file_safe(f)
        assert isinstance(result, str)
        assert len(result) > 0


class TestCountLines:
    """Тесты count_lines."""

    def test_normal_file(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        assert count_lines(f) == 3

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        assert count_lines(f) == 0

    def test_nonexistent_file(self, tmp_path: Path):
        f = tmp_path / "nope.txt"
        assert count_lines(f) == 0


# ── Дерево директорий ─────────────────────────────────────────────────────


class TestDirTree:
    """Тесты dir_tree."""

    def test_empty_dir(self, tmp_path: Path):
        result = dir_tree(tmp_path)
        assert result == []

    def test_single_file(self, tmp_path: Path):
        (tmp_path / "file.txt").touch()
        result = dir_tree(tmp_path)
        assert "file.txt" in result[0]

    def test_nested_dirs(self, tmp_path: Path):
        (tmp_path / "a.txt").touch()
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").touch()
        result = dir_tree(tmp_path)
        assert any("a.txt" in r for r in result)
        assert any("sub" in r for r in result)
        assert any("b.txt" in r for r in result)

    def test_depth_limit(self, tmp_path: Path):
        """Дерево не должно уходить глубже 3 уровней."""
        deep = tmp_path
        for i in range(5):
            deep = deep / f"level{i}"
        deep.mkdir(parents=True)
        (deep / "deep.txt").touch()
        result = dir_tree(tmp_path)
        # Должно быть не больше 3 уровней вложенности
        depth = 0
        for line in result:
            d = line.count("│   ") + line.count("    ")
            if d > depth:
                depth = d
        assert depth <= 3


# ── Статистика скриптов ───────────────────────────────────────────────────


class TestCollectScriptStats:
    """Тесты collect_script_stats."""

    def test_empty_scripts_dir(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        result = collect_script_stats(scripts, tmp_path)
        assert result == []

    def test_stats_for_real_script(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        f = scripts / "example.py"
        f.write_text(
            '"""Module docstring."""\n\nclass Foo:\n    def bar(self):\n        pass\n',
            encoding="utf-8",
        )
        result = collect_script_stats(scripts, tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "example"
        assert result[0]["lines"] > 0
        assert result[0]["functions"] == 1
        assert result[0]["classes"] == 1
        assert result[0]["has_docstring"] is True

    def test_relative_path(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        f = scripts / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        result = collect_script_stats(scripts, tmp_path)
        # Windows использует обратные слеши, нормализуем
        assert result[0]["path"].replace("\\", "/") == "scripts/test.py"


# ── Статистика тестов ─────────────────────────────────────────────────────


class TestCollectTestStats:
    """Тесты collect_test_stats."""

    def test_empty_tests_dir(self, tmp_path: Path):
        tests = tmp_path / "tests"
        tests.mkdir()
        result = collect_test_stats(tests, tmp_path)
        assert result["total_files"] == 0
        assert result["total_tests"] == 0

    def test_stats_with_tests(self, tmp_path: Path):
        tests = tmp_path / "tests"
        tests.mkdir()
        f = tests / "test_example.py"
        f.write_text(
            "def test_one(): pass\n\ndef test_two(): pass\n",
            encoding="utf-8",
        )
        result = collect_test_stats(tests, tmp_path)
        assert result["total_files"] == 1
        assert result["total_tests"] == 2
        assert len(result["files"]) == 1
        assert result["files"][0]["tests"] == 2


# ── Статистика состояния ──────────────────────────────────────────────────


class TestCollectStateStats:
    """Тесты collect_state_stats."""

    def test_empty_state_dir(self, tmp_path: Path):
        state = tmp_path / "state"
        state.mkdir()
        result = collect_state_stats(state, tmp_path)
        assert result["total_files"] == 0

    def test_stats_with_md_files(self, tmp_path: Path):
        state = tmp_path / "state"
        state.mkdir()
        (state / "plan.md").write_text("# План\n\nТекст\n", encoding="utf-8")
        (state / "notes.md").write_text("# Заметки\n", encoding="utf-8")
        result = collect_state_stats(state, tmp_path)
        assert result["total_files"] == 2
        assert result["total_lines"] > 0


# ── История ────────────────────────────────────────────────────────────────


class TestReadHistorySummary:
    """Тесты read_history_summary."""

    def test_no_history_file(self, tmp_path: Path):
        logs = tmp_path / "logs"
        logs.mkdir()
        result = read_history_summary(logs)
        assert result == []

    def test_empty_history(self, tmp_path: Path):
        logs = tmp_path / "logs"
        logs.mkdir()
        (logs / "history.md").write_text("", encoding="utf-8")
        result = read_history_summary(logs)
        assert result == []

    def test_parses_sessions(self, tmp_path: Path):
        logs = tmp_path / "logs"
        logs.mkdir()
        history = (
            "## Сессия 1\n\n- Сделал что-то\n\n"
            "## Сессия 2\n\n- Сделал ещё что-то\n"
        )
        (logs / "history.md").write_text(history, encoding="utf-8")
        result = read_history_summary(logs)
        assert len(result) == 2
        assert result[0]["session"] == "1"
        assert result[1]["session"] == "2"

    def test_last_n_limit(self, tmp_path: Path):
        logs = tmp_path / "logs"
        logs.mkdir()
        entries = "\n".join(
            f"## Сессия {i}\n\n- Запись {i}\n" for i in range(1, 11)
        )
        (logs / "history.md").write_text(entries, encoding="utf-8")
        result = read_history_summary(logs, last_n=3)
        assert len(result) == 3
        assert result[0]["session"] == "8"


# ── Генерация HTML ────────────────────────────────────────────────────────


class TestGenerateHtml:
    """Тесты generate_html."""

    def test_creates_html_file(self, tmp_path: Path):
        # Создаём минимальную структуру проекта
        (tmp_path / "scripts").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "state").mkdir()
        (tmp_path / "logs").mkdir()
        (tmp_path / "scripts" / "dummy.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "tests" / "test_dummy.py").write_text(
            "def test_x(): pass\n", encoding="utf-8"
        )
        output = tmp_path / "output.html"
        generate_html(tmp_path, output)
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "ai-lives" in content

    def test_html_contains_stats(self, tmp_path: Path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "state").mkdir()
        (tmp_path / "logs").mkdir()
        (tmp_path / "scripts" / "app.py").write_text(
            '"""App."""\n\nclass App:\n    def run(self): pass\n',
            encoding="utf-8",
        )
        (tmp_path / "tests" / "test_app.py").write_text(
            "def test_run(): pass\n\ndef test_stop(): pass\n",
            encoding="utf-8",
        )
        output = tmp_path / "output.html"
        generate_html(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "app.py" in content
        assert "test_app.py" in content
        assert "2" in content  # 2 теста


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ── Дополнительные тесты для улучшения покрытия ────────────────────────────


class TestCollectScriptStatsRelativeError:
    """Тест ветки ValueError при relative_to (файл не в проекте)."""

    def test_relative_to_value_error(self, tmp_path: Path):
        outside = tmp_path / "outside"
        outside.mkdir()
        f = outside / "orphan.py"
        f.write_text("x = 1\n", encoding="utf-8")
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        result = collect_script_stats(scripts, tmp_path)
        assert result == []


class TestCollectTestStatsRelativeError:
    """Тест ветки ValueError при relative_to в collect_test_stats."""

    def test_relative_to_value_error(self, tmp_path: Path):
        tests = tmp_path / "tests"
        tests.mkdir()
        f = tests / "test_x.py"
        f.write_text("def test_x(): pass\n", encoding="utf-8")
        result = collect_test_stats(tests, tmp_path)
        assert result["total_files"] == 1
        assert "test_x.py" in result["files"][0]["path"]


class TestCollectStateStatsRelativeError:
    """Тест ветки ValueError при relative_to в collect_state_stats."""

    def test_relative_to_value_error(self, tmp_path: Path):
        state = tmp_path / "state"
        state.mkdir()
        f = state / "plan.md"
        f.write_text("# План\n", encoding="utf-8")
        result = collect_state_stats(state, tmp_path)
        assert result["total_files"] == 1


class TestReadHistoryEmptySummary:
    """Тест чтения истории с пустой записью."""

    def test_session_with_no_summary(self, tmp_path: Path):
        logs = tmp_path / "logs"
        logs.mkdir()
        history = "## Сессия 1\n\n## Сессия 2\n\n- Запись\n"
        (logs / "history.md").write_text(history, encoding="utf-8")
        result = read_history_summary(logs)
        assert len(result) == 2
        assert result[0]["session"] == "1"
        assert result[0]["summary"] == []


class TestGenerateHtmlLongTree:
    """Тест генерации HTML с большим деревом (>80 записей)."""

    def test_html_with_long_tree(self, tmp_path: Path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "state").mkdir()
        (tmp_path / "logs").mkdir()
        for i in range(90):
            (tmp_path / f"file{i}.py").write_text("x = 1\n", encoding="utf-8")
        output = tmp_path / "output.html"
        generate_html(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "и ещё" in content
        assert "записей" in content


class TestGenerateHtmlNoHistory:
    """Тест генерации HTML без истории."""

    def test_html_no_history(self, tmp_path: Path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "state").mkdir()
        logs = tmp_path / "logs"
        logs.mkdir()
        output = tmp_path / "output.html"
        generate_html(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "Записей не найдено" in content


class TestGenerateHtmlSnapshotsExcluded:
    """Тест что директория snapshots исключается из подсчёта строк."""

    def test_snapshots_excluded(self, tmp_path: Path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "state").mkdir()
        (tmp_path / "logs").mkdir()
        snapshots = tmp_path / "snapshots"
        snapshots.mkdir()
        big_file = snapshots / "big.py"
        big_file.write_text("x = 1\n" * 100, encoding="utf-8")
        (tmp_path / "scripts" / "app.py").write_text("x = 1\n", encoding="utf-8")
        output = tmp_path / "output.html"
        generate_html(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "app.py" in content


class TestGenerateHtmlVenvExcluded:
    """Тест что .venv исключается из подсчёта строк."""

    def test_venv_excluded(self, tmp_path: Path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "state").mkdir()
        (tmp_path / "logs").mkdir()
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        big_file = venv / "big.py"
        big_file.write_text("x = 1\n" * 100, encoding="utf-8")
        (tmp_path / "scripts" / "app.py").write_text("x = 1\n", encoding="utf-8")
        output = tmp_path / "output.html"
        generate_html(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "app.py" in content


class TestMainCli:
    """Тесты CLI main()."""

    def test_main_with_output_arg(self, tmp_path: Path, monkeypatch):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "state").mkdir()
        (tmp_path / "logs").mkdir()
        (tmp_path / "scripts" / "app.py").write_text("x = 1\n", encoding="utf-8")
        output = tmp_path / "custom.html"
        monkeypatch.setattr("sys.argv", ["project_dashboard", "--output", str(output)])
        main()
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "ai-lives" in content

    def test_main_with_root_arg(self, tmp_path: Path, monkeypatch):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "state").mkdir()
        (tmp_path / "logs").mkdir()
        (tmp_path / "scripts" / "app.py").write_text("x = 1\n", encoding="utf-8")
        output = tmp_path / "root_output.html"
        monkeypatch.setattr(
            "sys.argv", ["project_dashboard", "--root", str(tmp_path), "-o", str(output)]
        )
        main()
        assert output.exists()

    def test_main_missing_scripts_dir(self, tmp_path: Path, monkeypatch, capsys):
        output = tmp_path / "out.html"
        monkeypatch.setattr(
            "sys.argv", ["project_dashboard", "--root", str(tmp_path), "-o", str(output)]
        )
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "Не найден каталог scripts" in captured.err


class TestDirTreeDepthLimit:
    """Тест ветки depth > 3 в dir_tree."""

    def test_depth_limit_returns_empty(self, tmp_path: Path):
        """При depth=4 функция должна сразу вернуть пустой список."""
        result = dir_tree(tmp_path, depth=4)
        assert result == []


class TestDirTreeOSError:
    """Тест ветки OSError при iterdir() в dir_tree."""

    def test_iterdir_oserror(self, tmp_path: Path, monkeypatch):
        """При ошибке доступа к директории — пустой список."""

        def mock_iterdir(self):
            raise OSError(13, "Permission denied")

        monkeypatch.setattr(Path, "iterdir", mock_iterdir)
        result = dir_tree(tmp_path)
        assert result == []


class TestCollectScriptStatsNotDir:
    """Тест ветки if not scripts_dir.is_dir() в collect_script_stats."""

    def test_not_a_directory(self, tmp_path: Path):
        """Если scripts_dir — файл, а не директория, вернуть пустой список."""
        scripts_file = tmp_path / "scripts.txt"
        scripts_file.write_text("x = 1\n", encoding="utf-8")
        result = collect_script_stats(scripts_file, tmp_path)
        assert result == []


class TestCollectTestStatsNotDir:
    """Тест ветки if not tests_dir.is_dir() в collect_test_stats."""

    def test_not_a_directory(self, tmp_path: Path):
        """Если tests_dir — файл, а не директория, вернуть пустой словарь."""
        tests_file = tmp_path / "tests.txt"
        tests_file.write_text("def test_x(): pass\n", encoding="utf-8")
        result = collect_test_stats(tests_file, tmp_path)
        assert result == {"total": 0, "files": []}


class TestCollectStateStatsNotDir:
    """Тест ветки if not state_dir.is_dir() в collect_state_stats."""

    def test_not_a_directory(self, tmp_path: Path):
        """Если state_dir — файл, а не директория, вернуть пустой словарь."""
        state_file = tmp_path / "state.txt"
        state_file.write_text("# План\n", encoding="utf-8")
        result = collect_state_stats(state_file, tmp_path)
        assert result == {"total_files": 0, "total_lines": 0}


class TestCollectScriptStatsValueError:
    """Тест ветки ValueError при relative_to в collect_script_stats."""

    def test_relative_to_value_error(self, tmp_path: Path, monkeypatch):
        """Файл из другой файловой системы вызывает ValueError."""
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        f = scripts / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        def mock_relative_to(self, *args, **kwargs):
            raise ValueError("path is on mount '', start is on mount ''")

        monkeypatch.setattr(Path, "relative_to", mock_relative_to)
        result = collect_script_stats(scripts, tmp_path)
        assert len(result) == 1
        assert result[0]["path"] == str(f)


class TestCollectTestStatsValueError:
    """Тест ветки ValueError при relative_to в collect_test_stats."""

    def test_relative_to_value_error(self, tmp_path: Path, monkeypatch):
        """Файл из другой файловой системы вызывает ValueError."""
        tests = tmp_path / "tests"
        tests.mkdir()
        f = tests / "test_x.py"
        f.write_text("def test_x(): pass\n", encoding="utf-8")

        def mock_relative_to(self, *args, **kwargs):
            raise ValueError("path is on mount '', start is on mount ''")

        monkeypatch.setattr(Path, "relative_to", mock_relative_to)
        result = collect_test_stats(tests, tmp_path)
        assert result["total_files"] == 1
        assert result["files"][0]["path"] == str(f)


class TestCollectStateStatsValueError:
    """Тест ветки ValueError при relative_to в collect_state_stats."""

    def test_relative_to_value_error(self, tmp_path: Path, monkeypatch):
        """Файл из другой файловой системы вызывает ValueError."""
        state = tmp_path / "state"
        state.mkdir()
        f = state / "plan.md"
        f.write_text("# План\n", encoding="utf-8")

        def mock_relative_to(self, *args, **kwargs):
            raise ValueError("path is on mount '', start is on mount ''")

        monkeypatch.setattr(Path, "relative_to", mock_relative_to)
        result = collect_state_stats(state, tmp_path)
        assert result["total_files"] == 1
        assert result["files"][0] == str(f)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ── Дополнительные тесты для улучшения покрытия ────────────────────────────

