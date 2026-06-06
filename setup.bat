@echo off
chcp 65001 >nul
title GameAuto 一键配置安装

echo ========================================
echo    GameAuto 一键配置安装
echo ========================================
echo.

:: 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [警告] 请以管理员身份运行此脚本！
    echo 右键 setup.bat → 以管理员身份运行
    pause
    exit /b 1
)

:: 检查 Python
echo [1/3] 检查 Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo.

:: 升级 pip
echo [2/3] 升级 pip...
python -m pip install --upgrade pip -q
echo.

:: 安装依赖
echo [3/3] 安装项目依赖...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.

:: 检查关键文件
echo ========================================
echo    检查项目文件
echo ========================================
if not exist "models\loftr_model.onnx" (
    echo [警告] 缺少 models\loftr_model.onnx（LoFTR模型）
    echo 请确保模型文件存在
)
if not exist "models\best_20260601.pt" (
    echo [提示] 缺少 YOLO 模型，请将模型放入 models\ 目录
)
if not exist "maps\big_map.png" (
    echo [警告] 缺少 maps\big_map.png（大地图）
)
echo.

echo ========================================
echo    安装完成！
echo ========================================
echo.
echo 双击 run.bat 启动程序
echo.
pause
