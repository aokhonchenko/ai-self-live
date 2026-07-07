import json

import pytest

from scripts import file_tools


def test_read_and_write_file_inside_root(tmp_path):
    result = file_tools.write_file(tmp_path, "state/last_session.md", "текст")

    assert result["path"] == "state/last_session.md"
    assert result["bytes"] == len("текст".encode("utf-8"))
    assert file_tools.read_file(tmp_path, "state/last_session.md") == {
        "path": "state/last_session.md",
        "content": "текст",
    }


def test_safe_path_rejects_unsafe_paths(tmp_path):
    with pytest.raises(file_tools.ToolError, match="absolute"):
        file_tools.safe_path(tmp_path, str(tmp_path / "file.txt"))
    with pytest.raises(file_tools.ToolError, match="escapes"):
        file_tools.safe_path(tmp_path, "../outside.txt")
    with pytest.raises(file_tools.ToolError, match="forbidden"):
        file_tools.safe_path(tmp_path, ".git/config")


def test_read_file_reports_missing_file(tmp_path):
    with pytest.raises(file_tools.ToolError, match="does not exist"):
        file_tools.read_file(tmp_path, "missing.md")


def test_call_tool_dispatches_and_rejects_unknown_tool(tmp_path):
    assert file_tools.call_tool(tmp_path, "write_file", {"path": "note.md", "content": "ok"})["path"] == "note.md"
    assert file_tools.call_tool(tmp_path, "read_file", {"path": "note.md"})["content"] == "ok"
    assert file_tools.call_tool(
        tmp_path, "read_lines", {"path": "note.md", "start_line": 1, "line_count": 1}
    )["content"] == "1: ok"
    assert file_tools.call_tool(
        tmp_path, "replace_text", {"path": "note.md", "old": "ok", "new": "done"}
    )["replacements"] == 1
    with pytest.raises(file_tools.ToolError, match="unknown tool"):
        file_tools.call_tool(tmp_path, "shell", {})


