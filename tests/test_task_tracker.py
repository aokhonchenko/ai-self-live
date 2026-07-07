"""Тесты для scripts/task_tracker.py."""

from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime, timezone

from scripts.task_tracker import (
    TaskError,
    create_task,
    update_task,
    close_task,
    list_tasks,
    read_task,
    delete_task,
    parse_meta,
    task_title,
    task_status,
    task_priority,
    task_created,
    task_updated,
    task_body,
    tasks_dir,
    today_str,
    _title_to_slug,
)


# --- Утилиты ---

def _sample_content(title: str = "Тестовая задача", status: str = "open",
                    priority: str = "medium", created: str = "2026-07-08",
                    updated: str = "2026-07-08") -> str:
    return f"""# Задача: {title}

Статус: {status}
Приоритет: {priority}
Создана: {created}
Обновлено: {updated}

## Описание

Текст задачи.
"""


# --- today_str ---

class TestTodayStr:
    def test_returns_date_format(self):
        result = today_str()
        assert len(result) == 10
        assert result[4] == "-"
        assert result[7] == "-"

    def test_returns_current_date(self):
        result = today_str()
        expected = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert result == expected


# --- _title_to_slug ---

class TestTitleToSlug:
    def test_simple_title(self):
        assert _title_to_slug("Простая задача") == "простая-задача"

    def test_cyrillic_title(self):
        assert _title_to_slug("Исправить баг") == "исправить-баг"

    def test_with_numbers(self):
        assert _title_to_slug("Задача 42") == "задача-42"

    def test_special_chars_removed(self):
        assert _title_to_slug("Задача с !@#$") == "задача-с"

    def test_empty_result_becomes_untitled(self):
        assert _title_to_slug("!@#$") == "untitled"

    def test_multiple_spaces_become_single_dash(self):
        assert _title_to_slug("Много   пробелов") == "много-пробелов"

    def test_leading_trailing_special(self):
        assert _title_to_slug("-Задача-") == "задача"

    def test_mixed_language(self):
        assert _title_to_slug("Fix bug 123") == "fix-bug-123"


# --- parse_meta ---

class TestParseMeta:
    def test_parses_all_fields(self):
        content = """# Задача: Тест

Статус: open
Приоритет: high
Создана: 2026-07-08
Обновлено: 2026-07-09
"""
        meta = parse_meta(content)
        assert meta["статус"] == "open"
        assert meta["приоритет"] == "high"
        assert meta["создана"] == "2026-07-08"
        assert meta["обновлено"] == "2026-07-09"

    def test_parses_english_fields(self):
        content = """# Задача: Тест

Status: closed
Priority: low
Created: 2026-01-01
Updated: 2026-01-02
"""
        meta = parse_meta(content)
        assert meta["status"] == "closed"
        assert meta["priority"] == "low"

    def test_empty_content(self):
        assert parse_meta("") == {}

    def test_no_meta_lines(self):
        content = "# Задача: Тест\n\nТело без метаданных."
        meta = parse_meta(content)
        assert meta == {}

    def test_extra_whitespace(self):
        content = "Статус:   open  \n"
        meta = parse_meta(content)
        assert meta["статус"] == "open"


# --- task_title ---

class TestTaskTitle:
    def test_returns_first_heading(self):
        content = "# Задача: Исправить баг\n\nТекст."
        assert task_title(content) == "Исправить баг"

    def test_empty_content(self):
        assert task_title("") == ""

    def test_no_heading(self):
        content = "Текст без заголовка."
        assert task_title(content) == ""

    def test_heading_with_extra_spaces(self):
        content = "#   Задача: Тест   \n\nТекст."
        assert task_title(content) == "Тест"


# --- task_status ---

class TestTaskStatus:
    def test_russian_status(self):
        content = "# Задача: Тест\n\nСтатус: open\n"
        assert task_status(content) == "open"

    def test_english_status(self):
        content = "# Задача: Тест\n\nStatus: closed\n"
        assert task_status(content) == "closed"

    def test_default_open(self):
        content = "# Задача: Тест\n\nТекст."
        assert task_status(content) == "open"

    def test_in_progress_status(self):
        content = "# Задача: Тест\n\nСтатус: in_progress\n"
        assert task_status(content) == "in_progress"


