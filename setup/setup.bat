@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ================================
REM SMAI Server Analytics Setup
REM ================================

set "SCRIPT_DIR=%~dp0"
set "REPO_ROOT=%SCRIPT_DIR%\.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"
set "VENV_NAME=venv_SMAI_Analytics"
set "VENV_DIR=%REPO_ROOT%\%VENV_NAME%"
set "REQ_RUNTIME=%SCRIPT_DIR%\requirements.txt"
set "REQ_DEV=%SCRIPT_DIR%\requirements-dev.txt"

if "%~1"=="/?" goto :help
if /I "%~1"=="--help" goto :help
if not "%~1"=="" (
    echo [ERROR] Unknown argument: %~1
    goto :help_error
)

if not exist "%REQ_RUNTIME%" (
    echo [ERROR] Runtime requirements were not found: %REQ_RUNTIME%
    exit /b 1
)
if not exist "%REQ_DEV%" (
    echo [ERROR] Development requirements were not found: %REQ_DEV%
    exit /b 1
)

set "PYCMD="
where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYCMD=py -3.12"
    if not defined PYCMD (
        py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>&1
        if not errorlevel 1 set "PYCMD=py -3.11"
    )
)
if not defined PYCMD (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)" >nul 2>&1
        if not errorlevel 1 set "PYCMD=python"
    )
)
if not defined PYCMD (
    echo [ERROR] Python 3.11 or 3.12 was not found. Install Python and reopen the terminal.
    exit /b 1
)

echo [0/5] Repo root: %REPO_ROOT%
echo       Using: %PYCMD%

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [1/5] Creating virtual environment: %VENV_DIR%
    %PYCMD% -m venv "%VENV_DIR%" || (echo [ERROR] Virtual environment creation failed & exit /b 1)
) else (
    echo [1/5] Reusing existing virtual environment: %VENV_DIR%
)

call "%VENV_DIR%\Scripts\activate.bat" || (echo [ERROR] Virtual environment activation failed & exit /b 1)

echo [2/5] Upgrading pip...
python -m pip install --upgrade pip || (echo [ERROR] pip upgrade failed & exit /b 1)

echo [3/5] Installing runtime and development dependencies from setup\...
python -m pip install -r "%REQ_RUNTIME%" -r "%REQ_DEV%" || (echo [ERROR] Dependency installation failed & exit /b 1)

echo [4/5] Verifying installed tools...
python -c "import PIL, streamlit; print('Pillow', PIL.__version__); print('Streamlit', streamlit.__version__)" || (echo [ERROR] Runtime dependency verification failed & exit /b 1)
python -m pytest --version || (echo [ERROR] pytest verification failed & exit /b 1)
python -m ruff --version || (echo [ERROR] ruff verification failed & exit /b 1)

echo [5/5] Setup finished successfully.
echo.
echo Web console:    run_analytics_web.bat
echo Activate later: %VENV_DIR%\Scripts\Activate.ps1
exit /b 0

:help
echo Usage: setup\setup.bat
echo.
echo Creates or updates %VENV_NAME% and installs setup\requirements.txt and setup\requirements-dev.txt.
echo The existing virtual environment is reused; this script never deletes it.
exit /b 0

:help_error
exit /b 1
