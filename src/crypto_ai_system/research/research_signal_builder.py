from __future__ import annotations

import hashlib
from typing import Any

from crypto_ai_system.analysis.scenario_builder import build_scenarios
from crypto_ai_system.config import AppConfig
from crypto_ai_system.data.data_source_policy import classify_data_source
from crypto_ai_system.utils.audit import utc_now_canonical


RESEARCH_SIGNAL_V2_VERSION = 'research_signal_v2_step259_weight_calibration_permission_distribution'
RESEARCH_SIGNAL_LINEAGE_VERSION = 'research_signal_lineage_step270_data_snapshot_health_chain'


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _risk_policy(snapshot: dict[str, Any], cfg: AppConfig) -> tuple[list[str], list[str], str]:
    """Return hard blocks, soft reductions, and final risk level.

    Step258 keeps the Trading Bot connection as a permission signal instead of
    changing entry/SL/TP generation. Hard blocks prevent new entries. Soft
    reductions allow a setup but tell the Trading Bot to reduce size later.
    """
    hard: list[str] = []
    soft: list[str] = []

    spread = _float(snapshot.get('spread_bps'))
    funding_abs = abs(_float(snapshot.get('funding_rate')))
    oi_chg_abs = abs(_float(snapshot.get('oi_change_pct') or snapshot.get('oi_change_1h')))
    exchange_flow_score = _float(snapshot.get('exchange_flow_score'))
    binance_derivatives_score = _float(snapshot.get('binance_derivatives_score'))
    etf_flow_score = _float(snapshot.get('etf_flow_score'))
    stablecoin_liquidity_score = _float(snapshot.get('stablecoin_liquidity_score'))
    risk_component = _float(snapshot.get('score_risk'))
    data_quality = str(snapshot.get('data_quality_status') or 'UNKNOWN')

    if data_quality == 'WARMUP':
        hard.append('DATA_WARMUP')
    if spread >= _float(cfg.get('entry_policy.spread_bps_block', 10), 10):
        hard.append('SPREAD_TOO_WIDE')
    elif spread >= _float(cfg.get('entry_policy.spread_bps_reduce', 6), 6):
        soft.append('SPREAD_WIDE_REDUCE_SIZE')

    if funding_abs > _float(cfg.get('entry_policy.funding_abs_block', 0.0008), 0.0008):
        hard.append('FUNDING_ABS_BLOCK')
    elif funding_abs > _float(cfg.get('entry_policy.funding_abs_reduce', 0.0005), 0.0005):
        soft.append('FUNDING_ELEVATED_REDUCE_SIZE')

    if oi_chg_abs > _float(cfg.get('entry_policy.oi_change_abs_block', 0.08), 0.08):
        hard.append('OI_CHANGE_ABS_BLOCK')
    elif oi_chg_abs > _float(cfg.get('entry_policy.oi_change_abs_reduce', 0.04), 0.04):
        soft.append('OI_EXPANSION_REDUCE_SIZE')

    if exchange_flow_score <= -_float(cfg.get('entry_policy.exchange_flow_sell_pressure_block', 0.75), 0.75):
        hard.append('EXCHANGE_FLOW_SELL_PRESSURE_BLOCK')
    elif exchange_flow_score <= -_float(cfg.get('entry_policy.exchange_flow_sell_pressure_reduce', 0.40), 0.40):
        soft.append('EXCHANGE_FLOW_SELL_PRESSURE_REDUCE_SIZE')

    if abs(binance_derivatives_score) >= _float(cfg.get('entry_policy.binance_derivatives_crowding_block', 0.90), 0.90):
        hard.append('BINANCE_DERIVATIVES_CROWDING_BLOCK')
    elif abs(binance_derivatives_score) >= _float(cfg.get('entry_policy.binance_derivatives_crowding_reduce', 0.65), 0.65):
        soft.append('BINANCE_DERIVATIVES_CROWDING_REDUCE_SIZE')

    if etf_flow_score <= -_float(cfg.get('entry_policy.etf_outflow_block', 0.85), 0.85):
        hard.append('ETF_OUTFLOW_BLOCK')
    elif etf_flow_score <= -_float(cfg.get('entry_policy.etf_outflow_reduce', 0.45), 0.45):
        soft.append('ETF_OUTFLOW_REDUCE_SIZE')

    if stablecoin_liquidity_score <= -_float(cfg.get('entry_policy.stablecoin_liquidity_contraction_block', 0.85), 0.85):
        hard.append('STABLECOIN_LIQUIDITY_CONTRACTION_BLOCK')
    elif stablecoin_liquidity_score <= -_float(cfg.get('entry_policy.stablecoin_liquidity_contraction_reduce', 0.45), 0.45):
        soft.append('STABLECOIN_LIQUIDITY_CONTRACTION_REDUCE_SIZE')

    if risk_component <= -_float(cfg.get('entry_policy.risk_score_reduce', 0.45), 0.45):
        soft.append('LOW_RISK_SCORE_REDUCE_SIZE')

    risk_level = 'blocked' if hard else 'reduced' if soft else 'normal'
    return sorted(set(hard)), sorted(set(soft)), risk_level


