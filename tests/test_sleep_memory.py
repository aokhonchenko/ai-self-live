from pathlib import Path

from scripts import sleep_memory


def write_question(path: Path, status: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Вопрос\n\nСтатус: {status}\n\n## Ответ создателя\n\nТекст.\n",
        encoding="utf-8",
    )


def test_classify_question_detects_statuses(tmp_path):
    open_question = tmp_path / "open.md"
    answered_question = tmp_path / "answered.md"
    closed_question = tmp_path / "closed.md"
    unknown_question = tmp_path / "unknown.md"
    write_question(open_question, "open")
    write_question(answered_question, "answered")
    write_question(closed_question, "closed")
    unknown_question.write_text("# Без статуса\n", encoding="utf-8")

    assert sleep_memory.classify_question(open_question) == "open"
    assert sleep_memory.classify_question(answered_question) == "answered"
    assert sleep_memory.classify_question(closed_question) == "closed"
    assert sleep_memory.classify_question(unknown_question) == "unknown"


def test_archive_closed_questions_moves_only_closed_questions(tmp_path):
    root = tmp_path
    questions = root / "state" / "questions"
    write_question(questions / "0001-open.md", "open")
    write_question(questions / "0002-answered.md", "answered")
    write_question(questions / "0003-closed.md", "closed")

    archived = sleep_memory.archive_closed_questions(root, sleep_memory.datetime(2026, 7, 6, tzinfo=sleep_memory.timezone.utc))

    assert len(archived) == 1
    assert archived[0].name == "0003-closed.md"
    assert not (questions / "0003-closed.md").exists()
    assert (questions / "0001-open.md").exists()
    assert (questions / "0002-answered.md").exists()


def test_run_sleep_writes_report_history_and_last_session(tmp_path):
    root = tmp_path
    (root / "logs").mkdir()
    (root / "logs" / "history.md").write_text("# История\n", encoding="utf-8")
    (root / "state").mkdir()
    write_question(root / "state" / "questions" / "0001-closed.md", "closed")

    report_path = sleep_memory.run_sleep(root)

    assert report_path.exists()
    assert (root / "state" / "sleep" / "last_sleep.md").exists()
    assert "Сон завершён" in (root / "state" / "sleep" / "last_sleep.md").read_text(encoding="utf-8")
    assert "Последняя сессия была сном" in (root / "state" / "last_session.md").read_text(encoding="utf-8")
    assert "Закрытые вопросы перенесены" in (root / "logs" / "history.md").read_text(encoding="utf-8")


def test_question_files_returns_empty_when_no_questions_dir(tmp_path):
    """question_files возвращает [] если директории вопросов не существует."""
    root = tmp_path
    result = sleep_memory.question_files(root)
    assert result == []


def test_archive_closed_questions_handles_name_conflict(tmp_path):
    """При конфликте имён в архиве добавляется timestamp."""
    root = tmp_path
    questions = root / "state" / "questions"
    questions.mkdir(parents=True)
    write_question(questions / "0001-closed.md", "closed")
    archive_dir = questions / "archive" / "2026-07-06"
    archive_dir.mkdir(parents=True)
    (archive_dir / "0001-closed.md").write_text("old archived", encoding="utf-8")

    now = sleep_memory.datetime(2026, 7, 6, 12, 0, 0, tzinfo=sleep_memory.timezone.utc)
    archived = sleep_memory.archive_closed_questions(root, now)

    assert len(archived) == 1
    assert "0001-closed" in archived[0].name
    assert archived[0].exists()


def test_build_sleep_report_includes_all_sections(tmp_path):
    """build_sleep_report формирует отчёт со всеми секциями."""
    root = tmp_path
    questions = root / "state" / "questions"
    questions.mkdir(parents=True)
    write_question(questions / "0001-open.md", "open")
    write_question(questions / "0002-answered.md", "answered")
    write_question(questions / "0003-unknown.md", "unknown")

    now = sleep_memory.datetime(2026, 7, 6, tzinfo=sleep_memory.timezone.utc)
    report = sleep_memory.build_sleep_report(root, [], now)

    assert "Отчёт сна" in report
    assert "Открытые вопросы" in report
    assert "Вопросы с ответом" in report
    assert "Вопросы без распознанного статуса" in report
    assert "0001-open.md" in report
    assert "0002-answered.md" in report
    assert "0003-unknown.md" in report


def test_build_sleep_report_empty_questions(tmp_path):
    """build_sleep_report корректно обрабатывает пустой список вопросов."""
    root = tmp_path
    now = sleep_memory.datetime(2026, 7, 6, tzinfo=sleep_memory.timezone.utc)
    report = sleep_memory.build_sleep_report(root, [], now)

    assert "нет" in report


def test_write_sleep_artifacts_creates_all_files(tmp_path):
    """write_sleep_artifacts создаёт все необходимые файлы."""
    root = tmp_path
    (root / "logs").mkdir()
    (root / "logs" / "history.md").write_text("# История\n", encoding="utf-8")

    now = sleep_memory.datetime(2026, 7, 6, 12, 0, 0, tzinfo=sleep_memory.timezone.utc)
    report_path = sleep_memory.write_sleep_artifacts(root, "# Отчёт\n", now)

    assert report_path.exists()
    assert report_path.name.startswith("2026-07-06")
    assert (root / "state" / "sleep" / "last_sleep.md").exists()
    assert (root / "state" / "last_session.md").exists()
    assert "Последняя сессия была сном" in (root / "state" / "last_session.md").read_text(encoding="utf-8")


def test_main_success(tmp_path, monkeypatch):
    """main возвращает 0 при успешном выполнении."""
    root = tmp_path
    (root / "logs").mkdir()
    (root / "logs" / "history.md").write_text("# История\n", encoding="utf-8")
    (root / "state").mkdir()
    write_question(root / "state" / "questions" / "0001-closed.md", "closed")

    class FakeArgs:
        pass

    fake_args = FakeArgs()
    fake_args.root = str(root)
    fake_args.prompt_file = ""

    class FakeParser:
        def add_argument(self, *a, **kw):
            pass
        def parse_args(self):
            return fake_args

    monkeypatch.setattr(sleep_memory.argparse, "ArgumentParser", lambda **kw: FakeParser())

    result = sleep_memory.main()
    assert result == 0


def test_main_failure_returns_1(tmp_path, monkeypatch):
    """main возвращает 1 при исключении."""
    class FakeArgs:
        pass

    fake_args = FakeArgs()
    fake_args.root = "/nonexistent"
    fake_args.prompt_file = ""

    class FakeParser:
        def add_argument(self, *a, **kw):
            pass
        def parse_args(self):
            return fake_args

    monkeypatch.setattr(sleep_memory.argparse, "ArgumentParser", lambda **kw: FakeParser())

    result = sleep_memory.main()
    assert result == 1
