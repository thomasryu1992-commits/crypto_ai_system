from __future__ import annotations

from typing import Dict, Any

import numpy as np
import pandas as pd


def compute_backtest_summary(trades: pd.DataFrame, equity_curve: pd.DataFrame, initial_equity: float) -> Dict[str, Any]:
    if trades.empty:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'total_return_pct': 0,
            'max_drawdown_pct': 0,
            'expectancy_r': 0,
            'average_r': 0,
            'average_win_r': 0,
            'average_loss_r': 0,
            'consecutive_losses': 0,
        }
    pnl = trades['pnl'].astype(float)
    r = trades['r_multiple'].astype(float)
    wins = trades[pnl > 0]
    losses = trades[pnl < 0]
    gross_profit = wins['pnl'].sum() if not wins.empty else 0.0
    gross_loss = abs(losses['pnl'].sum()) if not losses.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
    win_rate = len(wins) / len(trades) if len(trades) else 0
    avg_win_r = wins['r_multiple'].mean() if not wins.empty else 0
    avg_loss_r = losses['r_multiple'].mean() if not losses.empty else 0
    expectancy = win_rate * avg_win_r + (1 - win_rate) * avg_loss_r

    eq = equity_curve['equity'].astype(float) if not equity_curve.empty else pd.Series([initial_equity])
    peak = eq.cummax()
    dd = (eq - peak) / peak
    max_dd = float(dd.min() * 100) if not dd.empty else 0

    loss_streak = 0
    max_loss_streak = 0
    for val in pnl:
        if val < 0:
            loss_streak += 1
            max_loss_streak = max(max_loss_streak, loss_streak)
        else:
            loss_streak = 0

    by_side = {}
    if 'side' in trades.columns:
        for side, group in trades.groupby('side'):
            by_side[side] = {
                'trades': int(len(group)),
                'win_rate': float((group['pnl'] > 0).mean()) if len(group) else 0,
                'avg_r': float(group['r_multiple'].mean()) if len(group) else 0,
                'pnl': float(group['pnl'].sum()),
            }

    by_regime = {}
    if 'entry_regime' in trades.columns:
        for regime, group in trades.groupby('entry_regime'):
            by_regime[regime] = {
                'trades': int(len(group)),
                'win_rate': float((group['pnl'] > 0).mean()) if len(group) else 0,
                'avg_r': float(group['r_multiple'].mean()) if len(group) else 0,
                'pnl': float(group['pnl'].sum()),
            }

    return {
        'total_trades': int(len(trades)),
        'win_rate': float(win_rate),
        'profit_factor': float(profit_factor) if np.isfinite(profit_factor) else 999.0,
        'total_return_pct': float((eq.iloc[-1] / initial_equity - 1) * 100),
        'max_drawdown_pct': max_dd,
        'expectancy_r': float(expectancy),
        'average_r': float(r.mean()),
        'average_win_r': float(avg_win_r),
        'average_loss_r': float(avg_loss_r),
        'consecutive_losses': int(max_loss_streak),
        'by_side': by_side,
        'by_regime': by_regime,
        'tp1_hit_rate': float(trades.get('tp1_hit', pd.Series([False]*len(trades))).mean()) if len(trades) else 0,
        'breakeven_stop_rate': float((trades.get('exit_reason', pd.Series([])) == 'BREAKEVEN_STOP').mean()) if len(trades) else 0,
    }
