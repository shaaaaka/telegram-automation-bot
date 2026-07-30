@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Python не знайдено. Встанови Python 3.x i додай в PATH.
    pause
    exit /b 1
)

python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt

echo.
echo Готово. Тепер запускай start.bat
pause
