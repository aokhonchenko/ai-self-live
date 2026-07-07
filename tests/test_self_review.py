#!/usr/bin/env python3
"""
Тесты для src/tools/self_review.py — модуля самоанализа агента.

Запуск: python -m pytest tests/test_self_review.py -v

Создан: сессия 36 (2026-07-06)
Цель: проверить парсинг истории, анализаторы и форматирование отчёта.
"""

import sys
import os
import tempfile
import json
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'tools'))

from self_review import (
    SessionRecord, ReviewFinding, ReviewReport,
    parse_history, parse_last_session,
    find_repeated_problems, find_unused_opportunities,
    find_outdated_artifacts, analyze_session_gaps,
    generate_recommendations, run_self_review, format_report
)


# ─── Вспомогательные функции ───────────────────────────────────────

def _make_temp_file(content: str, suffix: str = '.md') -> str:
    """Создаёт временный файл с заданным содержимым."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


# ─── Тесты парсинга истории ────────────────────────────────────────

class TestParseHistory:
    """Тесты парсинга logs/history.md."""

    def test_empty_file(self):
        path = _make_temp_file('')
        try:
            records = parse_history(path)
            assert records == []
        finally:
            os.unlink(path)

    def test_single_session(self):
        content = """# История сессий

## Сессия 1 — 2026-07-01

Создан первый артефакт.
"""
        path = _make_temp_file(content)
        try:
            records = parse_history(path)
            assert len(records) == 1
            assert records[0].number == 1
            assert records[0].date == '2026-07-01'
            assert 'Создан первый артефакт' in records[0].summary
        finally:
            os.unlink(path)

    def test_multiple_sessions(self):
        content = """# История

## Сессия 1 — 2026-07-01
Создан файл A.

## Сессия 2 — 2026-07-02
Создан файл B.
"""
        path = _make_temp_file(content)
        try:
            records = parse_history(path)
            assert len(records) == 2
            assert records[0].number == 1
            assert records[1].number == 2
        finally:
            os.unlink(path)

    def test_with_dash_variants(self):
        """Проверка разных тире."""
        content = "## Сессия 5 – 2026-07-05\nОбновлён план.\n"
        path = _make_temp_file(content)
        try:
            records = parse_history(path)
            assert len(records) == 1
            assert records[0].number == 5
        finally:
            os.unlink(path)

    def test_no_sessions(self):
        content = "# Просто файл\nбез сессий\n"
        path = _make_temp_file(content)
        try:
            records = parse_history(path)
            assert records == []
        finally:
            os.unlink(path)


# ─── Тесты парсинга last_session ───────────────────────────────────

class TestParseLastSession:
    """Тесты парсинга state/last_session.md."""

    def test_empty_file(self):
        path = _make_temp_file('')
        try:
            sections = parse_last_session(path)
            assert sections == {}
        finally:
            os.unlink(path)

    def test_with_sections(self):
        content = """# Title

## Что было сделано

Создан инструмент.

## Текущее состояние

Всё работает.
"""
        path = _make_temp_file(content)
        try:
            sections = parse_last_session(path)
            assert 'Что было сделано' in sections
            assert 'Текущее состояние' in sections
            assert 'Создан инструмент' in sections['Что было сделано']
        finally:
            os.unlink(path)

    def test_no_sections(self):
        content = "# Просто заголовок\nбез секций\n"
        path = _make_temp_file(content)
        try:
            sections = parse_last_session(path)
            assert sections == {}
        finally:
            os.unlink(path)


# ─── Тесты анализаторов ───────────────────────────────────────────

class TestFindRepeatedProblems:
    """Тесты поиска повторяющихся проблем."""

    def test_no_problems(self):
        records = [
            SessionRecord(1, '2026-07-01', 'Создан полезный артефакт.', ''),
            SessionRecord(2, '2026-07-02', 'Добавлены тесты.', ''),
        ]
        findings = find_repeated_problems(records)
        assert len(findings) == 0

    def test_repeated_bugs(self):
        records = [
            SessionRecord(1, '2026-07-01', 'Исправлен баг в reader.', ''),
            SessionRecord(2, '2026-07-02', 'Ещё один баг.', ''),
            SessionRecord(3, '2026-07-03', 'Снова баг в парсере.', ''),
        ]
        findings = find_repeated_problems(records)
        bug_findings = [f for f in findings if 'баг' in f.title.lower()]
        assert len(bug_findings) >= 1


class TestFindUnusedOpportunities:
    """Тесты поиска неиспользованных возможностей."""

    def test_no_opportunities(self):
        records = [
            SessionRecord(1, '2026-07-01', 'Создан инструмент.', ''),
        ]
        last_session = {}
        findings = find_unused_opportunities(records, last_session)
        # Может найти что-то по ключевым словам, но не критично
        assert isinstance(findings, list)

    def test_with_plan_indicator(self):
        records = [
            SessionRecord(1, '2026-07-01', 'Следующий шаг: создать модуль X.', ''),
        ]
        last_session = {}
        findings = find_unused_opportunities(records, last_session)
        plan_findings = [f for f in findings if 'следующий шаг' in f.title.lower()]
        assert len(plan_findings) >= 1


class TestFindOutdatedArtifacts:
    """Тесты поиска устаревших артефактов."""

    def test_no_outdated(self):
        records = [
            SessionRecord(1, '2026-07-01', 'Создан новый инструмент.', ''),
            SessionRecord(2, '2026-07-02', 'Созданы тесты.', ''),
        ]
        findings = find_outdated_artifacts(records)
        assert len(findings) == 0

    def test_many_updates(self):
        records = [
            SessionRecord(i, f'2026-07-{i:02d}', 'Обновлён файл состояния.', '')
            for i in range(1, 6)
        ]
        findings = find_outdated_artifacts(records)
        assert len(findings) >= 1


class TestAnalyzeSessionGaps:
    """Тесты анализа пробелов в сессиях."""

    def test_no_gaps(self):
        records = [
            SessionRecord(1, '2026-07-01', 'Сессия 1.', ''),
            SessionRecord(2, '2026-07-02', 'Сессия 2.', ''),
            SessionRecord(3, '2026-07-03', 'Сессия 3.', ''),
        ]
        findings = analyze_session_gaps(records)
        gap_findings = [f for f in findings if 'Пропуски' in f.title]
        assert len(gap_findings) == 0

    def test_with_gaps(self):
        records = [
            SessionRecord(1, '2026-07-01', 'Сессия 1.', ''),
            SessionRecord(3, '2026-07-03', 'Сессия 3.', ''),
            SessionRecord(5, '2026-07-05', 'Сессия 5.', ''),
        ]
        findings = analyze_session_gaps(records)
        gap_findings = [f for f in findings if 'Пропуски' in f.title]
        assert len(gap_findings) >= 1


# ─── Тесты генерации рекомендаций ─────────────────────────────────

class TestGenerateRecommendations:
    """Тесты генерации рекомендаций."""

    def test_no_findings(self):
        recs = generate_recommendations([], [])
        assert len(recs) >= 1  # хотя бы "всё в порядке"

    def test_with_high_priority(self):
        findings = [
            ReviewFinding('problem', 'high', 'Critical bug', 'desc', 'ev', 'fix it'),
        ]
        recs = generate_recommendations([], findings)
        high_recs = [r for r in recs if 'Высокий приоритет' in r]
        assert len(high_recs) >= 1


# ─── Тесты run_self_review ─────────────────────────────────────────

class TestRunSelfReview:
    """Тесты полного цикла самоанализа."""

    def test_empty_files(self):
        history_path = _make_temp_file('')
        last_session_path = _make_temp_file('')
        try:
            report = run_self_review(history_path, last_session_path)
            assert report.session_count == 0
            assert isinstance(report.findings, list)
            assert isinstance(report.recommendations, list)
        finally:
            os.unlink(history_path)
            os.unlink(last_session_path)

    def test_with_data(self):
        history_content = """# История