# --- task_priority ---

class TestTaskPriority:
    def test_russian_priority(self):
        content = "# Задача: Тест\n\nПриоритет: high\n"
        assert task_priority(content) == "high"

    def test_english_priority(self):
        content = "# Задача: Тест\n\nPriority: critical\n"
        assert task_priority(content) == "critical"

    def test_default_medium(self):
        content = "# Задача: Тест\n\nТекст."
        assert task_priority(content) == "medium"

    def test_low_priority(self):
        content = "# Задача: Тест\n\nПриоритет: low\n"
        assert task_priority(content) == "low"


# --- task_created / task_updated ---

class TestTaskCreated:
    def test_returns_created_date(self):
        content = "# Задача: Тест\n\nСоздана: 2026-01-15\n"
        assert task_created(content) == "2026-01-15"

    def test_english_created(self):
        content = "# Задача: Тест\n\nCreated: 2026-03-20\n"
        assert task_created(content) == "2026-03-20"

    def test_empty_when_missing(self):
        content = "# Задача: Тест\n\nТекст."
        assert task_created(content) == ""


class TestTaskUpdated:
    def test_returns_updated_date(self):
        content = "# Задача: Тест\n\nОбновлено: 2026-02-20\n"
        assert task_updated(content) == "2026-02-20"

    def test_english_updated(self):
        content = "# Задача: Тест\n\nUpdated: 2026-04-10\n"
        assert task_updated(content) == "2026-04-10"

    def test_empty_when_missing(self):
        content = "# Задача: Тест\n\nТекст."
        assert task_updated(content) == ""


# --- task_body ---

class TestTaskBody:
    def test_returns_body_text(self):
        content = "# Задача: Тест\n\nСтатус: open\n\nТело задачи.\nЕщё строка."
        body = task_body(content)
        assert "Тело задачи." in body
        assert "Ещё строка." in body

    def test_empty_when_no_body(self):
        content = "# Задача: Тест\n\nСтатус: open\n"
        assert task_body(content) == ""

    def test_body_after_meta(self):
        content = "# Задача: Тест\n\nСтатус: open\nПриоритет: high\n\n## Описание\n\nТекст."
        body = task_body(content)
        assert "Текст." in body


# --- tasks_dir ---

class TestTasksDir:
    def test_returns_correct_path(self, tmp_path: Path):
        result = tasks_dir(tmp_path)
        assert result == tmp_path / "state" / "tasks"


# --- create_task ---

