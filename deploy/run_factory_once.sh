#!/usr/bin/env bash
# One strategy-factory generation per symbol (Linux port of
# scripts/run_factory_once.bat - keep the two in sync).
#
# Must match the pool's operating regime or it corrodes it: 1d candles (1h
# cost ~0.21R/trade kills every edge), the directive's honest gates (the
# shipped CLI defaults are thin-sample), and a cap at least as large as the
# standing pool (25 since 2026-07-20) - a smaller cap makes every scheduled
# champion displace a current member via cross-symbol score comparison.
# Position risk stays bounded by the book caps, not the pool size.
cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/bin/python}"
SYMBOLS="BTCUSDT ETHUSDT BNBUSDT DOGEUSDT SOLUSDT"

for S in $SYMBOLS; do
  "$PY" run_strategy_factory.py --symbol "$S" --history 2200 --interval 1d --cycles 2 --cap 25 \
    --min-trades 100 --min-expectancy 0.1 --min-profit-factor 1.15 \
    --min-wf-pass 0.7 --max-drawdown 10.0 --min-stability 0.3
done

# Rule mining after the template pass, seeded by the adopted champions. One
# fresh seed per run - a fixed seed would repeat the same search forever;
# logged so any mined champion's search is reproducible.
MINER_SEED=$((RANDOM * 32768 + RANDOM))
echo "[miner] seed $MINER_SEED"
for S in $SYMBOLS; do
  "$PY" run_rule_miner.py --symbol "$S" --history 2200 --interval 1d --cap 25 --seed "$MINER_SEED"
done
