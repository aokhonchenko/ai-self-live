#!/usr/bin/env python3
"""
Тесты для src/tools/prompt_builder/core.py.

Первые тесты для prompt_builder.
Запуск: python -m pytest tests/test_prompt_builder.py -v
    или: python tests/test_prompt_builder.py

Создан: сессия 31 (2026-07-07)
"""

import sys
import os
import json
import tempfile
import textwrap
from pathlib import Path

# Добавляем src в путь для импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'tools'))

from prompt_builder.core import PromptBuilder


# ─── Вспомогательные функции ───────────────────────────────────────

def _make_temp_dir(files: dict) -> str:
    """Создаёт временную директорию с файлами {name: content}."""
    tmpdir = tempfile.mkdtemp()
    for name, content in files.items():
        filepath = os.path.join(tmpdir, name)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    return tmpdir


def _cleanup(tmpdir: str):
    """Удаляет временную директорию."""
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


# ─── Тесты __init__ и build ────────────────────────────────────────

class TestInit:
    """Проверка инициализации PromptBuilder."""

    def test_default_root(self):
        builder = PromptBuilder()
        assert builder.root is not None
        assert isinstance(builder.root, Path)

    def test_custom_root(self):
        tmpdir = tempfile.mkdtemp()
        try:
            builder = PromptBuilder(tmpdir)
            assert str(builder.root) == tmpdir
        finally:
            _cleanup(tmpdir)

    def test_context_initially_empty(self):
        builder = PromptBuilder()
        assert builder._context == {}
        assert builder._stats == {}


class TestBuild:
    """Тесты сборки контекста."""

    def test_build_missing_files(self):
        """build() должен корректно обрабатывать отсутствующие файлы."""
        tmpdir = tempfile.mkdtemp()
        try:
            builder = PromptBuilder(tmpdir)
            context = builder.build()
            # Файлы не существуют — должны быть сообщения "[Файл не найден: ...]"
            assert 'last_session' in context
            assert 'current_plan' in context
            assert 'external_messages' in context
            assert 'active_tasks' in context
            assert 'Файл не найден' in context['last_session']
        finally:
            _cleanup(tmpdir)

    def test_build_with_existing_files(self):
        """build() должен читать существующие файлы."""
        tmpdir = _make_temp_dir({
            'state/last_session.md': '# Сессия 1\n\nТекст сессии.\n',
            'state/current_plan.md': '# План\n\nПункт один.\n',
            'state/external_messages.md': '# Сообщения\n\nНичего нового.\n',
        })
        try:
            builder = PromptBuilder(tmpdir)
            context = builder.build()
            # Файлы ≤40 строк читаются целиком (full)
            assert 'Сессия 1' in context['last_session']
            assert 'План' in context['current_plan']
            assert 'Ничего нового' in context['external_messages']
        finally:
            _cleanup(tmpdir)

    def test_build_returns_dict(self):
        tmpdir = tempfile.mkdtemp()
        try:
            builder = PromptBuilder(tmpdir)
            result = builder.build()
            assert isinstance(result, dict)
            assert set(result.keys()) == {'last_session', 'current_plan',
                                          'external_messages', 'active_tasks'}
        finally:
            _cleanup(tmpdir)

    def test_get_context_lazy(self):
        """get_context() должен вызывать build() при первом вызове."""
        tmpdir = tempfile.mkdtemp()
        try:
            builder = PromptBuilder(tmpdir)
            assert builder._context == {}
            ctx = builder.get_context()
            assert ctx is not None
            assert len(ctx) == 4
        finally:
            _cleanup(tmpdir)

    def test_get_stats_lazy(self):
        """get_stats() должен вызывать build() при первом вызове."""
        tmpdir = tempfile.mkdtemp()
        try:
            builder = PromptBuilder(tmpdir)
            assert builder._stats == {}
            stats = builder.get_stats()
            assert isinstance(stats, dict)
            assert len(stats) == 4
        finally:
            _cleanup(tmpdir)


# ─── Тесты _read_optimized ─────────────────────────────────────────

