from scripts import file_tools
from src.tools.reader import core


def test_reader_core_file_modes_return_error_for_directory(tmp_path):
    directory = tmp_path / "export"
    directory.mkdir()

    calls = [
        core.read_lines(str(directory), 1, 1),
        core.read_head(str(directory)),
        core.read_tail(str(directory)),
        core.read_func(str(directory), "main"),
        core.read_class(str(directory), "Service"),
        core.read_pattern(str(directory), "func"),
        core.read_section(str(directory), "Контекст"),
    ]

    for result in calls:
        assert result.lines_read == 0
        assert "директория" in result.error
        assert "директория" in result.content


def test_reader_pattern_tool_handles_directory_without_crashing(tmp_path):
    export_dir = tmp_path / "projects" / "foundation-finance" / "backend" / "internal" / "export"
    export_dir.mkdir(parents=True)

    result = file_tools.call_tool(
        tmp_path,
        "reader",
        {
            "mode": "pattern",
            "path": "projects/foundation-finance/backend/internal/export",
            "pattern": "func",
        },
    )

    assert result["method"] == "pattern"
    assert result["lines_read"] == 0
    assert "директория" in result["error"]
