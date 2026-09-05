@echo off
REM מפעיל את Vertex: Orchestrator (Python) ואז UI Shell (Electron).
REM לא פותח את תיקיית ההתקנה עצמה — רק את חלון הצ'אט (§10).

setlocal
set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..

echo מפעיל Vertex Orchestrator...
start "Vertex Orchestrator" /min "%ROOT_DIR%\venv\Scripts\python.exe" -m uvicorn core.main:app --host 127.0.0.1 --port 8420 --app-dir "%ROOT_DIR%"

timeout /t 2 /nobreak >nul

echo מפעיל ממשק Vertex...
cd /d "%ROOT_DIR%\ui_shell"
call npm start

endlocal
