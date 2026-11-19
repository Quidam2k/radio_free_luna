@echo off
REM #3840: retired. The legacy RFL supervisor window (#6914) is replaced by the
REM service supervisor, which keeps the station up (auto_restart) in one
REM window. scripts\rfl_supervisor.py is kept on disk but nothing launches it.
echo Radio Free Luna is supervised by the service supervisor now.
echo Log: see the supervisor's services log folder (rfl.log).
pause
