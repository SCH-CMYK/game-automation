@echo off
cd /d "%~dp0"
powershell -Command "Start-Process python -ArgumentList 'data_collector.py' -WorkingDirectory '%~dp0' -Verb RunAs"
