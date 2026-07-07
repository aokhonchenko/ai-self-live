"""Тесты для инструмента read_lines."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.tools._runtime import ToolError
from src.tools.read_lines.tool import read_lines, handle


ROOT = Path(__file__).parent / 'test_data' / 'read_lines_test'


@pytest.fixture(autouse=True)
def _setup_root():
    """Изолированная тестовая директория."""
    ROOT.mkdir(parents=True, exist_ok=True)
    yield
    for f in ROOT.iterdir():
        if f.is_file():
            f.unlink()


def _write(rel: str, content: str) -> Path:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')
    return p


# --- Базовые тесты ---

def test_read_first_3_lines():
    """Чтение первых 3 строк."""
    _write('three.txt', 'one\ntwo\nthree\nfour\nfive\n')
    result = read_lines(ROOT, 'three.txt', start_line=1, line_count=3)
    assert result['path'] == 'three.txt'
    assert result['start_line'] == 1
    assert result['end_line'] == 3
    assert result['total_lines'] == 5
    assert '1: one' in result['content']
    assert '2: two' in result['content']
    assert '3: three' in result['content']


def test_read_middle_lines():
    """Чтение строк из середины файла."""
    _write('mid.txt', 'a\nb\nc\nd\ne\n')
    result = read_lines(ROOT, 'mid.txt', start_line=2, line_count=2)
    assert result['start_line'] == 2
    assert result['end_line'] == 3
    assert '2: b' in result['content']
    assert '3: c' in result['content']


def test_read_last_line():
    """Чтение последней строки."""
    _write('last.txt', 'first\nsecond\nthird\n')
    result = read_lines(ROOT, 'last.txt', start_line=3, line_count=1)
    assert result['start_line'] == 3
    assert result['end_line'] == 3
    assert '3: third' in result['content']


def test_read_single_line():
    """Чтение одной строки."""
    _write('single.txt', 'only line\n')
    result = read_lines(ROOT, 'single.txt', start_line=1, line_count=1)
    assert result['total_lines'] == 1
    assert '1: only line' in result['content']


def test_read_all_lines():
    """Чтение всего файла."""
    _write('all.txt', 'x\ny\nz\n')
    result = read_lines(ROOT, 'all.txt', start_line=1, line_count=3)
    assert result['total_lines'] == 3
    assert result['end_line'] == 3
    assert '1: x' in result['content']
    assert '2: y' in result['content']
    assert '3: z' in result['content']


# --- Unicode и спецсимволы ---

def test_read_unicode_lines():
    """Чтение строк с Unicode."""
    _write('uni.txt', 'Привет\nмир\n🎉\n')
    result = read_lines(ROOT, 'uni.txt', start_line=1, line_count=3)
    assert '1: Привет' in result['content']
    assert '2: мир' in result['content']
    assert '3: 🎉' in result['content']


def test_read_empty_lines():
    """Чтение файла с пустыми строками."""
    _write('empty_lines.txt', 'a\n\nb\n\nc\n')
    result = read_lines(ROOT, 'empty_lines.txt', start_line=2, line_count=2)
    assert '2: ' in result['content']  # пустая строка с номером
    assert '3: b' in result['content']


def test_read_long_line():
    """Чтение строки с длинным содержимым."""
    long_line = 'x' * 500
    _write('long.txt', f'{long_line}\nshort\n')
    result = read_lines(ROOT, 'long.txt', start_line=1, line_count=1)
    assert result['content'] == f'1: {long_line}'


# --- Границы и переполнение ---

def test_read_past_end():
    """Чтение за пределами файла — берёт сколько есть."""
    _write('short.txt', 'a\nb\n')
    result = read_lines(ROOT, 'short.txt', start_line=1, line_count=10)
    assert result['total_lines'] == 2
    assert result['end_line'] == 2
    assert '1: a' in result['content']
    assert '2: b' in result['content']


def test_read_zero_count():
    """line_count=0 вызывает ошибку — валидация не пропускает 0."""
    _write('any.txt', 'a\nb\n')
    with pytest.raises(ToolError, match='at least 1'):
        read_lines(ROOT, 'any.txt', start_line=1, line_count=0)


# --- Ошибки ---

def test_start_line_zero():
    """start_line=0 вызывает ошибку."""
    _write('any.txt', 'a\n')
    with pytest.raises(ToolError, match='at least 1'):
        read_lines(ROOT, 'any.txt', start_line=0, line_count=1)


def test_start_line_negative():
    """start_line=-1 вызывает ошибку."""
    _write('any.txt', 'a\n')
    with pytest.raises(ToolError, match='at least 1'):
        read_lines(ROOT, 'any.txt', start_line=-1, line_count=1)


def test_line_count_zero():
    """line_count=0 вызывает ошибку."""
    _write('any.txt', 'a\n')
    with pytest.raises(ToolError, match='at least 1'):
        read_lines(ROOT, 'any.txt', start_line=1, line_count=0)


def test_nonexistent_file():
    """Чтение несуществующего файла."""
    with pytest.raises(ToolError, match='does not exist'):
        read_lines(ROOT, 'no_such.txt', start_line=1, line_count=1)


def test_read_directory():
    """Чтение директории вместо файла."""
    sub = ROOT / 'subdir'
    sub.mkdir(exist_ok=True)
    with pytest.raises(ToolError, match='not a file'):
        read_lines(ROOT, 'subdir', start_line=1, line_count=1)


# --- Структура результата ---

def test_result_keys():
    """Результат содержит все ожидаемые ключи."""
    _write('meta.txt', 'a\nb\n')
    result = read_lines(ROOT, 'meta.txt', start_line=1, line_count=1)
    assert set(result.keys()) == {'path', 'start_line', 'end_line', 'total_lines', 'content'}


# --- handle() обёртка ---

def test_handle_basic():
    """handle() передаёт аргументы в read_lines."""
    _write('handle.txt', 'alpha\nbeta\ngamma\n')
    result = handle(ROOT, {'path': 'handle.txt', 'start_line': 2, 'line_count': 2})
    assert '2: beta' in result['content']
    assert '3: gamma' in result['content']


def test_handle_defaults():
    """handle() с дефолтными значениями читает 1 строку."""
    _write('def.txt', 'first\nsecond\n')
    result = handle(ROOT, {'path': 'def.txt'})
    assert '1: first' in result['content']


def test_handle_missing_path():
    """handle() без path вызывает ошибку."""
    with pytest.raises(ToolError):
        handle(ROOT, {'start_line': 1, 'line_count': 1})