def _direction_permission(snapshot: dict[str, Any], side: str) -> tuple[bool, bool, list[str]]:
    """Additional directional permission checks for long/short setups."""
    reasons: list[str] = []
    exchange_flow_score = _float(snapshot.get('exchange_flow_score'))
    etf_flow_score = _float(snapshot.get('etf_flow_score'))
    stablecoin_liquidity_score = _float(snapshot.get('stablecoin_liquidity_score'))
    binance_derivatives_score = _float(snapshot.get('binance_derivatives_score'))

    allow_long = True
    allow_short = True

    if exchange_flow_score <= -0.60 and side == 'LONG':
        allow_long = False
        reasons.append('LONG_BLOCKED_BY_EXCHANGE_SELL_PRESSURE')
    if etf_flow_score <= -0.65 and side == 'LONG':
        allow_long = False
        reasons.append('LONG_BLOCKED_BY_ETF_OUTFLOW')
    if stablecoin_liquidity_score <= -0.65 and side == 'LONG':
        allow_long = False
        reasons.append('LONG_BLOCKED_BY_LIQUIDITY_CONTRACTION')

    # Strong spot/ETF support makes fresh shorts lower quality unless price score is very bearish.
    if side == 'SHORT' and exchange_flow_score >= 0.60 and etf_flow_score >= 0.35:
        allow_short = False
        reasons.append('SHORT_BLOCKED_BY_SPOT_ACCUMULATION_AND_ETF_SUPPORT')
    if side == 'SHORT' and stablecoin_liquidity_score >= 0.70 and etf_flow_score >= 0.45:
        allow_short = False
        reasons.append('SHORT_BLOCKED_BY_RISK_ON_LIQUIDITY')

    # Very positive derivatives positioning can also mean long crowding; keep it as a warning unless extreme.
    if side == 'LONG' and binance_derivatives_score >= 0.80:
        reasons.append('LONG_CROWDED_DERIVATIVES_WARNING')

    return allow_long, allow_short, reasons


def _entry_decision(snapshot: dict[str, Any], cfg: AppConfig, source_allowed: bool, source_blocks: list[str]) -> dict[str, Any]:
    blocks = list(source_blocks)
    warnings: list[str] = []
    score = _float(snapshot.get('score_total_score') or snapshot.get('total_score'))
    condition = str(snapshot.get('market_condition') or '')

    if not source_allowed:
        blocks.extend(source_blocks or ['DATA_SOURCE_NOT_TRADING_ALLOWED'])

    hard_risks, soft_risks, risk_level = _risk_policy(snapshot, cfg)
    blocks.extend(hard_risks)
    warnings.extend(soft_risks)

    bullish_threshold = _float(cfg.get('entry_policy.bullish_threshold', 0.58), 0.58)
    bearish_threshold = _float(cfg.get('entry_policy.bearish_threshold', -0.58), -0.58)
    side = 'FLAT'
    if score >= bullish_threshold and 'BULLISH' in condition:
        side = 'LONG'
    elif score <= bearish_threshold and 'BEARISH' in condition:
        side = 'SHORT'
    else:
        blocks.append('NO_SCORE_CONDITION_ALIGNMENT')

    allow_long_by_direction, allow_short_by_direction, directional_reasons = _direction_permission(snapshot, side)
    if side == 'LONG' and not allow_long_by_direction:
        blocks.extend(directional_reasons)
    elif side == 'SHORT' and not allow_short_by_direction:
        blocks.extend(directional_reasons)
    else:
        warnings.extend(directional_reasons)

    blocks = sorted(set(blocks))
    warnings = sorted(set(warnings))
    if blocks:
        risk_level = 'blocked'

    allowed = bool(side != 'FLAT' and not blocks)
    confidence = min(1.0, abs(score)) if side != 'FLAT' else min(0.5, abs(score))
    return {
        'side': side,
        'entry_allowed': allowed,
        'confidence': confidence,
        'blocks': blocks,
        'warnings': warnings,
        'risk_level': risk_level,
        'allow_long': bool(side == 'LONG' and allowed),
        'allow_short': bool(side == 'SHORT' and allowed),
        'allow_new_position': bool(allowed),
    }


