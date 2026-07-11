@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\restart_dashboard.ps1"
exit /b %ERRORLEVEL%
