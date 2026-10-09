@echo off
setlocal
REM Preview by default. --apply requires an independently reviewed --approved-manifest.
py -3 "%~dp0artifacts.py" refresh %*
exit /b %errorlevel%

