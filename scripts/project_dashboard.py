"""Генерация HTML-дашборда проекта ai-lives.

Собирает метрики проекта и создаёт интерактивный HTML-отчёт:
- структура директорий
- покрытие тестов
- статистика по скриптам
- последние сессии из истории

Запуск: python scripts/project_dashboard.py [--output dashboard.html]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── Утилиты ────────────────────────────────────────────────────────────────

def read_file_safe(path: Path) -> str:
    """Прочитать файл, вернуть пустую строку при ошибке."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return ""


def count_lines(path: Path) -> int:
    """Количество строк в файле."""
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return 0


def dir_tree(path: Path, prefix: str = "", is_last: bool = True, depth: int = 0) -> list[str]:
    """Рекурсивно собрать текстовое дерево директории (до 3 уровней)."""
    lines: list[str] = []
    if depth > 3:
        return lines

    try:
        entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name))
    except OSError:
        return lines

    for i, entry in enumerate(entries):
        is_last_entry = (i == len(entries) - 1)
        connector = "└── " if is_last_entry else "├── "
        lines.append(f"{prefix}{connector}{entry.name}")

        if entry.is_dir() and depth < 3:
            extension = "    " if is_last_entry else "│   "
            lines.extend(dir_tree(entry, prefix + extension, is_last_entry, depth + 1))

    return lines


def collect_script_stats(scripts_dir: Path, project_root: Path) -> list[dict]:
    """Собрать статистику по всем .py файлам в scripts/."""
    stats = []
    if not scripts_dir.is_dir():
        return stats

    for py_file in sorted(scripts_dir.glob("*.py")):
        lines = count_lines(py_file)
        content = read_file_safe(py_file)
        # Подсчёт функций и классов
        func_count = content.count("def ")
        class_count = content.count("class ")
        docstrings = content.count('"""') // 2  # парные тройные кавычки
        try:
            rel_path = str(py_file.relative_to(project_root))
        except ValueError:
            rel_path = str(py_file)
        stats.append({
            "name": py_file.stem,
            "path": rel_path,
            "lines": lines,
            "functions": func_count,
            "classes": class_count,
            "has_docstring": docstrings > 0,
        })

    return stats


def collect_test_stats(tests_dir: Path, project_root: Path) -> dict:
    """Собрать статистику по тестам."""
    if not tests_dir.is_dir():
        return {"total": 0, "files": []}

    test_files = sorted(tests_dir.glob("test_*.py"))
    total_files = len(test_files)
    total_tests = 0
    file_details = []

    for tf in test_files:
        content = read_file_safe(tf)
        # Подсчёт test_ функций
        test_funcs = [line.strip() for line in content.splitlines() if line.strip().startswith("def test_")]
        num_tests = len(test_funcs)
        total_tests += num_tests
        try:
            rel_path = str(tf.relative_to(project_root))
        except ValueError:
            rel_path = str(tf)
        file_details.append({
            "name": tf.stem,
            "tests": num_tests,
            "lines": count_lines(tf),
            "path": rel_path,
        })

    return {
        "total_files": total_files,
        "total_tests": total_tests,
        "files": file_details,
    }


def collect_state_stats(state_dir: Path, project_root: Path) -> dict:
    """Статистика директории состояния."""
    if not state_dir.is_dir():
        return {"total_files": 0, "total_lines": 0}

    md_files = list(state_dir.rglob("*.md"))
    total_lines = sum(count_lines(f) for f in md_files)

    file_paths = []
    for f in sorted(md_files):
        try:
            file_paths.append(str(f.relative_to(project_root)))
        except ValueError:
            file_paths.append(str(f))

    return {
        "total_files": len(md_files),
        "total_lines": total_lines,
        "files": file_paths,
    }


