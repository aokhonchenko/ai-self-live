import sys

import pytest

from scripts import file_tools


def tool_names():
    return {schema["function"]["name"] for schema in file_tools.TOOL_SCHEMAS}


def test_registry_discovers_tool_schemas_and_passport():
    names = tool_names()

    assert {
        "read_file",
        "read_lines",
        "replace_text",
        "write_file",
        "run_command",
        "run_pytest",
        "run_python_script",
        "apply_patch",
        "reader",
        "partial_reader",
        "code_analyzer",
        "prompt_builder",
        "self_review",
        "command_runner",
        "compat_reader",
    } <= names
    assert "`run_command" in file_tools.TOOL_PASSPORT
    assert "`run_pytest" in file_tools.TOOL_PASSPORT
    assert "`apply_patch" in file_tools.TOOL_PASSPORT
    assert "`reader" in file_tools.TOOL_PASSPORT


def test_discovered_command_tool_executes_inside_root(tmp_path):
    command = f'"{sys.executable}" -c "print(123)"'

    result = file_tools.call_tool(tmp_path, "run_command", {"command": command, "timeout": 10})

    assert result["returncode"] == 0
    assert result["stdout"].strip() == "123"
    assert result["stderr"] == ""


def test_discovered_command_tool_rejects_cwd_outside_root(tmp_path):
    with pytest.raises(file_tools.ToolError, match="cwd escapes"):
        file_tools.call_tool(
            tmp_path,
            "run_command",
            {"command": "echo nope", "cwd": str(tmp_path.parent), "timeout": 10},
        )


def test_discovered_run_python_script_tool(tmp_path):
    script = tmp_path / "hello.py"
    script.write_text("print('hello from script')\n", encoding="utf-8")

    result = file_tools.call_tool(
        tmp_path,
        "run_python_script",
        {"script_path": "hello.py", "timeout": 10},
    )

    assert result["returncode"] == 0
    assert result["stdout"].strip() == "hello from script"


def test_discovered_run_pytest_tool(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    result = file_tools.call_tool(
        tmp_path,
        "run_pytest",
        {"test_path": "tests/test_sample.py", "args": ["-q"], "timeout": 30},
    )

    assert result["returncode"] == 0
    assert "1 passed" in result["stdout"]


def test_legacy_reader_tools_are_callable(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("# Title\nbody\n", encoding="utf-8")

    partial = file_tools.call_tool(tmp_path, "partial_reader", {"mode": "headers", "path": "note.md"})
    focused = file_tools.call_tool(tmp_path, "reader", {"mode": "head", "path": "note.md", "n": 1})
    compat = file_tools.call_tool(tmp_path, "compat_reader", {"mode": "head", "path": "note.md", "n": 1})

    assert "Title" in partial["content"]
    assert "Title" in focused["content"]
    assert "Title" in compat["content"]


def test_legacy_apply_patch_tool_is_callable(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("old\n", encoding="utf-8")

    result = file_tools.call_tool(
        tmp_path,
        "apply_patch",
        {"operation": "replace", "path": "note.md", "old": "old", "new": "new"},
    )

    assert result["applied"] is True
    assert note.read_text(encoding="utf-8") == "new\n"


def test_legacy_code_analyzer_tool_is_callable(tmp_path):
    module = tmp_path / "sample.py"
    module.write_text("def ok():\n    return True\n", encoding="utf-8")

    result = file_tools.call_tool(tmp_path, "code_analyzer", {"path": "sample.py", "mode": "file"})

    assert "ok" in result["content"]


def test_prompt_builder_tool_is_callable(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "state" / "last_session.md").write_text("прошлая\n", encoding="utf-8")
    (tmp_path / "state" / "current_plan.md").write_text("план\n", encoding="utf-8")
    (tmp_path / "state" / "external_messages.md").write_text("сообщение\n", encoding="utf-8")
    (tmp_path / "tasks" / "active.md").write_text("задача\n", encoding="utf-8")

    result = file_tools.call_tool(tmp_path, "prompt_builder", {"format": "stats"})

    assert result["format"] == "stats"
    assert result["content"]["sections"] == 4


def test_partial_reader_info_handles_directory(tmp_path):
    project = tmp_path / "projects" / "foundation-finance"
    project.mkdir(parents=True)
    (project / "README.md").write_text("# demo\n", encoding="utf-8")

    result = file_tools.call_tool(
        tmp_path,
        "partial_reader",
        {"mode": "info", "path": "projects/foundation-finance"},
    )

    assert result["mode"] == "info"
    assert "\u0414\u0438\u0440\u0435\u043a\u0442\u043e\u0440\u0438\u044f:" in result["content"]
    assert "README.md" in result["content"]


def test_partial_reader_file_modes_reject_directory(tmp_path):
    project = tmp_path / "projects" / "foundation-finance"
    project.mkdir(parents=True)

    with pytest.raises(file_tools.ToolError, match="path is a directory"):
        file_tools.call_tool(
            tmp_path,
            "partial_reader",
            {"mode": "head", "path": "projects/foundation-finance"},
        )

