@echo off
chcp 65001 > nul

cd /d "%~dp0"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================
echo CRYPTO AI SYSTEM - DAILY SCHEDULER START
echo ============================================
echo Current directory: %cd%
echo Started at: %date% %time%

python check_scheduler_health.py

echo ============================================
echo CRYPTO AI SYSTEM - DAILY SCHEDULER END
echo ============================================
echo Finished at: %date% %time%

pause