def read_history_summary(logs_dir: Path, last_n: int = 5) -> list[dict]:
    """Прочитать последние N записей из истории."""
    history_file = logs_dir / "history.md"
    content = read_file_safe(history_file)
    if not content:
        return []

    entries = []
    current_entry: dict = {}
    for line in content.splitlines():
        if line.startswith("## Сессия "):
            if current_entry:
                entries.append(current_entry)
            session_id = line.replace("## Сессия ", "").strip()
            current_entry = {"session": session_id, "summary": []}
        elif line.strip() and not line.startswith("#") and current_entry:
            current_entry["summary"].append(line.strip())

    if current_entry:
        entries.append(current_entry)

    return entries[-last_n:]


# ── Генерация HTML ─────────────────────────────────────────────────────────

def generate_html(
    project_root: Path,
    output_path: Path,
) -> None:
    """Сгенерировать HTML-дашборд."""
    scripts_dir = project_root / "scripts"
    tests_dir = project_root / "tests"
    state_dir = project_root / "state"
    logs_dir = project_root / "logs"
    src_dir = project_root / "src"

    # Сбор метрик
    tree_lines = dir_tree(project_root)
    script_stats = collect_script_stats(scripts_dir, project_root)
    test_stats = collect_test_stats(tests_dir, project_root)
    state_stats = collect_state_stats(state_dir, project_root)
    history = read_history_summary(logs_dir)

    # Подсчёт общего количества строк в проекте
    # Исключаем .venv и директории снимков
    total_lines = 0
    total_py_files = 0
    for py_file in project_root.rglob("*.py"):
        path_str = str(py_file)
        if ".venv" in path_str or "__pycache__" in path_str:
            continue
        # Исключаем директории snapshots (снимки сессий)
        parts = py_file.parts
        if "snapshots" in parts:
            continue
        total_lines += count_lines(py_file)
        total_py_files += 1

    # Сводка по скриптам
    total_script_lines = sum(s["lines"] for s in script_stats)
    total_script_funcs = sum(s["functions"] for s in script_stats)

    # Генерация дерева
    tree_html = "<br>".join(f"<code>{line}</code>" for line in tree_lines[:80])
    if len(tree_lines) > 80:
        tree_html += f"<br><em>... и ещё {len(tree_lines) - 80} записей</em>"

    # Таблица скриптов
    script_rows = ""
    for s in script_stats:
        script_rows += f"""
        <tr>
            <td><code>{s['name']}.py</code></td>
            <td>{s['lines']}</td>
            <td>{s['functions']}</td>
            <td>{s['classes']}</td>
            <td>✅</td>
        </tr>"""

    # Таблица тестов
    test_rows = ""
    for f in test_stats.get("files", []):
        test_rows += f"""
        <tr>
            <td><code>{f['name']}.py</code></td>
            <td>{f['tests']}</td>
            <td>{f['lines']}</td>
        </tr>"""

    # Последние сессии
    history_rows = ""
    for h in history:
        summary_text = "<br>".join(h.get("summary", [])[:3])
        history_rows += f"""
        <tr>
            <td><strong>{h['session']}</strong></td>
            <td>{summary_text}</td>
        </tr>"""

    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ai-lives — Дашборд проекта</title>
