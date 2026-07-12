from __future__ import annotations

from typing import Any, Dict


def _fmt(value: Any, digits: int = 3, default: str = 'n/a') -> str:
    try:
        if value is None:
            return default
        return f'{float(value):.{digits}f}'
    except Exception:
        return default


def render_daily_summary(result: Dict[str, Any]) -> str:
    snap = result.get('snapshot', result)
    signal = result.get('research_signal') or {}
    permission = signal.get('trade_permission') or {}
    source = result.get('source') or snap.get('data_source') or snap.get('source') or 'UNKNOWN'
    trading_allowed = signal.get('trading_allowed_by_data_source', snap.get('trading_allowed_by_data_source', 'UNKNOWN'))
    blocks = signal.get('block_reasons') or snap.get('data_block_reasons') or []
    warnings = signal.get('risk_warnings') or permission.get('risk_warnings') or []
    return '\n'.join([
        'Crypto AI Daily Research Summary',
        f"Symbol: {snap.get('canonical_symbol', snap.get('symbol', 'BTC-PERP'))}",
        f"Market: {snap.get('exchange_market', 'BTC-USD')}",
        f"Data Source: {source}",
        f"Data Source Role: {signal.get('data_source_role', snap.get('data_source_role', 'UNKNOWN'))}",
        f"Live Trading Data Allowed: {trading_allowed}",
        f"Regime: {snap.get('market_regime', 'UNKNOWN')}",
        f"Condition: {snap.get('market_condition', 'UNKNOWN')}",
        f"Score: {_fmt(snap.get('score_total_score', 0))}",
        f"Bias: {snap.get('score_bias', 'NEUTRAL')}",
        f"Entry Side: {signal.get('entry_side', snap.get('entry_side', 'FLAT'))}",
        f"Entry Allowed: {signal.get('entry_allowed', snap.get('entry_allowed', False))}",
        f"Risk Level: {permission.get('risk_level', 'unknown')}",
        f"Block Reasons: {', '.join(map(str, blocks)) if blocks else 'none'}",
        f"Risk Warnings: {', '.join(map(str, warnings)) if warnings else 'none'}",
        f"MTF Bias: {snap.get('mtf_bias', 'UNKNOWN')}",
        f"MTF Alignment: {_fmt(snap.get('mtf_alignment_score') or 0)}",
        '',
        'Extra Data Summary',
        f"Binance Derivatives Score: {_fmt(snap.get('binance_derivatives_score'))}",
        f"Exchange Flow Score: {_fmt(snap.get('exchange_flow_score'))}",
        f"ETF Flow Score: {_fmt(snap.get('etf_flow_score'))}",
        f"Stablecoin Liquidity Score: {_fmt(snap.get('stablecoin_liquidity_score'))}",
        f"Exchange Netflow Z-Score 30D: {_fmt(snap.get('exchange_netflow_zscore_30d'))}",
        f"ETF 5D Flow: {_fmt(snap.get('etf_flow_5d_sum'))}",
        f"Stablecoin 7D Change: {_fmt(snap.get('stablecoin_total_mcap_7d_change'))}",
    ]) + '\n'
