#!/usr/bin/env python3
"""
Сервер управления сессиями ai-lives.

Запуск: uv run python server/server.py [--port 11000]
Endpoints:
  GET  /                    — веб-дашборд
  GET  /api/last-session    — содержимое state/last_session.md
  GET  /api/status          — статус сервера (idle/running/auto)
  GET  /api/events          — SSE-поток для real-time обновлений
  POST /api/session/start   — запуск одной сессии
  POST /api/auto/toggle     — переключение автосессии
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import subprocess as sp

try:
    from server.config import auto_session_delay_seconds, load_server_dotenv
except ModuleNotFoundError:
    from config import auto_session_delay_seconds, load_server_dotenv

# Корень проекта — родительская директория относительно server/
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def ensure_project_import_path() -> None:
    """Добавить корень проекта в sys.path для импортов src.*."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


ensure_project_import_path()

STATE_DIR = PROJECT_ROOT / "state"
STATIC_DIR = Path(__file__).resolve().parent / "static"
SESSION_COMMAND = ["uv", "run", "python", "scripts/session_transaction.py"]


def utf8_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env

# Глобальное состояние
class ServerState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.status: str = "idle"  # idle | running | auto
        self.auto_enabled: bool = False
        self.auto_thread: threading.Thread | None = None
        self.last_error: str = ""
        self.last_run_time: str = ""
        self.session_count: int = 0
        self.next_start_time: float | None = None
        self.next_start_delay_seconds: int | None = None
        self._sse_clients: list[Any] = []
        self._sse_lock = threading.Lock()

    def broadcast(self, event: str, data: dict) -> None:
        """Отправить SSE-событие всем подключённым клиентам."""
        msg = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        with self._sse_lock:
            dead = []
            for client in self._sse_clients:
                try:
                    client.write(msg.encode("utf-8"))
                    client.flush()
                except Exception:
                    dead.append(client)
            for c in dead:
                self._sse_clients.remove(c)

    def add_sse_client(self, wfile: Any) -> None:
        with self._sse_lock:
            self._sse_clients.append(wfile)

    def remove_sse_client(self, wfile: Any) -> None:
        with self._sse_lock:
            if wfile in self._sse_clients:
                self._sse_clients.remove(wfile)


STATE = ServerState()


def read_last_session() -> str:
    """Прочитать state/last_session.md."""
    path = STATE_DIR / "last_session.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "# Сообщение будущей сессии\n\nФайл пока не создан."


def read_current_plan() -> str:
    """Прочитать state/current_plan.md — текущую цель агента."""
    path = STATE_DIR / "current_plan.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "# Текущая цель\n\nНе установлена."
    

