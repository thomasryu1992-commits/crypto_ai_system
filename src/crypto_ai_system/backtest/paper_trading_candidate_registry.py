from __future__ import annotations

import json, hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

STEP208_STATUS_OK = "STEP208_V5_PAPER_TRADING_CANDIDATE_REGISTRY_OK"
STEP208_COMPATIBILITY_MODE = "compat_stub"
STEP208_COMPATIBILITY_SCOPE = "Step208 compatibility backfill stub for Step209~237 artifact-chain validation only"


def _canonical_json(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def _sha256(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()

def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def execute_paper_trading_candidate_registry(root: str | Path, *, write_output: bool = True) -> Any:
    root = Path(root).resolve()
    latest = root / "storage/latest/step208_paper_trading_candidate_registry_latest.json"
    candidates: List[Dict[str, Any]] = [
        {
            "registry_id": "compat_stub_reg_synth_long_1h",
            "candidate_rank": 1,
            "comparison_group": "compat_stub_synthetic_long_1h_rr2",
            "timeframe": "1h",
            "rr": 2.0,
            "side": "LONG",
            "permission_mode": "research_signal_v2_permission_gate",
            "registry_status": "PAPER_CANDIDATE_REVIEW_ONLY",
            "paper_tracking_enabled": True,
            "paper_observation_days_required": 28,
            "min_paper_trades_required": 20,
            "expanded_oos_score": 99.0,
            "blockers": [],
        },
        {
            "registry_id": "compat_stub_reg_synth_short_1h",
            "candidate_rank": 2,
            "comparison_group": "compat_stub_synthetic_short_1h_rr2",
            "timeframe": "1h",
            "rr": 2.0,
            "side": "SHORT",
            "permission_mode": "research_signal_v2_permission_gate",
            "registry_status": "PAPER_CANDIDATE_REVIEW_ONLY",
            "paper_tracking_enabled": True,
            "paper_observation_days_required": 28,
            "min_paper_trades_required": 20,
            "expanded_oos_score": 98.0,
            "blockers": [],
        },
    ]
    result = {
        "status": STEP208_STATUS_OK,
        "compatibility_mode": STEP208_COMPATIBILITY_MODE,
        "compatibility_scope": STEP208_COMPATIBILITY_SCOPE,
        "canonical_step208_available": False,
        "compat_stub": True,
        "root": str(root),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "paper_order_execution_enabled": False,
        "paper_trade_execution_enabled": False,
        "live_trading_allowed": False,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    result["result_sha256"] = _sha256(_canonical_json({k:v for k,v in result.items() if k != "result_sha256"}))
    if write_output:
        _write_json(latest, result)
    return type("Step208Result", (), {"to_dict": lambda self: result, **result})()
