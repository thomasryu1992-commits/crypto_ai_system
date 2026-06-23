@echo off
chcp 65001 > nul

cd /d "%~dp0"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

python check_scheduler_health.py >> ".\storage\scheduler_logs\windows_task_scheduler.log" 2>&1