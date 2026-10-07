@echo off
REM #3840: Radio Free Luna runs under the Pantheon Service Supervisor (one window,
REM log at Q:\Pantheon\data\logs\services\rfl.log). This bat used to open its own
REM window and kill whatever held :8080, which cut the supervised stream.
echo Radio Free Luna runs under the Pantheon Service Supervisor.
echo Start or restart it from Mission Control (its restart button) or the persona wake tool.
echo Log: Q:\Pantheon\data\logs\services\rfl.log
pause
