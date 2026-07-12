@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "SMAI_PROJECT_ROOT=C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"
set "SMAI_RUNTIME_ROOT=C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"
set "SMAI_ANALYTICS_PYTHON=%~dp0venv_SMAI_Analytics\Scripts\python.exe"
set "SMAI_COMPATIBILITY_PYTHON=%SMAI_PROJECT_ROOT%\venv_SMAI\Scripts\python.exe"
set "SMAI_ANALYTICS_PORT=8502"

if not exist "%SMAI_ANALYTICS_PYTHON%" (
    if exist "%SMAI_COMPATIBILITY_PYTHON%" (
        echo [SMAI Analytics] Analytics venv was not found; using SMAI venv_SMAI for compatibility.
        set "SMAI_ANALYTICS_PYTHON=%SMAI_COMPATIBILITY_PYTHON%"
    ) else (
        echo [SMAI Analytics] Streamlit-enabled Python was not found:
        echo                  %SMAI_ANALYTICS_PYTHON%
        echo [SMAI Analytics] Run setup\setup.bat before starting the web console.
        exit /b 1
    )
)

set "SMAI_ANALYTICS_LAN_IP="
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "Get-NetIPConfiguration -ErrorAction SilentlyContinue ^| Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.IPv4Address -ne $null } ^| Select-Object -First 1 -ExpandProperty IPv4Address ^| Select-Object -ExpandProperty IPAddress" 2^>nul`) do set "SMAI_ANALYTICS_LAN_IP=%%I"

if "%SMAI_ANALYTICS_LAN_IP%"=="" set "SMAI_ANALYTICS_LAN_IP=localhost"

echo [SMAI Analytics] Starting the read-only web console on private LAN port %SMAI_ANALYTICS_PORT%.
echo [SMAI Analytics] This PC: http://localhost:%SMAI_ANALYTICS_PORT%
echo [SMAI Analytics] Trusted LAN devices: http://%SMAI_ANALYTICS_LAN_IP%:%SMAI_ANALYTICS_PORT%
echo [SMAI Analytics] Do not expose this port to the Internet.
echo.

"%SMAI_ANALYTICS_PYTHON%" -m streamlit run "%~dp0analytics_web.py" ^
  --server.address 0.0.0.0 ^
  --server.port %SMAI_ANALYTICS_PORT% ^
  --server.headless true ^
  --server.runOnSave false ^
  --server.enableXsrfProtection true ^
  --browser.gatherUsageStats false ^
  --browser.serverAddress %SMAI_ANALYTICS_LAN_IP%

exit /b %ERRORLEVEL%
