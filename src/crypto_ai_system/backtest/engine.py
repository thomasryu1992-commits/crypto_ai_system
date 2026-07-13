from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from crypto_ai_system.config import AppConfig
from crypto_ai_system.strategy.exit_policy import breakeven_stop, initial_stop, load_exit_policy, target_price
from crypto_ai_system.strategy.risk import calculate_position_size


def _apply_cost(price: float, side: str, action: str, slippage_bps: float) -> float:
    if (side == 'LONG' and action == 'entry') or (side == 'SHORT' and action == 'exit'):
        return price * (1 + slippage_bps / 10000)
    return price * (1 - slippage_bps / 10000)


def _funding_pnl(side: str, position_notional: float, funding_rate: float) -> float:
    # Extended formula: Funding Payment = Position Size * Mark Price * (-Funding Rate).
    # Long receives negative funding when rate < 0 and pays when rate > 0.
    if side == 'LONG':
        return position_notional * (-funding_rate)
    return position_notional * funding_rate


def run_backtest(features: pd.DataFrame, cfg: AppConfig) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    policy = load_exit_policy(cfg)
    initial_equity = float(cfg.get('backtest.initial_equity', 10000))
    risk_pct = float(cfg.get('backtest.risk_per_trade_pct', 0.01))
    taker_fee_bps = float(cfg.get('backtest.taker_fee_bps', 2.5))
    slippage_bps = float(cfg.get('backtest.slippage_bps', 3))
    use_funding = bool(cfg.get('backtest.use_funding_payment', True))

    df = features.reset_index(drop=True).copy()
    equity = initial_equity
    equity_rows: List[Dict] = []
    trades: List[Dict] = []
    position = None

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        row = df.iloc[i]
        ts = row['timestamp']

        if position is not None:
            side = position['side']
            high = float(row['high'])
            low = float(row['low'])
            close = float(row['close'])
            atr = float(row.get('atr') or 0)
            position['bars_held'] += 1

            if use_funding:
                mark_price = float(row.get('mark_price') or close)
                funding_rate = float(row.get('funding_rate') or 0)
                notional = mark_price * position['qty_remaining']
                funding = _funding_pnl(side, notional, funding_rate)
                equity += funding
                position['funding_pnl'] += funding

            if side == 'LONG':
                position['mfe_price'] = max(position['mfe_price'], high)
                mfe_r = (position['mfe_price'] - position['entry']) / position['risk_per_unit']
            else:
                position['mfe_price'] = min(position['mfe_price'], low)
                mfe_r = (position['entry'] - position['mfe_price']) / position['risk_per_unit']
            position['max_mfe_r'] = max(position['max_mfe_r'], mfe_r)

            if not position['tp1_hit']:
                hit_tp1 = high >= position['tp1'] if side == 'LONG' else low <= position['tp1']
                if hit_tp1:
                    qty_exit = position['qty_remaining'] * policy.tp1_size_pct
                    exit_price = _apply_cost(position['tp1'], side, 'exit', slippage_bps)
                    pnl = _pnl(side, position['entry'], exit_price, qty_exit)
                    fees = _fees(position['entry'], exit_price, qty_exit, taker_fee_bps)
                    equity += pnl - fees
                    position['realized_pnl'] += pnl - fees
                    position['qty_remaining'] -= qty_exit
                    position['tp1_hit'] = True
                    if policy.breakeven_enabled and policy.breakeven_after_tp1:
                        be = breakeven_stop(position['entry'], side, policy.breakeven_fee_buffer_bps)
                        if side == 'LONG':
                            position['stop'] = max(position['stop'], be)
                        else:
                            position['stop'] = min(position['stop'], be)

            if policy.trailing_enabled and position['qty_remaining'] > 0:
                allowed_after_tp1 = (not policy.trailing_only_after_tp1) or position['tp1_hit']
                allowed_regime = (not policy.trailing_only_in_trend) or str(row.get('market_regime', '')).startswith('TREND')
                if allowed_after_tp1 and allowed_regime and atr > 0:
                    if side == 'LONG':
                        trail = position['mfe_price'] - atr * policy.trailing_atr_multiplier
                        position['stop'] = max(position['stop'], trail)
                    else:
                        trail = position['mfe_price'] + atr * policy.trailing_atr_multiplier
                        position['stop'] = min(position['stop'], trail)

            hit_stop = low <= position['stop'] if side == 'LONG' else high >= position['stop']
            hit_tp2 = high >= position['tp2'] if side == 'LONG' else low <= position['tp2']

            exit_reason = None
            exit_price_raw = None
            if hit_stop:
                exit_reason = 'BREAKEVEN_STOP' if position['tp1_hit'] else 'STOP_LOSS'
                exit_price_raw = position['stop']
            elif hit_tp2:
                exit_reason = 'TP2'
                exit_price_raw = position['tp2']
            elif policy.time_stop_enabled and position['bars_held'] >= policy.time_stop_candles and position['max_mfe_r'] < policy.time_stop_min_mfe_r:
                exit_reason = 'TIME_STOP'
                exit_price_raw = close

            if exit_reason and position['qty_remaining'] > 0:
                exit_price = _apply_cost(float(exit_price_raw), side, 'exit', slippage_bps)
                pnl = _pnl(side, position['entry'], exit_price, position['qty_remaining'])
                fees = _fees(position['entry'], exit_price, position['qty_remaining'], taker_fee_bps)
                equity += pnl - fees
                realized_total = position['realized_pnl'] + pnl - fees + position['funding_pnl']
                r_mult = realized_total / position['initial_risk_amount'] if position['initial_risk_amount'] else 0
                trades.append(_trade_row(position, ts, exit_price, exit_reason, realized_total, r_mult))
                position = None

        if position is None:
            signal = prev.get('signal', 'FLAT')
            if signal in ('LONG', 'SHORT') and pd.notna(prev.get('atr')):
                side = signal
                raw_entry = float(row['open'])
                entry = _apply_cost(raw_entry, side, 'entry', slippage_bps)
                stop = initial_stop(entry, float(prev['atr']), side, policy)
                qty, risk_amount, risk_per_unit = calculate_position_size(equity, risk_pct, entry, stop)
                if qty > 0:
                    position = {
                        'side': side,
                        'entry_ts': ts,
                        'entry': entry,
                        'initial_stop': stop,
                        'stop': stop,
                        'risk_per_unit': risk_per_unit,
                        'qty': qty,
                        'qty_remaining': qty,
                        'initial_risk_amount': risk_amount,
                        'tp1': target_price(entry, stop, side, policy.tp1_r),
                        'tp2': target_price(entry, stop, side, policy.tp2_r),
                        'tp1_hit': False,
                        'realized_pnl': 0.0,
                        'funding_pnl': 0.0,
                        'bars_held': 0,
                        'mfe_price': entry,
                        'max_mfe_r': 0.0,
                        'entry_regime': prev.get('market_regime', 'UNCLEAR'),
                        'entry_score': float(prev.get('research_score', 0) or 0),
                        'entry_spread_bps': float(prev.get('spread_bps', 0) or 0),
                        'entry_funding_rate': float(prev.get('funding_rate', 0) or 0),
                    }

        equity_rows.append({'timestamp': ts, 'equity': equity})

    if position is not None:
        row = df.iloc[-1]
        side = position['side']
        exit_price = _apply_cost(float(row['close']), side, 'exit', slippage_bps)
        pnl = _pnl(side, position['entry'], exit_price, position['qty_remaining'])
        fees = _fees(position['entry'], exit_price, position['qty_remaining'], taker_fee_bps)
        equity += pnl - fees
        realized_total = position['realized_pnl'] + pnl - fees + position['funding_pnl']
        r_mult = realized_total / position['initial_risk_amount'] if position['initial_risk_amount'] else 0
        trades.append(_trade_row(position, row['timestamp'], exit_price, 'FORCE_CLOSE', realized_total, r_mult))
        equity_rows.append({'timestamp': row['timestamp'], 'equity': equity})

    return pd.DataFrame(trades), pd.DataFrame(equity_rows), {'final_equity': equity, 'settlement_asset': cfg.get('data.settlement_asset', 'USDC')}


