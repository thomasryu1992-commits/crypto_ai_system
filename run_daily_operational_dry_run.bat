@echo off
cd /d %~dp0
python run_operational_dry_run.py >> storage\logs\daily_operational_dry_run.log 2>&1
