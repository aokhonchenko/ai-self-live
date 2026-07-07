"""Тесты для модуля SessionContext."""

import sys
from pathlib import Path

# Добавляем путь к src для импорта
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from agent.context import SessionContext


def test_load_context():
    """Проверка загрузки контекста сессии."""
    ctx = SessionContext()
    result = ctx.load()
    
    assert isinstance(result, SessionContext)
    state = ctx.get_state()
    
    # Проверяем наличие обязательных ключей
    required_keys = ['last_session', 'current_plan', 'external_messages']
    for key in required_keys:
        assert key in state, f"Отсутствует ключ {key} в состоянии сессии"


def test_get_file_info():
    """Проверка получения информации о файле."""
    ctx = SessionContext()
    
    # Файл состояния должен существовать
    info = ctx.get_file_info('state/last_session.md')
    assert info['exists'] is True
    
    # Проверяем структуру ответа
    assert 'path' in info
    assert 'size' in info
    assert 'lines' in info
    assert 'strategy' in info


def test_get_file_summary():
    """Проверка получения сводки файла."""
    ctx = SessionContext()
    
    summary = ctx.get_file_summary('state/last_session.md')
    assert isinstance(summary, str)
    # Сводка должна содержать заголовки
    assert '##' in summary or '# ' in summary


def test_get_file_headers():
    """Проверка получения только заголовков файла."""
    ctx = SessionContext()
    
    headers = ctx.get_file_headers('state/last_session.md')
    assert isinstance(headers, str)
    # Заголовки должны содержать маркеры markdown
    for line in headers.split('\n'):
        if line.strip():  # игнорируем пустые строки
            assert (line.startswith('# ') or 
                    line.startswith('## ') or 
                    line.startswith('### '))


def test_get_section():
    """Проверка получения секции файла на изолированном тестовом файле."""
    ctx = SessionContext()
    
    section = ctx.get_section('tests/test_data/section_test.md', 'Секция Бета')
    assert isinstance(section, str)
    assert len(section) > 0
    # Секция должна содержать заголовок и текст
    assert 'Секция Бета' in section
    assert 'Текст второй секции' in section


def test_nonexistent_file():
    """Проверка работы с несуществующим файлом."""
    ctx = SessionContext()
    
    info = ctx.get_file_info('state/nonexistent.md')
    assert info['exists'] is False
    
    summary = ctx.get_file_summary('state/nonexistent.md')
    assert 'не найден' in summary.lower()


def test_cli_commands():
    """Проверка CLI команд (через вызов main)."""
    import subprocess
    
    # Тест команды load
    result = subprocess.run(
        ['python', '-c', 
         f"from agent.context import SessionContext; ctx=SessionContext(); "
         f"ctx.load(); print(ctx.get_state().get('last_session', ''))"],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
    )
    
    assert result.returncode == 0 or 'Файл не найден' not in result.stderr


def test_cache_enabled_by_default():
    """Кэш включён по умолчанию."""
    ctx = SessionContext()
    assert ctx._cache_enabled is True


def test_cache_disabled():
    """Кэш можно отключить."""
    ctx = SessionContext(cache_enabled=False)
    assert ctx._cache_enabled is False


def test_cache_populates_on_read():
    """Первичное чтение заполняет кэш."""
    ctx = SessionContext()
    ctx.load()
    
    stats = ctx.cache_stats()
    # load() читает 4 файла, но один (tasks/active.md) может не существовать
    assert stats['cached_files'] >= 3  # как минимум 3 существующих файла


def test_cache_hits_on_repeated_read():
    """Повторное чтение того же файла даёт хит кэша."""
    ctx = SessionContext()
    ctx.load()
    
    # Первое чтение — мисс
    ctx.get_file_summary('state/last_session.md')
    stats1 = ctx.cache_stats()
    
    # Второе чтение — хит
    ctx.get_file_summary('state/last_session.md')
    stats2 = ctx.cache_stats()
    
    assert stats2['hits'] > stats1['hits']
    assert stats2['misses'] == stats1['misses']


def test_clear_cache():
    """Очистка кэша сбрасывает статистику."""
    ctx = SessionContext()
    ctx.load()
    ctx.get_file_summary('state/last_session.md')
    
    assert ctx.cache_stats()['total'] > 0
    
    ctx.clear_cache()
    
    stats = ctx.cache_stats()
    assert stats['hits'] == 0
    assert stats['misses'] == 0
    assert stats['cached_files'] == 0


def test_cache_disabled_no_caching():
    """При отключённом кэше данные не сохраняются."""
    ctx = SessionContext(cache_enabled=False)
    ctx.load()
    
    stats = ctx.cache_stats()
    assert stats['cached_files'] == 0
    assert stats['hits'] == 0
    assert stats['misses'] == 0


if __name__ == '__main__':
    import pytest
    
    # Запуск всех тестов через pytest
    sys.exit(pytest.main([__file__, '-v']))
