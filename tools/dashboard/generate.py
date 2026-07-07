#!/usr/bin/env python3
"""
Генератор UI-дашборда проекта ai-lives.

Читает ключевые файлы проекта и генерирует статический HTML-дашборд
для просмотра в браузере без необходимости запускать сессию.

Создан: сессия 27 (2026-07-06)
Цель: визуализация состояния проекта без консольных сессий.

Использование:
    python generate.py [--root PATH] [--output PATH]

    --root    — корень проекта (по умолчанию — три уровня выше от скрипта)
    --output  — путь к выходному HTML (по умолчанию — index.html рядом со скриптом)
"""

import sys
import os
import re
from pathlib import Path
from datetime import datetime

from dashboard_style import STYLE


def find_project_root(script_path: str) -> Path:
    """Находит корень проекта относительно скрипта или его каталога."""
    path = Path(script_path).resolve()
    dashboard_dir = path if path.is_dir() else path.parent
    return dashboard_dir.parent.parent

def read_file_safe(filepath: Path) -> str:
    """Безопасно читает файл, возвращает пустую строку при ошибке."""
    try:
        return filepath.read_text(encoding='utf-8')
    except Exception:
        return ''


def parse_front_matter(content: str) -> tuple:
    """Извлекает метаданные из начала markdown-файла."""
    lines = content.strip().split('\n')
    meta = {}
    body_start = 0
    
    for i, line in enumerate(lines):
        if line.startswith('**') and ':**' in line:
            # Парсим **Key:** value
            match = re.match(r'\*\*(.+?):\*\*\s*(.+)', line)
            if match:
                meta[match.group(1).strip()] = match.group(2).strip()
        elif line.startswith('#') or (line.strip() and not line.startswith('**')):
            body_start = i
            break
    
    return meta, '\n'.join(lines[body_start:])


def md_to_html_simple(text: str) -> str:
    """Простой конвертер markdown в HTML."""
    lines = text.split('\n')
    html_lines = []
    in_table = False
    in_list = False
    in_code = False
    
    for line in lines:
        stripped = line.strip()
        
        # Code blocks
        if stripped.startswith('```'):
            if in_code:
                html_lines.append('</code></pre>')
                in_code = False
            else:
                lang = stripped[3:].strip()
                html_lines.append(f'<pre><code class="language-{lang}">')
                in_code = True
            continue
        
        if in_code:
            html_lines.append(line.replace('<', '<').replace('>', '>'))
            continue
        
        # Empty line
        if not stripped:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            if in_table:
                html_lines.append('</tbody></table>')
                in_table = False
            html_lines.append('')
            continue
        
        # Headers
        if stripped.startswith('### '):
            html_lines.append(f'<h4>{stripped[4:]}</h4>')
            continue
        if stripped.startswith('## '):
            html_lines.append(f'<h3>{stripped[3:]}</h3>')
            continue
        if stripped.startswith('# '):
            html_lines.append(f'<h2>{stripped[2:]}</h2>')
            continue
        
        # Horizontal rule
        if stripped == '---':
            html_lines.append('<hr>')
            continue
        
        # Table
        if '|' in stripped and stripped.startswith('|'):
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            
            # Skip separator rows
            if all(re.match(r'^[-:]+$', c) for c in cells):
                continue
            
            if not in_table:
                html_lines.append('<table>')
                html_lines.append('<thead><tr>')
                for cell in cells:
                    html_lines.append(f'<th>{inline_md(cell)}</th>')
                html_lines.append('</tr></thead><tbody>')
                in_table = True
            else:
                html_lines.append('<tr>')
                for cell in cells:
                    html_lines.append(f'<td>{inline_md(cell)}</td>')
                html_lines.append('</tr>')
            continue
        
        # List items
        if stripped.startswith('- ') or stripped.startswith('* '):
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            content = stripped[2:]
            html_lines.append(f'<li>{inline_md(content)}</li>')
            continue
        
        # Checkbox list
        if re.match(r'^- \[[ x]\]', stripped):
            if not in_list:
                html_lines.append('<ul class="task-list">')
                in_list = True
            checked = stripped[3] == 'x'
            content = stripped[6:]
            checkbox = '☑' if checked else '☐'
            cls = 'done' if checked else 'pending'
            html_lines.append(f'<li class="{cls}"><span class="checkbox">{checkbox}</span> {inline_md(content)}</li>')
            continue
        
        # Blockquote
        if stripped.startswith('> '):
            html_lines.append(f'<blockquote>{inline_md(stripped[2:])}</blockquote>')
            continue
        
        # Regular paragraph
        if in_list:
            html_lines.append('</ul>')
            in_list = False
        html_lines.append(f'<p>{inline_md(stripped)}</p>')
    
    if in_list:
        html_lines.append('</ul>')
    if in_table:
        html_lines.append('</tbody></table>')
    if in_code:
        html_lines.append('</code></pre>')
    
    return '\n'.join(html_lines)


def inline_md(text: str) -> str:
    """Обрабатывает inline markdown: bold, italic, code, links."""
    # Inline code
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    # Bold
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    # Italic
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
    # Links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    # Checkbox symbols
    text = text.replace('✅', '<span class="icon-ok">✅</span>')
    text = text.replace('❌', '<span class="icon-no">❌</span>')
    text = text.replace('⏳', '<span class="icon-wait">⏳</span>')
    text = text.replace('🟡', '<span class="icon-med">🟡</span>')
    text = text.replace('🟢', '<span class="icon-low">🟢</span>')
    return text


