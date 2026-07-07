import subprocess
from pathlib import Path


from scripts import run_session


def write_minimal_experiment(root: Path) -> None:
    (root / "state").mkdir()
    (root / "logs").mkdir()
    (root / "knowledge").mkdir()
    (root / "projects").mkdir()
    (root / "tools").mkdir()
    (root / "SYSTEM_PROMPT.md").write_text("Системные правила\n", encoding="utf-8")
    (root / "state" / "last_session.md").write_text("Предыдущая сессия\n", encoding="utf-8")
    (root / "state" / "current_plan.md").write_text("Текущий план\n", encoding="utf-8")
    (root / "state" / "external_messages.md").write_text("Сообщение человека\n", encoding="utf-8")
    (root / "state" / "session_counter.txt").write_text("7\n", encoding="utf-8")


def test_read_text_or_default_reads_existing_file(tmp_path):
    path = tmp_path / "note.md"
    path.write_text("текст", encoding="utf-8")

    assert run_session.read_text_or_default(path, "default") == "текст"


def test_read_text_or_default_returns_default_for_missing_file(tmp_path):
    assert run_session.read_text_or_default(tmp_path / "missing.md", "default") == "default"


def test_read_counter_returns_existing_numeric_value(tmp_path):
    path = tmp_path / "session_counter.txt"
    path.write_text("42\n", encoding="utf-8")

    assert run_session.read_counter(path) == 42


def test_read_counter_falls_back_to_one_for_missing_or_invalid_file(tmp_path):
    assert run_session.read_counter(tmp_path / "missing.txt") == 1

    invalid = tmp_path / "invalid.txt"
    invalid.write_text("not-a-number", encoding="utf-8")

    assert run_session.read_counter(invalid) == 1


def test_build_prompt_includes_memory_and_session_number(tmp_path):
    write_minimal_experiment(tmp_path)

    prompt = run_session.build_prompt(tmp_path, 7)

    assert "# Активный промпт сессии 7" in prompt
    assert "Системные правила" in prompt
    assert "Предыдущая сессия" in prompt
    assert "Текущий план" in prompt
    assert "Сообщение человека" in prompt
    assert "Все пользовательские артефакты пиши на русском языке" in prompt


def test_build_prompt_uses_defaults_when_files_are_missing(tmp_path):
    (tmp_path / "state").mkdir()

    prompt = run_session.build_prompt(tmp_path, 1)

    assert "Системный промпт отсутствует" in prompt
    assert "Самостоятельно выбери" in prompt
    assert "Предыдущих сообщений нет" in prompt
    assert "Текущий план пока не задан" in prompt
    assert "Внешних сообщений нет" in prompt


def test_expand_command_replaces_all_placeholders(tmp_path):
    prompt_file = tmp_path / "state" / "active_prompt.md"

    command = run_session.expand_command(
        'agent --cwd "{ROOT}" --prompt "{PROMPT_FILE}" --session {SESSION}',
        root=tmp_path,
        prompt_file=prompt_file,
        session=3,
    )

    assert str(tmp_path) in command
    assert str(prompt_file) in command
    assert "--session 3" in command
    assert "{ROOT}" not in command
    assert "{PROMPT_FILE}" not in command
    assert "{SESSION}" not in command


def test_main_dry_run_writes_prompt_without_incrementing_counter(tmp_path, monkeypatch, capsys):
    write_minimal_experiment(tmp_path)
    monkeypatch.setattr(run_session, "ROOT_OVERRIDE", tmp_path, raising=False)
    monkeypatch.setattr(run_session.sys, "argv", ["run_session.py", "--dry-run"])

    result = run_session.main()

    captured = capsys.readouterr()
    assert result == 0
    assert "Dry-run" in captured.out
    assert (tmp_path / "state" / "active_prompt.md").exists()
    assert (tmp_path / "state" / "session_counter.txt").read_text(encoding="utf-8") == "7\n"


def test_main_without_agent_command_increments_counter_and_logs(tmp_path, monkeypatch, capsys):
    write_minimal_experiment(tmp_path)
    monkeypatch.setattr(run_session, "ROOT_OVERRIDE", tmp_path, raising=False)
    monkeypatch.setattr(run_session.sys, "argv", ["run_session.py"])

    result = run_session.main()

    captured = capsys.readouterr()
    assert result == 0
    assert "задайте AI_AGENT_COMMAND" in captured.out
    assert (tmp_path / "state" / "session_counter.txt").read_text(encoding="utf-8") == "8\n"
    history = (tmp_path / "logs" / "history.md").read_text(encoding="utf-8")
    assert "Сессия 7 - prompt prepared" in history
    assert "command missing" in history