class TestReadOptimized:
    """Тесты оптимального чтения файлов."""

    def test_missing_file(self):
        tmpdir = tempfile.mkdtemp()
        try:
            builder = PromptBuilder(tmpdir)
            content, stats = builder._read_optimized('nonexistent.md')
            assert 'Файл не найден' in content
            assert stats['exists'] is False
            assert stats['lines'] == 0
            assert stats['strategy'] == 'missing'
        finally:
            _cleanup(tmpdir)

    def test_small_file_full_read(self):
        """Файл ≤40 строк читается целиком."""
        lines = [f'Строка {i}\n' for i in range(20)]
        tmpdir = _make_temp_dir({'small.md': ''.join(lines)})
        try:
            builder = PromptBuilder(tmpdir)
            content, stats = builder._read_optimized('small.md')
            assert stats['strategy'] == 'full'
            assert stats['lines'] == 20
            assert 'Строка 19' in content
        finally:
            _cleanup(tmpdir)

    def test_medium_file_summary(self):
        """Файл 40-100 строк читается через summary.
        
        read_summary возвращает пустую строку для файлов без заголовков —
        это документированное поведение partial_reader.
        """
        lines = [f'Строка {i}\n' for i in range(50)]
        tmpdir = _make_temp_dir({'medium.md': ''.join(lines)})
        try:
            builder = PromptBuilder(tmpdir)
            content, stats = builder._read_optimized('medium.md')
            assert stats['strategy'] == 'summary'
            assert stats['lines'] == 50
            # read_summary возвращает '' для файлов без заголовков
            assert content == ''
        finally:
            _cleanup(tmpdir)

    def test_medium_file_with_headers(self):
        """Файл 40-100 строк с заголовками читается через summary корректно."""
        lines = []
        for i in range(25):
            lines.append(f'# Заголовок {i}\n')
            lines.append(f'Текст секции {i}\n')
        tmpdir = _make_temp_dir({'medium.md': ''.join(lines)})
        try:
            builder = PromptBuilder(tmpdir)
            content, stats = builder._read_optimized('medium.md')
            assert stats['strategy'] == 'summary'
            assert stats['lines'] == 50
            assert 'Заголовок 0' in content
            assert 'Заголовок 24' in content
        finally:
            _cleanup(tmpdir)

    def test_large_file_headers_only(self):
        """Файл >100 строк читается только заголовки."""
        lines = [f'# Заголовок {i}\nСтрока {i}\n' for i in range(150)]
        tmpdir = _make_temp_dir({'large.md': ''.join(lines)})
        try:
            builder = PromptBuilder(tmpdir)
            content, stats = builder._read_optimized('large.md')
            assert stats['strategy'] == 'headers_only'
            assert stats['lines'] == 300  # 150 * 2
            # Заголовки должны быть
            assert '# Заголовок 0' in content
            assert '# Заголовок 149' in content
        finally:
            _cleanup(tmpdir)

    def test_empty_file(self):
        tmpdir = _make_temp_dir({'empty.md': ''})
        try:
            builder = PromptBuilder(tmpdir)
            content, stats = builder._read_optimized('empty.md')
            assert stats['strategy'] == 'full'
            assert stats['lines'] == 0
        finally:
            _cleanup(tmpdir)

    def test_stats_include_path(self):
        tmpdir = _make_temp_dir({'test.md': 'x = 1\n'})
        try:
            builder = PromptBuilder(tmpdir)
            _, stats = builder._read_optimized('test.md')
            assert stats['path'] == 'test.md'
            assert stats['chars'] > 0
        finally:
            _cleanup(tmpdir)


# ─── Тесты get_total_stats ─────────────────────────────────────────

