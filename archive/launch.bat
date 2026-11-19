@echo off
REM #3840: Radio Free Luna runs under a service supervisor (one window,
REM log in the supervisor's services log folder). This bat used to open its own
REM window and kill whatever held :8080, which cut the supervised stream.
echo Radio Free Luna runs under a service supervisor.
echo Start or restart it from Mission Control (its restart button) or the persona wake tool.
echo Log: see the supervisor's services log folder (rfl.log).
pause
