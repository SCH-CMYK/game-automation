@echo off
chcp 65001 >nul
title GameAuto
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process -FilePath 'python.exe' -ArgumentList 'main.py' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)
python main.py
pause