class TestTotalStats:
    """Тесты общей статистики."""

    def test_total_stats_structure(self):
        tmpdir = tempfile.mkdtemp()
        try:
            builder = PromptBuilder(tmpdir)
            total = builder.get_total_stats()
            assert isinstance(total, dict)
            assert 'sections' in total
            assert 'total_lines' in total
            assert 'total_chars' in total
            assert 'estimated_tokens' in total
            assert 'strategies' in total
            assert total['sections'] == 4
        finally:
            _cleanup(tmpdir)

    def test_total_stats_with_files(self):
        tmpdir = _make_temp_dir({
            'state/last_session.md': 'Текст сессии.\n',
            'state/current_plan.md': 'План.\n',
        })
        try:
            builder = PromptBuilder(tmpdir)
            total = builder.get_total_stats()
            assert total['total_lines'] > 0
            assert total['total_chars'] > 0
            assert total['estimated_tokens'] > 0
        finally:
            _cleanup(tmpdir)


# ─── Тесты format_compact ──────────────────────────────────────────

class TestFormatCompact:
    """Тесты компактного форматирования."""

    def test_compact_output_contains_sections(self):
        tmpdir = _make_temp_dir({
            'state/last_session.md': '# Сессия 1\n\nТекст.\n',
            'state/current_plan.md': '# План\n\nПункт.\n',
            'state/external_messages.md': '# Сообщения\n\nНичего.\n',
        })
        try:
            builder = PromptBuilder(tmpdir)
            output = builder.format_compact()
            assert isinstance(output, str)
            assert 'КОНТЕКСТ СЕССИИ' in output
            assert 'last_session' in output
            assert 'current_plan' in output
            assert 'external_messages' in output
            assert 'СТАТИСТИКА' in output
            assert 'Секций:' in output
            assert 'Строк:' in output
        finally:
            _cleanup(tmpdir)

    def test_compact_output_is_single_string(self):
        tmpdir = tempfile.mkdtemp()
        try:
            builder = PromptBuilder(tmpdir)
            output = builder.format_compact()
            assert isinstance(output, str)
            assert len(output) > 0
        finally:
            _cleanup(tmpdir)


# ─── Тесты format_json ─────────────────────────────────────────────

class TestFormatJson:
    """Тесты JSON-вывода."""

    def test_valid_json(self):
        tmpdir = _make_temp_dir({
            'state/last_session.md': '# Сессия 1\n\nТекст.\n',
        })
        try:
            builder = PromptBuilder(tmpdir)
            json_str = builder.format_json()
            data = json.loads(json_str)
            assert 'context' in data
            assert 'stats' in data
            assert 'total' in data
            assert 'timestamp' in data
            assert 'last_session' in data['context']
        finally:
            _cleanup(tmpdir)

    def test_json_with_russian_text(self):
        tmpdir = _make_temp_dir({
            'state/last_session.md': '# Сессия 1\n\nТекст на русском.\n',
        })
        try:
            builder = PromptBuilder(tmpdir)
            json_str = builder.format_json()
            data = json.loads(json_str)
            assert 'русском' in data['context']['last_session']
        finally:
            _cleanup(tmpdir)

    def test_json_empty_context(self):
        tmpdir = tempfile.mkdtemp()
        try:
            builder = PromptBuilder(tmpdir)
            json_str = builder.format_json()
            data = json.loads(json_str)
            assert 'last_session' in data['context']
            assert 'Файл не найден' in data['context']['last_session']
        finally:
            _cleanup(tmpdir)


# ─── Интеграционный тест: сам prompt_builder ───────────────────────

class TestSelfAnalysis:
    """Интеграционный тест: анализируем сам core.py."""

    def test_analyze_self(self):
        core_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'tools', 'prompt_builder', 'core.py'
        )
        if not os.path.exists(core_path):
            return  # пропускаем, если файл не найден

        builder = PromptBuilder(os.path.dirname(core_path))
        # Просто проверяем, что build() не падает
        context = builder.build()
        assert isinstance(context, dict)


# ─── Запуск ────────────────────────────────────────────────────────

def run_tests():
    """Запуск тестов без pytest (fallback)."""
    test_classes = [
        TestInit, TestBuild, TestReadOptimized, TestTotalStats,
        TestFormatCompact, TestFormatJson, TestSelfAnalysis,
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
