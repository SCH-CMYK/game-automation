@echo off
title GameAuto Setup
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ========================================
echo    GameAuto - One-Click Setup
echo ========================================
echo.

:: ===========================================
:: 1. Admin check
:: ===========================================
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Administrator privileges required!
    echo.
    echo Please right-click setup.bat -^> "Run as Administrator"
    echo.
    pause
    exit /b 1
)
echo [OK] Administrator
echo.

:: ===========================================
:: 2. Python check
:: ===========================================
set PYTHON=
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found!
    echo.
    echo Install Python 3.10+ from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER%

:: Check version >= 3.10
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set MAJOR=%%a
    set MINOR=%%b
)
if %MAJOR% LSS 3 (
    echo [ERROR] Python version too old, need 3.10+
    pause
    exit /b 1
)
if %MAJOR% EQU 3 if %MINOR% LSS 10 (
    echo [ERROR] Python version need 3.10+, current is %PYVER%
    pause
    exit /b 1
)
echo.

:: ===========================================
:: 3. Virtual environment
:: ===========================================
if not exist ".venv\" (
    echo [3/5] Creating virtual environment ...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
) else (
    echo [SKIP] Virtual environment already exists
)

call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment activated
echo.

:: ===========================================
:: 4. Install dependencies (use mirror for faster downloads in China)
:: ===========================================
echo [4/5] Installing Python dependencies ...

:: Configure pip mirror for faster downloads
python -m pip config --site set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple 2>nul
python -m pip config --site set global.trusted-host pypi.tuna.tsinghua.edu.cn 2>nul

python -m pip install --upgrade pip -q --default-timeout=120
pip install -r requirements.txt --default-timeout=120
if %errorlevel% neq 0 (
    echo [ERROR] Dependency installation failed
    echo.
    echo Common issues:
    echo   1. PyTorch install failed: pip install torch --index-url https://download.pytorch.org/whl/cu121
    echo   2. interception-python needs Visual C++ Build Tools
    echo   3. Check network connection
    pause
    exit /b 1
)
echo [OK] Dependencies installed
echo.

:: ===========================================
:: 5. Download model files
:: ===========================================
echo [5/5] Downloading model and map files ...
python download_models.py
if %errorlevel% neq 0 (
    echo [WARN] Some model downloads failed
    echo.
    echo Download URLs:
    echo   https://github.com/SCH-CMYK/game-automation/releases/tag/v1.0
    echo.
    echo Place downloaded files in:
    echo   models\  -- best_20260601.pt, loftr_model.onnx
    echo   maps\    -- big_map.png
)
echo.

:: ===========================================
:: 6. Interception driver check
:: ===========================================
echo ========================================
echo    Interception Driver Check
echo ========================================
echo.

sc query interception >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Interception driver is running
) else (
    echo [WARN] Interception driver NOT installed!
    echo.
    echo This kernel driver is required for keyboard/mouse control.
    echo Installation steps:
    echo.
    echo   1. Download: https://github.com/oblitum/Interception/releases/latest
    echo   2. Extract, open cmd as Administrator in that folder
    echo   3. Run: install-interception.exe /install
    echo   4. Restart your computer
    echo.
    echo Verify: sc query interception should show RUNNING
)
echo.

:: ===========================================
:: Summary
:: ===========================================
echo ========================================
echo    Setup Complete!
echo ========================================
echo.
echo Next steps:
echo   run.bat           Launch GUI
echo   python main.py    Start program
echo.
echo If model files are missing:
echo   python download_models.py
echo.
pause