def build_research_signal(snapshot: dict[str, Any], condition: dict[str, Any], cfg: AppConfig, *, source: str | None = None) -> dict[str, Any]:
    src = source or snapshot.get('data_source') or snapshot.get('source') or 'UNKNOWN'
    policy = classify_data_source(src)
    timestamp = str(snapshot.get('timestamp') or condition.get('timestamp') or '')
    symbol = str(snapshot.get('canonical_symbol') or snapshot.get('symbol') or 'BTC-PERP')
    timeframe = str(snapshot.get('timeframe') or cfg.get('data.timeframe', 'PT1H'))
    exchange_market = str(snapshot.get('exchange_market') or cfg.get('data.exchange_market', 'BTC-USD'))
    decision = _entry_decision(snapshot, cfg, policy.trading_allowed, policy.block_reasons)
    side = decision['side']
    profile_id = str(snapshot.get('profile_id') or snapshot.get('research_profile_id') or cfg.get('research.active_profile_id', 'default_review_profile'))
    profile_version = str(snapshot.get('profile_version') or cfg.get('research.profile_version', 'unknown'))
    config_version = str(snapshot.get('config_version') or cfg.get('project.version', 'unknown'))
    data_snapshot_id = snapshot.get('data_snapshot_id')
    feature_snapshot_id = snapshot.get('feature_snapshot_id')
    feature_matrix_sha256 = snapshot.get('feature_matrix_sha256')
    source_bundle_sha256 = snapshot.get('source_bundle_sha256')
    data_snapshot_manifest_sha256 = snapshot.get('data_snapshot_manifest_sha256')
    optional_data_health = snapshot.get('optional_data_health') if isinstance(snapshot.get('optional_data_health'), dict) else {}
    manifest = snapshot.get('feature_snapshot_manifest') if isinstance(snapshot.get('feature_snapshot_manifest'), dict) else {}
    data_snapshot_id = data_snapshot_id or manifest.get('data_snapshot_id')
    feature_snapshot_id = feature_snapshot_id or manifest.get('feature_snapshot_id')
    feature_matrix_sha256 = feature_matrix_sha256 or manifest.get('feature_matrix_sha256')
    source_bundle_sha256 = source_bundle_sha256 or manifest.get('source_bundle_sha256')
    data_snapshot_manifest_sha256 = data_snapshot_manifest_sha256 or manifest.get('data_snapshot_manifest_sha256')
    optional_data_health = optional_data_health or manifest.get('optional_data_health', {})
    raw_id = f'{symbol}|{timeframe}|{timestamp}|{src}|{side}|{profile_id}|{feature_snapshot_id}|{feature_matrix_sha256}'
    signal_id = hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:24]
    scenarios = build_scenarios(snapshot).to_dict()
    score_total = _float(snapshot.get('score_total_score') or snapshot.get('total_score'))
    return {
        'signal_id': signal_id,
        'research_signal_id': signal_id,
        'signal_version': RESEARCH_SIGNAL_LINEAGE_VERSION,
        'profile_id': profile_id,
        'profile_version': profile_version,
        'config_version': config_version,
        'data_snapshot_id': data_snapshot_id,
        'feature_snapshot_id': feature_snapshot_id,
        'feature_matrix_sha256': feature_matrix_sha256,
        'source_bundle_sha256': source_bundle_sha256,
        'data_snapshot_manifest_sha256': data_snapshot_manifest_sha256,
        'market_thesis_note_id': snapshot.get('market_thesis_note_id'),
        'market_thesis_note_sha256': snapshot.get('market_thesis_note_sha256'),
        'optional_data_health': optional_data_health,
        'missing_optional_source_count': snapshot.get('missing_optional_source_count') or manifest.get('missing_optional_source_count'),
        'stale_optional_source_count': snapshot.get('stale_optional_source_count') or manifest.get('stale_optional_source_count'),
        'live_candidate_eligible': bool(snapshot.get('live_candidate_eligible', manifest.get('live_candidate_eligible', False))),
        'created_at_utc': utc_now_canonical(),
        'timestamp': timestamp,
        'symbol': symbol,
        'timeframe': timeframe,
        'exchange_market': exchange_market,
        'data_source': policy.source,
        'data_source_role': policy.role,
        'data_quality_status': str(snapshot.get('data_quality_status') or 'UNKNOWN'),
        'data_freshness_sec': snapshot.get('data_freshness_sec'),
        'stale_optional_data': bool(snapshot.get('stale_optional_data', False)),
        'missing_optional_data_neutral': bool(snapshot.get('missing_optional_data_neutral', False)),
        'trading_allowed_by_data_source': policy.trading_allowed,
        'close': snapshot.get('close'),
        'score_total': score_total,
        'score_bias': str(snapshot.get('score_bias') or snapshot.get('bias') or 'NEUTRAL'),
        'market_regime': str(snapshot.get('market_regime') or 'UNKNOWN'),
        'market_condition': str(snapshot.get('market_condition') or condition.get('final_condition') or 'UNKNOWN'),
        'mtf_bias': str(snapshot.get('mtf_bias') or 'UNKNOWN'),
        'mtf_alignment_score': _float(snapshot.get('mtf_alignment_score')),
        'entry_side': side,
        'entry_allowed': bool(decision['entry_allowed']),
        'entry_confidence': decision['confidence'],
        'block_reasons': decision['blocks'],
        'risk_warnings': decision['warnings'],
        'score_components': {
            'price': _float(snapshot.get('score_structure')) + _float(snapshot.get('score_momentum')),
            'structure': snapshot.get('score_structure'),
            'momentum': snapshot.get('score_momentum'),
            'derivatives': snapshot.get('score_derivatives'),
            'exchange_flow': snapshot.get('score_exchange_flow'),
            'etf_flow': snapshot.get('score_etf_flow'),
            'stablecoin_liquidity': snapshot.get('score_stablecoin_liquidity'),
            'risk': snapshot.get('score_risk'),
            'onchain': snapshot.get('score_onchain'),
        },
        'features': {
            'price_trend_1h': snapshot.get('mtf_1h_trend'),
            'price_trend_4h': snapshot.get('mtf_4h_trend'),
            'oi_change_1h': snapshot.get('oi_change_1h') or snapshot.get('oi_change_pct'),
            'oi_change_4h': snapshot.get('oi_change_4h') or snapshot.get('oi_change_4h_pct'),
            'funding_rate': snapshot.get('funding_rate'),
            'binance_derivatives_score': snapshot.get('binance_derivatives_score'),
            'exchange_flow_score': snapshot.get('exchange_flow_score'),
            'etf_flow_score': snapshot.get('etf_flow_score'),
            'stablecoin_liquidity_score': snapshot.get('stablecoin_liquidity_score'),
            'exchange_netflow_1d': snapshot.get('btc_exchange_netflow'),
            'exchange_netflow_zscore_30d': snapshot.get('exchange_netflow_zscore_30d'),
            'etf_flow_1d': snapshot.get('total_flow_usd_m'),
            'etf_flow_5d': snapshot.get('etf_flow_5d_sum'),
            'stablecoin_supply_change_7d': snapshot.get('stablecoin_total_mcap_7d_change'),
            'taker_buy_sell_ratio': snapshot.get('taker_buy_sell_ratio'),
            'top_trader_long_short_ratio': snapshot.get('top_trader_position_long_short_ratio'),
        },
        'trade_permission': {
            'allow_long': bool(decision['allow_long']),
            'allow_short': bool(decision['allow_short']),
            'allow_new_position': bool(decision['allow_new_position']),
            'risk_level': decision['risk_level'],
            'risk_warnings': decision['warnings'],
            'block_reasons': decision['blocks'],
            'live_candidate_eligible': bool(snapshot.get('live_candidate_eligible', False)),
            'missing_optional_data_neutral': bool(snapshot.get('missing_optional_data_neutral', False)),
            'stale_optional_data': bool(snapshot.get('stale_optional_data', False)),
        },
        'price_context': snapshot.get('price_context') or {},
        'scenarios': scenarios,
        'snapshot': snapshot,
        'version': RESEARCH_SIGNAL_V2_VERSION,
    }