def extract_tasks_summary(content: str) -> dict:
    """Извлекает сводку по задачам."""
    summary = {'high': 0, 'medium': 0, 'low': 0, 'done': 0, 'total': 0}
    
    for line in content.split('\n'):
        stripped = line.strip()
        if re.match(r'^- \[ \]', stripped):
            summary['total'] += 1
            if '🟡' in stripped or 'Средний' in stripped:
                summary['medium'] += 1
            elif '🟢' in stripped or 'Низкий' in stripped:
                summary['low'] += 1
            else:
                summary['high'] += 1
        elif re.match(r'^- \[x\]', stripped):
            summary['done'] += 1
    
    return summary


def extract_session_number(content: str) -> str:
    """Извлекает номер сессии из last_session.md."""
    match = re.search(r'сессия\s+(\d+)', content, re.IGNORECASE)
    return match.group(1) if match else '?'


def generate_dashboard(root: Path, output: Path):
    """Генерирует HTML-дашборд."""
    
    # Читаем ключевые файлы
    quick_context = read_file_safe(root / 'knowledge' / 'quick_context.md')
    last_session = read_file_safe(root / 'state' / 'last_session.md')
    current_plan = read_file_safe(root / 'state' / 'current_plan.md')
    active_tasks = read_file_safe(root / 'tasks' / 'active.md')
    history = read_file_safe(root / 'logs' / 'history.md')
    external_messages = read_file_safe(root / 'state' / 'external_messages.md')
    
    # Извлекаем метаданные
    session_num = extract_session_number(last_session)
    tasks_summary = extract_tasks_summary(active_tasks)
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    # Считаем статистику файлов
    py_files = list(root.rglob('*.py'))
    md_files = list(root.rglob('*.md'))
    total_py_lines = 0
    for f in py_files:
        if '__pycache__' not in str(f):
            try:
                total_py_lines += len(f.read_text(encoding='utf-8').split('\n'))
            except Exception:
                pass
    
    # Генерируем HTML
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ai-lives — Дашборд</title>
    <style>
        {STYLE}
    </style>
</head>
<body>
    <header>
        <h1>🤖 <span>ai-lives</span> — Дашборд</h1>
        <div class="meta">
            Сессия {session_num} · Обновлено: {now}
        </div>
    </header>
    
    <div class="stats-grid">
        <div class="stat-card">
            <div class="value">{session_num}</div>
            <div class="label">Текущая сессия</div>
        </div>
        <div class="stat-card green">
            <div class="value">{len(py_files)}</div>
            <div class="label">Python-файлов</div>
        </div>
        <div class="stat-card yellow">
            <div class="value">{total_py_lines}</div>
            <div class="label">Строк кода</div>
        </div>
        <div class="stat-card purple">
            <div class="value">{len(md_files)}</div>
            <div class="label">Markdown-файлов</div>
        </div>
        <div class="stat-card">
            <div class="value">{tasks_summary['total']}</div>
            <div class="label">Активных задач</div>
        </div>
        <div class="stat-card green">
            <div class="value">{tasks_summary['done']}</div>
            <div class="label">Выполнено</div>
        </div>
    </div>
    
    <div class="grid">
        <div class="card">
            <div class="card-header">
                <span class="icon">⚡</span> Последняя сессия
            </div>
            <div class="card-body">
                {md_to_html_simple(last_session)}
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <span class="icon">📋</span> Активные задачи
            </div>
            <div class="card-body">
                {md_to_html_simple(active_tasks)}
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <span class="icon">🎯</span> Быстрый контекст
            </div>
            <div class="card-body">
                {md_to_html_simple(quick_context)}
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <span class="icon">💬</span> Внешние сообщения
            </div>
            <div class="card-body">
                {md_to_html_simple(external_messages) if external_messages.strip() else '<p style="color: var(--text-muted); font-style: italic;">Сообщений пока нет</p>'}
            </div>
        </div>
        
        <div class="card full-width">
            <div class="card-header">
                <span class="icon">🗺️</span> Текущий план
            </div>
            <div class="card-body scroll-indicator">
                {md_to_html_simple(current_plan)}
            </div>
        </div>
        
        <div class="card full-width">
            <div class="card-header">
                <span class="icon">📜</span> История сессий
            </div>
            <div class="card-body scroll-indicator">
                {md_to_html_simple(history)}
            </div>
        </div>
    </div>
    
    <footer>
        ai-lives · Автономный агент · Сгенерировано {now}
    </footer>
</body>
</html>"""
    
    output.write_text(html, encoding='utf-8')
    return output


def print_usage():
    """Выводит справку."""
    print("Использование: python generate.py [--root PATH] [--output PATH]")
    print()
    print("Аргументы:")
    print("  --root    — корень проекта (по умолчанию — три уровня выше)")
    print("  --output  — путь к выходному HTML (по умолчанию — index.html)")
    print()
    print("Примеры:")
    print("  python generate.py")
    print("  python generate.py --root /path/to/session-0027")
    print("  python generate.py --output dashboard.html")


def main():
    if '--help' in sys.argv or '-h' in sys.argv:
        print_usage()
        sys.exit(0)
    
    script_dir = Path(__file__).resolve().parent
    root = find_project_root(str(script_dir))
    output = script_dir / 'index.html'
    
    # Парсинг аргументов
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--root' and i + 1 < len(args):
            root = Path(args[i + 1]).resolve()
            i += 2
        elif args[i] == '--output' and i + 1 < len(args):
            output = Path(args[i + 1]).resolve()
            i += 2
        else:
            i += 1
    
    if not root.exists():
        print(f"Ошибка: корень проекта не найден: {root}")
        sys.exit(1)
    
    result = generate_dashboard(root, output)
    print(f"OK: Дашборд сгенерирован: {result}")
    print(f"   Откройте в браузере: file:///{result.as_posix()}")


if __name__ == '__main__':
    main()

