@echo off
cd /d "%~dp0.."
if not exist logs mkdir logs
".venv\Scripts\python.exe" -m uvicorn spectra.web.server:app --host 127.0.0.1 --port 8081 --log-level info 1>logs\backend.out.log 2>logs\backend.err.log
echo backend exited with %errorlevel%>>logs\backend.err.log
timeout /t 60 >nul
