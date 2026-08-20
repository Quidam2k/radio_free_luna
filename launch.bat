@echo off
REM Launch the Radio Free Luna server. Close this window to stop.
cd /d "%~dp0"

REM Kill anything already listening on port 8080 (taskkill /T kills the whole process tree)
for /f "tokens=5" %%p in ('netstat -aon ^| findstr "LISTENING" ^| findstr ":8080 "') do (
    echo Killing process tree rooted at PID %%p
    taskkill /F /T /PID %%p >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo Starting Radio Free Luna server on http://0.0.0.0:8080 ...
echo.
python main.py
echo.
echo Server stopped.
pause
