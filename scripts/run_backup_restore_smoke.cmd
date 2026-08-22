@echo off
setlocal EnableExtensions
set "RUNNER=%~dp0run_backup_restore_smoke.ps1"

if not exist "%RUNNER%" (
  echo [SMAI Analytics] Backup restore smoke runner was not found.
  exit /b 1
)

%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%RUNNER%"
exit /b %ERRORLEVEL%
