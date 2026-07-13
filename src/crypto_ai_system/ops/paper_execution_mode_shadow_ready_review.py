from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.final_config_apply_gate_review_only import (
    execute_final_config_apply_gate_review_only,
)

STEP226_STATUS_OK = "STEP226_V5_PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW_ONLY_OK"
STEP226_VALIDATION_OK = "STEP226_V5_PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW_ONLY_VALIDATION_OK"
SHADOW_READY_MODE = "PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW_ONLY"


@dataclass
class Step226Result:
    status: str
    root: str
    source_step225_result_path: str
    shadow_ready_decisions_json_path: str
    shadow_ready_decisions_jsonl_path: str
    shadow_ready_decisions_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_final_gate_decision_count: int
    shadow_ready_decision_count: int
    shadow_ready_review_ready_count: int
    shadow_ready_blocked_count: int
    shadow_ready_watchlist_count: int
    paper_execution_mode_shadow_ready_review_created: bool
    shadow_ready_mode: str
    shadow_ready_review_only: bool
    shadow_ready_mode_allowed: bool
    shadow_ready_mode_enabled: bool
    paper_execution_enabled: bool
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    adapter_routing_enabled: bool
    shadow_execution_enabled: bool
    config_apply_allowed: bool
    config_applied: bool
    config_activation_allowed: bool
    config_activated: bool
    limited_live_review_allowed: bool
    live_trading_allowed: bool
    strategy_registry_write_allowed: bool
    promotion_allowed: bool
    auto_strategy_promotion: bool
    external_api_call_performed: bool
    live_order_executed: bool
    real_adapter_call_performed: bool
    telegram_real_send: bool
    production_cutover_executable: bool
    live_mode_enable_allowed: bool
    decisions: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step226ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step225_present: bool
    shadow_ready_json_exists: bool
    shadow_ready_jsonl_exists: bool
    shadow_ready_csv_exists: bool
    markdown_report_exists: bool
    source_final_gate_decisions_present: bool
    shadow_ready_decisions_present: bool
    shadow_ready_review_created: bool
    shadow_ready_mode_review_only: bool
    no_shadow_ready_mode_allowed: bool
    no_shadow_ready_mode_enabled: bool
    no_paper_execution_enabled: bool
    no_paper_order_execution: bool
    no_adapter_routing: bool
    no_shadow_execution: bool
    no_config_apply: bool
    no_live_trading: bool
    no_strategy_registry_write: bool
    no_live_side_effects: bool
    blocking_failure_count: int
    blocking_failures: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows) + ("\n" if rows else ""), encoding="utf-8")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["shadow_ready_decision_id", "shadow_ready_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["shadow_ready_checklist"] = json.dumps(out.get("shadow_ready_checklist", {}), sort_keys=True)
            out["shadow_ready_blockers"] = "|".join(out.get("shadow_ready_blockers", []))
            out["shadow_ready_warnings"] = "|".join(out.get("shadow_ready_warnings", []))
            writer.writerow(out)


def _ensure_step225(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step225_final_config_apply_gate_review_only_latest.json"
    if not path.exists():
        execute_final_config_apply_gate_review_only(root, write_output=True)
    return _load_json(path)


def _load_decisions(step225: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = Path(step225.get("final_gate_decisions_json_path", ""))
    if path.exists():
        return list(_load_json(path).get("decisions", []) or [])
    return list(step225.get("decisions", []) or [])


def _shadow_decision(src: Dict[str, Any]) -> Dict[str, Any]:
    checklist = {
        "source_final_gate_review_ready": src.get("final_gate_status") == "FINAL_CONFIG_APPLY_GATE_REVIEW_READY",
        "source_final_gate_mode_review_only": src.get("final_gate_mode") == "FINAL_CONFIG_APPLY_GATE_REVIEW_ONLY",
        "source_final_gate_decision_created": src.get("final_gate_decision_created") is True,
        "source_final_apply_gate_passed_false": src.get("final_apply_gate_passed") is False,
        "source_config_apply_allowed_false": src.get("config_apply_allowed") is False,
        "source_config_applied_false": src.get("config_applied") is False,
        "source_paper_execution_enabled_false": src.get("paper_execution_enabled") is False,
        "source_paper_order_execution_enabled_false": src.get("paper_order_execution_enabled") is False,
        "source_adapter_routing_enabled_false": src.get("adapter_routing_enabled") is False,
        "source_live_trading_allowed_false": src.get("live_trading_allowed") is False,
    }
    blockers = list(src.get("final_gate_blockers", []) or [])
    for key, ok in checklist.items():
        if not ok:
            blockers.append(key.upper() + "_FAILED")
    blockers.append("STEP226_REVIEW_ONLY_NO_SHADOW_READY_ENABLEMENT")
    blockers = sorted(set(blockers))
    hard = [b for b in blockers if b != "STEP226_REVIEW_ONLY_NO_SHADOW_READY_ENABLEMENT"]
    status = "PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW_READY" if not hard and all(checklist.values()) else "PAPER_EXECUTION_MODE_SHADOW_READY_BLOCKED"
    did = "shready_" + hashlib.sha1(
        "|".join([
            str(src.get("final_gate_decision_id", "")),
            str(src.get("activation_apply_stub_id", "")),
            str(src.get("observation_id", "")),
        ]).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "shadow_ready_decision_id": did,
        "final_gate_decision_id": str(src.get("final_gate_decision_id", "")),
        "activation_apply_stub_id": str(src.get("activation_apply_stub_id", "")),
        "activation_candidate_id": str(src.get("activation_candidate_id", "")),
        "config_draft_id": str(src.get("config_draft_id", "")),
        "enablement_plan_id": str(src.get("enablement_plan_id", "")),
        "approval_validation_id": str(src.get("approval_validation_id", "")),
        "observation_id": str(src.get("observation_id", "")),
        "registry_id": str(src.get("registry_id", "")),
        "comparison_group": str(src.get("comparison_group", "")),
        "side": str(src.get("side", "")),
        "source_final_gate_status": str(src.get("final_gate_status", "")),
        "shadow_ready_mode": SHADOW_READY_MODE,
        "shadow_ready_status": status,
        "shadow_ready_checklist": checklist,
        "shadow_ready_blockers": blockers,
        "shadow_ready_warnings": sorted(set(list(src.get("final_gate_warnings", []) or []) + [
            "SHADOW_READY_REVIEW_ONLY_NO_PAPER_EXECUTION",
            "STEP227_REQUIRED_FOR_PAPER_EXECUTION_MODE_PRE_ENABLEMENT_AUDIT",
        ])),
        "next_required_step": "STEP227_PAPER_EXECUTION_MODE_PRE_ENABLEMENT_AUDIT_REVIEW_ONLY" if status.endswith("REVIEW_READY") else "DO_NOT_CREATE_PRE_ENABLEMENT_AUDIT_UNTIL_BLOCKERS_RESOLVED",
        "shadow_ready_decision_created": True,
        "shadow_ready_mode_allowed": False,
        "shadow_ready_mode_enabled": False,
        "paper_execution_enabled": False,
        "paper_order_execution_enabled": False,
        "paper_trade_execution_enabled": False,
        "adapter_routing_enabled": False,
        "shadow_execution_enabled": False,
        "config_apply_allowed": False,
        "config_applied": False,
        "config_activation_allowed": False,
        "config_activated": False,
        "limited_live_review_allowed": False,
        "live_trading_allowed": False,
        "strategy_registry_write_allowed": False,
        "promotion_allowed": False,
        "live_order_executed": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _summary(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        for blocker in row.get("shadow_ready_blockers", []):
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _render_md(result: Step226Result) -> str:
    lines = [
        "# Step226 v5 Paper Execution Mode Shadow-Ready Review-Only",
        "",
        "Step226 creates paper execution mode shadow-ready review decisions from Step225 final config apply gate decisions.",
        "This is review-only and does not enable paper execution, order execution, adapter routing, shadow execution, or live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_final_gate_decision_count: {result.source_final_gate_decision_count}",
        f"- shadow_ready_decision_count: {result.shadow_ready_decision_count}",
        f"- shadow_ready_review_ready_count: {result.shadow_ready_review_ready_count}",
        f"- shadow_ready_blocked_count: {result.shadow_ready_blocked_count}",
        f"- shadow_ready_mode: `{result.shadow_ready_mode}`",
        f"- shadow_ready_mode_enabled: {result.shadow_ready_mode_enabled}",
        f"- paper_execution_enabled: {result.paper_execution_enabled}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        f"- shadow_execution_enabled: {result.shadow_execution_enabled}",
        "",
        "## Decisions",
    ]
    for d in result.decisions:
        blockers = ", ".join(d.get("shadow_ready_blockers", [])) if d.get("shadow_ready_blockers") else "NO_BLOCKER"
        lines.append(f"- `{d.get('comparison_group','')}` {d.get('side','')}: status={d.get('shadow_ready_status')}, blockers={blockers}")
    return "\n".join(lines) + "\n"


def execute_paper_execution_mode_shadow_ready_review(root: str | Path, *, write_output: bool = True) -> Step226Result:
    root_path = Path(root).resolve()
    step225_path = root_path / "storage/latest/step225_final_config_apply_gate_review_only_latest.json"
    step225 = _ensure_step225(root_path)
    src_rows = _load_decisions(step225)
    rows = [_shadow_decision(r) for r in src_rows]

    json_path = root_path / "data/reports/step226_paper_execution_mode_shadow_ready_decisions.json"
    jsonl_path = root_path / "data/stores/step226_paper_execution_mode_shadow_ready_decisions.jsonl"
    csv_path = root_path / "data/reports/step226_paper_execution_mode_shadow_ready_decisions.csv"
    md_path = root_path / "data/reports/step226_paper_execution_mode_shadow_ready_review_report.md"
    latest_path = root_path / "storage/latest/step226_paper_execution_mode_shadow_ready_review_latest.json"

    result = Step226Result(
        status=STEP226_STATUS_OK,
        root=str(root_path),
        source_step225_result_path=str(step225_path),
        shadow_ready_decisions_json_path=str(json_path),
        shadow_ready_decisions_jsonl_path=str(jsonl_path),
        shadow_ready_decisions_csv_path=str(csv_path),
        markdown_report_path=str(md_path),
        latest_result_path=str(latest_path),
        source_final_gate_decision_count=len(src_rows),
        shadow_ready_decision_count=len(rows),
        shadow_ready_review_ready_count=sum(1 for r in rows if r.get("shadow_ready_status") == "PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW_READY"),
        shadow_ready_blocked_count=sum(1 for r in rows if r.get("shadow_ready_status") == "PAPER_EXECUTION_MODE_SHADOW_READY_BLOCKED"),
        shadow_ready_watchlist_count=sum(1 for r in rows if r.get("shadow_ready_status") == "PAPER_EXECUTION_MODE_SHADOW_READY_WATCHLIST"),
        paper_execution_mode_shadow_ready_review_created=True,
        shadow_ready_mode=SHADOW_READY_MODE,
        shadow_ready_review_only=True,
        shadow_ready_mode_allowed=False,
        shadow_ready_mode_enabled=False,
        paper_execution_enabled=False,
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        adapter_routing_enabled=False,
        shadow_execution_enabled=False,
        config_apply_allowed=False,
        config_applied=False,
        config_activation_allowed=False,
        config_activated=False,
        limited_live_review_allowed=False,
        live_trading_allowed=False,
        strategy_registry_write_allowed=False,
        promotion_allowed=False,
        auto_strategy_promotion=False,
        external_api_call_performed=False,
        live_order_executed=False,
        real_adapter_call_performed=False,
        telegram_real_send=False,
        production_cutover_executable=False,
        live_mode_enable_allowed=False,
        decisions=rows,
        blocker_summary=_summary(rows),
    )
    payload = result.to_dict()
    result.result_sha256 = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    if write_output:
        _write_json(json_path, {"decisions": rows})
        _write_jsonl(jsonl_path, rows)
        _write_csv(csv_path, rows)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_render_md(result), encoding="utf-8")
        _write_json(latest_path, result.to_dict())
    return result


def validate_paper_execution_mode_shadow_ready_review(root: str | Path) -> Step226ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step226_paper_execution_mode_shadow_ready_review_latest.json"
    if not result_path.exists():
        execute_paper_execution_mode_shadow_ready_review(root_path, write_output=True)
    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    rows = list(payload.get("decisions", []) or [])
    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step225_present": Path(payload.get("source_step225_result_path", "")).exists(),
        "shadow_ready_json_exists": Path(payload.get("shadow_ready_decisions_json_path", "")).exists(),
        "shadow_ready_jsonl_exists": Path(payload.get("shadow_ready_decisions_jsonl_path", "")).exists(),
        "shadow_ready_csv_exists": Path(payload.get("shadow_ready_decisions_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_final_gate_decisions_present": int(payload.get("source_final_gate_decision_count", 0)) > 0,
        "shadow_ready_decisions_present": int(payload.get("shadow_ready_decision_count", 0)) > 0 and bool(rows),
        "shadow_ready_review_created": payload.get("paper_execution_mode_shadow_ready_review_created") is True and all(r.get("shadow_ready_decision_created") is True for r in rows),
        "shadow_ready_mode_review_only": payload.get("shadow_ready_mode") == SHADOW_READY_MODE and all(r.get("shadow_ready_mode") == SHADOW_READY_MODE for r in rows),
        "no_shadow_ready_mode_allowed": payload.get("shadow_ready_mode_allowed") is False and all(r.get("shadow_ready_mode_allowed") is False for r in rows),
        "no_shadow_ready_mode_enabled": payload.get("shadow_ready_mode_enabled") is False and all(r.get("shadow_ready_mode_enabled") is False for r in rows),
        "no_paper_execution_enabled": payload.get("paper_execution_enabled") is False and all(r.get("paper_execution_enabled") is False for r in rows),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False and all(r.get("paper_order_execution_enabled") is False for r in rows),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False and all(r.get("adapter_routing_enabled") is False for r in rows),
        "no_shadow_execution": payload.get("shadow_execution_enabled") is False and all(r.get("shadow_execution_enabled") is False for r in rows),
        "no_config_apply": payload.get("config_apply_allowed") is False and payload.get("config_applied") is False,
        "no_live_trading": payload.get("live_trading_allowed") is False and all(r.get("live_trading_allowed") is False for r in rows),
        "no_strategy_registry_write": payload.get("strategy_registry_write_allowed") is False and all(r.get("strategy_registry_write_allowed") is False for r in rows),
        "no_live_side_effects": payload.get("live_order_executed") is False and payload.get("real_adapter_call_performed") is False and payload.get("telegram_real_send") is False and all(r.get("live_order_executed") is False for r in rows),
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step226ValidationResult(
        status=STEP226_VALIDATION_OK if not failures else "STEP226_V5_PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
