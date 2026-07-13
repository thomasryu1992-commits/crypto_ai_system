from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

from crypto_ai_system.backtest.engine import run_backtest
from crypto_ai_system.backtest.metrics import compute_backtest_summary
from crypto_ai_system.config import AppConfig


def _set_nested(d: Dict[str, Any], path: str, value: Any) -> None:
    node = d
    parts = path.split('.')
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def default_parameter_grid(cfg: AppConfig | None = None) -> List[Dict[str, Any]]:
    if cfg is None:
        tp1_values = [1.0, 1.5, 2.0]
        tp1_sizes = [0.3, 0.5, 0.7]
        atr_values = [1.2, 1.5, 2.0]
        trailing_values = [1.5, 2.0]
        time_values = [12, 24]
        funding_modes = ['normal']
        oi_modes = ['normal']
        spread_values = [10]
    else:
        tp1_values = list(cfg.get('parameter_sweep.tp1_r_values', [1.0, 1.5, 2.0]))
        tp1_sizes = list(cfg.get('parameter_sweep.tp1_size_values', [0.3, 0.5, 0.7]))
        atr_values = list(cfg.get('parameter_sweep.atr_multipliers', [1.2, 1.5, 2.0]))
        trailing_values = list(cfg.get('parameter_sweep.trailing_atr_multipliers', [1.5, 2.0]))
        time_values = list(cfg.get('parameter_sweep.time_stop_candles', [12, 24]))
        funding_modes = list(cfg.get('parameter_sweep.funding_filter_modes', ['normal']))
        oi_modes = list(cfg.get('parameter_sweep.oi_filter_modes', ['normal']))
        spread_values = list(cfg.get('parameter_sweep.spread_filter_bps', [10]))

    grid = []
    # Keep validation lightweight: use a representative but not explosive grid.
    for tp1_r in tp1_values:
        for tp1_size in tp1_sizes:
            for atr_mult in atr_values:
                for trailing_mult in trailing_values:
                    for time_stop in time_values:
                        for funding_mode in funding_modes[:2]:
                            for oi_mode in oi_modes[:2]:
                                for spread_bps in spread_values[-2:]:
                                    grid.append({
                                        'exit_policy.tp1_r': tp1_r,
                                        'exit_policy.tp1_size_pct': tp1_size,
                                        'exit_policy.atr_multiplier': atr_mult,
                                        'exit_policy.trailing_atr_multiplier': trailing_mult,
                                        'exit_policy.time_stop_candles': time_stop,
                                        'entry_policy.funding_filter_mode': funding_mode,
                                        'entry_policy.oi_filter_mode': oi_mode,
                                        'entry_policy.spread_bps_block': spread_bps,
                                    })
    return grid[:240]


def run_parameter_sweep(features: pd.DataFrame, cfg: AppConfig, grid: Iterable[Dict[str, Any]] | None = None) -> pd.DataFrame:
    rows = []
    grid = list(grid or default_parameter_grid(cfg))
    for idx, params in enumerate(grid, 1):
        settings = copy.deepcopy(cfg.settings)
        for path, value in params.items():
            _set_nested(settings, path, value)
        sweep_cfg = AppConfig(root=cfg.root, settings=settings)
        trades, equity_curve, _ = run_backtest(features, sweep_cfg)
        summary = compute_backtest_summary(trades, equity_curve, float(sweep_cfg.get('backtest.initial_equity', 10000)))
        rows.append({
            'candidate_id': idx,
            **params,
            'total_trades': summary['total_trades'],
            'win_rate': summary['win_rate'],
            'profit_factor': summary['profit_factor'],
            'total_return_pct': summary['total_return_pct'],
            'max_drawdown_pct': summary['max_drawdown_pct'],
            'expectancy_r': summary['expectancy_r'],
            'average_r': summary['average_r'],
            'tp1_hit_rate': summary.get('tp1_hit_rate', 0),
            'breakeven_stop_rate': summary.get('breakeven_stop_rate', 0),
        })
    result = pd.DataFrame(rows)
    if not result.empty:
        result['score'] = (
            result['profit_factor'].clip(0, 5) * 0.32
            + result['expectancy_r'].clip(-2, 2) * 0.32
            + result['total_return_pct'].clip(-100, 200) / 100 * 0.18
            - result['max_drawdown_pct'].abs().clip(0, 100) / 100 * 0.12
            + (result['total_trades'].clip(0, 40) / 40) * 0.06
        )
        result = result.sort_values(['score', 'profit_factor', 'expectancy_r'], ascending=False).reset_index(drop=True)
    return result


def write_strategy_comparison_report(results: pd.DataFrame, path: str) -> None:
    lines = ['# Extended Strategy Comparison Report — Step157E', '']
    lines.append('This report compares Extended-specific backtest candidates using USDC settlement, Extended fee/slippage assumptions, funding payment approximation, spread guard, and OI/funding filters.')
    lines.append('')
    if results.empty:
        lines.append('No sweep results generated.')
    else:
        top = results.head(10)
        lines.append('## Top Candidates')
        lines.append('')
        lines.append(top.to_markdown(index=False))
        lines.append('')
        best = top.iloc[0].to_dict()
        lines.append('## Best Candidate Summary')
        lines.append('')
        for k, v in best.items():
            lines.append(f'- {k}: {v}')
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('\n'.join(lines), encoding='utf-8')
