@echo off
title Verification Bot & Admin Panel
cd /d "%~dp0"
echo ===================================================
echo   Starting Verification Bot and Web Admin Panel...
echo ===================================================
echo.

if not exist .venv (
    echo Error: Virtual environment (.venv) not found!
    echo Please make sure you are running this in the project root directory.
    pause
    exit /b
)

call .venv\Scripts\activate.bat
python main.py
pause
