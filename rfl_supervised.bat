@echo off
REM #3840: retired. The legacy RFL supervisor window (#6914) is replaced by the
REM Pantheon Service Supervisor, which keeps the station up (auto_restart) in one
REM window. scripts\rfl_supervisor.py is kept on disk but nothing launches it.
echo Radio Free Luna is supervised by the Pantheon Service Supervisor now.
echo Log: Q:\Pantheon\data\logs\services\rfl.log
pause
