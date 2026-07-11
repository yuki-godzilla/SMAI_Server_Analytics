@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "SMAI_PROJECT_ROOT=C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"
set "SMAI_RUNTIME_ROOT=C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"
set "SMAI_PYTHON_LAUNCHER=%LocalAppData%\Programs\Python\Launcher\py.exe"

if exist "%SMAI_PYTHON_LAUNCHER%" (
    "%SMAI_PYTHON_LAUNCHER%" -3.12 -c "import tkinter" >nul 2>&1
    if not errorlevel 1 (
        "%SMAI_PYTHON_LAUNCHER%" -3.12 "%~dp0dashboard.py"
        exit /b !errorlevel!
    )
)

python "%~dp0dashboard.py"
