@echo off
REM One pipeline cycle for Windows Task Scheduler. Logs to storage\logs\scheduler.log.
cd /d "%~dp0.."
if not exist "storage\logs" mkdir "storage\logs"
py run_scheduler.py --once >> "storage\logs\scheduler.log" 2>&1