def collect_project_metrics() -> dict:
    """Собрать метрики проекта: тесты, покрытие, инструменты, скрипты."""
    tests_dir = STATE_DIR.parent / "tests"
    scripts_dir = STATE_DIR.parent / "scripts"
    tools_dir = STATE_DIR.parent / "src" / "tools"

    # Считаем тесты
    total_tests = 0
    test_files = []
    if tests_dir.is_dir():
        for tf in sorted(tests_dir.glob("test_*.py")):
            content = tf.read_text(encoding="utf-8", errors="replace")
            num = len([l for l in content.splitlines() if l.strip().startswith("def test_")])
            total_tests += num
            test_files.append({"name": tf.stem, "tests": num})

    # Считаем скрипты
    script_count = 0
    script_lines = 0
    if scripts_dir.is_dir():
        for sf in sorted(scripts_dir.glob("*.py")):
            script_count += 1
            script_lines += len(sf.read_text(encoding="utf-8", errors="replace").splitlines())

    # Считаем инструменты
    tool_count = 0
    if tools_dir.is_dir():
        for td in sorted(tools_dir.iterdir()):
            if (td / "tool.py").is_file():
                tool_count += 1

    # Покрытие через pytest
    coverage = "—"
    try:
        result = sp.run(
            ["uv", "run", "python", "-m", "pytest", "--cov=scripts", "--cov=server",
             "--cov-report=term", "--cov-report=json:.coverage_tmp.json", "-q"],
            cwd=str(STATE_DIR.parent),
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode == 0 and result.stdout:
            # Парсим покрытие из stdout pytest-cov
            import re
            match = re.search(r"TOTAL\s+.*?\s+(\d+%)", result.stdout)
            if match:
                coverage = match.group(1)
            else:
                # Попробуем найти процент в последней строке
                lines = result.stdout.strip().split("\n")
                for line in reversed(lines):
                    pct = re.search(r"(\d+%)", line)
                    if pct:
                        coverage = pct.group(1)
                        break
        # Удаляем временный файл
        try:
            (STATE_DIR.parent / ".coverage_tmp.json").unlink(missing_ok=True)
        except OSError:
            pass
    except (sp.TimeoutExpired, FileNotFoundError, sp.CalledProcessError):
        coverage = "—"

    # Шумность state-файлов
    noise_ratio = 0.0
    try:
        state_dir = STATE_DIR.parent / "state"
        if state_dir.is_dir():
            md_files = list(state_dir.rglob("*.md"))
            total_noise_lines = 0
            total_lines = 0
            for mf in md_files:
                text = mf.read_text(encoding="utf-8", errors="replace")
                lines = text.splitlines()
                total_lines += len(lines)
                for line in lines:
                    s = line.strip()
                    if not s or s == "---" or s.startswith("###") or s.startswith("|") and s.endswith("|"):
                        total_noise_lines += 1
            if total_lines > 0:
                noise_ratio = round(total_noise_lines / total_lines * 100, 1)
    except Exception:
        noise_ratio = 0.0

    return {
        "total_tests": total_tests,
        "test_files": test_files,
        "script_count": script_count,
        "script_lines": script_lines,
        "tool_count": tool_count,
        "coverage": coverage,
        "noise_ratio": noise_ratio,
    }


load_server_dotenv(PROJECT_ROOT / ".env")


def collect_context_analysis() -> dict:
    """Собрать состояние контекста через context_analyzer."""
    try:
        from datetime import datetime as _dt
        from src.tools.context_analyzer.core import analyze as ctx_analyze
        report = ctx_analyze(str(PROJECT_ROOT))
        # Конвертируем datetime в строки для JSON-сериализации
        sections = []
        for s in report.get("sections", []):
            sec = dict(s)
            if isinstance(sec.get("date"), _dt):
                sec["date"] = sec["date"].isoformat()
            sections.append(sec)
        return {
            "health": report.get("health"),
            "health_label": report.get("health_label"),
            "total_tokens": report.get("total_tokens"),
            "total_chars": report.get("total_chars"),
            "total_lines": report.get("total_lines"),
            "sections": sections,
            "questions_count": report.get("questions", {}).get("count", 0),
            "questions_open": report.get("questions", {}).get("open", 0),
            "recommendations": report.get("recommendations", []),
        }
    except Exception as e:
        return {
            "health": "error",
            "health_label": "Ошибка",
            "total_tokens": 0,
            "total_chars": 0,
            "total_lines": 0,
            "sections": [],
            "questions_count": 0,
            "questions_open": 0,
            "recommendations": [f"Не удалось проанализировать контекст: {e}"],
        }


def run_session_transaction(on_output: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """Запустить session_transaction.py и вернуть (success, output)."""
    output: list[str] = []
    try:
        process = subprocess.Popen(
            SESSION_COMMAND,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=utf8_subprocess_env(),
        )
        if process.stdout is None:
            return False, "Сессия не открыла stdout"

        deadline = time.monotonic() + 600
        while True:
            line = process.stdout.readline()
            if line:
                output.append(line)
                if on_output is not None:
                    on_output(line.rstrip("\r\n"))
                continue

            if process.poll() is not None:
                break
            if time.monotonic() > deadline:
                process.kill()
                message = "Таймаут: сессия превысила 10 минут"
                output.append(message)
                if on_output is not None:
                    on_output(message)
                return False, "".join(output)
            time.sleep(0.1)

        return process.wait() == 0, "".join(output)
    except Exception as e:
        return False, str(e)


def auto_session_loop() -> None:
    """Цикл автосессий: запуск -> случайная пауза 5-15 минут -> повтор."""
    while True:
        with STATE.lock:
            if not STATE.auto_enabled:
                STATE.status = "idle"
                STATE.next_start_time = None
                STATE.next_start_delay_seconds = None
                break
            STATE.status = "running"
            STATE.next_start_time = None
            STATE.next_start_delay_seconds = None

        STATE.broadcast("status", {
            "status": "running",
            "auto_enabled": True,
            "next_start_time": None,
            "next_start_delay_seconds": None,
            "message": "Запуск сессии...",
        })

        success, output = run_session_transaction(lambda line: STATE.broadcast("session_log", {"line": line}))

        with STATE.lock:
            STATE.session_count += 1
            STATE.last_run_time = time.strftime("%Y-%m-%d %H:%M:%S")
            if not success:
                STATE.last_error = output[-500:] if len(output) > 500 else output

            if STATE.auto_enabled:
                delay_seconds = auto_session_delay_seconds()
                STATE.status = "auto"
                STATE.next_start_delay_seconds = delay_seconds
                STATE.next_start_time = time.time() + delay_seconds
            else:
                STATE.status = "idle"
                STATE.next_start_delay_seconds = None
                STATE.next_start_time = None

            session_count = STATE.session_count
            last_run_time = STATE.last_run_time
            last_error = STATE.last_error
            next_start_time = STATE.next_start_time
            next_start_delay_seconds = STATE.next_start_delay_seconds
            auto_enabled = STATE.auto_enabled

        # Перечитать last_session.md после сессии
        last_session = read_last_session()

        STATE.broadcast("session_done", {
            "success": success,
            "count": session_count,
            "time": last_run_time,
            "last_session": last_session,
            "error": last_error if not success else "",
            "next_start_time": next_start_time,
            "next_start_delay_seconds": next_start_delay_seconds,
        })

        # Отправить обновлённый контекст через SSE
        ctx_data = collect_context_analysis()
        STATE.broadcast("context_update", ctx_data)

        STATE.broadcast("status", {
            "status": "auto" if auto_enabled else "idle",
            "auto_enabled": auto_enabled,
            "next_start_time": next_start_time,
            "next_start_delay_seconds": next_start_delay_seconds,
        })

        while True:
            with STATE.lock:
                if not STATE.auto_enabled:
                    break
                if STATE.next_start_time is None or time.time() >= STATE.next_start_time:
                    break
            time.sleep(1)

        with STATE.lock:
            if not STATE.auto_enabled:
                STATE.status = "idle"
                STATE.next_start_time = None
                STATE.next_start_delay_seconds = None
                break
            STATE.next_start_time = None
            STATE.next_start_delay_seconds = None


class SessionHandler(BaseHTTPRequestHandler):
    """HTTP-обработчик для управления сессиями."""

    def log_message(self, format: str, *args: Any) -> None:
        # Подавляем стандартные логи для чистоты
        pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse_headers(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = self._route_path()
        if path == "/":
            self._serve_index()
        elif path == "/api/last-session":
            self._api_last_session()
        elif path == "/api/status":
            self._api_status()
        elif path == "/api/events":
            self._api_events()
        elif path == "/api/current-plan":
            self._api_current_plan()
        elif path == "/api/project-metrics":
            self._api_project_metrics()
        elif path == "/api/context-analysis":
            self._api_context_analysis()
        elif path == "/app.js":
            self._serve_static("app.js", "application/javascript; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        path = self._route_path()
        if path == "/api/session/start":
            self._api_session_start()
        elif path == "/api/auto/toggle":
            self._api_auto_toggle()
        elif path == "/api/compress":
            self._api_compress()
        else:
            self.send_error(404)

    def _route_path(self) -> str:
        """Вернуть путь без query string, допускающий завершающий слэш."""
        path = urlsplit(self.path).path
        if path != "/" and path.endswith("/"):
            return path.rstrip("/")
        return path

    def _serve_index(self) -> None:
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            html = index_path.read_text(encoding="utf-8")
            self._send_html(html)
        else:
            self._send_html("<h1>index.html не найден</h1>")

    def _serve_static(self, filename: str, content_type: str) -> None:
        path = STATIC_DIR / filename
        if not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_last_session(self) -> None:
        content = read_last_session()
        self._send_json({"content": content})

    def _api_current_plan(self) -> None:
        content = read_current_plan()
        self._send_json({"content": content})

    def _api_project_metrics(self) -> None:
        metrics = collect_project_metrics()
        self._send_json(metrics)

    def _api_context_analysis(self) -> None:
        data = collect_context_analysis()
        self._send_json(data)

    def _api_compress(self) -> None:
        """Сжать файл last_session.md через context_compressor."""
        import json
        from src.tools.context_compressor import core

        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            params = json.loads(body) if body else {}
        except Exception:
            params = {}

        dry_run = bool(params.get("dry_run", False))
        keep_recent = int(params.get("keep_recent", 5))

        try:
            last_session_path = PROJECT_ROOT / "state" / "last_session.md"
            if not last_session_path.exists():
                self._send_json({"ok": False, "error": "Файл last_session.md не найден"})
                return

            text = last_session_path.read_text(encoding="utf-8")
            result = core.compress_last_session(text, keep_recent=keep_recent)
            output = core.format_compression_result(result)

            if not dry_run and result.compressed_lines < result.original_lines:
                last_session_path.write_text(result.compressed_text, encoding="utf-8")

            self._send_json({
                "ok": True,
                "dry_run": dry_run,
                "content": output,
                "original_lines": result.original_lines,
                "compressed_lines": result.compressed_lines,
                "reduction_pct": result.size_reduction_pct,
            })
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _api_status(self) -> None:
        with STATE.lock:
            self._send_json({
                "status": STATE.status,
                "auto_enabled": STATE.auto_enabled,
                "session_count": STATE.session_count,
                "last_run_time": STATE.last_run_time,
                "last_error": STATE.last_error,
                "next_start_time": STATE.next_start_time,
                "next_start_delay_seconds": STATE.next_start_delay_seconds,
            })

    def _api_events(self) -> None:
        """SSE-поток для real-time обновлений."""
        self._send_sse_headers()
        STATE.add_sse_client(self.wfile)

        # Отправляем начальное состояние
        with STATE.lock:
            status_data = {
                "status": STATE.status,
                "auto_enabled": STATE.auto_enabled,
                "session_count": STATE.session_count,
                "last_run_time": STATE.last_run_time,
                "next_start_time": STATE.next_start_time,
                "next_start_delay_seconds": STATE.next_start_delay_seconds,
            }
        msg = f"event: status\ndata: {json.dumps(status_data, ensure_ascii=False)}\n\n"
        try:
            self.wfile.write(msg.encode("utf-8"))
            self.wfile.flush()
        except Exception:
            STATE.remove_sse_client(self.wfile)
            return

        # Держим соединение открытым
        try:
            while True:
                time.sleep(1)
                # Проверяем что клиент ещё жив
                try:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                except Exception:
                    break
        except Exception:
            pass
        finally:
            STATE.remove_sse_client(self.wfile)

    def _api_session_start(self) -> None:
        with STATE.lock:
            if STATE.status == "running":
                self._send_json({"ok": False, "error": "Сессия уже выполняется"}, 409)
                return
            STATE.status = "running"
            STATE.next_start_time = None
            STATE.next_start_delay_seconds = None

        STATE.broadcast("status", {
            "status": "running",
            "next_start_time": None,
            "next_start_delay_seconds": None,
            "message": "Запуск сессии...",
        })

        # Запускаем в отдельном потоке, чтобы не блокировать ответ
        def run_and_report():
            success, output = run_session_transaction(lambda line: STATE.broadcast("session_log", {"line": line}))
            with STATE.lock:
                STATE.session_count += 1
                STATE.last_run_time = time.strftime("%Y-%m-%d %H:%M:%S")
                if not success:
                    STATE.last_error = output[-500:] if len(output) > 500 else output
                if not STATE.auto_enabled:
                    STATE.status = "idle"
                else:
                    STATE.status = "auto"

            last_session = read_last_session()
            with STATE.lock:
                session_count = STATE.session_count
                last_run_time = STATE.last_run_time
                last_error = STATE.last_error
                next_start_time = STATE.next_start_time
                next_start_delay_seconds = STATE.next_start_delay_seconds

            STATE.broadcast("session_done", {
                "success": success,
                "count": session_count,
                "time": last_run_time,
                "last_session": last_session,
                "error": last_error if not success else "",
                "next_start_time": next_start_time,
                "next_start_delay_seconds": next_start_delay_seconds,
            })

            # Отправить обновлённый контекст через SSE
            ctx_data = collect_context_analysis()
            STATE.broadcast("context_update", ctx_data)

        t = threading.Thread(target=run_and_report, daemon=True)
        t.start()

        self._send_json({"ok": True, "message": "Сессия запущена"})

    def _api_auto_toggle(self) -> None:
        with STATE.lock:
            STATE.auto_enabled = not STATE.auto_enabled
            enabled = STATE.auto_enabled

            if enabled:
                STATE.status = "auto"
                STATE.next_start_time = None
                STATE.next_start_delay_seconds = None
                # Запускаем цикл автосессий
                if STATE.auto_thread is None or not STATE.auto_thread.is_alive():
                    STATE.auto_thread = threading.Thread(target=auto_session_loop, daemon=True)
                    STATE.auto_thread.start()
            else:
                STATE.next_start_time = None
                STATE.next_start_delay_seconds = None

            next_start_time = STATE.next_start_time
            next_start_delay_seconds = STATE.next_start_delay_seconds

        STATE.broadcast("status", {
            "status": "auto" if enabled else "idle",
            "auto_enabled": enabled,
            "next_start_time": next_start_time,
            "next_start_delay_seconds": next_start_delay_seconds,
            "message": "Автосессия " + ("включена" if enabled else "выключена"),
        })

        self._send_json({"ok": True, "auto_enabled": enabled})

def create_server(host: str, port: int) -> ThreadingHTTPServer:
    """Создать многопоточный HTTP-сервер, чтобы SSE не блокировал API."""
    return ThreadingHTTPServer((host, port), SessionHandler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Сервер управления сессиями ai-lives")
    parser.add_argument("--port", type=int, default=11000, help="Порт (по умолчанию 11000)")
    parser.add_argument("--host", default="127.0.0.1", help="Хост (по умолчанию 127.0.0.1)")
    args = parser.parse_args()

    server = create_server(args.host, args.port)
    print(f"[server] Запущен на http://{args.host}:{args.port}")
    print(f"[server] Корень проекта: {PROJECT_ROOT}")
    print(f"[server] Ctrl+C для остановки")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] Остановка...")
        with STATE.lock:
            STATE.auto_enabled = False
        server.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
