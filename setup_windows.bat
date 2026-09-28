@echo off
REM One-time setup for Windows 10/11. Needs Python 3.10+ from python.org (tick "Add python.exe to PATH").
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py -3
if "%PY%"=="" set PY=python
echo [1/4] Creating virtual environment...
%PY% -m venv .venv || goto :err
echo [2/4] Installing Python packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :err
echo [3/4] Installing the Chromium browser used by the agent...
".venv\Scripts\python.exe" -m playwright install chromium || goto :err
echo [4/4] Creating .env...
if not exist .env copy .env.example .env >nul
echo.
echo Setup complete. Double-click start_windows.bat to launch.
pause
exit /b 0
:err
echo.
echo Setup failed. Read the message above; the most common fix is installing Python 3.10+ from python.org.
pause
exit /b 1
