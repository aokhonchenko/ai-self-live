#!/usr/bin/env python3
"""
Тесты для модуля context.py.

Запуск: python test_context.py
"""

import sys
import os
import tempfile
from pathlib import Path

# Добавляем путь к модулю
sys.path.insert(0, str(Path(__file__).parent))

from context import SessionContext


def test_session_context_init():
    """Тест инициализации контекста."""
    ctx = SessionContext()
    assert ctx.root == Path.cwd()
    assert ctx._loaded == False
    print("✓ Инициализация OK")


def test_session_context_custom_root():
    """Тест с кастомным корнем."""
    ctx = SessionContext(root="/tmp")
    assert ctx.root == Path("/tmp")
    print("✓ Кастомный корень OK")


def test_get_file_info():
    """Тест получения информации о файле."""
    ctx = SessionContext()
    
    # Существующий файл
    info = ctx.get_file_info('SYSTEM_PROMPT.md')
    assert info['exists'] == True
    assert info['lines'] > 0
    assert info['strategy'] in ('full', 'summary', 'headers_only')
    print(f"✓ Информация о файле: {info['lines']} строк, стратегия: {info['strategy']}")
    
    # Несуществующий файл
    info = ctx.get_file_info('nonexistent.md')
    assert info['exists'] == False
    print("✓ Несуществующий файл обработан корректно")


def test_get_file_headers():
    """Тест чтения заголовков."""
    ctx = SessionContext()
    headers = ctx.get_file_headers('SYSTEM_PROMPT.md')
    assert '#' in headers
    print(f"✓ Заголовки: {len(headers)} символов")


def test_get_file_summary():
    """Тест чтения сводки."""
    ctx = SessionContext()
    summary = ctx.get_file_summary('SYSTEM_PROMPT.md')
    assert len(summary) > 0
    print(f"✓ Сводка: {len(summary)} символов")


def test_get_section():
    """Тест чтения секции."""
    ctx = SessionContext()
    section = ctx.get_section('SYSTEM_PROMPT.md', 'Главные принципы')
    assert len(section) > 0
    print(f"✓ Секция: {len(section)} символов")


def test_load():
    """Тест загрузки контекста."""
    ctx = SessionContext()
    ctx.load()
    
    state = ctx.get_state()
    assert 'last_session' in state
    assert 'current_plan' in state
    assert 'active_tasks' in state
    
    # Проверяем что все файлы прочитаны
    for key, content in state.items():
        assert len(content) > 0, f"Пустой контент: {key}"
    
    print(f"✓ Контекст загружен: {len(state)} файлов")
    
    # Статистика
    total = sum(len(c) for c in state.values())
    print(f"  Итого: {total} символов ≈ {total // 4} токенов")


def test_optimization_effect():
    """Тест: проверяем что контекст оптимизирован (не читает файлы целиком)."""
    ctx = SessionContext()
    
    # Проверяем стратегии для известных больших файлов
    info = ctx.get_file_info('knowledge/system_map.md')
    if info['exists']:
        print(f"  system_map.md: {info['lines']} строк → стратегия: {info['strategy']}")
        assert info['strategy'] in ('summary', 'headers_only'), \
            "Большой файл должен читаться не целиком"
    
    info = ctx.get_file_info('knowledge/file_manifest.md')
    if info['exists']:
        print(f"  file_manifest.md: {info['lines']} строк → стратегия: {info['strategy']}")
    
    print("✓ Оптимизация работает: большие файлы читаются точечно")


def run_all_tests():
    """Запуск всех тестов."""
    print("=== Тесты SessionContext ===\n")
    
    tests = [
        test_session_context_init,
        test_session_context_custom_root,
        test_get_file_info,
        test_get_file_headers,
        test_get_file_summary,
        test_get_section,
        test_load,
        test_optimization_effect,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
    
    print(f"\n=== Результат: {passed} OK, {failed} ошибок ===")
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)

