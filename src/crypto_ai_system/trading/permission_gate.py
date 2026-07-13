from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable, Mapping


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on', 'allowed'}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except Exception:
        return default


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x)]
    if isinstance(value, tuple) or isinstance(value, set):
        return [str(x) for x in value if str(x)]
    if isinstance(value, str):
        return [value] if value else []
    return [str(value)]


def _cfg_get(cfg: Any, path: str, default: Any) -> Any:
    if cfg is None:
        return default
    getter = getattr(cfg, 'get', None)
    if callable(getter):
        try:
            return getter(path, default)
        except Exception:
            return default
    return default


def _extract_signal(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(payload or {})
    if isinstance(data.get('research_signal'), Mapping):
        return dict(data['research_signal'])
    return data


def _infer_side(signal: Mapping[str, Any], permission: Mapping[str, Any]) -> str:
    side = str(signal.get('entry_side') or signal.get('side') or signal.get('signal') or 'FLAT').upper()
    if side in {'LONG', 'SHORT'}:
        return side
    allow_long = _to_bool(permission.get('allow_long'), False)
    allow_short = _to_bool(permission.get('allow_short'), False)
    if allow_long and not allow_short:
        return 'LONG'
    if allow_short and not allow_long:
        return 'SHORT'
    return 'FLAT'


@dataclass
class TradePermissionDecision:
    permission_gate_applied: bool
    side: str
    entry_allowed: bool
    allow_long: bool
    allow_short: bool
    allow_new_position: bool
    risk_level: str
    position_size_multiplier: float
    confidence: float
    block_reasons: list[str]
    risk_warnings: list[str]
    reasons: list[str]
    research_signal_id: str | None = None
    signal_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_trade_permission(payload: Mapping[str, Any] | None, cfg: Any = None) -> TradePermissionDecision:
    """Normalize ResearchSignal v2 trade_permission into a Trading Bot gate decision.

    This function is intentionally conservative: a blocked risk level, missing
    side-specific permission, or entry_allowed=False always returns FLAT / no
    new position. Reduced risk remains tradable but lowers position sizing.
    """
    signal = _extract_signal(payload)
    permission = dict(signal.get('trade_permission') or {})
    applied = bool(permission or 'entry_allowed' in signal or 'entry_side' in signal)

    side = _infer_side(signal, permission)
    risk_level = str(permission.get('risk_level') or signal.get('risk_level') or 'normal').lower()
    if risk_level not in {'normal', 'reduced', 'blocked'}:
        risk_level = 'normal'

    entry_allowed = _to_bool(signal.get('entry_allowed'), _to_bool(permission.get('allow_new_position'), False))
    allow_long = _to_bool(permission.get('allow_long'), side == 'LONG' and entry_allowed)
    allow_short = _to_bool(permission.get('allow_short'), side == 'SHORT' and entry_allowed)
    allow_new_position = _to_bool(permission.get('allow_new_position'), entry_allowed)

    blocks = []
    blocks.extend(_as_list(signal.get('block_reasons')))
    blocks.extend(_as_list(permission.get('block_reasons')))
    warnings = []
    warnings.extend(_as_list(signal.get('risk_warnings')))
    warnings.extend(_as_list(permission.get('risk_warnings')))

    if risk_level == 'blocked':
        blocks.append('RESEARCH_SIGNAL_RISK_LEVEL_BLOCKED')
    if not allow_new_position:
        blocks.append('RESEARCH_SIGNAL_DISALLOWS_NEW_POSITION')
    if side == 'LONG' and not allow_long:
        blocks.append('RESEARCH_SIGNAL_DISALLOWS_LONG')
    if side == 'SHORT' and not allow_short:
        blocks.append('RESEARCH_SIGNAL_DISALLOWS_SHORT')
    if side not in {'LONG', 'SHORT'}:
        blocks.append('RESEARCH_SIGNAL_NO_DIRECTIONAL_ENTRY')
    if not entry_allowed:
        blocks.append('RESEARCH_SIGNAL_ENTRY_NOT_ALLOWED')

    if risk_level == 'blocked':
        multiplier = _to_float(_cfg_get(cfg, 'trading.risk_level_blocked_position_multiplier', 0.0), 0.0)
    elif risk_level == 'reduced':
        multiplier = _to_float(_cfg_get(cfg, 'trading.risk_level_reduced_position_multiplier', 0.5), 0.5)
    else:
        multiplier = 1.0

    multiplier = max(0.0, min(1.0, multiplier))
    allowed = bool(applied and side in {'LONG', 'SHORT'} and entry_allowed and allow_new_position and not blocks and multiplier > 0)
    final_side = side if allowed else 'FLAT'
    if not allowed and risk_level != 'blocked' and blocks:
        # The permission gate is a hard final authority. Any block forces blocked state.
        risk_level = 'blocked'
        multiplier = 0.0

    confidence = _to_float(signal.get('entry_confidence') or signal.get('confidence'), 0.0)
    if confidence > 1.0:
        confidence = confidence / 100.0
    confidence = max(0.0, min(1.0, confidence))

    reasons = []
    if allowed:
        reasons.append('research_signal_v2_permission_approved')
        if risk_level == 'reduced':
            reasons.append('research_signal_v2_reduced_risk_position_size')
    else:
        reasons.append('research_signal_v2_permission_blocked')
    reasons.extend(sorted(set(blocks + warnings)))

    return TradePermissionDecision(
        permission_gate_applied=applied,
        side=final_side,
        entry_allowed=allowed,
        allow_long=bool(allow_long and not blocks and side == 'LONG'),
        allow_short=bool(allow_short and not blocks and side == 'SHORT'),
        allow_new_position=bool(allowed),
        risk_level=risk_level,
        position_size_multiplier=multiplier if allowed else 0.0,
        confidence=confidence,
        block_reasons=sorted(set(blocks)),
        risk_warnings=sorted(set(warnings)),
        reasons=reasons,
        research_signal_id=str(signal.get('signal_id')) if signal.get('signal_id') else None,
        signal_version=str(signal.get('version')) if signal.get('version') else None,
    )


def trading_signal_payload_from_research_signal(payload: Mapping[str, Any] | None, cfg: Any = None) -> dict[str, Any]:
    decision = evaluate_trade_permission(payload, cfg=cfg)
    if not decision.permission_gate_applied:
        return {
            'signal': 'NONE',
            'confidence': 0,
            'reasons': ['research_signal_v2_not_available'],
            'permission_gate_applied': False,
            'allow_new_position': False,
            'risk_level': 'blocked',
            'position_size_multiplier': 0.0,
        }
    return {
        'signal': decision.side if decision.entry_allowed else 'NONE',
        'confidence': int(round(decision.confidence * 100)),
        'reasons': decision.reasons,
        'permission_gate_applied': True,
        'research_signal_id': decision.research_signal_id,
        'research_signal_version': decision.signal_version,
        'allow_long': decision.allow_long,
        'allow_short': decision.allow_short,
        'allow_new_position': decision.allow_new_position,
        'risk_level': decision.risk_level,
        'position_size_multiplier': decision.position_size_multiplier,
        'block_reasons': decision.block_reasons,
        'risk_warnings': decision.risk_warnings,
        'trade_permission': decision.to_dict(),
    }


# Step241 compatibility export for legacy root trading.permission_gate callers.
def signal_payload_from_research_signal(payload: Mapping[str, Any] | None, cfg: Any = None) -> dict[str, Any]:
    return trading_signal_payload_from_research_signal(payload, cfg=cfg)
