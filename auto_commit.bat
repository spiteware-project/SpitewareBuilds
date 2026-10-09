@echo off
setlocal
REM Preview only unless --publish --approved-manifest FILE is explicitly supplied.
REM Publishing is restricted to the five reviewed artifacts on main.
py -3 "%~dp0artifacts.py" publish %*
exit /b %errorlevel%
