@echo off
cd /d %~dp0
python run_operational_dry_run.py >> storage\logs\daily_scheduler.log 2>&1
python check_scheduler_health.py >> storage\logs\daily_scheduler.log 2>&1
