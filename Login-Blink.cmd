@echo off
setlocal
cd /d "%~dp0"
set "BLINK_STATE=%~dp0data\auth.json"
set "BLINK_CREDENTIALS_FILE=%~dp0data\credentials.json"
"%~dp0.venv\Scripts\python.exe" "%~dp0bridge\app.py" auth
pause
