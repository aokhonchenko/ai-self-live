#!/usr/bin/env python3
"""
Модуль управления контекстом сессии.

Читает файлы точечно через partial_reader, экономя токены модели.
Вместо чтения целого файла — только нужные секции, заголовки, первые N строк.

Создан: сессия 22 (2026-07-06)
Цель: оптимизировать работу агента с моделью через точечное воздействие.

Использование:
    from context import SessionContext

    ctx = SessionContext()
    ctx.load()  # загружает минимальный контекст
    ctx.get_state()  # возвращает словарь состояния
"""

import sys
import os
from pathlib import Path

# Добавляем путь к src для импорта partial_reader и compat
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from src.tools.partial_reader import read_head, read_headers, read_section, read_summary
except ImportError:
    from src.tools.compat import read_head, read_headers, read_section, read_summary


class SessionContext:
    """
    Управляет контекстом сессии.
    
    Загружает только необходимую информацию, используя точечное чтение.
    Каждый файл читается оптимальным способом:
    - Маленькие (≤40 строк) — целиком
    - Средние (40-100 строк) — заголовки + нужные секции
    - Большие (>100 строк) — только заголовки + summary
    """
    
    def __init__(self, root=None, cache_enabled=True):
        """
        Args:
            root: корневая директория проекта (по умолчанию — текущая)
            cache_enabled: включать ли кэширование результатов чтения (по умолчанию True)
        """
        self.root = Path(root) if root else Path.cwd()
        self._state = {}
        self._loaded = False
        self._cache_enabled = cache_enabled
        self._cache = {}  # {abs_path: (mtime, content)}
        self._cache_hits = 0
        self._cache_misses = 0
    
    def load(self):
        """Загружает минимальный контекст сессии."""
        self._state = {
            'last_session': self._read_optimized('state/last_session.md'),
            'current_plan': self._read_optimized('state/current_plan.md'),
            'external_messages': self._read_optimized('state/external_messages.md'),
            'active_tasks': self._read_optimized('tasks/active.md'),
        }
        self._loaded = True
        return self
    
    def _read_optimized(self, rel_path):
        """
        Читает файл оптимальным способом, основываясь на размере.
        Использует кэш для повторных чтений.
        
        Returns:
            str: содержимое файла (полное или частичное)
        """
        filepath = self.root / rel_path
        
        if not filepath.exists():
            return f"[Файл не найден: {rel_path}]"
        
        # Проверяем кэш
        cached = self._cache_get(filepath)
        if cached is not None:
            return cached
        
        try:
            # Определяем размер файла
            size = filepath.stat().st_size
            with open(filepath, 'r', encoding='utf-8') as f:
                line_count = sum(1 for _ in f)
            
            # Стратегия чтения по размеру
            if line_count <= 40:
                # Маленький файл — читаем целиком
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            elif line_count <= 100:
                # Средний файл — заголовки + первые строки
                content = read_summary(str(filepath), context_lines=2)
            else:
                # Большой файл — только заголовки
                content = read_headers(str(filepath))
            
            # Сохраняем в кэш
            self._cache_set(filepath, content)
            return content
                
        except Exception as e:
            return f"[Ошибка чтения {rel_path}: {e}]"
    
    def _cache_get(self, filepath):
        """
        Получить содержимое файла из кэша.
        
        Returns:
            str или None: содержимое файла, если есть в кэше и актуально; None иначе
        """
        if not self._cache_enabled:
            return None
        
        abs_path = str(filepath.resolve())
        try:
            mtime = filepath.stat().st_mtime
        except OSError:
            return None
        
        if abs_path in self._cache:
            cached_mtime, cached_content = self._cache[abs_path]
            if cached_mtime == mtime:
                self._cache_hits += 1
                return cached_content
        
        self._cache_misses += 1
        return None
    
    def _cache_set(self, filepath, content):
        """Сохранить содержимое файла в кэш."""
        if not self._cache_enabled:
            return
        
        abs_path = str(filepath.resolve())
        try:
            mtime = filepath.stat().st_mtime
        except OSError:
            return
        
        self._cache[abs_path] = (mtime, content)
    
    def cache_stats(self):
        """Возвращает статистику кэширования."""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0.0
        return {
            'hits': self._cache_hits,
            'misses': self._cache_misses,
            'total': total,
            'hit_rate': round(hit_rate, 1),
            'cached_files': len(self._cache)
        }
    
    def clear_cache(self):
        """Очищает кэш."""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
    
    def _read_with_cache(self, filepath, read_fn):
        """
        Читает файл с кэшированием результата read_fn.
        
        Args:
            filepath: Path к файлу
            read_fn: callable(filepath) -> str — функция чтения
        """
        if not filepath.exists():
            return None
        
        cached = self._cache_get(filepath)
        if cached is not None:
            return cached
        
        content = read_fn(filepath)
        self._cache_set(filepath, content)
        return content
    
    def get_state(self):
        """Возвращает загруженное состояние."""
        if not self._loaded:
            self.load()
        return self._state
    
    def get_file_summary(self, rel_path):
        """
        Возвращает краткую сводку файла.
        
        Args:
            rel_path: относительный путь к файлу
            
        Returns:
            str: заголовки + первые строки секций
        """
        filepath = self.root / rel_path
        if not filepath.exists():
            return f"[Файл не найден: {rel_path}]"
        
        def _read(filepath):
            return read_summary(str(filepath), context_lines=2)
        
        result = self._read_with_cache(filepath, _read)
        return result if result is not None else "[Ошибка чтения]"
    
    def get_file_headers(self, rel_path):
        """
        Возвращает только заголовки файла.
        
        Args:
            rel_path: относительный путь к файлу
            
        Returns:
            str: заголовки markdown (# и ##)
        """
        filepath = self.root / rel_path
        if not filepath.exists():
            return f"[Файл не найден: {rel_path}]"
        
        def _read(filepath):
            return read_headers(str(filepath))
        
        result = self._read_with_cache(filepath, _read)
        return result if result is not None else "[Ошибка чтения]"
    
    def get_section(self, rel_path, section_name):
        """
        Возвращает конкретную секцию файла.
        
        Args:
            rel_path: относительный путь к файлу
            section_name: имя секции (подстрока заголовка)
            
        Returns:
            str: содержимое секции
        """
        filepath = self.root / rel_path
        if not filepath.exists():
            return f"[Файл не найден: {rel_path}]"
        
        def _read(filepath):
            return read_section(str(filepath), section_name)
        
        result = self._read_with_cache(filepath, _read)
        return result if result is not None else "[Ошибка чтения]"
    
    def get_file_info(self, rel_path):
        """
        Возвращает информацию о файле.
        
        Args:
            rel_path: относительный путь к файлу
            
        Returns:
            dict: {path, size, lines, strategy}
        """
        filepath = self.root / rel_path
        if not filepath.exists():
            return {'path': rel_path, 'exists': False}
        
        size = filepath.stat().st_size
        with open(filepath, 'r', encoding='utf-8') as f:
            line_count = sum(1 for _ in f)
        
        # Определяем стратегию чтения
        if line_count <= 40:
            strategy = 'full'
        elif line_count <= 100:
            strategy = 'summary'
        else:
            strategy = 'headers_only'
        
        return {
            'path': rel_path,
            'exists': True,
            'size': size,
            'lines': line_count,
            'strategy': strategy
        }


