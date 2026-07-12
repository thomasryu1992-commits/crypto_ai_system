from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.paper_execution_enablement_request_final_validator_review import (
    execute_paper_execution_enablement_request_final_validator_review,
)

STEP230_STATUS_OK = "STEP230_V5_OPERATOR_FINAL_ENABLEMENT_APPROVAL_STUB_REVIEW_ONLY_OK"
STEP230_VALIDATION_OK = "STEP230_V5_OPERATOR_FINAL_ENABLEMENT_APPROVAL_STUB_REVIEW_ONLY_VALIDATION_OK"
APPROVAL_STUB_MODE = "OPERATOR_FINAL_ENABLEMENT_APPROVAL_STUB_ONLY"


@dataclass
class Step230Result:
    status: str
    root: str
    source_step229_result_path: str
    approval_stubs_json_path: str
    approval_stubs_jsonl_path: str
    approval_stubs_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_final_validation_record_count: int
    source_final_validation_review_ready_count: int
    approval_stub_count: int
    approval_stub_review_ready_count: int
    approval_stub_blocked_count: int
    approval_stub_watchlist_count: int
    operator_final_approval_stub_review_created: bool
    approval_stub_mode: str
    approval_stub_only: bool
    operator_final_approval_template_created: bool
    operator_final_approval_submitted: bool
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
    approval_stubs: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step230ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step229_present: bool
    approval_stubs_json_exists: bool
    approval_stubs_jsonl_exists: bool
    approval_stubs_csv_exists: bool
    markdown_report_exists: bool
    source_final_validation_records_present: bool
    approval_stubs_present: bool
    approval_stub_review_created: bool
    approval_stub_mode_only: bool
    no_operator_final_approval_submitted: bool
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
    fields = list(rows[0].keys()) if rows else ["operator_final_approval_stub_id", "approval_stub_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("approval_template", "approval_preconditions", "operator_recheck_requirements"):
                out[key] = json.dumps(out.get(key, {}), sort_keys=True)
            for key in ("approval_blockers", "approval_warnings"):
                out[key] = "|".join(out.get(key, []))
            writer.writerow(out)


def _ensure_step229(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step229_paper_execution_enablement_request_final_validator_review_latest.json"
    if not path.exists():
        execute_paper_execution_enablement_request_final_validator_review(root, write_output=True)
    return _load_json(path)


def _load_validation_records(step229: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = Path(step229.get("final_validation_records_json_path", ""))
    if path.exists():
        return list(_load_json(path).get("validation_records", []) or [])
    return list(step229.get("validation_records", []) or [])


def _approval_stub(src: Dict[str, Any]) -> Dict[str, Any]:
    checklist = {
        "source_final_validation_review_ready": src.get("final_validation_status") == "PAPER_EXECUTION_ENABLEMENT_REQUEST_FINAL_VALIDATION_REVIEW_READY",
        "source_final_validator_mode_review_only": src.get("final_validator_mode") == "PAPER_EXECUTION_ENABLEMENT_REQUEST_FINAL_VALIDATOR_REVIEW_ONLY",
        "source_final_validation_record_created": src.get("final_validation_record_created") is True,
        "source_final_enablement_request_validation_passed_false": src.get("final_enablement_request_validation_passed") is False,
        "source_enablement_request_submit_allowed_false": src.get("enablement_request_submit_allowed") is False,
        "source_enablement_request_submitted_false": src.get("enablement_request_submitted") is False,
        "source_paper_execution_enablement_allowed_false": src.get("paper_execution_enablement_allowed") is False,
        "source_paper_execution_enabled_false": src.get("paper_execution_enabled") is False,
        "source_paper_order_execution_enabled_false": src.get("paper_order_execution_enabled") is False,
        "source_adapter_routing_enabled_false": src.get("adapter_routing_enabled") is False,
        "source_shadow_execution_enabled_false": src.get("shadow_execution_enabled") is False,
        "source_live_trading_allowed_false": src.get("live_trading_allowed") is False,
    }
    blockers = list(src.get("final_validation_blockers", []) or [])
    for key, ok in checklist.items():
        if not ok:
            blockers.append(key.upper() + "_FAILED")
    blockers.append("STEP230_REVIEW_ONLY_NO_OPERATOR_FINAL_APPROVAL_SUBMIT")
    blockers = sorted(set(blockers))
    hard = [b for b in blockers if b != "STEP230_REVIEW_ONLY_NO_OPERATOR_FINAL_APPROVAL_SUBMIT"]
    status = "OPERATOR_FINAL_ENABLEMENT_APPROVAL_STUB_REVIEW_READY" if not hard and all(checklist.values()) else "OPERATOR_FINAL_ENABLEMENT_APPROVAL_STUB_BLOCKED"
    sid = "opfinal_" + hashlib.sha1(
        "|".join([
            str(src.get("final_validation_record_id", "")),
            str(src.get("enablement_request_stub_id", "")),
            str(src.get("observation_id", "")),
        ]).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "operator_final_approval_stub_id": sid,
        "final_validation_record_id": str(src.get("final_validation_record_id", "")),
        "enablement_request_stub_id": str(src.get("enablement_request_stub_id", "")),
        "audit_record_id": str(src.get("audit_record_id", "")),
        "shadow_ready_decision_id": str(src.get("shadow_ready_decision_id", "")),
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
        "source_final_validation_status": str(src.get("final_validation_status", "")),
        "approval_stub_mode": APPROVAL_STUB_MODE,
        "approval_stub_status": status,
        "approval_template": {
            "approval_type": "OPERATOR_FINAL_ENABLEMENT_APPROVAL_TEMPLATE",
            "approval_mode": APPROVAL_STUB_MODE,
            "final_validation_record_id": str(src.get("final_validation_record_id", "")),
            "enablement_request_stub_id": str(src.get("enablement_request_stub_id", "")),
            "observation_id": str(src.get("observation_id", "")),
            "registry_id": str(src.get("registry_id", "")),
            "side": str(src.get("side", "")),
            "required_operator_fields": [
                "operator_id",
                "approval_timestamp_utc",
                "explicit_paper_mode_only_confirmation",
                "explicit_enablement_risk_acceptance",
                "kill_switch_confirmed",
                "daily_loss_cap_confirmed",
                "position_count_cap_confirmed",
                "rollback_plan_confirmed",
            ],
            "submit_to_runtime": False,
            "paper_only": True,
            "live_trading_allowed": False,
        },
        "approval_preconditions": checklist,
        "operator_recheck_requirements": {
            "fresh_operator_approval_required": True,
            "approval_max_age_minutes": 30,
            "manual_kill_switch_confirmation_required": True,
            "rollback_plan_required": True,
            "paper_mode_only_confirmation_required": True,
            "risk_limits_recheck_required": True,
            "telegram_dry_run_notice_required": True,
        },
        "approval_blockers": blockers,
        "approval_warnings": sorted(set(list(src.get("final_validation_warnings", []) or []) + [
            "OPERATOR_FINAL_APPROVAL_STUB_ONLY_NO_SUBMIT",
            "STEP231_REQUIRED_FOR_OPERATOR_APPROVAL_INTAKE_VALIDATOR",
        ])),
        "next_required_step": "STEP231_OPERATOR_FINAL_APPROVAL_INTAKE_VALIDATOR_REVIEW_ONLY" if status.endswith("REVIEW_READY") else "DO_NOT_VALIDATE_OPERATOR_APPROVAL_UNTIL_BLOCKERS_RESOLVED",
        "operator_final_approval_stub_created": True,
        "operator_final_approval_template_created": True,
        "operator_final_approval_submitted": False,
        "operator_final_approval_recorded": False,
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
        for blocker in row.get("approval_blockers", []):
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _render_md(result: Step230Result) -> str:
    lines = [
        "# Step230 v5 Operator Final Enablement Approval Stub Review-Only",
        "",
        "Step230 creates operator final enablement approval stubs from Step229 final validation records.",
        "This is approval-stub-only and does not submit or record operator approvals, submit enablement requests, enable paper execution, route adapters, or live trade.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_final_validation_record_count: {result.source_final_validation_record_count}",
        f"- approval_stub_count: {result.approval_stub_count}",
        f"- approval_stub_review_ready_count: {result.approval_stub_review_ready_count}",
        f"- approval_stub_blocked_count: {result.approval_stub_blocked_count}",
        f"- approval_stub_mode: `{result.approval_stub_mode}`",
        f"- operator_final_approval_submitted: {result.operator_final_approval_submitted}",
        f"- operator_final_approval_recorded: {result.operator_final_approval_recorded}",
        f"- paper_execution_enabled: {result.paper_execution_enabled}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        "",
        "## Approval stubs",
    ]
    for row in result.approval_stubs:
        blockers = ", ".join(row.get("approval_blockers", [])) if row.get("approval_blockers") else "NO_BLOCKER"
        lines.append(f"- `{row.get('comparison_group','')}` {row.get('side','')}: status={row.get('approval_stub_status')}, submitted={row.get('operator_final_approval_submitted')}, blockers={blockers}")
    return "\n".join(lines) + "\n"


def execute_operator_final_enablement_approval_stub_review(root: str | Path, *, write_output: bool = True) -> Step230Result:
    root_path = Path(root).resolve()
    step229_path = root_path / "storage/latest/step229_paper_execution_enablement_request_final_validator_review_latest.json"
    step229 = _ensure_step229(root_path)
    src_rows = _load_validation_records(step229)
    rows = [_approval_stub(r) for r in src_rows]

    json_path = root_path / "data/reports/step230_operator_final_enablement_approval_stubs.json"
    jsonl_path = root_path / "data/stores/step230_operator_final_enablement_approval_stubs.jsonl"
    csv_path = root_path / "data/reports/step230_operator_final_enablement_approval_stubs.csv"
    md_path = root_path / "data/reports/step230_operator_final_enablement_approval_stub_review_report.md"
    latest_path = root_path / "storage/latest/step230_operator_final_enablement_approval_stub_review_latest.json"

    result = Step230Result(
        status=STEP230_STATUS_OK,
        root=str(root_path),
        source_step229_result_path=str(step229_path),
        approval_stubs_json_path=str(json_path),
        approval_stubs_jsonl_path=str(jsonl_path),
        approval_stubs_csv_path=str(csv_path),
        markdown_report_path=str(md_path),
        latest_result_path=str(latest_path),
        source_final_validation_record_count=len(src_rows),
        source_final_validation_review_ready_count=sum(1 for r in src_rows if r.get("final_validation_status") == "PAPER_EXECUTION_ENABLEMENT_REQUEST_FINAL_VALIDATION_REVIEW_READY"),
        approval_stub_count=len(rows),
        approval_stub_review_ready_count=sum(1 for r in rows if r.get("approval_stub_status") == "OPERATOR_FINAL_ENABLEMENT_APPROVAL_STUB_REVIEW_READY"),
        approval_stub_blocked_count=sum(1 for r in rows if r.get("approval_stub_status") == "OPERATOR_FINAL_ENABLEMENT_APPROVAL_STUB_BLOCKED"),
        approval_stub_watchlist_count=sum(1 for r in rows if r.get("approval_stub_status") == "OPERATOR_FINAL_ENABLEMENT_APPROVAL_STUB_WATCHLIST"),
        operator_final_approval_stub_review_created=True,
        approval_stub_mode=APPROVAL_STUB_MODE,
        approval_stub_only=True,
        operator_final_approval_template_created=True,
        operator_final_approval_submitted=False,
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
        approval_stubs=rows,
        blocker_summary=_summary(rows),
    )
    payload = result.to_dict()
    result.result_sha256 = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    if write_output:
        _write_json(json_path, {"approval_stubs": rows})
        _write_jsonl(jsonl_path, rows)
        _write_csv(csv_path, rows)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_render_md(result), encoding="utf-8")
        _write_json(latest_path, result.to_dict())
    return result


def validate_operator_final_enablement_approval_stub_review(root: str | Path) -> Step230ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step230_operator_final_enablement_approval_stub_review_latest.json"
    if not result_path.exists():
        execute_operator_final_enablement_approval_stub_review(root_path, write_output=True)
    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    rows = list(payload.get("approval_stubs", []) or [])
    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step229_present": Path(payload.get("source_step229_result_path", "")).exists(),
        "approval_stubs_json_exists": Path(payload.get("approval_stubs_json_path", "")).exists(),
        "approval_stubs_jsonl_exists": Path(payload.get("approval_stubs_jsonl_path", "")).exists(),
        "approval_stubs_csv_exists": Path(payload.get("approval_stubs_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_final_validation_records_present": int(payload.get("source_final_validation_record_count", 0)) > 0,
        "approval_stubs_present": int(payload.get("approval_stub_count", 0)) > 0 and bool(rows),
        "approval_stub_review_created": payload.get("operator_final_approval_stub_review_created") is True and all(r.get("operator_final_approval_stub_created") is True for r in rows),
        "approval_stub_mode_only": payload.get("approval_stub_mode") == APPROVAL_STUB_MODE and all(r.get("approval_stub_mode") == APPROVAL_STUB_MODE for r in rows),
        "no_operator_final_approval_submitted": payload.get("operator_final_approval_submitted") is False and all(r.get("operator_final_approval_submitted") is False for r in rows),
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
    return Step230ValidationResult(
        status=STEP230_VALIDATION_OK if not failures else "STEP230_V5_OPERATOR_FINAL_ENABLEMENT_APPROVAL_STUB_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
