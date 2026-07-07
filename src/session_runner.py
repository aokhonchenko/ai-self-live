#!/usr/bin/env python3
"""
Обёртка для запуска сессии агента.

Собирает контекст через prompt_builder, а не через прямое чтение файлов.
Генерирует компактный промпт для модели.

Создан: сессия 25 (2026-07-06)

Использование:
    python session_runner.py [--root DIR] [--session N]
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Добавляем путь к tools
sys.path.insert(0, str(Path(__file__).parent / 'tools'))

from src.tools.prompt_builder import PromptBuilder


def build_session_prompt(root, session_num=None):
    """
    Собирает промпт сессии через оптимизированное чтение.
    
    Args:
        root: корневая директория проекта
        session_num: номер сессии (опционально)
    
    Returns:
        str: готовый промпт для модели
    """
    builder = PromptBuilder(root)
    context = builder.build()
    stats = builder.get_total_stats()
    
    # Определяем номер сессии
    if session_num is None:
        session_num = detect_session_number(root)
    
    # Собираем промпт
    parts = []
    
    # Заголовок
    parts.append(f"# Активный промпт сессии {session_num}")
    parts.append(f"")
    parts.append(f"Время сборки промпта: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %z')}")
    parts.append(f"Корень эксперимента: {root}")
    parts.append(f"")
    
    # Системный промпт (читаем отдельно, он стабилен)
    system_prompt_path = Path(root) / 'SYSTEM_PROMPT.md'
    if system_prompt_path.exists():
        with open(system_prompt_path, 'r', encoding='utf-8') as f:
            parts.append(f.read())
        parts.append("")
    
    # Контекст из prompt_builder
    for name, content in context.items():
        parts.append(f"# {name}")
        parts.append("")
        parts.append(content)
        parts.append("")
    
    # Инструкция на сессию
    parts.append(f"# Инструкция на эту сессию")
    parts.append("")
    parts.append(f"Ты находишься в сессии {session_num}. Работай в корне эксперимента: `{root}`.")
    parts.append("")
    parts.append("Самостоятельно выбери и сделай один осмысленный шаг. Можно создать артефакт, начать или улучшить проект, улучшить инструменты агента, навести порядок в памяти или выбрать сон. Все пользовательские артефакты пиши на русском языке.")
    parts.append("")
    parts.append("Перед завершением обязательно обнови:")
    parts.append("")
    parts.append("1. `state/last_session.md`")
    parts.append("2. `logs/history.md`")
    parts.append("")
    parts.append("Если ты меняешь план, обнови `state/current_plan.md`.")
    
    return '\n'.join(parts)


def detect_session_number(root):
    """Определяет номер сессии из пути."""
    root_path = Path(root)
    dir_name = root_path.name
    
    # Пытаемся извлечь номер из session-NNNN
    if dir_name.startswith('session-'):
        try:
            return int(dir_name.split('-')[1])
        except (IndexError, ValueError):
            pass
    
    return 0


def main():
    root = None
    session_num = None
    
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--root' and i + 1 < len(sys.argv):
            root = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--session' and i + 1 < len(sys.argv):
            session_num = int(sys.argv[i + 1])
            i += 2
        else:
            i += 1
    
    if root is None:
        root = os.getcwd()
    
    prompt = build_session_prompt(root, session_num)
    print(prompt)


if __name__ == '__main__':
    main()

