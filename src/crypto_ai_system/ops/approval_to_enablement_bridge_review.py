from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.operator_final_approval_intake_validator_review import (
    execute_operator_final_approval_intake_validator_review,
)

STEP232_STATUS_OK = "STEP232_V5_APPROVAL_TO_ENABLEMENT_BRIDGE_REVIEW_ONLY_OK"
STEP232_VALIDATION_OK = "STEP232_V5_APPROVAL_TO_ENABLEMENT_BRIDGE_REVIEW_ONLY_VALIDATION_OK"
BRIDGE_MODE = "APPROVAL_TO_ENABLEMENT_BRIDGE_REVIEW_ONLY"
APPROVED_STATUS = "APPROVED"


@dataclass
class Step232Result:
    status: str
    root: str
    source_step231_result_path: str
    bridge_records_json_path: str
    bridge_records_jsonl_path: str
    bridge_records_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_intake_record_count: int
    source_intake_valid_count: int
    bridge_record_count: int
    bridge_review_ready_count: int
    bridge_blocked_count: int
    bridge_watchlist_count: int
    approval_to_enablement_bridge_review_created: bool
    bridge_mode: str
    bridge_review_only: bool
    bridge_record_created: bool
    approval_bridge_passed: bool
    operator_final_approval_accepted: bool
    operator_final_approval_recorded: bool
    enablement_request_submit_allowed: bool
    enablement_request_submitted: bool
    paper_execution_enablement_allowed: bool
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
    bridge_records: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step232ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step231_present: bool
    bridge_records_json_exists: bool
    bridge_records_jsonl_exists: bool
    bridge_records_csv_exists: bool
    markdown_report_exists: bool
    source_intake_records_present: bool
    bridge_records_present: bool
    bridge_review_created: bool
    bridge_mode_review_only: bool
    no_approval_bridge_passed: bool
    no_operator_final_approval_accepted: bool
    no_operator_final_approval_recorded: bool
    no_enablement_request_submit_allowed: bool
    no_enablement_request_submitted: bool
    no_paper_execution_enablement_allowed: bool
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
    fields = list(rows[0].keys()) if rows else ["approval_to_enablement_bridge_record_id", "bridge_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("bridge_checklist", "bridge_context", "enablement_bridge_payload"):
                out[key] = json.dumps(out.get(key, {}), sort_keys=True)
            for key in ("bridge_blockers", "bridge_warnings"):
                out[key] = "|".join(out.get(key, []))
            writer.writerow(out)


def _ensure_step231(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step231_operator_final_approval_intake_validator_review_latest.json"
    if not path.exists():
        execute_operator_final_approval_intake_validator_review(root, write_output=True)
    return _load_json(path)


def _load_intake_records(step231: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = Path(step231.get("intake_records_json_path", ""))
    if path.exists():
        return list(_load_json(path).get("intake_records", []) or [])
    return list(step231.get("intake_records", []) or [])


def _bridge_record(src: Dict[str, Any]) -> Dict[str, Any]:
    checklist = {
        "source_intake_valid_review_only": src.get("intake_status") == "OPERATOR_FINAL_APPROVAL_INTAKE_VALID_REVIEW_ONLY",
        "source_intake_validator_mode_review_only": src.get("intake_validator_mode") == "OPERATOR_FINAL_APPROVAL_INTAKE_VALIDATOR_REVIEW_ONLY",
        "source_intake_record_created": src.get("intake_record_created") is True,
        "source_operator_final_approval_input_validated": src.get("operator_final_approval_input_validated") is True,
        "source_operator_final_approval_accepted_false": src.get("operator_final_approval_accepted") is False,
        "source_operator_final_approval_recorded_false": src.get("operator_final_approval_recorded") is False,
        "source_operator_final_approval_submitted_false": src.get("operator_final_approval_submitted") is False,
        "source_enablement_request_submit_allowed_false": src.get("enablement_request_submit_allowed") is False,
        "source_enablement_request_submitted_false": src.get("enablement_request_submitted") is False,
        "source_paper_execution_enablement_allowed_false": src.get("paper_execution_enablement_allowed") is False,
        "source_paper_execution_enabled_false": src.get("paper_execution_enabled") is False,
        "source_paper_order_execution_enabled_false": src.get("paper_order_execution_enabled") is False,
        "source_adapter_routing_enabled_false": src.get("adapter_routing_enabled") is False,
        "source_shadow_execution_enabled_false": src.get("shadow_execution_enabled") is False,
        "source_live_trading_allowed_false": src.get("live_trading_allowed") is False,
        "operator_approval_status_approved": src.get("operator_approval_status") == APPROVED_STATUS,
    }
    blockers = list(src.get("intake_blockers", []) or [])
    for key, ok in checklist.items():
        if not ok:
            blockers.append(key.upper() + "_FAILED")
    blockers.append("STEP232_REVIEW_ONLY_NO_ENABLEMENT_BRIDGE_PASS")
    blockers = sorted(set(blockers))
    hard = [b for b in blockers if b != "STEP232_REVIEW_ONLY_NO_ENABLEMENT_BRIDGE_PASS"]
    status = "APPROVAL_TO_ENABLEMENT_BRIDGE_REVIEW_READY" if not hard and all(checklist.values()) else "APPROVAL_TO_ENABLEMENT_BRIDGE_BLOCKED"
    bridge_id = "apprbridge_" + hashlib.sha1(
        "|".join([
            str(src.get("operator_final_approval_intake_record_id", "")),
            str(src.get("operator_final_approval_stub_id", "")),
            str(src.get("observation_id", "")),
        ]).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "approval_to_enablement_bridge_record_id": bridge_id,
        "operator_final_approval_intake_record_id": str(src.get("operator_final_approval_intake_record_id", "")),
        "operator_final_approval_stub_id": str(src.get("operator_final_approval_stub_id", "")),
        "final_validation_record_id": str(src.get("final_validation_record_id", "")),
        "enablement_request_stub_id": str(src.get("enablement_request_stub_id", "")),
        "audit_record_id": str(src.get("audit_record_id", "")),
        "shadow_ready_decision_id": str(src.get("shadow_ready_decision_id", "")),
        "final_gate_decision_id": str(src.get("final_gate_decision_id", "")),
        "activation_candidate_id": str(src.get("activation_candidate_id", "")),
        "config_draft_id": str(src.get("config_draft_id", "")),
        "enablement_plan_id": str(src.get("enablement_plan_id", "")),
        "observation_id": str(src.get("observation_id", "")),
        "registry_id": str(src.get("registry_id", "")),
        "comparison_group": str(src.get("comparison_group", "")),
        "side": str(src.get("side", "")),
        "source_intake_status": str(src.get("intake_status", "")),
        "operator_approval_status": str(src.get("operator_approval_status", "")),
        "bridge_mode": BRIDGE_MODE,
        "bridge_status": status,
        "bridge_checklist": checklist,
        "bridge_context": {
            "approval_input_was_validated": True,
            "operator_approval_status": str(src.get("operator_approval_status", "")),
            "bridge_review_only": True,
            "paper_only": True,
            "requires_step233_enablement_pre_submit_review": True,
            "live_trading_allowed": False,
        },
        "enablement_bridge_payload": {
            "enablement_request_stub_id": str(src.get("enablement_request_stub_id", "")),
            "operator_final_approval_stub_id": str(src.get("operator_final_approval_stub_id", "")),
            "operator_final_approval_intake_record_id": str(src.get("operator_final_approval_intake_record_id", "")),
            "observation_id": str(src.get("observation_id", "")),
            "registry_id": str(src.get("registry_id", "")),
            "side": str(src.get("side", "")),
            "submit_enablement_request": False,
            "paper_execution_enabled": False,
            "adapter_routing_enabled": False,
            "live_trading_allowed": False,
        },
        "bridge_blockers": blockers,
        "bridge_warnings": sorted(set(list(src.get("intake_warnings", []) or []) + [
            "APPROVAL_TO_ENABLEMENT_BRIDGE_REVIEW_ONLY_NO_ENABLEMENT",
            "STEP233_REQUIRED_FOR_ENABLEMENT_PRE_SUBMIT_REVIEW",
        ])),
        "next_required_step": "STEP233_ENABLEMENT_PRE_SUBMIT_REVIEW_ONLY" if status.endswith("REVIEW_READY") else "DO_NOT_CREATE_ENABLEMENT_PRE_SUBMIT_REVIEW_UNTIL_BLOCKERS_RESOLVED",
        "bridge_record_created": True,
        "approval_bridge_passed": False,
        "operator_final_approval_accepted": False,
        "operator_final_approval_recorded": False,
        "operator_final_approval_submitted": False,
        "enablement_request_submit_allowed": False,
        "enablement_request_submitted": False,
        "paper_execution_enablement_allowed": False,
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
        for blocker in row.get("bridge_blockers", []):
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _render_md(result: Step232Result) -> str:
    lines = [
        "# Step232 v5 Approval-to-Enablement Bridge Review-Only",
        "",
        "Step232 converts Step231 operator final approval intake records into approval-to-enablement bridge records.",
        "This is bridge-review-only and does not accept or record approvals, submit enablement requests, enable paper execution, route adapters, or live trade.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_intake_record_count: {result.source_intake_record_count}",
        f"- source_intake_valid_count: {result.source_intake_valid_count}",
        f"- bridge_record_count: {result.bridge_record_count}",
        f"- bridge_review_ready_count: {result.bridge_review_ready_count}",
        f"- bridge_blocked_count: {result.bridge_blocked_count}",
        f"- bridge_mode: `{result.bridge_mode}`",
        f"- approval_bridge_passed: {result.approval_bridge_passed}",
        f"- enablement_request_submitted: {result.enablement_request_submitted}",
        f"- paper_execution_enabled: {result.paper_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        "",
        "## Bridge records",
    ]
    for row in result.bridge_records:
        blockers = ", ".join(row.get("bridge_blockers", [])) if row.get("bridge_blockers") else "NO_BLOCKER"
        lines.append(f"- `{row.get('comparison_group','')}` {row.get('side','')}: status={row.get('bridge_status')}, approval={row.get('operator_approval_status')}, blockers={blockers}")
    return "\n".join(lines) + "\n"


def execute_approval_to_enablement_bridge_review(root: str | Path, *, write_output: bool = True) -> Step232Result:
    root_path = Path(root).resolve()
    step231_path = root_path / "storage/latest/step231_operator_final_approval_intake_validator_review_latest.json"
    step231 = _ensure_step231(root_path)
    src_rows = _load_intake_records(step231)
    rows = [_bridge_record(r) for r in src_rows]

    json_path = root_path / "data/reports/step232_approval_to_enablement_bridge_records.json"
    jsonl_path = root_path / "data/stores/step232_approval_to_enablement_bridge_records.jsonl"
    csv_path = root_path / "data/reports/step232_approval_to_enablement_bridge_records.csv"
    md_path = root_path / "data/reports/step232_approval_to_enablement_bridge_review_report.md"
    latest_path = root_path / "storage/latest/step232_approval_to_enablement_bridge_review_latest.json"

    result = Step232Result(
        status=STEP232_STATUS_OK,
        root=str(root_path),
        source_step231_result_path=str(step231_path),
        bridge_records_json_path=str(json_path),
        bridge_records_jsonl_path=str(jsonl_path),
        bridge_records_csv_path=str(csv_path),
        markdown_report_path=str(md_path),
        latest_result_path=str(latest_path),
        source_intake_record_count=len(src_rows),
        source_intake_valid_count=sum(1 for r in src_rows if r.get("intake_status") == "OPERATOR_FINAL_APPROVAL_INTAKE_VALID_REVIEW_ONLY"),
        bridge_record_count=len(rows),
        bridge_review_ready_count=sum(1 for r in rows if r.get("bridge_status") == "APPROVAL_TO_ENABLEMENT_BRIDGE_REVIEW_READY"),
        bridge_blocked_count=sum(1 for r in rows if r.get("bridge_status") == "APPROVAL_TO_ENABLEMENT_BRIDGE_BLOCKED"),
        bridge_watchlist_count=sum(1 for r in rows if r.get("bridge_status") == "APPROVAL_TO_ENABLEMENT_BRIDGE_WATCHLIST"),
        approval_to_enablement_bridge_review_created=True,
        bridge_mode=BRIDGE_MODE,
        bridge_review_only=True,
        bridge_record_created=True,
        approval_bridge_passed=False,
        operator_final_approval_accepted=False,
        operator_final_approval_recorded=False,
        enablement_request_submit_allowed=False,
        enablement_request_submitted=False,
        paper_execution_enablement_allowed=False,
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
        bridge_records=rows,
        blocker_summary=_summary(rows),
    )
    payload = result.to_dict()
    result.result_sha256 = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    if write_output:
        _write_json(json_path, {"bridge_records": rows})
        _write_jsonl(jsonl_path, rows)
        _write_csv(csv_path, rows)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_render_md(result), encoding="utf-8")
        _write_json(latest_path, result.to_dict())
    return result


def validate_approval_to_enablement_bridge_review(root: str | Path) -> Step232ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step232_approval_to_enablement_bridge_review_latest.json"
    if not result_path.exists():
        execute_approval_to_enablement_bridge_review(root_path, write_output=True)
    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    rows = list(payload.get("bridge_records", []) or [])
    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step231_present": Path(payload.get("source_step231_result_path", "")).exists(),
        "bridge_records_json_exists": Path(payload.get("bridge_records_json_path", "")).exists(),
        "bridge_records_jsonl_exists": Path(payload.get("bridge_records_jsonl_path", "")).exists(),
        "bridge_records_csv_exists": Path(payload.get("bridge_records_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_intake_records_present": int(payload.get("source_intake_record_count", 0)) > 0,
        "bridge_records_present": int(payload.get("bridge_record_count", 0)) > 0 and bool(rows),
        "bridge_review_created": payload.get("approval_to_enablement_bridge_review_created") is True and all(r.get("bridge_record_created") is True for r in rows),
        "bridge_mode_review_only": payload.get("bridge_mode") == BRIDGE_MODE and all(r.get("bridge_mode") == BRIDGE_MODE for r in rows),
        "no_approval_bridge_passed": payload.get("approval_bridge_passed") is False and all(r.get("approval_bridge_passed") is False for r in rows),
        "no_operator_final_approval_accepted": payload.get("operator_final_approval_accepted") is False and all(r.get("operator_final_approval_accepted") is False for r in rows),
        "no_operator_final_approval_recorded": payload.get("operator_final_approval_recorded") is False and all(r.get("operator_final_approval_recorded") is False for r in rows),
        "no_enablement_request_submit_allowed": payload.get("enablement_request_submit_allowed") is False and all(r.get("enablement_request_submit_allowed") is False for r in rows),
        "no_enablement_request_submitted": payload.get("enablement_request_submitted") is False and all(r.get("enablement_request_submitted") is False for r in rows),
        "no_paper_execution_enablement_allowed": payload.get("paper_execution_enablement_allowed") is False and all(r.get("paper_execution_enablement_allowed") is False for r in rows),
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
    return Step232ValidationResult(
        status=STEP232_VALIDATION_OK if not failures else "STEP232_V5_APPROVAL_TO_ENABLEMENT_BRIDGE_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
