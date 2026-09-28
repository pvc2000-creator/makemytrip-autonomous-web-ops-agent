@echo off
REM Wipes local run history, snapshots and frames (keeps your settings). Stop the server first.
cd /d "%~dp0"
del /q webops.db webops.db-shm webops.db-wal 2>nul
rmdir /s /q data\runtime_snapshots 2>nul
echo Local data reset.
pause