def _trade_row(position: Dict, exit_ts: str, exit_price: float, exit_reason: str, realized_total: float, r_mult: float) -> Dict:
    return {
        'entry_timestamp': position['entry_ts'],
        'exit_timestamp': exit_ts,
        'side': position['side'],
        'entry_price': position['entry'],
        'exit_price': exit_price,
        'initial_stop': position['initial_stop'],
        'final_stop': position['stop'],
        'tp1': position['tp1'],
        'tp2': position['tp2'],
        'qty': position['qty'],
        'pnl': realized_total,
        'funding_pnl': position.get('funding_pnl', 0.0),
        'r_multiple': r_mult,
        'bars_held': position['bars_held'],
        'exit_reason': exit_reason,
        'tp1_hit': position['tp1_hit'],
        'max_mfe_r': position['max_mfe_r'],
        'entry_regime': position['entry_regime'],
        'entry_score': position['entry_score'],
        'entry_spread_bps': position.get('entry_spread_bps', 0),
        'entry_funding_rate': position.get('entry_funding_rate', 0),
        'settlement_asset': 'USDC',
    }


def _pnl(side: str, entry: float, exit_price: float, qty: float) -> float:
    if side == 'LONG':
        return (exit_price - entry) * qty
    return (entry - exit_price) * qty


def _fees(entry: float, exit_price: float, qty: float, fee_bps: float) -> float:
    return (entry * qty + exit_price * qty) * fee_bps / 10000
