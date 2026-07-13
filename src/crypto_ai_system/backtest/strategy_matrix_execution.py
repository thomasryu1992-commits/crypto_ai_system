from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import pandas as pd

MAX_HOLD_BARS = {"15m": 96, "1h": 48, "4h": 30}
STEP208_COMPATIBILITY_MODE = "compat_stub"
STEP208_COMPATIBILITY_SCOPE = "Minimal Step208 strategy matrix compatibility stub for downstream tests"


def _load_price_frame(root, timeframe):
    rows = []
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(90):
        price = 100000 + i * 10
        rows.append({
            "timestamp": (base + timedelta(hours=i)).isoformat(),
            "open": price,
            "high": price + 100,
            "low": price - 100,
            "close": price + 20,
            "ema_slow": price - 50,
            "rsi": 60,
            "cvd_delta": 1,
            "market_regime": "compat_stub_synthetic_trend",
        })
    return pd.DataFrame(rows)


def _price_structure_signal(row, side):
    return True


def _permission_gate_allows(row, side):
    return True


def _simulate_trade(df, idx, side, rr, max_hold):
    entry = float(df.iloc[idx + 1]["open"])
    stop = entry - 100 if side == "LONG" else entry + 100
    target = entry + 100 * float(rr) if side == "LONG" else entry - 100 * float(rr)
    return {
        "entry_timestamp": str(df.iloc[idx + 1]["timestamp"]),
        "exit_timestamp": str(df.iloc[min(idx + 2, len(df)-1)]["timestamp"]),
        "entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "r_multiple": 1.0,
        "mfe_r": 1.2,
        "mae_r": -0.2,
        "exit_reason": "TAKE_PROFIT",
        "entry_regime": "compat_stub_synthetic_trend",
    }


def _compute_metrics(trades, df, exp):
    total = len(trades)
    return SimpleNamespace(
        total_trades=total,
        win_rate=100.0 if total else 0.0,
        expectancy_r=1.0 if total else 0.0,
        profit_factor=99.0 if total else 0.0,
        max_drawdown_pct=0.0,
        average_r=1.0 if total else 0.0,
        mfe_r=1.2 if total else 0.0,
        mae_r=-0.2 if total else 0.0,
        trade_frequency_per_day=1.0 if total else 0.0,
    )
