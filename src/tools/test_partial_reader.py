#!/usr/bin/env python3
"""
Тесты для partial_reader.py.

Запуск: python src/tools/test_partial_reader.py
"""

import sys
import os
import tempfile

# Добавляем путь к модулю
sys.path.insert(0, os.path.dirname(__file__))

from partial_reader import read_head, read_headers, read_section, read_summary, get_file_info


def create_test_file(content: str) -> str:
    """Создаёт временный файл с заданным содержимым."""
    fd, path = tempfile.mkstemp(suffix='.md', encoding='utf-8')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def test_read_head():
    """Тест чтения первых N строк."""
    content = "строка 1\nстрока 2\nстрока 3\nстрока 4\nстрока 5\n"
    path = create_test_file(content)
    
    try:
        result = read_head(path, 3)
        assert result == "строка 1\nстрока 2\nстрока 3\n", f"Ожидалось 3 строки, получено: {repr(result)}"
        
        result_all = read_head(path, 100)
        assert result_all == content, f"Ожидалось все строки"
        
        print("✓ test_read_head")
    finally:
        os.unlink(path)


def test_read_headers():
    """Тест чтения заголовков."""
    content = """# Заголовок 1
Текст под заголовком 1

## Подзаголовок 1.1
Ещё текст

### Подподзаголовок
Глубокий текст

## Подзаголовок 1.2
Финальный текст

# Заголовок 2
Текст второго заголовка
"""
    path = create_test_file(content)
    
    try:
        result = read_headers(path)
        lines = result.strip().split('\n')
        
        # Должны быть только # и ##
        assert len(lines) == 4, f"Ожидалось 4 заголовка, получено {len(lines)}: {lines}"
        assert '# Заголовок 1' in lines[0]
        assert '## Подзаголовок 1.1' in lines[1]
        assert '## Подзаголовок 1.2' in lines[2]
        assert '# Заголовок 2' in lines[3]
        
        print("✓ test_read_headers")
    finally:
        os.unlink(path)


def test_read_section():
    """Тест чтения特定ной секции."""
    content = """# Первая секция
Текст первой секции
Ещё текст

# Вторая секция
Текст второй секции
Много строк
здесь

# Третья секция
Финальный текст
"""
    path = create_test_file(content)
    
    try:
        result = read_section(path, "вторая")
        assert "Вторая секция" in result, f"Секция не найдена в: {repr(result)}"
        assert "Текст второй секции" in result
        assert "Первая секция" not in result
        assert "Третья секция" not in result
        
        print("✓ test_read_section")
    finally:
        os.unlink(path)


def test_read_summary():
    """Тест краткой сводки."""
    content = """# Заголовок A
Первая строка A
Вторая строка A
Третья строка A

# Заголовок B
Первая строка B
Вторая строка B
"""
    path = create_test_file(content)
    
    try:
        result = read_summary(path, context_lines=2)
        assert "# Заголовок A" in result
        assert "Первая строка A" in result
        assert "Вторая строка A" in result
        assert "Третья строка A" not in result  # context_lines=2
        assert "# Заголовок B" in result
        
        print("✓ test_read_summary")
    finally:
        os.unlink(path)


def test_get_file_info():
    """Тест информации о файле."""
    content = "строка 1\nстрока 2\nстрока 3\n"
    path = create_test_file(content)
    
    try:
        result = get_file_info(path)
        assert "Строк: 3" in result, f"Ожидалось 3 строки в: {result}"
        assert "Файл:" in result
        assert "Размер:" in result
        
        print("✓ test_get_file_info")
    finally:
        os.unlink(path)


def test_nonexistent_file():
    """Тест обработки несуществующего файла."""
    try:
        read_head("/nonexistent/file.md")
        assert False, "Должно было выбросить исключение"
    except FileNotFoundError:
        print("✓ test_nonexistent_file")


if __name__ == '__main__':
    print("Запуск тестов partial_reader.py...\n")
    
    test_read_head()
    test_read_headers()
    test_read_section()
    test_read_summary()
    test_get_file_info()
    test_nonexistent_file()
    
    print("\n✓ Все тесты пройдены!")
