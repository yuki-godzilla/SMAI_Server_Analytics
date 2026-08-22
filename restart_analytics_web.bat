@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\restart_analytics_web.ps1"
exit /b %ERRORLEVEL%
