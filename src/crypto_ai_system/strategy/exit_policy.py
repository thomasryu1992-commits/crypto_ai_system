from __future__ import annotations

from dataclasses import dataclass

from crypto_ai_system.config import AppConfig
from crypto_ai_system.strategy.risk import clamp_stop_distance


@dataclass
class ExitPolicy:
    atr_multiplier: float
    min_stop_bps: float
    max_stop_bps: float
    tp1_r: float
    tp1_size_pct: float
    tp2_r: float
    breakeven_enabled: bool
    breakeven_after_tp1: bool
    breakeven_fee_buffer_bps: float
    trailing_enabled: bool
    trailing_only_after_tp1: bool
    trailing_only_in_trend: bool
    trailing_atr_multiplier: float
    time_stop_enabled: bool
    time_stop_candles: int
    time_stop_min_mfe_r: float


def load_exit_policy(cfg: AppConfig) -> ExitPolicy:
    return ExitPolicy(
        atr_multiplier=float(cfg.get('exit_policy.atr_multiplier', 1.5)),
        min_stop_bps=float(cfg.get('exit_policy.min_stop_bps', 30)),
        max_stop_bps=float(cfg.get('exit_policy.max_stop_bps', 250)),
        tp1_r=float(cfg.get('exit_policy.tp1_r', 1.5)),
        tp1_size_pct=float(cfg.get('exit_policy.tp1_size_pct', 0.5)),
        tp2_r=float(cfg.get('exit_policy.tp2_r', 3.0)),
        breakeven_enabled=bool(cfg.get('exit_policy.breakeven_enabled', True)),
        breakeven_after_tp1=bool(cfg.get('exit_policy.breakeven_after_tp1', True)),
        breakeven_fee_buffer_bps=float(cfg.get('exit_policy.breakeven_fee_buffer_bps', 5)),
        trailing_enabled=bool(cfg.get('exit_policy.trailing_enabled', True)),
        trailing_only_after_tp1=bool(cfg.get('exit_policy.trailing_only_after_tp1', True)),
        trailing_only_in_trend=bool(cfg.get('exit_policy.trailing_only_in_trend', True)),
        trailing_atr_multiplier=float(cfg.get('exit_policy.trailing_atr_multiplier', 2.0)),
        time_stop_enabled=bool(cfg.get('exit_policy.time_stop_enabled', True)),
        time_stop_candles=int(cfg.get('exit_policy.time_stop_candles', 24)),
        time_stop_min_mfe_r=float(cfg.get('exit_policy.time_stop_min_mfe_r', 0.5)),
    )


def initial_stop(entry: float, atr: float, side: str, policy: ExitPolicy) -> float:
    if atr <= 0:
        raw = entry * (0.99 if side == 'LONG' else 1.01)
    else:
        raw = entry - atr * policy.atr_multiplier if side == 'LONG' else entry + atr * policy.atr_multiplier
    return clamp_stop_distance(entry, raw, side, policy.min_stop_bps, policy.max_stop_bps)


def target_price(entry: float, stop: float, side: str, r_multiple: float) -> float:
    risk = abs(entry - stop)
    if side == 'LONG':
        return entry + risk * r_multiple
    if side == 'SHORT':
        return entry - risk * r_multiple
    raise ValueError(f'Invalid side: {side}')


def breakeven_stop(entry: float, side: str, fee_buffer_bps: float) -> float:
    if side == 'LONG':
        return entry * (1 + fee_buffer_bps / 10000)
    if side == 'SHORT':
        return entry * (1 - fee_buffer_bps / 10000)
    raise ValueError(f'Invalid side: {side}')