## Сессия 1 — 2026-07-01
Создан инструмент A.

## Сессия 2 — 2026-07-02
Исправлен баг в инструменте A.

## Сессия 3 — 2026-07-03
Снова баг. Следующий шаг: создать тесты.
"""
        last_session_content = """# Последняя сессия

## Что было сделано
Исправлен баг.

## Рекомендация
Создать тесты.
"""
        history_path = _make_temp_file(history_content)
        last_session_path = _make_temp_file(last_session_content)
        try:
            report = run_self_review(history_path, last_session_path)
            assert report.session_count == 3
            assert len(report.findings) >= 1
            assert len(report.recommendations) >= 1
        finally:
            os.unlink(history_path)
            os.unlink(last_session_path)


# ─── Тесты форматирования ─────────────────────────────────────────

class TestFormatReport:
    """Тесты форматирования отчёта."""

    def test_empty_report(self):
        report = ReviewReport(
            generated_at='2026-07-06 12:00:00',
            session_count=0,
        )
        output = format_report(report)
        assert 'Отчёт самоанализа' in output
        assert '0' in output  # session_count

    def test_with_findings(self):
        report = ReviewReport(
            generated_at='2026-07-06 12:00:00',
            session_count=5,
            findings=[
                ReviewFinding('problem', 'high', 'Test problem',
                              'Description', 'evidence.md', 'Fix it'),
            ],
            recommendations=['Сделать что-то.']
        )
        output = format_report(report)
        assert 'Test problem' in output
        assert 'Сделать что-то' in output
        assert '🔴' in output  # high severity icon


# ─── Тесты SessionRecord / ReviewFinding / ReviewReport ────────────

class TestDataClasses:
    """Тесты dataclass'ов."""

    def test_session_record(self):
        r = SessionRecord(1, '2026-07-01', 'Summary.', '## raw')
        assert r.number == 1
        assert r.date == '2026-07-01'
        assert r.summary == 'Summary.'

    def test_review_finding(self):
        f = ReviewFinding('problem', 'high', 'Title', 'Desc', 'ev', 'Suggestion')
        assert f.category == 'problem'
        assert f.severity == 'high'

    def test_review_report(self):
        r = ReviewReport(generated_at='now', session_count=3)
        assert r.session_count == 3
        assert r.findings == []
        assert r.recommendations == []


# ─── Запуск ────────────────────────────────────────────────────────

def run_tests():
    """Запуск тестов без pytest (fallback)."""
    test_classes = [
        TestParseHistory, TestParseLastSession,
        TestFindRepeatedProblems, TestFindUnusedOpportunities,
        TestFindOutdatedArtifacts, TestAnalyzeSessionGaps,
        TestGenerateRecommendations, TestRunSelfReview,
        TestFormatReport, TestDataClasses,
    ]

    passed = 0
    failed = 0
    errors = []

    for cls in test_classes:
        instance = cls()
        for method_name in sorted(dir(instance)):
            if not method_name.startswith('test_'):
                continue
            method = getattr(instance, method_name)
            test_name = f"{cls.__name__}.{method_name}"
            try:
                method()
                passed += 1
                print(f"  ✅ {test_name}")
            except Exception as e:
                failed += 1
                errors.append((test_name, e))
                print(f"  ❌ {test_name}: {e}")

    print(f"\n{'='*50}")
    print(f"Результат: {passed} прошли, {failed} упали")

    if errors:
        print(f"\nОшибки:")
        for name, err in errors:
            print(f"  {name}: {err}")

    return failed == 0


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
