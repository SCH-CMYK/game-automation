@echo off
title GameAuto Setup
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ========================================
echo    GameAuto — 一键安装
echo ========================================
echo.

:: ===========================================
:: 1. 管理员权限检查
:: ===========================================
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 需要管理员权限！
    echo.
    echo 请右键 setup.bat → "以管理员身份运行"
    echo 或者以管理员身份打开终端后运行此脚本
    echo.
    pause
    exit /b 1
)
echo [OK] 管理员权限
echo.

:: ===========================================
:: 2. Python 检查
:: ===========================================
set PYTHON=
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 未找到 Python！
    echo.
    echo 请安装 Python 3.10+ ： https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER%
python --version

:: 检查版本 >= 3.10
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set MAJOR=%%a
    set MINOR=%%b
)
if %MAJOR% LSS 3 (
    echo [ERROR] Python 版本太旧，需要 3.10+
    pause
    exit /b 1
)
if %MAJOR% EQU 3 if %MINOR% LSS 10 (
    echo [ERROR] Python 版本需要 3.10+，当前 %PYVER%
    pause
    exit /b 1
)
echo.

:: ===========================================
:: 3. 虚拟环境
:: ===========================================
if not exist ".venv\" (
    echo [3/5] 创建虚拟环境 ...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [OK] 虚拟环境已创建
) else (
    echo [SKIP] 虚拟环境已存在
)

:: 激活虚拟环境
call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [ERROR] 激活虚拟环境失败
    pause
    exit /b 1
)
echo [OK] 虚拟环境已激活
echo.

:: ===========================================
:: 4. 安装 Python 依赖
:: ===========================================
echo [4/5] 安装 Python 依赖 ...
python -m pip install --upgrade pip -q
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] 依赖安装失败
    echo.
    echo 常见问题：
    echo   1. PyTorch 安装失败 → 手动安装：pip install torch --index-url https://download.pytorch.org/whl/cu121
    echo   2. interception-python 需要 Visual C++ Build Tools
    echo   3. 检查网络连接
    pause
    exit /b 1
)
echo [OK] 依赖安装完成
echo.

:: ===========================================
:: 5. 下载模型文件
:: ===========================================
echo [5/5] 下载模型和地图文件 ...
python download_models.py
if %errorlevel% neq 0 (
    echo [WARN] 部分模型下载失败，请手动下载
    echo.
    echo 下载地址：
    echo   https://github.com/SCH-CMYK/game-automation/releases/tag/v1.0
    echo.
    echo 下载后放入：
    echo   models\  → best_20260601.pt, loftr_model.onnx
    echo   maps\    → big_map.png
)
echo.

:: ===========================================
:: 6. Interception 驱动检查
:: ===========================================
echo ========================================
echo    Interception 驱动检查
echo ========================================
echo.

sc query interception >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Interception 驱动已安装并运行
) else (
    echo [WARN] Interception 驱动未安装！
    echo.
    echo 这是控制键鼠所必需的内核驱动。安装步骤：
    echo.
    echo   1. 下载: https://github.com/oblitum/Interception/releases/latest
    echo   2. 解压，管理员 cmd 进入目录
    echo   3. 执行: install-interception.exe /install
    echo   4. 重启电脑
    echo.
    echo 安装后运行: sc query interception  应显示 RUNNING
)
echo.

:: ===========================================
:: 检查结果汇总
:: ===========================================
echo ========================================
echo    安装完成！
echo ========================================
echo.
echo 下一步：
echo   run.bat           → 进入图形界面
echo   python main.py    → 启动程序
echo.
echo 如果缺少模型文件，运行：
echo   python download_models.py
echo.
pause
