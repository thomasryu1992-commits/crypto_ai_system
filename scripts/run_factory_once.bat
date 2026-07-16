@echo off
REM One strategy-factory generation for Windows Task Scheduler.
REM Fetches a longer history for a sounder backtest sample, degrading to the
REM cached candles if the public API is unreachable. Logs to
REM storage\logs\strategy_factory.log.
cd /d "%~dp0.."
if not exist "storage\logs" mkdir "storage\logs"
py run_strategy_factory.py --cycles 1 --history 1500 >> "storage\logs\strategy_factory.log" 2>&1