class TestCreateTask:
    def test_creates_file(self, tmp_path: Path):
        path = create_task(tmp_path, "Новая задача", "Описание")
        assert path.exists()
        assert path.name == "новая-задача.md"

    def test_file_contains_title(self, tmp_path: Path):
        create_task(tmp_path, "Исправить баг", "Критический баг")
        content = (tmp_path / "state" / "tasks" / "исправить-баг.md").read_text()
        assert "Исправить баг" in content

    def test_file_contains_description(self, tmp_path: Path):
        create_task(tmp_path, "Задача", "Подробное описание")
        content = (tmp_path / "state" / "tasks" / "задача.md").read_text()
        assert "Подробное описание" in content

    def test_default_priority(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        content = (tmp_path / "state" / "tasks" / "задача.md").read_text()
        assert "Приоритет: medium" in content

    def test_custom_priority(self, tmp_path: Path):
        create_task(tmp_path, "Задача", priority="high")
        content = (tmp_path / "state" / "tasks" / "задача.md").read_text()
        assert "Приоритет: high" in content

    def test_custom_status(self, tmp_path: Path):
        create_task(tmp_path, "Задача", status="in_progress")
        content = (tmp_path / "state" / "tasks" / "задача.md").read_text()
        assert "Статус: in_progress" in content

    def test_raises_on_duplicate(self, tmp_path: Path):
        create_task(tmp_path, "Уникальная задача")
        with pytest.raises(TaskError, match="уже существует"):
            create_task(tmp_path, "Уникальная задача")

    def test_raises_on_invalid_status(self, tmp_path: Path):
        with pytest.raises(TaskError, match="Недопустимый статус"):
            create_task(tmp_path, "Задача", status="invalid")

    def test_raises_on_invalid_priority(self, tmp_path: Path):
        with pytest.raises(TaskError, match="Недопустимый приоритет"):
            create_task(tmp_path, "Задача", priority="extreme")

    def test_creates_tasks_dir(self, tmp_path: Path):
        tasks_dir_path = tmp_path / "state" / "tasks"
        assert not tasks_dir_path.exists()
        create_task(tmp_path, "Задача")
        assert tasks_dir_path.exists()

    def test_contains_date(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        content = (tmp_path / "state" / "tasks" / "задача.md").read_text()
        assert today_str() in content


# --- update_task ---

class TestUpdateTask:
    def test_updates_status(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        update_task(tmp_path, "Задача", status="in_progress")
        content = (tmp_path / "state" / "tasks" / "задача.md").read_text()
        assert "Статус: in_progress" in content

    def test_updates_priority(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        update_task(tmp_path, "Задача", priority="critical")
        content = (tmp_path / "state" / "tasks" / "задача.md").read_text()
        assert "Приоритет: critical" in content

    def test_raises_on_not_found(self, tmp_path: Path):
        with pytest.raises(TaskError, match="не найдена"):
            update_task(tmp_path, "Не существует")

    def test_raises_on_invalid_status(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        with pytest.raises(TaskError, match="Недопустимый статус"):
            update_task(tmp_path, "Задача", status="invalid")

    def test_raises_on_invalid_priority(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        with pytest.raises(TaskError, match="Недопустимый приоритет"):
            update_task(tmp_path, "Задача", priority="super")

    def test_adds_note(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        update_task(tmp_path, "Задача", note="Важная заметка")
        content = (tmp_path / "state" / "tasks" / "задача.md").read_text()
        assert "> Важная заметка" in content

    def test_updates_date_on_note(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        update_task(tmp_path, "Задача", note="Заметка")
        content = (tmp_path / "state" / "tasks" / "задача.md").read_text()
        assert "Обновлено:" in content

    def test_returns_path(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        path = update_task(tmp_path, "Задача", status="closed")
        assert path.exists()


# --- close_task ---

class TestCloseTask:
    def test_sets_status_closed(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        close_task(tmp_path, "Задача")
        content = (tmp_path / "state" / "tasks" / "задача.md").read_text()
        assert "Статус: closed" in content

    def test_adds_resolution(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        close_task(tmp_path, "Задача", resolution="Исправлено")
        content = (tmp_path / "state" / "tasks" / "задача.md").read_text()
        assert "Исправлено" in content

    def test_raises_on_not_found(self, tmp_path: Path):
        with pytest.raises(TaskError, match="не найдена"):
            close_task(tmp_path, "Не существует")

    def test_updates_date(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        close_task(tmp_path, "Задача")
        content = (tmp_path / "state" / "tasks" / "задача.md").read_text()
        assert "Обновлено:" in content

    def test_returns_path(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        path = close_task(tmp_path, "Задача")
        assert path.exists()


# --- list_tasks ---

class TestListTasks:
    def test_returns_empty_when_no_tasks(self, tmp_path: Path):
        result = list_tasks(tmp_path)
        assert result == []

    def test_returns_list_of_tasks(self, tmp_path: Path):
        create_task(tmp_path, "Задача 1")
        create_task(tmp_path, "Задача 2")
        result = list_tasks(tmp_path)
        assert len(result) == 2

    def test_task_has_required_fields(self, tmp_path: Path):
        create_task(tmp_path, "Задача", priority="high")
        result = list_tasks(tmp_path)
        task = result[0]
        assert "title" in task
        assert "status" in task
        assert "priority" in task
        assert "created" in task
        assert "updated" in task
        assert "path" in task

    def test_filters_by_status(self, tmp_path: Path):
        create_task(tmp_path, "Открытая задача", status="open")
        create_task(tmp_path, "Закрытая задача", status="closed")
        result = list_tasks(tmp_path, status="open")
        assert len(result) == 1
        assert result[0]["title"] == "Открытая задача"

    def test_filters_by_priority(self, tmp_path: Path):
        create_task(tmp_path, "Высокий приоритет", priority="high")
        create_task(tmp_path, "Низкий приоритет", priority="low")
        result = list_tasks(tmp_path, priority="high")
        assert len(result) == 1

    def test_filters_by_both(self, tmp_path: Path):
        create_task(tmp_path, "Открытая высокая", status="open", priority="high")
        create_task(tmp_path, "Закрытая высокая", status="closed", priority="high")
        result = list_tasks(tmp_path, status="open", priority="high")
        assert len(result) == 1
        assert result[0]["title"] == "Открытая высокая"

    def test_sorted_by_name(self, tmp_path: Path):
        create_task(tmp_path, "Б задача")
        create_task(tmp_path, "А задача")
        result = list_tasks(tmp_path)
        assert result[0]["title"] == "А задача"

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path):
        result = list_tasks(tmp_path)
        assert result == []


# --- read_task ---

class TestReadTask:
    def test_returns_task_dict(self, tmp_path: Path):
        create_task(tmp_path, "Задача", "Описание", priority="high")
        task = read_task(tmp_path, "Задача")
        assert task["title"] == "Задача"
        assert task["status"] == "open"
        assert task["priority"] == "high"
        assert task["body"] == "Описание"

    def test_raises_on_not_found(self, tmp_path: Path):
        with pytest.raises(TaskError, match="не найдена"):
            read_task(tmp_path, "Не существует")

    def test_contains_path(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        task = read_task(tmp_path, "Задача")
        assert "state/tasks/задача.md" in task["path"] or "state\\tasks\\задача.md" in task["path"]


# --- delete_task ---

class TestDeleteTask:
    def test_removes_file(self, tmp_path: Path):
        create_task(tmp_path, "Задача")
        delete_task(tmp_path, "Задача")
        assert not (tmp_path / "state" / "tasks" / "задача.md").exists()

    def test_raises_on_not_found(self, tmp_path: Path):
        with pytest.raises(TaskError, match="не найдена"):
            delete_task(tmp_path, "Не существует")

    def test_other_tasks_unchanged(self, tmp_path: Path):
        create_task(tmp_path, "Задача 1")
        create_task(tmp_path, "Задача 2")
        delete_task(tmp_path, "Задача 1")
        assert read_task(tmp_path, "Задача 2")["title"] == "Задача 2"


# --- CLI main ---

class TestMain:
    def test_no_command_prints_help(self, tmp_path: Path, capsys, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "argv", ["task_tracker"])
        from scripts.task_tracker import main as main_func
        with pytest.raises(SystemExit):
            main_func()
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "Трекер задач" in combined or "usage" in combined.lower() or "create" in combined
        
    def test_create_command(self, tmp_path: Path, capsys, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "argv", [
            "task_tracker", "create", "Новая задача",
            "--description", "Описание задачи", "--priority", "high"
        ])
        monkeypatch.chdir(tmp_path)
        from scripts.task_tracker import main as main_func
        main_func()
        captured = capsys.readouterr()
        assert "Создана задача:" in captured.out
        task_file = tmp_path / "state" / "tasks" / "новая-задача.md"
        assert task_file.exists()
        content = task_file.read_text()
        assert "Приоритет: high" in content

    def test_list_command_empty(self, tmp_path: Path, capsys, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "argv", ["task_tracker", "list"])
        monkeypatch.chdir(tmp_path)
        from scripts.task_tracker import main as main_func
        main_func()
        captured = capsys.readouterr()
        assert "Задач не найдено" in captured.out

    def test_list_command_with_tasks(self, tmp_path: Path, capsys, monkeypatch):
        import sys
        create_task(tmp_path, "Задача А", "Описание", priority="high")
        create_task(tmp_path, "Задача Б", "Описание", priority="low")
        monkeypatch.setattr(sys, "argv", ["task_tracker", "list"])
        monkeypatch.chdir(tmp_path)
        from scripts.task_tracker import main as main_func
        main_func()
        captured = capsys.readouterr()
        assert "Задача А" in captured.out
        assert "Задача Б" in captured.out

    def test_read_command(self, tmp_path: Path, capsys, monkeypatch):
        import sys
        create_task(tmp_path, "Прочитать", "Текст задачи", status="open")
        monkeypatch.setattr(sys, "argv", ["task_tracker", "read", "Прочитать"])
        monkeypatch.chdir(tmp_path)
        from scripts.task_tracker import main as main_func
        main_func()
        captured = capsys.readouterr()
        assert "Заголовок: Прочитать" in captured.out
        assert "Статус: open" in captured.out
        assert "Тело:" in captured.out
        assert "Текст задачи" in captured.out

    def test_read_command_not_found(self, tmp_path: Path, capsys, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "argv", ["task_tracker", "read", "Не существует"])
        monkeypatch.chdir(tmp_path)
        from scripts.task_tracker import main as main_func
        with pytest.raises(SystemExit):
            main_func()
        captured = capsys.readouterr()
        assert "Ошибка" in captured.err

    def test_update_command(self, tmp_path: Path, capsys, monkeypatch):
        import sys
        create_task(tmp_path, "Обновить", "Текст", status="open")
        monkeypatch.setattr(sys, "argv", [
            "task_tracker", "update", "Обновить",
            "--status", "in_progress", "--note", "Работа началась"
        ])
        monkeypatch.chdir(tmp_path)
        from scripts.task_tracker import main as main_func
        main_func()
        captured = capsys.readouterr()
        assert "Обновлена задача:" in captured.out
        task_file = tmp_path / "state" / "tasks" / "обновить.md"
        content = task_file.read_text()
        assert "Статус: in_progress" in content
        assert "> Работа началась" in content

    def test_close_command(self, tmp_path: Path, capsys, monkeypatch):
        import sys
        create_task(tmp_path, "Закрыть", "Текст", status="open")
        monkeypatch.setattr(sys, "argv", [
            "task_tracker", "close", "Закрыть",
            "--resolution", "Исправлено"
        ])
        monkeypatch.chdir(tmp_path)
        from scripts.task_tracker import main as main_func
        main_func()
        captured = capsys.readouterr()
        assert "Задача закрыта:" in captured.out
        task_file = tmp_path / "state" / "tasks" / "закрыть.md"
        content = task_file.read_text()
        assert "Статус: closed" in content
        assert "## Решение" in content

    def test_close_command_not_found(self, tmp_path: Path, capsys, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "argv", ["task_tracker", "close", "Не существует"])
        monkeypatch.chdir(tmp_path)
        from scripts.task_tracker import main as main_func
        with pytest.raises(SystemExit):
            main_func()
        captured = capsys.readouterr()
        assert "Ошибка" in captured.err

    def test_delete_command(self, tmp_path: Path, capsys, monkeypatch):
        import sys
        create_task(tmp_path, "Удалить", "Текст", status="open")
        monkeypatch.setattr(sys, "argv", ["task_tracker", "delete", "Удалить"])
        monkeypatch.chdir(tmp_path)
        from scripts.task_tracker import main as main_func
        main_func()
        captured = capsys.readouterr()
        assert "Задача удалена" in captured.out
        task_file = tmp_path / "state" / "tasks" / "удалить.md"
        assert not task_file.exists()

    def test_delete_command_not_found(self, tmp_path: Path, capsys, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "argv", ["task_tracker", "delete", "Не существует"])
        monkeypatch.chdir(tmp_path)
        from scripts.task_tracker import main as main_func
        with pytest.raises(SystemExit):
            main_func()
        captured = capsys.readouterr()
        assert "Ошибка" in captured.err
        

# --- close_task: английские поля и решение ---

class TestCloseTaskEnglish:
    def test_closes_with_english_fields(self, tmp_path: Path):
        create_task(tmp_path, "Тест", "Текст", status="open")
        task_file = tmp_path / "state" / "tasks" / "тест.md"
        content = task_file.read_text()
        # Заменяем русские поля на английские
        content = content.replace("Статус: open", "Status: open")
        content = content.replace("Приоритет: medium", "Priority: medium")
        content = content.replace("Создана:", "Created:")
        content = content.replace("Обновлено:", "Updated:")
        task_file.write_text(content)
        close_task(tmp_path, "Тест")
        content = task_file.read_text()
        assert "Status: closed" in content

    def test_closes_with_english_updated(self, tmp_path: Path):
        create_task(tmp_path, "Тест", "Текст", status="open")
        task_file = tmp_path / "state" / "tasks" / "тест.md"
        content = task_file.read_text()
        content = content.replace("Статус: open", "Status: open")
        content = content.replace("Приоритет: medium", "Priority: medium")
        content = content.replace("Создана:", "Created:")
        content = content.replace("Обновлено:", "Updated:")
        task_file.write_text(content)
        close_task(tmp_path, "Тест")
        content = task_file.read_text()
        assert "Status: closed" in content
        assert "Updated:" in content

    def test_close_with_resolution(self, tmp_path: Path):
        create_task(tmp_path, "Тест", "Текст задачи", status="open")
        close_task(tmp_path, "Тест", resolution="Исправлено")
        content = (tmp_path / "state" / "tasks" / "тест.md").read_text()
        assert "## Решение" in content
        assert "Исправлено" in content

    def test_close_without_resolution(self, tmp_path: Path):
        create_task(tmp_path, "Тест", "Текст", status="open")
        close_task(tmp_path, "Тест")
        content = (tmp_path / "state" / "tasks" / "тест.md").read_text()
        assert "Статус: closed" in content
        assert "## Решение" not in content


# --- update_task: английские поля и ветки ---

class TestUpdateTaskEnglish:
    def test_updates_english_status(self, tmp_path: Path):
        create_task(tmp_path, "Тест", "Текст", status="open")
        task_file = tmp_path / "state" / "tasks" / "тест.md"
        content = task_file.read_text()
        content = content.replace("Статус: open", "Status: open")
        content = content.replace("Приоритет: medium", "Priority: medium")
        content = content.replace("Создана:", "Created:")
        content = content.replace("Обновлено:", "Updated:")
        task_file.write_text(content)
        update_task(tmp_path, "Тест", status="in_progress")
        content = task_file.read_text()
        assert "Status: in_progress" in content

    def test_updates_english_priority(self, tmp_path: Path):
        create_task(tmp_path, "Тест", "Текст", status="open")
        task_file = tmp_path / "state" / "tasks" / "тест.md"
        content = task_file.read_text()
        content = content.replace("Статус: open", "Status: open")
        content = content.replace("Приоритет: medium", "Priority: medium")
        content = content.replace("Создана:", "Created:")
        content = content.replace("Обновлено:", "Updated:")
        task_file.write_text(content)
        update_task(tmp_path, "Тест", priority="high")
        content = task_file.read_text()
        assert "Priority: high" in content

    def test_updates_english_updated_date(self, tmp_path: Path):
        create_task(tmp_path, "Тест", "Текст", status="open")
        task_file = tmp_path / "state" / "tasks" / "тест.md"
        content = task_file.read_text()
        content = content.replace("Статус: open", "Status: open")
        content = content.replace("Приоритет: medium", "Priority: medium")
        content = content.replace("Создана:", "Created:")
        content = content.replace("Обновлено:", "Updated:")
        task_file.write_text(content)
        update_task(tmp_path, "Тест", note="Заметка")
        content = task_file.read_text()
        assert "Updated:" in content

    def test_adds_status_when_missing(self, tmp_path: Path):
        create_task(tmp_path, "Тест", "Текст", status="open")
        task_file = tmp_path / "state" / "tasks" / "тест.md"
        content = task_file.read_text()
        # Удаляем строку со статусом
        lines = content.split("\n")
        lines = [l for l in lines if not l.startswith("Статус:")]
        content = "\n".join(lines)
        task_file.write_text(content)
        update_task(tmp_path, "Тест", status="in_progress")
        content = task_file.read_text()
        assert "Статус: in_progress" in content


# --- task_body: ветки без ## заголовков ---

class TestTaskBodyNoHeading:
    def test_body_without_heading(self):
        content = "# Задача: Тест\n\nСтатус: open\nПриоритет: high\n\nТело без заголовка.\nЕщё строка."
        body = task_body(content)
        assert "Тело без заголовка." in body
        assert "Ещё строка." in body

    def test_body_empty_after_meta(self):
        content = "# Задача: Тест\n\nСтатус: open\nПриоритет: high\n"
        body = task_body(content)
        assert body == ""

    def test_body_meta_not_separated_by_blank(self):
        """Контент: метаданные идут сразу после заголовка, без пустой строки,
        затем тело без ## заголовка. Покрывает ветку 148 (continue при метаданных)
        и 154 (past_meta = True при не-метаданной не-пустой строке)."""
        content = "# Задача: Тест\nСтатус: open\nПриоритет: high\nТело без разделителя."
        body = task_body(content)
        assert "Тело без разделителя." in body

    def test_body_meta_then_blank_then_text(self):
        """Метаданные, пустая строка, затем тело. Покрывает ветку 151-152."""
        content = "# Задача: Тест\nСтатус: open\n\nТекст после пустой строки."
        body = task_body(content)
        assert "Текст после пустой строки." in body
        
    def test_update_note_with_english_updated(self, tmp_path: Path):
        """Покрывает ветку 272-278: update_task с note и английским updated."""
        create_task(tmp_path, "Тест", "Текст", status="open")
        task_file = tmp_path / "state" / "tasks" / "тест.md"
        content = task_file.read_text()
        content = content.replace("Статус: open", "Status: open")
        content = content.replace("Приоритет: medium", "Priority: medium")
        content = content.replace("Создана:", "Created:")
        content = content.replace("Обновлено:", "Updated:")
        task_file.write_text(content)
        update_task(tmp_path, "Тест", note="Заметка на английском")
        content = task_file.read_text()
        assert "Updated:" in content
        assert "> Заметка на английском" in content

    def test_close_with_resolution_english(self, tmp_path: Path):
        """Покрывает ветку 325->329, 331->335: close_task с английскими полями и решением."""
        create_task(tmp_path, "Тест", "Текст задачи", status="open")
        task_file = tmp_path / "state" / "tasks" / "тест.md"
        content = task_file.read_text()
        content = content.replace("Статус: open", "Status: open")
        content = content.replace("Приоритет: medium", "Priority: medium")
        content = content.replace("Создана:", "Created:")
        content = content.replace("Обновлено:", "Updated:")
        task_file.write_text(content)
        # close_task с resolution покрывает ветки 335-341 (английские поля + решение)
        close_task(tmp_path, "Тест", resolution="Решено на английском")
        content = task_file.read_text()
        # Решение должно быть добавлено
        assert "## Решение" in content
        assert "Решено на английском" in content


# --- parse_meta: дополнительные тесты ---

class TestParseMetaEdge:
    def test_meta_with_colon_in_value(self):
        content = "Описание: значение: с двоеточием\nСтатус: open\n"
        meta = parse_meta(content)
        assert meta["описание"] == "значение: с двоеточием"
        assert meta["статус"] == "open"

    def test_meta_case_insensitive_keys(self):
        content = "СТАТУС: open\nСтатус: closed\n"
        meta = parse_meta(content)
        assert meta["статус"] == "closed"
