@echo off
REM server.bat - start ai-lives session server
REM Default port: 11000
REM Usage: server.bat [port]

setlocal

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
chcp 65001 >nul

set "PORT=11000"
if not "%~1"=="" set "PORT=%~1"

echo [server.bat] Starting server on port %PORT%...
echo [server.bat] Open http://127.0.0.1:%PORT% in browser
echo [server.bat] Press Ctrl+C to stop
echo.

cd /d "%~dp0"
uv run python "server\server.py" --port "%PORT%"

endlocal
