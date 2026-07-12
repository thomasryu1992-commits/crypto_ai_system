from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

try:
    from core.json_io import append_jsonl, atomic_write_json
    from core.time_utils import utc_now_iso
except Exception:  # pragma: no cover
    import json
    from datetime import datetime, timezone

    def utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def append_jsonl(path: str | Path, row: dict[str, Any]) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')

    def atomic_write_json(path: str | Path, data: Any) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding='utf-8')


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x)]
    if isinstance(value, (tuple, set)):
        return [str(x) for x in value if str(x)]
    if isinstance(value, str):
        return [value] if value else []
    return [str(value)]


def build_permission_gate_audit_record(
    signal_payload: Mapping[str, Any] | None,
    paper_result: Mapping[str, Any] | None,
    market_snapshot: Mapping[str, Any] | None = None,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    signal_payload = dict(signal_payload or {})
    paper_result = dict(paper_result or {})
    market_snapshot = dict(market_snapshot or {})
    permission = signal_payload.get('trade_permission') if isinstance(signal_payload.get('trade_permission'), Mapping) else {}
    risk_level = str(signal_payload.get('risk_level') or permission.get('risk_level') or 'normal').lower()
    if risk_level not in {'normal', 'reduced', 'blocked'}:
        risk_level = 'normal'
    signal = str(signal_payload.get('signal') or signal_payload.get('side') or 'NONE').upper()
    paper_status = str(paper_result.get('status') or 'UNKNOWN')
    active_position = paper_result.get('active_position') if isinstance(paper_result.get('active_position'), Mapping) else {}
    block_reasons = _as_list(signal_payload.get('block_reasons')) + _as_list(permission.get('block_reasons'))
    if paper_status == 'BLOCKED_BY_PERMISSION_GATE' and not block_reasons:
        block_reasons += _as_list(paper_result.get('reasons'))
    risk_warnings = _as_list(signal_payload.get('risk_warnings')) + _as_list(permission.get('risk_warnings'))
    reasons = _as_list(signal_payload.get('reasons')) + _as_list(signal_payload.get('reason')) + _as_list(paper_result.get('reasons'))
    try:
        multiplier = float(signal_payload.get('position_size_multiplier', permission.get('position_size_multiplier', 0.0)) or 0.0)
    except Exception:
        multiplier = 0.0
    return {
        'created_at': created_at or utc_now_iso(),
        'symbol': market_snapshot.get('symbol') or signal_payload.get('symbol') or active_position.get('symbol'),
        'last_price': market_snapshot.get('last_close') or market_snapshot.get('close') or active_position.get('entry_price'),
        'signal': signal,
        'confidence': signal_payload.get('confidence'),
        'permission_gate_applied': bool(signal_payload.get('permission_gate_applied', False)),
        'allow_long': bool(signal_payload.get('allow_long', permission.get('allow_long', False))),
        'allow_short': bool(signal_payload.get('allow_short', permission.get('allow_short', False))),
        'allow_new_position': bool(signal_payload.get('allow_new_position', permission.get('allow_new_position', False))),
        'risk_level': risk_level,
        'position_size_multiplier': multiplier,
        'paper_status': paper_status,
        'position_opened': paper_status == 'POSITION_OPENED',
        'research_signal_id': signal_payload.get('research_signal_id') or permission.get('research_signal_id'),
        'research_signal_version': signal_payload.get('research_signal_version') or permission.get('signal_version'),
        'block_reasons': sorted(set(map(str, block_reasons))),
        'risk_warnings': sorted(set(map(str, risk_warnings))),
        'reasons': sorted(set(map(str, reasons))),
    }


def write_permission_gate_audit_record(record: Mapping[str, Any], *, audit_path: str | Path, latest_path: str | Path) -> dict[str, Any]:
    row = dict(record)
    append_jsonl(audit_path, row)
    atomic_write_json(latest_path, row)
    return row


# Step241 compatibility export for legacy root trading.permission_audit callers.
def log_permission_gate_audit(
    signal_payload: Mapping[str, Any] | None,
    paper_result: Mapping[str, Any] | None,
    market_snapshot: Mapping[str, Any] | None = None,
    *,
    audit_path: str | Path = "data/stores/permission_gate_audit.jsonl",
    latest_path: str | Path = "data/reports/permission_gate_audit_latest.json",
) -> dict[str, Any]:
    record = build_permission_gate_audit_record(signal_payload, paper_result, market_snapshot)
    return write_permission_gate_audit_record(record, audit_path=audit_path, latest_path=latest_path)
