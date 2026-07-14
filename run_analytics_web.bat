@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "SMAI_PROJECT_ROOT=C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"
set "SMAI_RUNTIME_ROOT=C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"
set "SMAI_ANALYTICS_PYTHON=%~dp0venv_SMAI_Analytics\Scripts\python.exe"
set "SMAI_COMPATIBILITY_PYTHON=%SMAI_PROJECT_ROOT%\venv_SMAI\Scripts\python.exe"

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

set "SMAI_SERVER_ANALYTICS_URL="
set "SMAI_LOCAL_ANALYTICS_URL="
for /f "delims=" %%I in ('"%SMAI_ANALYTICS_PYTHON%" -m smai_analytics.network --emit-batch') do %%I

if not defined SMAI_SERVER_ANALYTICS_URL (
    echo [SMAI Server Analytics] MagicDNS URL settings could not be loaded.
    echo [SMAI Server Analytics] Check config\network.json or SMAI_TAILSCALE_HOSTNAME.
    exit /b 2
)

echo [SMAI Server Analytics] Starting the read-only web console.
echo [SMAI Server Analytics] Server Analytics: %SMAI_SERVER_ANALYTICS_URL%
echo [SMAI Server Analytics] Server-local check: %SMAI_LOCAL_ANALYTICS_URL%
echo [SMAI Server Analytics] Start Tailscale on the connecting device before opening the Server Analytics URL.
echo [SMAI Server Analytics] Listening on 0.0.0.0:%SMAI_ANALYTICS_PORT% ^(bind address; do not open 0.0.0.0 in a browser^)
echo [SMAI Server Analytics] Do not expose this port to the Internet.
echo.

"%SMAI_ANALYTICS_PYTHON%" -m streamlit run "%~dp0analytics_web.py" ^
  --server.address 0.0.0.0 ^
  --server.port %SMAI_ANALYTICS_PORT% ^
  --server.headless true ^
  --server.runOnSave false ^
  --server.enableXsrfProtection true ^
  --browser.gatherUsageStats false ^
  --browser.serverAddress localhost

exit /b %ERRORLEVEL%
