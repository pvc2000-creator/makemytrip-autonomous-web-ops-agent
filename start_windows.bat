@echo off
REM Starts the Web Ops Agent and opens the console in your browser.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup_windows.bat first.
  pause
  exit /b 1
)
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo Starting on http://127.0.0.1:8000  (close this window to stop)
start "" /min cmd /c "ping -n 4 127.0.0.1 >nul & start http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
pause
