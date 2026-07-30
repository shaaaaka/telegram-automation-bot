@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe scripts\kill_port_8000.py
    .venv\Scripts\python.exe main.py
) else if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe scripts\kill_port_8000.py
    venv\Scripts\python.exe main.py
) else (
    python scripts\kill_port_8000.py
    python main.py
)

pause