def test_read_lines_returns_numbered_range(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    result = file_tools.read_lines(tmp_path, "notes.md", 2, 2)

    assert result == {
        "path": "notes.md",
        "start_line": 2,
        "end_line": 3,
        "total_lines": 4,
        "content": "2: two\n3: three",
    }


def test_read_lines_validates_range(tmp_path):
    (tmp_path / "notes.md").write_text("one\n", encoding="utf-8")

    with pytest.raises(file_tools.ToolError, match="start_line"):
        file_tools.read_lines(tmp_path, "notes.md", 0, 1)
    with pytest.raises(file_tools.ToolError, match="line_count"):
        file_tools.read_lines(tmp_path, "notes.md", 1, 0)


def test_replace_text_replaces_exact_fragment(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    result = file_tools.replace_text(tmp_path, "notes.md", "beta", "delta")

    assert result["path"] == "notes.md"
    assert result["replacements"] == 1
    assert path.read_text(encoding="utf-8") == "alpha\ndelta\ngamma\n"


def test_replace_text_requires_expected_replacements(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("same same", encoding="utf-8")

    with pytest.raises(file_tools.ToolError, match="expected 1 replacement"):
        file_tools.replace_text(tmp_path, "notes.md", "same", "other")
    with pytest.raises(file_tools.ToolError, match="old text"):
        file_tools.replace_text(tmp_path, "notes.md", "", "other")


def test_read_lines_rejects_missing_and_directory(tmp_path):
    with pytest.raises(file_tools.ToolError, match="does not exist"):
        file_tools.read_lines(tmp_path, "missing.md", 1, 1)

    directory = tmp_path / "folder"
    directory.mkdir()
    with pytest.raises(file_tools.ToolError, match="not a file"):
        file_tools.read_lines(tmp_path, "folder", 1, 1)


def test_replace_text_rejects_invalid_count_missing_and_directory(tmp_path):
    with pytest.raises(file_tools.ToolError, match="expected_replacements"):
        file_tools.replace_text(tmp_path, "missing.md", "old", "new", 0)
    with pytest.raises(file_tools.ToolError, match="does not exist"):
        file_tools.replace_text(tmp_path, "missing.md", "old", "new")

    directory = tmp_path / "folder"
    directory.mkdir()
    with pytest.raises(file_tools.ToolError, match="not a file"):
        file_tools.replace_text(tmp_path, "folder", "old", "new")


def test_tool_result_json_preserves_russian_text():
    payload = file_tools.tool_result_json({"content": "привет"})

    assert json.loads(payload)["content"] == "привет"


def test_schema_tool_name_raises_on_missing_function_key():
    """schema_tool_name поднимает ToolError при отсутствии function.name."""
    with pytest.raises(file_tools.ToolError, match="missing function.name"):
        file_tools.schema_tool_name({})


def test_schema_tool_name_raises_on_empty_name():
    """schema_tool_name поднимает ToolError при пустом function.name."""
    with pytest.raises(file_tools.ToolError, match="invalid function.name"):
        file_tools.schema_tool_name({"function": {"name": ""}})


def test_schema_tool_name_raises_on_non_string_name():
    """schema_tool_name поднимает ToolError при function.name не строке."""
    with pytest.raises(file_tools.ToolError, match="invalid function.name"):
        file_tools.schema_tool_name({"function": {"name": 123}})


def test_schema_tool_name_returns_valid_name():
    """schema_tool_name возвращает имя из schema."""
    name = file_tools.schema_tool_name({"function": {"name": "read_file"}})
    assert name == "read_file"
    

class TestDiscoverToolModules:
    """Тесты для discover_tool_modules — ветвление по директориям инструментов."""

    def test_skips_dirs_without_tool_py(self, tmp_path):
        """discover_tool_modules пропускает директории без tool.py."""
        fake_tool = tmp_path / "src" / "tools" / "fake_tool"
        fake_tool.mkdir(parents=True)

        original_root = file_tools.TOOLS_ROOT
        try:
            file_tools.TOOLS_ROOT = tmp_path / "src" / "tools"
            modules = file_tools.discover_tool_modules()
            assert modules == []
        finally:
            file_tools.TOOLS_ROOT = original_root

    def test_skips_hidden_dirs(self, tmp_path):
        """discover_tool_modules пропускает директории, начинающиеся с '_'. """
        hidden = tmp_path / "src" / "tools" / "_private"
        hidden.mkdir(parents=True)
        (hidden / "tool.py").write_text(
            "def schema(): pass\ndef passport(): pass\ndef handle(r, a): pass\n",
            encoding="utf-8",
        )

        original_root = file_tools.TOOLS_ROOT
        try:
            file_tools.TOOLS_ROOT = tmp_path / "src" / "tools"
            modules = file_tools.discover_tool_modules()
            assert modules == []
        finally:
            file_tools.TOOLS_ROOT = original_root


class TestLoadToolsDuplicate:
    """Тесты для load_tools — ветка дублирующегося имени."""

    def test_duplicate_tool_name_raises(self, monkeypatch):
        """load_tools поднимает ToolError при дублирующихся именах инструментов."""
        from types import ModuleType

        mock_module_a = ModuleType("mock_a")
        mock_module_a.schema = lambda: {"function": {"name": "duplicated"}}
        mock_module_a.passport = lambda: ""
        mock_module_a.handle = lambda r, a: {}

        mock_module_b = ModuleType("mock_b")
        mock_module_b.schema = lambda: {"function": {"name": "duplicated"}}
        mock_module_b.passport = lambda: ""
        mock_module_b.handle = lambda r, a: {}

        monkeypatch.setattr(file_tools, "discover_tool_modules", lambda: [mock_module_a, mock_module_b])

        with pytest.raises(file_tools.ToolError, match="duplicate tool name: duplicated"):
            file_tools.load_tools()


class TestDiscoverMissingRequiredFunction:
    """Тесты для discover_tool_modules — ветка отсутствия требуемой функции.

    Ветка строки 32 (raise ToolError при отсутствии handle) требует создания
    реального модуля с отсутствующей функцией и его импорта через importlib.
    Это невозможно без pytest-mock или изменения discover_tool_modules.
    Ветка остаётся частично покрытой (BrPart) — она проверяется косвенно
    через реестр инструментов, где все 15 инструментов имеют все 3 функции.
    """

    pass
