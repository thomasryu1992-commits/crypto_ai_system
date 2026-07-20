@echo off
REM One strategy-factory generation per symbol for Windows Task Scheduler.
REM Must match the pool's operating regime or it corrodes it: 1d candles (1h
REM cost ~0.21R/trade kills every edge), the directive's honest gates (the
REM shipped CLI defaults are thin-sample), and a cap at least as large as the
REM standing pool - a smaller cap makes every scheduled champion displace a
REM current member via cross-symbol score comparison. Logs to
REM storage\logs\strategy_factory.log.
cd /d "%~dp0.."
if not exist "storage\logs" mkdir "storage\logs"
REM Cap 25 (2026-07-20, was 15): the pool sat full at 15, so every new champion
REM could only displace an incumbent. Room to GROW lets the enlarged pool feed
REM multibook with more candidates; position risk is still bounded by the book
REM caps (5 open / 3 same-direction / 2 entries per cycle), not the pool size.
for %%S in (BTCUSDT ETHUSDT BNBUSDT DOGEUSDT SOLUSDT) do (
  py run_strategy_factory.py --symbol %%S --history 2200 --interval 1d --cycles 2 --cap 25 ^
    --min-trades 100 --min-expectancy 0.1 --min-profit-factor 1.15 ^
    --min-wf-pass 0.7 --max-drawdown 10.0 --min-stability 0.3 >> "storage\logs\strategy_factory.log" 2>&1
)
REM Rule mining after the template pass: evolve entry rules per symbol, seeded
REM by the adopted champions. The CLI defaults ARE the directive gates
REM (100 trades / 0.1R / PF 1.15 / WF 0.7 / dd 10 / holdout), so no flag soup.
REM One fresh seed per run - a fixed seed would repeat the same search forever;
REM logged so any mined champion's search is reproducible.
set MINER_SEED=%RANDOM%
echo [miner] seed %MINER_SEED% >> "storage\logs\strategy_factory.log"
for %%S in (BTCUSDT ETHUSDT BNBUSDT DOGEUSDT SOLUSDT) do (
  py run_rule_miner.py --symbol %%S --history 2200 --interval 1d --cap 25 ^
    --seed %MINER_SEED% >> "storage\logs\strategy_factory.log" 2>&1
)
