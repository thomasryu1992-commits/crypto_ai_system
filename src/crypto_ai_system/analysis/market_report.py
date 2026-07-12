from __future__ import annotations

from typing import Any, Dict

from crypto_ai_system.analysis.scenario_builder import build_scenarios


def _fmt_pct(value: Any) -> str:
    try:
        if value is None:
            return 'n/a'
        return f"{float(value) * 100:.2f}%"
    except Exception:
        return 'n/a'




def _fmt_float(value: Any, digits: int = 3) -> str:
    try:
        if value is None:
            return 'n/a'
        return f"{float(value):.{digits}f}"
    except Exception:
        return 'n/a'


def _render_extra_data_context(snapshot: Dict[str, Any]) -> list[str]:
    lines = [
        '## Additional Data Context',
        '| Component | Latest Feature | Score / Signal |',
        '|---|---:|---:|',
        f"| Binance Futures | taker ratio {_fmt_float(snapshot.get('taker_buy_sell_ratio'))}, top position LS {_fmt_float(snapshot.get('top_trader_position_long_short_ratio'))} | {_fmt_float(snapshot.get('binance_derivatives_score'))} |",
        f"| Exchange Flow | netflow BTC {_fmt_float(snapshot.get('btc_exchange_netflow'))}, z30 {_fmt_float(snapshot.get('exchange_netflow_zscore_30d'))} | {_fmt_float(snapshot.get('exchange_flow_score'))} |",
        f"| ETF Flow | 1d USDm {_fmt_float(snapshot.get('total_flow_usd_m'))}, 5d USDm {_fmt_float(snapshot.get('etf_flow_5d_sum'))} | {_fmt_float(snapshot.get('etf_flow_score'))} |",
        f"| Stablecoin Liquidity | 7d change {_fmt_pct(snapshot.get('stablecoin_total_mcap_7d_change'))}, 30d change {_fmt_pct(snapshot.get('stablecoin_total_mcap_30d_change'))} | {_fmt_float(snapshot.get('stablecoin_liquidity_score'))} |",
        '',
    ]
    return lines

def _render_price_context(snapshot: Dict[str, Any]) -> list[str]:
    ctx = snapshot.get('price_context') or {}
    if not ctx or not ctx.get('available'):
        return ['## Multi-Timeframe Price Context', 'Price context: unavailable', '']

    lines = [
        '## Multi-Timeframe Price Context',
        f"MTF Bias: {ctx.get('bias', 'UNKNOWN')}",
        f"MTF Alignment Score: {float(ctx.get('alignment_score') or 0):.3f}",
        '',
        '| TF | Trend | Close | 1-Bar Change | RSI | Rows | Latest |',
        '|---|---:|---:|---:|---:|---:|---|',
    ]
    order = ['15m', '1h', '4h', '1d', '3d', '1w', '1m']
    timeframes = ctx.get('timeframes') or {}
    for tf in order:
        if tf not in timeframes:
            continue
        item = timeframes[tf]
        close = item.get('close')
        rsi = item.get('rsi')
        close_txt = f"{float(close):.2f}" if close is not None else 'n/a'
        rsi_txt = f"{float(rsi):.2f}" if rsi is not None else 'n/a'
        lines.append(
            f"| {tf} | {item.get('trend', '')} | {close_txt} | "
            f"{_fmt_pct(item.get('change_1'))} | {rsi_txt} | {item.get('rows', '')} | {item.get('latest_timestamp', '')} |"
        )
    lines.append('')
    return lines


def _render_research_signal(signal: Dict[str, Any] | None) -> list[str]:
    if not signal:
        return ['## Research Signal', 'ResearchSignal: unavailable', '']
    blocks = signal.get('block_reasons') or []
    lines = [
        '## Research Signal',
        f"Signal ID: {signal.get('signal_id', '')}",
        f"Data Source Role: {signal.get('data_source_role', 'UNKNOWN')}",
        f"Trading Allowed By Data Source: {signal.get('trading_allowed_by_data_source')}",
        f"Entry Side: {signal.get('entry_side', 'FLAT')}",
        f"Entry Allowed: {signal.get('entry_allowed')}",
        f"Entry Confidence: {float(signal.get('entry_confidence') or 0):.3f}",
    ]
    if blocks:
        lines.append('Block Reasons:')
        lines.extend([f"- {x}" for x in blocks])
    else:
        lines.append('Block Reasons: none')
    lines.append('')
    return lines


def render_market_report(snapshot: Dict[str, Any], research_signal: Dict[str, Any] | None = None) -> str:
    scenarios = build_scenarios(snapshot)
    lines = [
        '# Crypto AI System Market Report',
        '',
        f"Timestamp: {snapshot.get('timestamp', '')}",
        f"Symbol: {snapshot.get('canonical_symbol', snapshot.get('symbol', 'BTC-PERP'))}",
        f"Exchange Market: {snapshot.get('exchange_market', 'BTC-USD')}",
        f"Data Source: {snapshot.get('data_source', snapshot.get('source', 'UNKNOWN'))}",
        f"Data Source Role: {snapshot.get('data_source_role', 'UNKNOWN')}",
        f"Regime: {snapshot.get('market_regime', 'UNKNOWN')}",
        f"Condition: {snapshot.get('market_condition', 'UNKNOWN')}",
        f"Score: {float(snapshot.get('score_total_score', snapshot.get('total_score', 0))):.3f}",
        f"Bias: {snapshot.get('score_bias', snapshot.get('bias', 'NEUTRAL'))}",
        f"MTF Bias: {snapshot.get('mtf_bias', 'UNKNOWN')}",
        f"MTF Alignment Score: {float(snapshot.get('mtf_alignment_score') or 0):.3f}",
        '',
    ]
    lines.extend(_render_research_signal(research_signal or {'signal_id': snapshot.get('research_signal_id'), 'data_source_role': snapshot.get('data_source_role'), 'trading_allowed_by_data_source': snapshot.get('trading_allowed_by_data_source'), 'entry_side': snapshot.get('entry_side'), 'entry_allowed': snapshot.get('entry_allowed'), 'entry_confidence': snapshot.get('entry_confidence'), 'block_reasons': snapshot.get('block_reasons')}))
    lines.extend(_render_extra_data_context(snapshot))
    lines.extend(_render_price_context(snapshot))
    lines.extend([
        '## Base Case',
        scenarios.base_case,
        '',
        '## Bullish Case',
        scenarios.bullish_case,
        '',
        '## Bearish Case',
        scenarios.bearish_case,
        '',
        '## Invalidation',
        scenarios.invalidation,
        '',
        '## Watchlist',
    ])
    lines.extend([f'- {item}' for item in scenarios.key_watchlist])
    return '\n'.join(lines) + '\n'
