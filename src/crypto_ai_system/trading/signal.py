from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict

from crypto_ai_system.trading.permission_gate import evaluate_trade_permission


@dataclass
class TradingSignal:
    symbol: str
    side: str
    confidence: float
    reason: str
    entry_allowed: bool
    risk_level: str = 'normal'
    position_size_multiplier: float = 1.0
    allow_new_position: bool = True
    block_reasons: list[str] | None = None
    risk_warnings: list[str] | None = None
    permission_gate_applied: bool = False
    research_signal_id: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def signal_from_research_snapshot(snapshot: Dict[str, Any]) -> TradingSignal:
    symbol = str(snapshot.get('canonical_symbol') or snapshot.get('symbol') or 'BTC-PERP')

    # Step163: ResearchSignal v2 trade_permission is the final Trading Bot gate.
    if 'trade_permission' in snapshot or 'entry_allowed' in snapshot or 'entry_side' in snapshot:
        decision = evaluate_trade_permission(snapshot)
        reason = '; '.join(decision.reasons or ['ResearchSignal permission evaluated'])
        return TradingSignal(
            symbol=symbol,
            side=decision.side,
            confidence=decision.confidence,
            reason=reason,
            entry_allowed=decision.entry_allowed,
            risk_level=decision.risk_level,
            position_size_multiplier=decision.position_size_multiplier,
            allow_new_position=decision.allow_new_position,
            block_reasons=decision.block_reasons,
            risk_warnings=decision.risk_warnings,
            permission_gate_applied=decision.permission_gate_applied,
            research_signal_id=decision.research_signal_id,
        )

    score = float(snapshot.get('score_total_score') or 0)
    condition = str(snapshot.get('market_condition') or '')
    spread_bps = float(snapshot.get('spread_bps') or 0)

    source = str(snapshot.get('data_source') or snapshot.get('source') or '').lower()
    explicit_allowed = snapshot.get('trading_allowed_by_data_source')
    blocked_sources = ('sample', 'synthetic', 'fallback', 'price_data')
    if explicit_allowed is False or any(source.startswith(x) for x in blocked_sources):
        reasons = snapshot.get('data_block_reasons') or ['fallback/synthetic/research-only data blocked entry']
        return TradingSignal(symbol, 'FLAT', 0.0, '; '.join(map(str, reasons)), False, risk_level='blocked', position_size_multiplier=0.0, allow_new_position=False, block_reasons=list(map(str, reasons)))

    if spread_bps >= 10:
        return TradingSignal(symbol, 'FLAT', 0.0, 'spread guard blocked entry', False, risk_level='blocked', position_size_multiplier=0.0, allow_new_position=False, block_reasons=['SPREAD_TOO_WIDE'])
    if score >= 0.35 and 'BULLISH' in condition:
        return TradingSignal(symbol, 'LONG', min(1.0, abs(score)), f'bullish score {score:.3f} and condition {condition}', True)
    if score <= -0.35 and 'BEARISH' in condition:
        return TradingSignal(symbol, 'SHORT', min(1.0, abs(score)), f'bearish score {score:.3f} and condition {condition}', True)
    return TradingSignal(symbol, 'FLAT', min(1.0, abs(score)), f'no trade: score {score:.3f}, condition {condition}', False, allow_new_position=False)
