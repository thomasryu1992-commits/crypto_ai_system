@echo off
chcp 65001 > nul

set PROJECT_DIR=%~dp0
set LOG_DIR=%PROJECT_DIR%storage\scheduler_logs

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

cd /d "%PROJECT_DIR%"

echo ================================================== >> "%LOG_DIR%\daily_operational_dry_run.log"
echo [START] %date% %time% >> "%LOG_DIR%\daily_operational_dry_run.log"
echo PROJECT_DIR=%PROJECT_DIR% >> "%LOG_DIR%\daily_operational_dry_run.log"

python run_operational_dry_run.py >> "%LOG_DIR%\daily_operational_dry_run.log" 2>&1
python check_scheduler_health.py >> "%LOG_DIR%\daily_operational_dry_run.log" 2>&1
python send_scheduler_health_report.py >> "%LOG_DIR%\daily_operational_dry_run.log" 2>&1

echo [END] %date% %time% >> "%LOG_DIR%\daily_operational_dry_run.log"
echo ================================================== >> "%LOG_DIR%\daily_operational_dry_run.log"