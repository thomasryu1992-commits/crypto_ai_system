from __future__ import annotations

import os
from typing import Dict, Any


def _fmt(value: Any, default: str = '-') -> str:
    if value is None:
        return default
    if isinstance(value, str) and not value.strip():
        return default
    return str(value)


def _join(values: Any) -> str:
    if not values:
        return '-'
    if isinstance(values, list):
        return ', '.join(str(x) for x in values[:5]) if values else '-'
    return str(values)


def _extra_data_from_research_signal(signal: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(signal, dict):
        return {}
    features = signal.get('features') if isinstance(signal.get('features'), dict) else {}
    components = signal.get('score_components') if isinstance(signal.get('score_components'), dict) else {}
    return {
        'binance_derivatives_score': features.get('binance_derivatives_score'),
        'exchange_flow_score': features.get('exchange_flow_score'),
        'etf_flow_score': features.get('etf_flow_score'),
        'stablecoin_liquidity_score': features.get('stablecoin_liquidity_score'),
        'exchange_netflow_zscore_30d': features.get('exchange_netflow_zscore_30d'),
        'etf_flow_5d': features.get('etf_flow_5d'),
        'stablecoin_supply_change_7d': features.get('stablecoin_supply_change_7d'),
        'score_derivatives': components.get('derivatives'),
        'score_exchange_flow': components.get('exchange_flow'),
        'score_etf_flow': components.get('etf_flow'),
        'score_stablecoin_liquidity': components.get('stablecoin_liquidity'),
        'score_risk': components.get('risk'),
    }


def _fmt_score(value: Any) -> str:
    try:
        return f"{float(value):+.2f}"
    except Exception:
        return '-'


def _fmt_pct_change(value: Any) -> str:
    try:
        return f"{float(value) * 100:+.2f}%"
    except Exception:
        return '-'


def _append_extra_data_summary(text: str, signal: Dict[str, Any] | None) -> str:
    extra = _extra_data_from_research_signal(signal)
    if not extra:
        return text
    text += '\n\nExtra Data Summary:'
    text += f"\nDerivatives Score: {_fmt_score(extra.get('binance_derivatives_score'))}"
    text += f"\nExchange Flow Score: {_fmt_score(extra.get('exchange_flow_score'))}"
    text += f"\nETF Flow Score: {_fmt_score(extra.get('etf_flow_score'))}"
    text += f"\nStablecoin Liquidity Score: {_fmt_score(extra.get('stablecoin_liquidity_score'))}"
    text += f"\nExchange Netflow Z 30D: {_fmt_score(extra.get('exchange_netflow_zscore_30d'))}"
    text += f"\nETF Flow 5D: {_fmt(extra.get('etf_flow_5d'))}"
    text += f"\nStablecoin Supply 7D: {_fmt_pct_change(extra.get('stablecoin_supply_change_7d'))}"
    return text


def build_telegram_message(summary: str, trade_plan: Dict[str, Any] | None = None, trade_decision: Dict[str, Any] | None = None) -> str:
    text = summary.strip()
    decision_signal = {}
    if isinstance(trade_decision, dict):
        decision_signal = trade_decision.get('signal', {}) if isinstance(trade_decision.get('signal'), dict) else trade_decision.get('trading_signal', {})
        if not isinstance(decision_signal, dict):
            decision_signal = {}
    if trade_plan:
        text += '\n\nTrade Candidate:'
        text += f"\nSide: {trade_plan.get('side')}"
        text += f"\nEntry: {trade_plan.get('entry_reference')}"
        text += f"\nSL: {trade_plan.get('initial_stop')}"
        text += f"\nTP1: {trade_plan.get('tp1')}"
        text += f"\nTP2: {trade_plan.get('tp2')}"
        text += f"\nRisk Level: {_fmt(trade_plan.get('risk_level'))}"
        text += f"\nPosition Size Multiplier: {_fmt(trade_plan.get('position_size_multiplier'))}"
        text += f"\nPermission Gate: {_fmt(trade_plan.get('permission_gate_applied'))}"
        text += f"\nResearch Signal ID: {_fmt(trade_plan.get('research_signal_id'))}"
    if decision_signal or (isinstance(trade_decision, dict) and not trade_plan):
        text += '\n\nTrade Permission:'
        text += f"\nAllow New Position: {_fmt(decision_signal.get('allow_new_position'))}"
        text += f"\nRisk Level: {_fmt(decision_signal.get('risk_level'))}"
        text += f"\nPosition Size Multiplier: {_fmt(decision_signal.get('position_size_multiplier'))}"
        text += f"\nBlock Reasons: {_join(decision_signal.get('block_reasons'))}"
        text += f"\nRisk Warnings: {_join(decision_signal.get('risk_warnings'))}"
    research_signal = {}
    if isinstance(trade_decision, dict):
        research_signal = trade_decision.get('research_signal', {}) if isinstance(trade_decision.get('research_signal'), dict) else {}
        if not research_signal and isinstance(trade_decision.get('signal'), dict):
            maybe_signal = trade_decision.get('signal', {})
            if isinstance(maybe_signal.get('features'), dict) or isinstance(maybe_signal.get('score_components'), dict):
                research_signal = maybe_signal
    text = _append_extra_data_summary(text, research_signal)
    return text


def send_telegram_message(message: str) -> Dict[str, Any]:
    # Safe default: no network send unless explicitly configured by user scripts.
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return {'sent': False, 'reason': 'TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured', 'preview': message[:500]}
    return {'sent': False, 'reason': 'network sending disabled in packaged template', 'preview': message[:500]}
