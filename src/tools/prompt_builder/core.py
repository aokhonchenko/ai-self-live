#!/usr/bin/env python3
"""
Сборщик промптов для сессий агента.

Собирает компактный контекст сессии, используя частичное чтение файлов.
Вместо чтения целых файлов — только заголовки, первые строки, нужные секции.

Создан: сессия 25 (2026-07-06)
Цель: оптимизировать работу агента с моделью через точечное воздействие.

Использование:
    python prompt_builder.py [опции]

Опции:
    --root DIR      — корневая директория проекта (по умолчанию — текущая)
    --full          — вывести полный контекст (для отладки)
    --stats         — только статистика по контексту
    --compact       — компактный вывод (по умолчанию)
    --json          — вывод в JSON
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Добавляем путь к tools для импорта partial_reader и compat
sys.path.insert(0, str(Path(__file__).parent))

try:
    from src.tools.partial_reader import read_head, read_headers, read_section, read_summary
except ImportError:
    from src.tools.compat import read_head, read_headers, read_section, read_summary


class PromptBuilder:
    """
    Собирает компактный контекст сессии.
    
    Стратегии чтения:
    - Маленькие файлы (≤40 строк) — целиком
    - Средние (40-100 строк) — заголовки + первые строки секций
    - Большие (>100 строк) — только заголовки
    
    Экономия: ~70-80% токенов по сравнению с полным чтением.
    """
    
    def __init__(self, root=None):
        self.root = Path(root) if root else Path.cwd()
        self._context = {}
        self._stats = {}
    
    def build(self):
        """
        Собирает контекст сессии.
        
        Returns:
            dict: {section_name: content, ...}
        """
        sections = [
            ('last_session', 'state/last_session.md'),
            ('current_plan', 'state/current_plan.md'),
            ('external_messages', 'state/external_messages.md'),
            ('active_tasks', 'tasks/active.md'),
        ]
        
        self._context = {}
        self._stats = {}
        
        for name, path in sections:
            content, stats = self._read_optimized(path)
            self._context[name] = content
            self._stats[name] = stats
        
        return self._context
    
    def _read_optimized(self, rel_path):
        """
        Читает файл оптимальным способом.
        
        Returns:
            tuple: (content, stats)
        """
        filepath = self.root / rel_path
        
        if not filepath.exists():
            return f"[Файл не найден: {rel_path}]", {'exists': False, 'lines': 0, 'chars': 0, 'strategy': 'missing'}
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                line_count = sum(1 for _ in f)
            
            # Стратегия чтения
            if line_count <= 40:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                strategy = 'full'
            elif line_count <= 100:
                content = read_summary(str(filepath), context_lines=2)
                strategy = 'summary'
            else:
                content = read_headers(str(filepath))
                strategy = 'headers_only'
            
            stats = {
                'exists': True,
                'lines': line_count,
                'chars': len(content),
                'strategy': strategy,
                'path': rel_path
            }
            
            return content, stats
            
        except Exception as e:
            return f"[Ошибка чтения: {e}]", {'exists': True, 'error': str(e)}
    
    def get_context(self):
        """Возвращает собранный контекст."""
        if not self._context:
            self.build()
        return self._context
    
    def get_stats(self):
        """Возвращает статистику по контексту."""
        if not self._stats:
            self.build()
        return self._stats
    
    def get_total_stats(self):
        """Возвращает общую статистику."""
        stats = self.get_stats()
        
        total_lines = 0
        total_chars = 0
        strategies = {}
        
        for name, s in stats.items():
            if s.get('exists'):
                total_lines += s.get('lines', 0)
                total_chars += s.get('chars', 0)
                strategy = s.get('strategy', 'unknown')
                strategies[strategy] = strategies.get(strategy, 0) + 1
        
        return {
            'sections': len(stats),
            'total_lines': total_lines,
            'total_chars': total_chars,
            'estimated_tokens': total_chars // 4,
            'strategies': strategies
        }
    
    def format_compact(self):
        """Форматирует контекст в компактном виде."""
        context = self.get_context()
        stats = self.get_stats()
        
        lines = []
        lines.append("=" * 60)
        lines.append("КОНТЕКСТ СЕССИИ (компактный)")
        lines.append(f"Собрано: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("=" * 60)
        
        for name, content in context.items():
            s = stats.get(name, {})
            strategy = s.get('strategy', 'unknown')
            lines.append(f"\n--- {name} [{strategy}] ---")
            lines.append(content)
        
        # Статистика
        total = self.get_total_stats()
        lines.append("\n" + "=" * 60)
        lines.append("СТАТИСТИКА")
        lines.append(f"  Секций: {total['sections']}")
        lines.append(f"  Строк: {total['total_lines']}")
        lines.append(f"  Символов: {total['total_chars']}")
        lines.append(f"  Токенов (~): {total['estimated_tokens']}")
        lines.append(f"  Стратегии: {total['strategies']}")
        lines.append("=" * 60)
        
        return '\n'.join(lines)
    
    def format_json(self):
        """Форматирует контекст в JSON."""
        context = self.get_context()
        stats = self.get_stats()
        total = self.get_total_stats()
        
        return json.dumps({
            'context': context,
            'stats': stats,
            'total': total,
            'timestamp': datetime.now().isoformat()
        }, ensure_ascii=False, indent=2)


def print_usage():
    """Выводит справку."""
    print("Использование: python prompt_builder.py [опции]")
    print()
    print("Опции:")
    print("  --root DIR   — корневая директория проекта")
    print("  --full       — полный контекст (для отладки)")
    print("  --stats      — только статистика")
    print("  --compact    — компактный вывод (по умолчанию)")
    print("  --json       — вывод в JSON")
    print()
    print("Примеры:")
    print("  python prompt_builder.py")
    print("  python prompt_builder.py --stats")
    print("  python prompt_builder.py --json > context.json")


def main():
    if '--help' in sys.argv or '-h' in sys.argv:
        print_usage()
        sys.exit(0)
    
    # Парсинг аргументов
    root = None
    mode = 'compact'
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--root' and i + 1 < len(sys.argv):
            root = sys.argv[i + 1]
            i += 2
        elif arg == '--full':
            mode = 'full'
            i += 1
        elif arg == '--stats':
            mode = 'stats'
            i += 1
        elif arg == '--compact':
            mode = 'compact'
            i += 1
        elif arg == '--json':
            mode = 'json'
            i += 1
        else:
            print(f"Неизвестный аргумент: {arg}")
            print_usage()
            sys.exit(1)
    
    builder = PromptBuilder(root)
    
    if mode == 'stats':
        builder.build()
        total = builder.get_total_stats()
        print("=== Статистика контекста ===")
        print(f"  Секций: {total['sections']}")
        print(f"  Строк: {total['total_lines']}")
        print(f"  Символов: {total['total_chars']}")
        print(f"  Токенов (~): {total['estimated_tokens']}")
        print(f"  Стратегии: {total['strategies']}")
    
    elif mode == 'json':
        print(builder.format_json())
    
    elif mode == 'full':
        builder.build()
        context = builder.get_context()
        for name, content in context.items():
            print(f"\n{'=' * 60}")
            print(f"  {name}")
            print(f"{'=' * 60}")
            print(content)
    
    else:  # compact
        print(builder.format_compact())


if __name__ == '__main__':
    main()

