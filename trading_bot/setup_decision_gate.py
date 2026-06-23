from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from scripts.json_utils import load_json, now_utc_iso, save_json


def run_setup_decision_gate(
    research_decision: Dict[str, Any],
    storage_dir: str | Path = "storage",
) -> Dict[str, Any]:
    storage_path = Path(storage_dir)

    decision_type = str(research_decision.get("decision_type") or "").upper() if isinstance(research_decision, dict) else ""
    decision_source = research_decision.get("decision_source") if isinstance(research_decision, dict) else None

    if decision_type == "OBSERVE_ONLY":
        result = _result(
            status="OBSERVE_ONLY",
            allowed=False,
            setup_type=None,
            decision=None,
            weight=None,
            reason="Research decision is OBSERVE_ONLY. No paper watch should be created.",
            decision_type=decision_type,
            decision_source=decision_source,
        )
        save_json(storage_path / "setup_decision_filter_result.json", result)
        return result

    if decision_type in {"NO_DECISION", "ERROR"}:
        result = _result(
            status="NO_VALID_DECISION",
            allowed=False,
            setup_type=None,
            decision=None,
            weight=None,
            reason=f"Research decision type is {decision_type}. No setup allowed.",
            decision_type=decision_type,
            decision_source=decision_source,
        )
        save_json(storage_path / "setup_decision_filter_result.json", result)
        return result

    setup = research_decision.get("conditional_setup", {}) if isinstance(research_decision, dict) else {}
    setup_type = setup.get("setup_type") if isinstance(setup, dict) else None

    weight_report = load_json(storage_path / "setup_weight_report.json", default={})
    setups = weight_report.get("setups", []) if isinstance(weight_report, dict) else []

    match = None

    for item in setups if isinstance(setups, list) else []:
        if isinstance(item, dict) and item.get("setup_type") == setup_type:
            match = item
            break

    if not setup_type:
        result = _result(
            status="NO_CONDITIONAL_SETUP",
            allowed=False,
            setup_type=setup_type,
            decision=None,
            weight=None,
            reason="No conditional setup found.",
            decision_type=decision_type,
            decision_source=decision_source,
        )

    elif match is None:
        result = _result(
            status="NO_SETUP_WEIGHT_FOUND",
            allowed=True,
            setup_type=setup_type,
            decision=None,
            weight=None,
            reason="No historical setup weight found. Allowing observation trade.",
            decision_type=decision_type,
            decision_source=decision_source,
        )

    elif match.get("setup_weight_decision") == "DISABLED":
        result = _result(
            status="BLOCKED",
            allowed=False,
            setup_type=setup_type,
            decision="DISABLED",
            weight=match.get("final_weight"),
            reason="Setup is disabled by performance history.",
            decision_type=decision_type,
            decision_source=decision_source,
        )

    else:
        result = _result(
            status="ALLOWED",
            allowed=True,
            setup_type=setup_type,
            decision=match.get("setup_weight_decision"),
            weight=match.get("final_weight"),
            reason=None,
            decision_type=decision_type,
            decision_source=decision_source,
        )

    save_json(storage_path / "setup_decision_filter_result.json", result)
    return result


def _result(
    status: str,
    allowed: bool,
    setup_type: str | None,
    decision: str | None,
    weight: Any,
    reason: str | None,
    decision_type: str | None,
    decision_source: str | None,
) -> Dict[str, Any]:
    return {
        "status": status,
        "timestamp_utc": now_utc_iso(),
        "allowed_to_create_watch": allowed,
        "setup_type": setup_type,
        "setup_weight_decision": decision,
        "final_weight": weight,
        "block_reason": reason,
        "decision_type": decision_type,
        "decision_source": decision_source,
    }