from __future__ import annotations

from typing import Any, Dict

from crypto_ai_system.trading.signal import signal_from_research_snapshot
from crypto_ai_system.strategy.exit_policy import initial_stop, load_exit_policy, target_price
from crypto_ai_system.strategy.risk import calculate_position_size


class TradingBot:
    """Signal/risk bridge. It does not send live orders."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.exit_policy = load_exit_policy(cfg)

    def build_trade_plan(self, research_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        signal = signal_from_research_snapshot(research_snapshot)
        if not signal.entry_allowed or signal.side == 'FLAT':
            return {'signal': signal.to_dict(), 'trade_plan': None, 'status': 'NO_TRADE'}

        entry = float(research_snapshot.get('close') or 0)
        atr = float(research_snapshot.get('atr') or 0)
        equity = float(self.cfg.get('backtest.initial_equity', 10000))
        base_risk_pct = float(self.cfg.get('backtest.risk_per_trade_pct', 0.01))
        multiplier = float(getattr(signal, 'position_size_multiplier', 1.0) or 0.0)
        if getattr(signal, 'risk_level', 'normal') == 'reduced':
            multiplier = min(multiplier, float(self.cfg.get('trading.risk_level_reduced_position_multiplier', 0.5)))
        if getattr(signal, 'risk_level', 'normal') == 'blocked':
            multiplier = 0.0
        if multiplier <= 0:
            return {'signal': signal.to_dict(), 'trade_plan': None, 'status': 'NO_TRADE'}
        risk_pct = base_risk_pct * multiplier
        stop = initial_stop(entry, atr, signal.side, self.exit_policy)
        qty, risk_amount, risk_per_unit = calculate_position_size(equity, risk_pct, entry, stop)
        tp1 = target_price(entry, stop, signal.side, self.exit_policy.tp1_r)
        tp2 = target_price(entry, stop, signal.side, self.exit_policy.tp2_r)

        plan = {
            'symbol': signal.symbol,
            'exchange_market': research_snapshot.get('exchange_market', 'BTC-USD'),
            'settlement_asset': research_snapshot.get('settlement_asset', 'USDC'),
            'side': signal.side,
            'entry_reference': entry,
            'initial_stop': stop,
            'tp1': tp1,
            'tp1_size_pct': self.exit_policy.tp1_size_pct,
            'tp2': tp2,
            'qty': qty,
            'risk_amount_usdc': risk_amount,
            'risk_per_unit': risk_per_unit,
            'confidence': signal.confidence,
            'risk_level': signal.risk_level,
            'position_size_multiplier': multiplier,
            'base_risk_per_trade_pct': base_risk_pct,
            'effective_risk_per_trade_pct': risk_pct,
            'permission_gate_applied': signal.permission_gate_applied,
            'research_signal_id': signal.research_signal_id,
            'execution_mode': 'PAPER_OR_BACKTEST_ONLY',
        }
        return {'signal': signal.to_dict(), 'trade_plan': plan, 'status': 'TRADE_CANDIDATE'}