<style>
    :root {{
        --bg: #0d1117;
        --surface: #161b22;
        --border: #30363d;
        --text: #c9d1d9;
        --text-muted: #8b949e;
        --accent: #58a6ff;
        --green: #3fb950;
        --orange: #d29922;
        --red: #f85149;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        background: var(--bg);
        color: var(--text);
        padding: 2rem;
        line-height: 1.6;
    }}
    h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; color: var(--accent); }}
    h2 {{ font-size: 1.3rem; margin: 2rem 0 1rem; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; }}
    h3 {{ font-size: 1.1rem; margin: 1rem 0 0.5rem; color: var(--text); }}
    .subtitle {{ color: var(--text-muted); margin-bottom: 2rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1rem 0; }}
    .card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 1.2rem;
    }}
    .card .value {{ font-size: 2rem; font-weight: 700; color: var(--green); }}
    .card .label {{ font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}
    table {{ width: 100%; border-collapse: collapse; margin: 0.5rem 0; }}
    th, td {{ text-align: left; padding: 0.5rem 0.8rem; border-bottom: 1px solid var(--border); }}
    th {{ color: var(--text-muted); font-size: 0.85rem; text-transform: uppercase; }}
    code {{ background: var(--surface); padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.9em; }}
    .tree {{ font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.85rem; color: var(--text-muted); white-space: pre-wrap; }}
    .history-table td:first-child {{ color: var(--accent); }}
    footer {{ margin-top: 3rem; color: var(--text-muted); font-size: 0.85rem; text-align: center; }}
</style>
</head>
<body>

<h1>🧠 ai-lives</h1>
<p class="subtitle">Дашборд проекта · Обновлено: {now}</p>

<!-- Сводка -->
<h2>📊 Сводка</h2>
<div class="grid">
    <div class="card">
        <div class="value">{total_py_files}</div>
        <div class="label">Python-файлов</div>
    </div>
    <div class="card">
        <div class="value">{total_lines:,}</div>
        <div class="label">Строк кода</div>
    </div>
    <div class="card">
        <div class="value">{test_stats['total_tests']}</div>
        <div class="label">Тестов</div>
    </div>
    <div class="card">
        <div class="value">{test_stats['total_files']}</div>
        <div class="label">Файлов тестов</div>
    </div>
    <div class="card">
        <div class="value">{total_script_funcs}</div>
        <div class="label">Функций в скриптах</div>
    </div>
    <div class="card">
        <div class="value">{state_stats['total_files']}</div>
        <div class="label">Файлов состояния</div>
    </div>
</div>

<!-- Структура -->
<h2>📁 Структура проекта</h2>
<div class="tree">{tree_html}</div>

<!-- Скрипты -->
<h2>⚙️ Скрипты</h2>
<p style="color:var(--text-muted);font-size:0.9rem;">{total_script_lines} строк, {len(script_stats)} файлов</p>
<table>
    <tr><th>Файл</th><th>Строки</th><th>Функции</th><th>Классы</th><th>Docstring</th></tr>
    {script_rows}
</table>

<!-- Тесты -->
<h2>🧪 Тесты</h2>
<p style="color:var(--text-muted);font-size:0.9rem;">{test_stats['total_tests']} тестов в {test_stats['total_files']} файлах</p>
<table>
    <tr><th>Файл</th><th>Тестов</th><th>Строк</th></tr>
    {test_rows}
</table>

<!-- История -->
<h2>📜 Последние сессии</h2>
<table class="history-table">
    <tr><th>Сессия</th><th>Краткое содержание</th></tr>
    {history_rows if history_rows else '<tr><td colspan="2" style="color:var(--text-muted)">Записей не найдено</td></tr>'}
</table>

<footer>ai-lives · Автономный агент · {now}</footer>

</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    print(f"✅ Дашборд сохранён: {output_path}")
    print(f"   Файлов: {total_py_files} · Строк: {total_lines:,} · Тестов: {test_stats['total_tests']}")


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    """Точка входа для генерации HTML-дашборда проекта."""
    parser = argparse.ArgumentParser(description="Генерация HTML-дашборда проекта ai-lives")
    parser.add_argument(
        "--output", "-o",
        default="dashboard.html",
        help="Путь к выходному файлу (по умолчанию: dashboard.html)",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Корень проекта (по умолчанию: ищется автоматически)",
    )
    args = parser.parse_args()

    # Определяем корень проекта
    if args.root:
        root = Path(args.root)
    else:
        # Пытаемся найти корень: ищем родительскую директорию, где есть scripts/ и tests/
        candidate = Path.cwd()
        for parent in [candidate] + list(candidate.parents):
            if (parent / "scripts").is_dir() and (parent / "tests").is_dir():
                root = parent
                break
        else:
            root = Path.cwd()

    output = Path(args.output)

    if not (root / "scripts").is_dir():
        print(f"⚠️  Не найден каталог scripts/ в {root}", file=sys.stderr)
        sys.exit(1)

    generate_html(root, output)


if __name__ == "__main__":
    main()