def print_context_stats(ctx):
    """Выводит статистику по загруженному контексту."""
    state = ctx.get_state()
    
    print("=== Статистика контекста сессии ===\n")
    
    total_chars = 0
    for key, content in state.items():
        chars = len(content)
        total_chars += chars
        lines = content.count('\n') + 1
        print(f"  {key}: {lines} строк, {chars} символов")
    
    print(f"\n  Итого: {total_chars} символов")
    print(f"  Примерно: {total_chars // 4} токенов (оценка)")


def main():
    """CLI для тестирования модуля."""
    if len(sys.argv) < 2:
        print("Использование: python context.py <команда> [параметры]")
        print()
        print("Команды:")
        print("  load          — загрузить и показать контекст")
        print("  stats         — статистика по контексту")
        print("  summary FILE  — сводка файла")
        print("  headers FILE  — заголовки файла")
        print("  section FILE X — секция файла")
        print("  info FILE     — информация о файле")
        print("  cache_stats   — статистика кэширования")
        print("  clear_cache   — очистить кэш")
        sys.exit(1)
    
    cmd = sys.argv[1]
    ctx = SessionContext()
    
    if cmd == 'load':
        ctx.load()
        state = ctx.get_state()
        for key, content in state.items():
            print(f"\n{'='*60}")
            print(f"  {key}")
            print(f"{'='*60}")
            print(content[:500])  # Первые 500 символов
            if len(content) > 500:
                print(f"\n  ... ({len(content)} всего символов)")
    
    elif cmd == 'stats':
        ctx.load()
        print_context_stats(ctx)
    
    elif cmd == 'summary':
        if len(sys.argv) < 3:
            print("Ошибка: укажите файл")
            sys.exit(1)
        print(ctx.get_file_summary(sys.argv[2]))
    
    elif cmd == 'headers':
        if len(sys.argv) < 3:
            print("Ошибка: укажите файл")
            sys.exit(1)
        print(ctx.get_file_headers(sys.argv[2]))
    
    elif cmd == 'section':
        if len(sys.argv) < 4:
            print("Ошибка: укажите файл и имя секции")
            sys.exit(1)
        print(ctx.get_section(sys.argv[2], sys.argv[3]))
    
    elif cmd == 'info':
        if len(sys.argv) < 3:
            print("Ошибка: укажите файл")
            sys.exit(1)
        info = ctx.get_file_info(sys.argv[2])
        for k, v in info.items():
            print(f"  {k}: {v}")
    
    elif cmd == 'cache_stats':
        ctx.load()
        stats = ctx.cache_stats()
        print("=== Статистика кэширования ===")
        print(f"  Хиты:      {stats['hits']}")
        print(f"  Миссы:     {stats['misses']}")
        print(f"  Всего:     {stats['total']}")
        print(f"  Точность:  {stats['hit_rate']}%")
        print(f"  Файлов:    {stats['cached_files']}")
    
    elif cmd == 'clear_cache':
        ctx.clear_cache()
        print("Кэш очищен.")
    
    else:
        print(f"Неизвестная команда: {cmd}")
        sys.exit(1)


if __name__ == '__main__':
    main()

