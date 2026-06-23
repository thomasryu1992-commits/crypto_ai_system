@echo off
cd /d %~dp0
python run_operational_dry_run.py
python check_scheduler_health.py
pause
