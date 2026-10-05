@echo off
REM Radio Free Luna supervisor (#6914). Keeps the station up; started minimized at logon
REM by the "RadioFreeLuna" scheduled task. Close this window to stop supervising
REM (the server keeps running). Logs: logs\supervisor.log, logs\rfl_server.out.log
title Radio Free Luna supervisor
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\rfl_supervisor.py
