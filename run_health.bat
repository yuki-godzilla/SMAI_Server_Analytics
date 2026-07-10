@echo off
setlocal
cd /d "%~dp0"
set "SMAI_PROJECT_ROOT=C:\Users\user\workspace\Smart_Market_AI"
set "SMAI_RUNTIME_ROOT=C:\Users\user\workspace\SMAI_Server_Runtime"
python health.py

