@echo off
:: 以管理员权限运行数据采集工具
cd /d "%~dp0"
powershell -Command "Start-Process python -ArgumentList 'data_collector.py' -WorkingDirectory '%~dp0' -Verb RunAs"
