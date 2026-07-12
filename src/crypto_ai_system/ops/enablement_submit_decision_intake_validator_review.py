from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from crypto_ai_system.ops.enablement_submit_decision_stub_review import (
    execute_enablement_submit_decision_stub_review,
)

STEP235_STATUS_OK = "STEP235_V5_ENABLEMENT_SUBMIT_DECISION_INTAKE_VALIDATOR_REVIEW_ONLY_OK"
STEP235_VALIDATION_OK = "STEP235_V5_ENABLEMENT_SUBMIT_DECISION_INTAKE_VALIDATOR_REVIEW_ONLY_VALIDATION_OK"
INTAKE_VALIDATOR_MODE = "ENABLEMENT_SUBMIT_DECISION_INTAKE_VALIDATOR_REVIEW_ONLY"
INPUT_PATH = "config/enablement_submit_decision_input.json"
APPROVED_STATUS = "APPROVED"
DEFAULT_STATUS = "NOT_APPROVED"


@dataclass
class Step235Result:
    status: str
    root: str
    source_step234_result_path: str
    submit_decision_input_path: str
    submit_decision_input_present: bool
    intake_records_json_path: str
    intake_records_jsonl_path: str
    intake_records_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_submit_decision_count: int
    source_submit_decision_review_ready_count: int
    intake_record_count: int
    intake_valid_count: int
    intake_not_approved_count: int
    intake_blocked_count: int
    intake_watchlist_count: int
    submit_decision_intake_validator_created: bool
    intake_validator_mode: str
    intake_validator_review_only: bool
    submit_decision_input_validated: bool
    submit_decision_accepted: bool
    submit_decision_recorded: bool
    submit_decision_approved: bool
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
    intake_records: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step235ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step234_present: bool
    intake_records_json_exists: bool
    intake_records_jsonl_exists: bool
    intake_records_csv_exists: bool
    markdown_report_exists: bool
    source_submit_decisions_present: bool
    intake_records_present: bool
    intake_validator_created: bool
    intake_validator_mode_review_only: bool
    no_submit_decision_accepted: bool
    no_submit_decision_recorded: bool
    no_submit_decision_approved: bool
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
    fields = list(rows[0].keys()) if rows else ["enablement_submit_decision_intake_record_id", "intake_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("input_snapshot", "required_fields_status", "intake_checklist"):
                out[key] = json.dumps(out.get(key, {}), sort_keys=True)
            for key in ("intake_blockers", "intake_warnings"):
                out[key] = "|".join(out.get(key, []))
            writer.writerow(out)


def _ensure_step234(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step234_enablement_submit_decision_stub_review_latest.json"
    if not path.exists():
        execute_enablement_submit_decision_stub_review(root, write_output=True)
    return _load_json(path)


def _load_submit_decisions(step234: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = Path(step234.get("submit_decisions_json_path", ""))
    if path.exists():
        return list(_load_json(path).get("submit_decisions", []) or [])
    return list(step234.get("submit_decisions", []) or [])


def _load_decision_input(root: Path) -> Tuple[bool, Dict[str, Any]]:
    path = root / INPUT_PATH
    if not path.exists():
        return False, {}
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return True, {"_invalid_payload_type": type(payload).__name__}
    return True, payload


def _lookup_input_record(decision_input: Dict[str, Any], stub: Dict[str, Any]) -> Dict[str, Any]:
    decision_id = str(stub.get("enablement_submit_decision_id", ""))
    pre_submit_id = str(stub.get("enablement_pre_submit_record_id", ""))
    observation_id = str(stub.get("observation_id", ""))
    records = decision_input.get("decisions", [])
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, dict):
                continue
            if str(record.get("enablement_submit_decision_id", "")) == decision_id:
                return record
            if str(record.get("enablement_pre_submit_record_id", "")) == pre_submit_id and pre_submit_id:
                return record
            if str(record.get("observation_id", "")) == observation_id and observation_id:
                return record
    if isinstance(decision_input.get(decision_id), dict):
        return decision_input[decision_id]
    return {}


def _required_status(record: Dict[str, Any]) -> Dict[str, bool]:
    required = [
        "decision_id",
        "decision_timestamp_utc",
        "operator_id",
        "explicit_submit_confirmation",
        "paper_mode_only_confirmation",
        "kill_switch_confirmed",
        "rollback_plan_confirmed",
    ]
    return {name: bool(record.get(name)) for name in required}


def _intake_record(stub: Dict[str, Any], input_present: bool, decision_input: Dict[str, Any]) -> Dict[str, Any]:
    record = _lookup_input_record(decision_input, stub) if input_present else {}
    decision_status = str(record.get("decision_status", DEFAULT_STATUS)).upper() if record else DEFAULT_STATUS
    required = _required_status(record)
    checklist = {
        "source_submit_decision_review_ready": stub.get("submit_decision_status") == "ENABLEMENT_SUBMIT_DECISION_STUB_REVIEW_READY",
        "source_submit_decision_mode_stub_only": stub.get("submit_decision_mode") == "ENABLEMENT_SUBMIT_DECISION_STUB_ONLY",
        "source_submit_decision_record_created": stub.get("submit_decision_record_created") is True,
        "source_submit_decision_template_created": stub.get("submit_decision_template_created") is True,
        "source_submit_decision_approved_false": stub.get("submit_decision_approved") is False,
        "source_submit_decision_recorded_false": stub.get("submit_decision_recorded") is False,
        "source_enablement_request_submit_allowed_false": stub.get("enablement_request_submit_allowed") is False,
        "source_enablement_request_submitted_false": stub.get("enablement_request_submitted") is False,
        "source_paper_execution_enabled_false": stub.get("paper_execution_enabled") is False,
        "source_paper_order_execution_enabled_false": stub.get("paper_order_execution_enabled") is False,
        "source_adapter_routing_enabled_false": stub.get("adapter_routing_enabled") is False,
        "source_live_trading_allowed_false": stub.get("live_trading_allowed") is False,
        "decision_input_present": input_present,
        "decision_input_record_present": bool(record),
        "decision_status_is_approved": decision_status == APPROVED_STATUS,
        "required_decision_fields_present": all(required.values()),
    }
    blockers = list(stub.get("submit_decision_blockers", []) or [])
    if decision_input.get("_invalid_payload_type"):
        blockers.append("SUBMIT_DECISION_INPUT_PAYLOAD_NOT_OBJECT")
    if not input_present:
        blockers.append("SUBMIT_DECISION_INPUT_FILE_MISSING_DEFAULT_NOT_APPROVED")
    if input_present and not record:
        blockers.append("SUBMIT_DECISION_RECORD_MISSING_DEFAULT_NOT_APPROVED")
    if decision_status != APPROVED_STATUS:
        blockers.append("ENABLEMENT_SUBMIT_DECISION_NOT_APPROVED")
    if not all(required.values()):
        blockers.append("SUBMIT_DECISION_REQUIRED_FIELDS_INCOMPLETE")
    for key, ok in checklist.items():
        if not ok and key.startswith("source_"):
            blockers.append(key.upper() + "_FAILED")
    blockers.append("STEP235_REVIEW_ONLY_NO_SUBMIT_DECISION_RECORD")
    blockers = sorted(set(blockers))

    hard = [b for b in blockers if b != "STEP235_REVIEW_ONLY_NO_SUBMIT_DECISION_RECORD"]
    status = "ENABLEMENT_SUBMIT_DECISION_INTAKE_VALID_REVIEW_ONLY" if not hard and all(checklist.values()) else "ENABLEMENT_SUBMIT_DECISION_INTAKE_BLOCKED"
    iid = "submitintake_" + hashlib.sha1(
        "|".join([
            str(stub.get("enablement_submit_decision_id", "")),
            str(stub.get("enablement_pre_submit_record_id", "")),
            str(stub.get("observation_id", "")),
        ]).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "enablement_submit_decision_intake_record_id": iid,
        "enablement_submit_decision_id": str(stub.get("enablement_submit_decision_id", "")),
        "enablement_pre_submit_record_id": str(stub.get("enablement_pre_submit_record_id", "")),
        "approval_to_enablement_bridge_record_id": str(stub.get("approval_to_enablement_bridge_record_id", "")),
        "operator_final_approval_intake_record_id": str(stub.get("operator_final_approval_intake_record_id", "")),
        "operator_final_approval_stub_id": str(stub.get("operator_final_approval_stub_id", "")),
        "final_validation_record_id": str(stub.get("final_validation_record_id", "")),
        "enablement_request_stub_id": str(stub.get("enablement_request_stub_id", "")),
        "audit_record_id": str(stub.get("audit_record_id", "")),
        "shadow_ready_decision_id": str(stub.get("shadow_ready_decision_id", "")),
        "final_gate_decision_id": str(stub.get("final_gate_decision_id", "")),
        "activation_candidate_id": str(stub.get("activation_candidate_id", "")),
        "config_draft_id": str(stub.get("config_draft_id", "")),
        "enablement_plan_id": str(stub.get("enablement_plan_id", "")),
        "observation_id": str(stub.get("observation_id", "")),
        "registry_id": str(stub.get("registry_id", "")),
        "comparison_group": str(stub.get("comparison_group", "")),
        "side": str(stub.get("side", "")),
        "source_submit_decision_status": str(stub.get("submit_decision_status", "")),
        "intake_validator_mode": INTAKE_VALIDATOR_MODE,
        "intake_status": status,
        "decision_status": decision_status,
        "input_snapshot": record,
        "required_fields_status": required,
        "intake_checklist": checklist,
        "intake_blockers": blockers,
        "intake_warnings": sorted(set(list(stub.get("submit_decision_warnings", []) or []) + [
            "SUBMIT_DECISION_INTAKE_VALIDATOR_REVIEW_ONLY_NO_RECORD",
            "STEP236_REQUIRED_FOR_ENABLEMENT_SUBMIT_GATE_REVIEW",
        ])),
        "next_required_step": "STEP236_ENABLEMENT_SUBMIT_GATE_REVIEW_ONLY" if status.endswith("REVIEW_ONLY") else "DO_NOT_CREATE_SUBMIT_GATE_UNTIL_BLOCKERS_RESOLVED",
        "intake_record_created": True,
        "submit_decision_input_validated": True,
        "submit_decision_accepted": False,
        "submit_decision_recorded": False,
        "submit_decision_approved": False,
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
        for blocker in row.get("intake_blockers", []):
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _render_md(result: Step235Result) -> str:
    lines = [
        "# Step235 v5 Enablement Submit Decision Intake Validator Review-Only",
        "",
        "Step235 validates optional enablement submit decision input against Step234 submit decision stubs.",
        "If `config/enablement_submit_decision_input.json` is missing, every intake record defaults to NOT_APPROVED.",
        "This is review-only and does not accept decisions, record decisions, submit enablement requests, enable paper execution, route adapters, or live trade.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- submit_decision_input_present: {result.submit_decision_input_present}",
        f"- source_submit_decision_count: {result.source_submit_decision_count}",
        f"- intake_record_count: {result.intake_record_count}",
        f"- intake_valid_count: {result.intake_valid_count}",
        f"- intake_not_approved_count: {result.intake_not_approved_count}",
        f"- intake_blocked_count: {result.intake_blocked_count}",
        f"- intake_validator_mode: `{result.intake_validator_mode}`",
        f"- submit_decision_accepted: {result.submit_decision_accepted}",
        f"- submit_decision_recorded: {result.submit_decision_recorded}",
        f"- enablement_request_submitted: {result.enablement_request_submitted}",
        f"- paper_execution_enabled: {result.paper_execution_enabled}",
        "",
        "## Intake records",
    ]
    for row in result.intake_records:
        blockers = ", ".join(row.get("intake_blockers", [])) if row.get("intake_blockers") else "NO_BLOCKER"
        lines.append(f"- `{row.get('comparison_group','')}` {row.get('side','')}: status={row.get('intake_status')}, decision={row.get('decision_status')}, blockers={blockers}")
    return "\n".join(lines) + "\n"


def execute_enablement_submit_decision_intake_validator_review(root: str | Path, *, write_output: bool = True) -> Step235Result:
    root_path = Path(root).resolve()
    step234_path = root_path / "storage/latest/step234_enablement_submit_decision_stub_review_latest.json"
    step234 = _ensure_step234(root_path)
    stubs = _load_submit_decisions(step234)
    input_present, decision_input = _load_decision_input(root_path)
    rows = [_intake_record(stub, input_present, decision_input) for stub in stubs]

    json_path = root_path / "data/reports/step235_enablement_submit_decision_intake_records.json"
    jsonl_path = root_path / "data/stores/step235_enablement_submit_decision_intake_records.jsonl"
    csv_path = root_path / "data/reports/step235_enablement_submit_decision_intake_records.csv"
    md_path = root_path / "data/reports/step235_enablement_submit_decision_intake_validator_review_report.md"
    latest_path = root_path / "storage/latest/step235_enablement_submit_decision_intake_validator_review_latest.json"

    result = Step235Result(
        status=STEP235_STATUS_OK,
        root=str(root_path),
        source_step234_result_path=str(step234_path),
        submit_decision_input_path=str(root_path / INPUT_PATH),
        submit_decision_input_present=input_present,
        intake_records_json_path=str(json_path),
        intake_records_jsonl_path=str(jsonl_path),
        intake_records_csv_path=str(csv_path),
        markdown_report_path=str(md_path),
        latest_result_path=str(latest_path),
        source_submit_decision_count=len(stubs),
        source_submit_decision_review_ready_count=sum(1 for s in stubs if s.get("submit_decision_status") == "ENABLEMENT_SUBMIT_DECISION_STUB_REVIEW_READY"),
        intake_record_count=len(rows),
        intake_valid_count=sum(1 for r in rows if r.get("intake_status") == "ENABLEMENT_SUBMIT_DECISION_INTAKE_VALID_REVIEW_ONLY"),
        intake_not_approved_count=sum(1 for r in rows if r.get("decision_status") != APPROVED_STATUS),
        intake_blocked_count=sum(1 for r in rows if r.get("intake_status") == "ENABLEMENT_SUBMIT_DECISION_INTAKE_BLOCKED"),
        intake_watchlist_count=sum(1 for r in rows if r.get("intake_status") == "ENABLEMENT_SUBMIT_DECISION_INTAKE_WATCHLIST"),
        submit_decision_intake_validator_created=True,
        intake_validator_mode=INTAKE_VALIDATOR_MODE,
        intake_validator_review_only=True,
        submit_decision_input_validated=True,
        submit_decision_accepted=False,
        submit_decision_recorded=False,
        submit_decision_approved=False,
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
        intake_records=rows,
        blocker_summary=_summary(rows),
    )
    payload = result.to_dict()
    result.result_sha256 = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    if write_output:
        _write_json(json_path, {"intake_records": rows})
        _write_jsonl(jsonl_path, rows)
        _write_csv(csv_path, rows)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_render_md(result), encoding="utf-8")
        _write_json(latest_path, result.to_dict())
    return result


def validate_enablement_submit_decision_intake_validator_review(root: str | Path) -> Step235ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step235_enablement_submit_decision_intake_validator_review_latest.json"
    if not result_path.exists():
        execute_enablement_submit_decision_intake_validator_review(root_path, write_output=True)
    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    rows = list(payload.get("intake_records", []) or [])
    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step234_present": Path(payload.get("source_step234_result_path", "")).exists(),
        "intake_records_json_exists": Path(payload.get("intake_records_json_path", "")).exists(),
        "intake_records_jsonl_exists": Path(payload.get("intake_records_jsonl_path", "")).exists(),
        "intake_records_csv_exists": Path(payload.get("intake_records_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_submit_decisions_present": int(payload.get("source_submit_decision_count", 0)) > 0,
        "intake_records_present": int(payload.get("intake_record_count", 0)) > 0 and bool(rows),
        "intake_validator_created": payload.get("submit_decision_intake_validator_created") is True and all(r.get("intake_record_created") is True for r in rows),
        "intake_validator_mode_review_only": payload.get("intake_validator_mode") == INTAKE_VALIDATOR_MODE and all(r.get("intake_validator_mode") == INTAKE_VALIDATOR_MODE for r in rows),
        "no_submit_decision_accepted": payload.get("submit_decision_accepted") is False and all(r.get("submit_decision_accepted") is False for r in rows),
        "no_submit_decision_recorded": payload.get("submit_decision_recorded") is False and all(r.get("submit_decision_recorded") is False for r in rows),
        "no_submit_decision_approved": payload.get("submit_decision_approved") is False and all(r.get("submit_decision_approved") is False for r in rows),
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
    return Step235ValidationResult(
        status=STEP235_VALIDATION_OK if not failures else "STEP235_V5_ENABLEMENT_SUBMIT_DECISION_INTAKE_VALIDATOR_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
