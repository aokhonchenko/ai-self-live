"""Тесты для инструмента read_file."""

import sys
from pathlib import Path

import pytest

# Добавляем путь к src для импорта
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.tools._runtime import ToolError
from src.tools.read_file.tool import read_file, handle


ROOT = Path(__file__).parent / 'test_data' / 'read_file_test'


@pytest.fixture(autouse=True)
def _setup_root():
    """Создаём изолированную тестовую директорию перед каждым тестом."""
    ROOT.mkdir(parents=True, exist_ok=True)
    yield
    # После теста удаляем созданные файлы, но не саму директорию
    for f in ROOT.iterdir():
        if f.is_file():
            f.unlink()


def _write(rel: str, content: str) -> Path:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')
    return p


# --- Базовые тесты ---

def test_read_simple_file():
    """Чтение простого файла."""
    _write('simple.txt', 'hello world')
    result = read_file(ROOT, 'simple.txt')
    assert result['path'] == 'simple.txt'
    assert result['content'] == 'hello world'


def test_read_multiline():
    """Чтение многострочного файла."""
    _write('multi.txt', 'line1\nline2\nline3\n')
    result = read_file(ROOT, 'multi.txt')
    assert result['content'] == 'line1\nline2\nline3\n'


def test_read_empty_file():
    """Чтение пустого файла."""
    _write('empty.txt', '')
    result = read_file(ROOT, 'empty.txt')
    assert result['content'] == ''


def test_read_unicode():
    """Чтение файла с Unicode (кириллица, японский)."""
    _write('unicode.txt', 'Привет мир\nこんにちは\n🎉')
    result = read_file(ROOT, 'unicode.txt')
    assert 'Привет мир' in result['content']
    assert 'こんにちは' in result['content']
    assert '🎉' in result['content']


def test_read_utf8_bytes():
    """Проверка, что содержимое — строка, а не байты."""
    _write('utf8.txt', 'юникод: ñoño')
    result = read_file(ROOT, 'utf8.txt')
    assert isinstance(result['content'], str)


def test_read_large_file():
    """Чтение большого файла (100K)."""
    _write('big.txt', 'x' * 100_000)
    result = read_file(ROOT, 'big.txt')
    assert len(result['content']) == 100_000


def test_read_special_chars_in_name():
    """Чтение файла со спецсимволами в имени."""
    _write('file-with_dots and spaces.txt', 'ok')
    result = read_file(ROOT, 'file-with_dots and spaces.txt')
    assert result['content'] == 'ok'


def test_read_nested_path():
    """Чтение файла во вложенной директории."""
    _write('a/b/c/deep.txt', 'deep content')
    result = read_file(ROOT, 'a/b/c/deep.txt')
    assert result['content'] == 'deep content'


# --- Ошибки ---

def test_read_nonexistent():
    """Чтение несуществующего файла вызывает ToolError."""
    with pytest.raises(ToolError, match='does not exist'):
        read_file(ROOT, 'no_such_file.txt')


def test_read_directory():
    """Чтение директории вместо файла вызывает ToolError."""
    sub = ROOT / 'subdir'
    sub.mkdir(exist_ok=True)
    with pytest.raises(ToolError, match='not a file'):
        read_file(ROOT, 'subdir')


# --- Структура результата ---

def test_result_structure():
    """Результат содержит path и content."""
    _write('meta.txt', 'data')
    result = read_file(ROOT, 'meta.txt')
    assert set(result.keys()) == {'path', 'content'}
    assert result['path'] == 'meta.txt'


def test_read_preserves_newlines():
    """Чтение сохраняет все переводы строк."""
    _write('nl.txt', 'a\nb\r\nc\nd\n')
    result = read_file(ROOT, 'nl.txt')
    # read_text читает как есть, без конвертации
    assert 'a\nb' in result['content']
    assert 'c\nd' in result['content']


# --- handle() обёртка ---

def test_handle_basic():
    """Обёртка handle() передаёт аргументы в read_file."""
    _write('handle_test.txt', 'handled')
    result = handle(ROOT, {'path': 'handle_test.txt'})
    assert result['content'] == 'handled'


def test_handle_missing_path():
    """handle() без path вызывает ошибку."""
    with pytest.raises(ToolError):
        handle(ROOT, {})
