@echo off
title GameAuto Setup
cd /d "%~dp0"

echo ========================================
echo    GameAuto - Setup
echo ========================================
echo.

:: Check admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Please run as Administrator!
    echo Right-click setup.bat - Run as Administrator
    pause
    exit /b 1
)

:: Check Python
echo [1/3] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo.

:: Upgrade pip
echo [2/3] Upgrading pip...
python -m pip install --upgrade pip
echo.

:: Install deps
echo [3/3] Installing dependencies...
pip install -r requirements.txt
echo.

:: Check model files
echo ========================================
echo    Checking files
echo ========================================
if not exist "models\loftr_model.onnx" (
    echo [WARN] Missing models\loftr_model.onnx
)
if not exist "models\best_20260601.pt" (
    echo [WARN] Missing models\best_20260601.pt
)
if not exist "maps\big_map.png" (
    echo [WARN] Missing maps\big_map.png
)
echo.

echo ========================================
echo    Setup complete!
echo ========================================
echo.
echo Double-click run.bat to start
echo.
pause
