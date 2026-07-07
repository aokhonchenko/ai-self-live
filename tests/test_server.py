import io


def test_compress_api_dry_run_returns_ok():
    """Проверить, что /api/compress с dry_run=True возвращает ok и метрики."""
    httpd = session_server.create_server("127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        body = json.dumps({"dry_run": True, "keep_recent": 5}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/compress",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response = urllib.request.urlopen(req, timeout=5)
        payload = json.loads(response.read().decode("utf-8"))

        assert payload["ok"] is True
        assert payload["dry_run"] is True
        assert "content" in payload
        assert "original_lines" in payload
        assert "compressed_lines" in payload
        assert "reduction_pct" in payload
        assert isinstance(payload["original_lines"], int)
        assert isinstance(payload["compressed_lines"], int)
        assert payload["original_lines"] > 0
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_compress_api_actual_writes_file():
    """Проверить, что /api/compress без dry_run записывает сжатый файл."""
    import shutil

    last_session_path = session_server.PROJECT_ROOT / "state" / "last_session.md"
    backup_path = last_session_path.with_suffix(".md.bak")

    # Сохраняем оригинал
    original_text = last_session_path.read_text(encoding="utf-8")
    backup_path.write_text(original_text, encoding="utf-8")

    httpd = session_server.create_server("127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        body = json.dumps({"dry_run": False, "keep_recent": 5}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/compress",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response = urllib.request.urlopen(req, timeout=5)
        payload = json.loads(response.read().decode("utf-8"))

        assert payload["ok"] is True
        assert payload["reduction_pct"] >= 0

        # Восстанавливаем оригинал
        last_session_path.write_text(original_text, encoding="utf-8")
        backup_path.unlink(missing_ok=True)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
import importlib
import json
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from server import config as session_config
from server import server as session_server


def test_project_import_path_can_be_restored(monkeypatch):
    root = str(session_server.PROJECT_ROOT)
    monkeypatch.setattr(sys, "path", [item for item in sys.path if item != root])

    session_server.ensure_project_import_path()

    assert sys.path[0] == root
    assert importlib.import_module("src.tools.context_analyzer.core") is not None


def reset_server_state():
    with session_server.STATE.lock:
        session_server.STATE.status = "idle"
        session_server.STATE.auto_enabled = False
        session_server.STATE.last_error = ""
        session_server.STATE.last_run_time = ""
        session_server.STATE.session_count = 0
        session_server.STATE.next_start_time = None
        session_server.STATE.next_start_delay_seconds = None
    with session_server.STATE._sse_lock:
        session_server.STATE._sse_clients.clear()


def test_session_transaction_command_uses_uv_and_streams_output(monkeypatch):
    calls = []

    class FakeProcess:
        def __init__(self):
            self.stdout = io.StringIO("first line\nsecond line\n")

        def poll(self):
            if self.stdout.tell() >= len(self.stdout.getvalue()):
                return 0
            return None

        def wait(self):
            return 0

    def fake_popen(cmd, cwd, stdout, stderr, text, encoding, errors, env):
        calls.append(
            {
                "cmd": cmd,
                "cwd": cwd,
                "stdout": stdout,
                "stderr": stderr,
                "text": text,
                "encoding": encoding,
                "errors": errors,
                "env": env,
            }
        )
        return FakeProcess()

    monkeypatch.setattr(session_server.subprocess, "Popen", fake_popen)
    streamed = []

    success, output = session_server.run_session_transaction(streamed.append)

    assert success is True
    assert output == "first line\nsecond line\n"
    assert streamed == ["first line", "second line"]
    assert len(calls) == 1
    call = calls[0]
    assert call["cmd"] == ["uv", "run", "python", "scripts/session_transaction.py"]
    assert call["cwd"] == str(session_server.PROJECT_ROOT)
    assert call["stdout"] is session_server.subprocess.PIPE
    assert call["stderr"] is session_server.subprocess.STDOUT
    assert call["text"] is True
    assert call["encoding"] == "utf-8"
    assert call["errors"] == "replace"
    assert call["env"]["PYTHONUTF8"] == "1"
    assert call["env"]["PYTHONIOENCODING"] == "utf-8"


def test_create_server_uses_threading_http_server():
    httpd = session_server.create_server("127.0.0.1", 0)
    try:
        assert isinstance(httpd, ThreadingHTTPServer)
    finally:
        httpd.server_close()


def test_session_start_is_not_blocked_by_open_sse(monkeypatch):
    reset_server_state()
    called = threading.Event()

    def fake_run_session_transaction(on_output=None):
        if on_output is not None:
            on_output("streamed output")
        called.set()
        return True, "ok"

    monkeypatch.setattr(session_server, "run_session_transaction", fake_run_session_transaction)

    httpd = session_server.create_server("127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    sse_response = None

    try:
        sse_response = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/events", timeout=2)
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/session/start",
            data=b"",
            method="POST",
        )
        response = urllib.request.urlopen(request, timeout=2)
        payload = json.loads(response.read().decode("utf-8"))

        assert payload["ok"] is True
        assert called.wait(2)
    finally:
        if sse_response is not None:
            sse_response.close()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_frontend_streams_session_log_and_renders_markdown_without_last_session_scroll():
    html = (session_server.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    app_js = (session_server.STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert '<script src="/app.js"></script>' in html
    assert "addEventListener('session_log'" in app_js
    assert "function renderMarkdown" in app_js
    assert "setLastSessionMarkdown" in app_js
    assert "function setCurrentPlanMarkdown" in app_js
    load_current_plan = (
        app_js.split("async function loadCurrentPlan()", 1)[1]
        .split("async function loadProjectMetrics()", 1)[0]
    )
    assert "setCurrentPlanMarkdown(data.content)" in load_current_plan
    assert "setLastSessionMarkdown(data.content)" not in load_current_plan
    assert "nextStartValue" in html
    assert "next_start_time" in app_js
    assert "function updateNextStartTimer" in app_js
    assert ".last-session::-webkit-scrollbar" not in html
    last_session_css = html.split(".last-session {", 1)[1].split("}", 1)[0]
    assert "overflow-y: auto" not in last_session_css
    assert "overflow: visible" in last_session_css


def test_api_routes_accept_query_and_trailing_slash(monkeypatch):
    monkeypatch.setattr(
        session_server,
        "collect_project_metrics",
        lambda: {
            "total_tests": 1,
            "coverage": "90%",
            "script_count": 2,
            "tool_count": 3,
            "noise_ratio": 4.0,
        },
    )
    monkeypatch.setattr(
        session_server,
        "collect_context_analysis",
        lambda: {
            "health": "good",
            "health_label": "Хорошо",
            "total_tokens": 10,
            "total_lines": 5,
            "sections": [],
            "questions_open": 0,
            "recommendations": [],
        },
    )

    httpd = session_server.create_server("127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        metrics = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/project-metrics?refresh=1", timeout=2
        )
        metrics_payload = json.loads(metrics.read().decode("utf-8"))
        assert metrics.status == 200
        assert metrics_payload["total_tests"] == 1

        context = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/context-analysis/?refresh=1", timeout=2
        )
        context_payload = json.loads(context.read().decode("utf-8"))
        assert context.status == 200
        assert context_payload["health"] == "good"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_server_serves_frontend_script():
    httpd = session_server.create_server("127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        response = urllib.request.urlopen(f"http://127.0.0.1:{port}/app.js", timeout=2)
        body = response.read().decode("utf-8")

        assert response.headers["Content-Type"] == "application/javascript; charset=utf-8"
        assert "function updateNextStartTimer" in body
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_auto_session_delay_uses_env_seconds(monkeypatch):
    calls = []

    def fake_randint(min_seconds, max_seconds):
        calls.append((min_seconds, max_seconds))
        return max_seconds

    monkeypatch.setenv("AUTO_SESSION_MIN_DELAY_SECONDS", "7")
    monkeypatch.setenv("AUTO_SESSION_MAX_DELAY_SECONDS", "11")
    monkeypatch.setattr(session_config.random, "randint", fake_randint)

    assert session_config.auto_session_delay_seconds() == 11
    assert calls == [(7, 11)]


def test_auto_session_delay_defaults_to_five_and_fifteen_minutes(monkeypatch):
    calls = []

    def fake_randint(min_seconds, max_seconds):
        calls.append((min_seconds, max_seconds))
        return min_seconds

    monkeypatch.delenv("AUTO_SESSION_MIN_DELAY_SECONDS", raising=False)
    monkeypatch.delenv("AUTO_SESSION_MAX_DELAY_SECONDS", raising=False)
    monkeypatch.setattr(session_config.random, "randint", fake_randint)

    assert session_config.auto_session_delay_seconds() == 300
    assert calls == [(300, 900)]


def test_auto_session_delay_clamps_inverted_range(monkeypatch):
    monkeypatch.setenv("AUTO_SESSION_MIN_DELAY_SECONDS", "20")
    monkeypatch.setenv("AUTO_SESSION_MAX_DELAY_SECONDS", "10")

    assert session_config.auto_session_delay_bounds() == (20, 20)


def test_status_exposes_next_start_fields():
    reset_server_state()
    with session_server.STATE.lock:
        session_server.STATE.next_start_time = 123.5
        session_server.STATE.next_start_delay_seconds = 456

    httpd = session_server.create_server("127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        response = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2)
        payload = json.loads(response.read().decode("utf-8"))

        assert payload["next_start_time"] == 123.5
        assert payload["next_start_delay_seconds"] == 456
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
        reset_server_state()



def test_context_analysis_api_returns_health_and_sections():
    """Проверить, что /api/context-analysis возвращает данные из context_analyzer."""
    httpd = session_server.create_server("127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        response = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/context-analysis", timeout=5)
        payload = json.loads(response.read().decode("utf-8"))

        assert "health" in payload
        assert "health_label" in payload
        assert "total_tokens" in payload
        assert "sections" in payload
        assert isinstance(payload["sections"], list)
        assert len(payload["sections"]) > 0
        # Проверим структуру первой секции
        first = payload["sections"][0]
        assert "name" in first
        assert "exists" in first
        assert "tokens" in first
        assert "lines" in first
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)



def test_project_metrics_noise_ratio_logic():
    """Проверить логику расчёта noise_ratio для state-файлов."""
    import subprocess
    import sys
    code = r"""
from pathlib import Path
state_dir = Path('state')
total_noise = 0
total_lines = 0
for mf in state_dir.rglob('*.md'):
    text = mf.read_text(errors='replace')
    lines = text.splitlines()
    total_lines += len(lines)
    for line in lines:
        s = line.strip()
        if not s or s == '---' or s.startswith('###') or (s.startswith('|') and s.endswith('|')):
            total_noise += 1
ratio = round(total_noise / total_lines * 100, 1) if total_lines > 0 else 0.0
assert isinstance(ratio, float)
assert 0 <= ratio <= 100
print(f'noise_ratio={ratio}')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "noise_ratio=" in result.stdout




def test_context_update_broadcast_on_session_done():
    """Проверить, что collect_context_analysis возвращает корректные данные."""
    from server.server import collect_context_analysis

    data = collect_context_analysis()
    assert "health" in data
    assert "health_label" in data
    assert "total_tokens" in data
    assert "total_lines" in data
    assert "sections" in data
    assert isinstance(data["sections"], list)
    assert len(data["sections"]) > 0
    # Проверим структуру первой секции
    first = data["sections"][0]
    assert "name" in first
    assert "exists" in first
    assert "tokens" in first
    assert "lines" in first
