@echo off
setlocal
cd /d "%~dp0"
set "SMAI_RUNTIME_ROOT=C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"
python retention.py