def test_main_runs_expanded_agent_command(tmp_path, monkeypatch):
    write_minimal_experiment(tmp_path)
    calls = []

    def fake_run(command, cwd, shell, env):
        calls.append((command, cwd, shell, env))
        return subprocess.CompletedProcess(command, 13)

    monkeypatch.setattr(run_session, "ROOT_OVERRIDE", tmp_path, raising=False)
    monkeypatch.setattr(run_session.subprocess, "run", fake_run)
    monkeypatch.setattr(
        run_session.sys,
        "argv",
        ["run_session.py", "--agent-command", 'agent "{ROOT}" "{PROMPT_FILE}" {SESSION}'],
    )

    result = run_session.main()

    assert result == 13
    assert len(calls) == 1
    command, cwd, shell, env = calls[0]
    assert str(tmp_path) in command
    assert str(tmp_path / "state" / "active_prompt.md") in command
    assert " 7" in command
    assert cwd == tmp_path
    assert shell is True
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"



def test_read_questions_includes_question_files_and_skips_readme(tmp_path):
    questions_dir = tmp_path / "state" / "questions"
    questions_dir.mkdir(parents=True)
    (questions_dir / "README.md").write_text("служебное описание", encoding="utf-8")
    (questions_dir / "0007-format.md").write_text(
        "# Вопрос\n\n## Ответ создателя\n\nОтвет есть.\n",
        encoding="utf-8",
    )

    questions = run_session.read_questions(tmp_path)

    assert "0007-format.md" in questions
    assert "Ответ есть" in questions
    assert "служебное описание" not in questions


def test_read_questions_reports_empty_state_when_no_questions_exist(tmp_path):
    assert "Вопросов создателю пока нет" in run_session.read_questions(tmp_path)

    (tmp_path / "state" / "questions").mkdir(parents=True)
    assert "Вопросов создателю пока нет" in run_session.read_questions(tmp_path)


def test_build_prompt_includes_questions_section(tmp_path):
    write_minimal_experiment(tmp_path)
    questions_dir = tmp_path / "state" / "questions"
    questions_dir.mkdir()
    (questions_dir / "0007-topic.md").write_text("## Ответ создателя\n\nДвигаться дальше.\n", encoding="utf-8")

    prompt = run_session.build_prompt(tmp_path, 7)

    assert "# state/questions/" in prompt
    assert "0007-topic.md" in prompt
    assert "Двигаться дальше" in prompt


def test_main_dry_run_creates_questions_directory(tmp_path, monkeypatch):
    write_minimal_experiment(tmp_path)
    monkeypatch.setattr(run_session, "ROOT_OVERRIDE", tmp_path, raising=False)
    monkeypatch.setattr(run_session.sys, "argv", ["run_session.py", "--dry-run"])

    result = run_session.main()

    assert result == 0
    assert (tmp_path / "state" / "questions").is_dir()


def test_build_prompt_includes_sleep_state(tmp_path):
    write_minimal_experiment(tmp_path)
    sleep_dir = tmp_path / "state" / "sleep"
    sleep_dir.mkdir()
    (sleep_dir / "last_sleep.md").write_text("Последний сон очистил память.\n", encoding="utf-8")

    prompt = run_session.build_prompt(tmp_path, 7)

    assert "# state/sleep/last_sleep.md" in prompt
    assert "Последний сон очистил память" in prompt
    

def test_main_print_prompt_outputs_prompt_to_stdout(tmp_path, monkeypatch, capsys):
    write_minimal_experiment(tmp_path)
    monkeypatch.setattr(run_session, "ROOT_OVERRIDE", tmp_path, raising=False)
    monkeypatch.setattr(run_session.sys, "argv", ["run_session.py", "--print-prompt"])

    result = run_session.main()

    captured = capsys.readouterr()
    assert result == 0
    assert "# Активный промпт сессии 7" in captured.out
    assert "Системные правила" in captured.out


def test_project_root_returns_default_when_override_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(run_session, "ROOT_OVERRIDE", None, raising=False)

    root = run_session.project_root()

    assert root == Path(__file__).resolve().parents[1]


def test_project_root_returns_override_when_set(tmp_path, monkeypatch):
    monkeypatch.setattr(run_session, "ROOT_OVERRIDE", tmp_path, raising=False)

    root = run_session.project_root()

    assert root == tmp_path
