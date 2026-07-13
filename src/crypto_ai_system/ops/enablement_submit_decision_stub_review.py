from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.enablement_pre_submit_review import (
    execute_enablement_pre_submit_review,
)

STEP234_STATUS_OK = "STEP234_V5_ENABLEMENT_SUBMIT_DECISION_STUB_REVIEW_ONLY_OK"
STEP234_VALIDATION_OK = "STEP234_V5_ENABLEMENT_SUBMIT_DECISION_STUB_REVIEW_ONLY_VALIDATION_OK"
SUBMIT_DECISION_MODE = "ENABLEMENT_SUBMIT_DECISION_STUB_ONLY"


@dataclass
class Step234Result:
    status: str
    root: str
    source_step233_result_path: str
    submit_decisions_json_path: str
    submit_decisions_jsonl_path: str
    submit_decisions_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_pre_submit_record_count: int
    source_pre_submit_review_ready_count: int
    submit_decision_count: int
    submit_decision_review_ready_count: int
    submit_decision_blocked_count: int
    submit_decision_watchlist_count: int
    enablement_submit_decision_stub_created: bool
    submit_decision_mode: str
    submit_decision_stub_only: bool
    submit_decision_template_created: bool
    submit_decision_approved: bool
    submit_decision_recorded: bool
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
    submit_decisions: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step234ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step233_present: bool
    submit_decisions_json_exists: bool
    submit_decisions_jsonl_exists: bool
    submit_decisions_csv_exists: bool
    markdown_report_exists: bool
    source_pre_submit_records_present: bool
    submit_decisions_present: bool
    submit_decision_stub_created: bool
    submit_decision_mode_stub_only: bool
    no_submit_decision_approved: bool
    no_submit_decision_recorded: bool
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
    fields = list(rows[0].keys()) if rows else ["enablement_submit_decision_id", "submit_decision_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("submit_decision_checklist", "submit_decision_template", "submit_candidate_payload"):
                out[key] = json.dumps(out.get(key, {}), sort_keys=True)
            for key in ("submit_decision_blockers", "submit_decision_warnings"):
                out[key] = "|".join(out.get(key, []))
            writer.writerow(out)


def _ensure_step233(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step233_enablement_pre_submit_review_latest.json"
    if not path.exists():
        execute_enablement_pre_submit_review(root, write_output=True)
    return _load_json(path)


def _load_pre_submit_records(step233: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = Path(step233.get("pre_submit_records_json_path", ""))
    if path.exists():
        return list(_load_json(path).get("pre_submit_records", []) or [])
    return list(step233.get("pre_submit_records", []) or [])


def _decision_record(src: Dict[str, Any]) -> Dict[str, Any]:
    candidate = src.get("submit_candidate_payload", {}) if isinstance(src.get("submit_candidate_payload", {}), dict) else {}
    checklist = {
        "source_pre_submit_review_ready": src.get("pre_submit_status") == "ENABLEMENT_PRE_SUBMIT_REVIEW_READY",
        "source_pre_submit_review_only": src.get("pre_submit_review_mode") == "ENABLEMENT_PRE_SUBMIT_REVIEW_ONLY",
        "source_pre_submit_record_created": src.get("pre_submit_record_created") is True,
        "source_pre_submit_review_passed_false": src.get("pre_submit_review_passed") is False,
        "source_enablement_request_submit_allowed_false": src.get("enablement_request_submit_allowed") is False,
        "source_enablement_request_submitted_false": src.get("enablement_request_submitted") is False,
        "source_paper_execution_enablement_allowed_false": src.get("paper_execution_enablement_allowed") is False,
        "source_paper_execution_enabled_false": src.get("paper_execution_enabled") is False,
        "source_paper_order_execution_enabled_false": src.get("paper_order_execution_enabled") is False,
        "source_adapter_routing_enabled_false": src.get("adapter_routing_enabled") is False,
        "source_shadow_execution_enabled_false": src.get("shadow_execution_enabled") is False,
        "source_live_trading_allowed_false": src.get("live_trading_allowed") is False,
        "submit_candidate_payload_present": bool(candidate),
        "submit_candidate_submit_false": candidate.get("submit_enablement_request") is False,
        "submit_candidate_keeps_execution_disabled": candidate.get("enable_paper_execution") is False
        and candidate.get("enable_paper_order_execution") is False
        and candidate.get("enable_adapter_routing") is False
        and candidate.get("enable_shadow_execution") is False
        and candidate.get("live_trading_allowed") is False,
    }
    blockers = list(src.get("pre_submit_blockers", []) or [])
    for key, ok in checklist.items():
        if not ok:
            blockers.append(key.upper() + "_FAILED")
    blockers.append("STEP234_REVIEW_ONLY_NO_SUBMIT_DECISION_APPROVAL")
    blockers = sorted(set(blockers))
    hard = [b for b in blockers if b != "STEP234_REVIEW_ONLY_NO_SUBMIT_DECISION_APPROVAL"]
    status = "ENABLEMENT_SUBMIT_DECISION_STUB_REVIEW_READY" if not hard and all(checklist.values()) else "ENABLEMENT_SUBMIT_DECISION_STUB_BLOCKED"
    did = "submitdec_" + hashlib.sha1(
        "|".join([
            str(src.get("enablement_pre_submit_record_id", "")),
            str(src.get("enablement_request_stub_id", "")),
            str(src.get("observation_id", "")),
        ]).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "enablement_submit_decision_id": did,
        "enablement_pre_submit_record_id": str(src.get("enablement_pre_submit_record_id", "")),
        "approval_to_enablement_bridge_record_id": str(src.get("approval_to_enablement_bridge_record_id", "")),
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
        "source_pre_submit_status": str(src.get("pre_submit_status", "")),
        "submit_decision_mode": SUBMIT_DECISION_MODE,
        "submit_decision_status": status,
        "submit_decision_checklist": checklist,
        "submit_decision_template": {
            "decision_type": "ENABLEMENT_SUBMIT_DECISION_TEMPLATE",
            "decision_mode": SUBMIT_DECISION_MODE,
            "enablement_pre_submit_record_id": str(src.get("enablement_pre_submit_record_id", "")),
            "enablement_request_stub_id": str(src.get("enablement_request_stub_id", "")),
            "observation_id": str(src.get("observation_id", "")),
            "registry_id": str(src.get("registry_id", "")),
            "side": str(src.get("side", "")),
            "required_decision_fields": [
                "decision_id",
                "decision_timestamp_utc",
                "operator_id",
                "explicit_submit_confirmation",
                "paper_mode_only_confirmation",
                "kill_switch_confirmed",
                "rollback_plan_confirmed",
            ],
            "approve_submit": False,
            "submit_to_runtime": False,
            "paper_only": True,
            "live_trading_allowed": False,
        },
        "submit_candidate_payload": candidate,
        "submit_decision_blockers": blockers,
        "submit_decision_warnings": sorted(set(list(src.get("pre_submit_warnings", []) or []) + [
            "ENABLEMENT_SUBMIT_DECISION_STUB_ONLY_NO_APPROVAL",
            "STEP235_REQUIRED_FOR_ENABLEMENT_SUBMIT_DECISION_INTAKE_VALIDATOR",
        ])),
        "next_required_step": "STEP235_ENABLEMENT_SUBMIT_DECISION_INTAKE_VALIDATOR_REVIEW_ONLY" if status.endswith("REVIEW_READY") else "DO_NOT_VALIDATE_SUBMIT_DECISION_UNTIL_BLOCKERS_RESOLVED",
        "submit_decision_record_created": True,
        "submit_decision_template_created": True,
        "submit_decision_approved": False,
        "submit_decision_recorded": False,
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
        for blocker in row.get("submit_decision_blockers", []):
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _render_md(result: Step234Result) -> str:
    lines = [
        "# Step234 v5 Enablement Submit Decision Stub Review-Only",
        "",
        "Step234 creates enablement submit decision stubs from Step233 pre-submit review records.",
        "This is submit-decision-stub-only and does not approve decisions, submit enablement requests, enable paper execution, route adapters, or live trade.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_pre_submit_record_count: {result.source_pre_submit_record_count}",
        f"- source_pre_submit_review_ready_count: {result.source_pre_submit_review_ready_count}",
        f"- submit_decision_count: {result.submit_decision_count}",
        f"- submit_decision_review_ready_count: {result.submit_decision_review_ready_count}",
        f"- submit_decision_blocked_count: {result.submit_decision_blocked_count}",
        f"- submit_decision_mode: `{result.submit_decision_mode}`",
        f"- submit_decision_approved: {result.submit_decision_approved}",
        f"- submit_decision_recorded: {result.submit_decision_recorded}",
        f"- enablement_request_submitted: {result.enablement_request_submitted}",
        f"- paper_execution_enabled: {result.paper_execution_enabled}",
        "",
        "## Submit decision stubs",
    ]
    for row in result.submit_decisions:
        blockers = ", ".join(row.get("submit_decision_blockers", [])) if row.get("submit_decision_blockers") else "NO_BLOCKER"
        lines.append(f"- `{row.get('comparison_group','')}` {row.get('side','')}: status={row.get('submit_decision_status')}, approved={row.get('submit_decision_approved')}, blockers={blockers}")
    return "\n".join(lines) + "\n"


def execute_enablement_submit_decision_stub_review(root: str | Path, *, write_output: bool = True) -> Step234Result:
    root_path = Path(root).resolve()
    step233_path = root_path / "storage/latest/step233_enablement_pre_submit_review_latest.json"
    step233 = _ensure_step233(root_path)
    src_rows = _load_pre_submit_records(step233)
    rows = [_decision_record(r) for r in src_rows]

    json_path = root_path / "data/reports/step234_enablement_submit_decision_stubs.json"
    jsonl_path = root_path / "data/stores/step234_enablement_submit_decision_stubs.jsonl"
    csv_path = root_path / "data/reports/step234_enablement_submit_decision_stubs.csv"
    md_path = root_path / "data/reports/step234_enablement_submit_decision_stub_review_report.md"
    latest_path = root_path / "storage/latest/step234_enablement_submit_decision_stub_review_latest.json"

    result = Step234Result(
        status=STEP234_STATUS_OK,
        root=str(root_path),
        source_step233_result_path=str(step233_path),
        submit_decisions_json_path=str(json_path),
        submit_decisions_jsonl_path=str(jsonl_path),
        submit_decisions_csv_path=str(csv_path),
        markdown_report_path=str(md_path),
        latest_result_path=str(latest_path),
        source_pre_submit_record_count=len(src_rows),
        source_pre_submit_review_ready_count=sum(1 for r in src_rows if r.get("pre_submit_status") == "ENABLEMENT_PRE_SUBMIT_REVIEW_READY"),
        submit_decision_count=len(rows),
        submit_decision_review_ready_count=sum(1 for r in rows if r.get("submit_decision_status") == "ENABLEMENT_SUBMIT_DECISION_STUB_REVIEW_READY"),
        submit_decision_blocked_count=sum(1 for r in rows if r.get("submit_decision_status") == "ENABLEMENT_SUBMIT_DECISION_STUB_BLOCKED"),
        submit_decision_watchlist_count=sum(1 for r in rows if r.get("submit_decision_status") == "ENABLEMENT_SUBMIT_DECISION_STUB_WATCHLIST"),
        enablement_submit_decision_stub_created=True,
        submit_decision_mode=SUBMIT_DECISION_MODE,
        submit_decision_stub_only=True,
        submit_decision_template_created=True,
        submit_decision_approved=False,
        submit_decision_recorded=False,
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
        submit_decisions=rows,
        blocker_summary=_summary(rows),
    )
    payload = result.to_dict()
    result.result_sha256 = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    if write_output:
        _write_json(json_path, {"submit_decisions": rows})
        _write_jsonl(jsonl_path, rows)
        _write_csv(csv_path, rows)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_render_md(result), encoding="utf-8")
        _write_json(latest_path, result.to_dict())
    return result


def validate_enablement_submit_decision_stub_review(root: str | Path) -> Step234ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step234_enablement_submit_decision_stub_review_latest.json"
    if not result_path.exists():
        execute_enablement_submit_decision_stub_review(root_path, write_output=True)
    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    rows = list(payload.get("submit_decisions", []) or [])
    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step233_present": Path(payload.get("source_step233_result_path", "")).exists(),
        "submit_decisions_json_exists": Path(payload.get("submit_decisions_json_path", "")).exists(),
        "submit_decisions_jsonl_exists": Path(payload.get("submit_decisions_jsonl_path", "")).exists(),
        "submit_decisions_csv_exists": Path(payload.get("submit_decisions_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_pre_submit_records_present": int(payload.get("source_pre_submit_record_count", 0)) > 0,
        "submit_decisions_present": int(payload.get("submit_decision_count", 0)) > 0 and bool(rows),
        "submit_decision_stub_created": payload.get("enablement_submit_decision_stub_created") is True and all(r.get("submit_decision_record_created") is True for r in rows),
        "submit_decision_mode_stub_only": payload.get("submit_decision_mode") == SUBMIT_DECISION_MODE and all(r.get("submit_decision_mode") == SUBMIT_DECISION_MODE for r in rows),
        "no_submit_decision_approved": payload.get("submit_decision_approved") is False and all(r.get("submit_decision_approved") is False for r in rows),
        "no_submit_decision_recorded": payload.get("submit_decision_recorded") is False and all(r.get("submit_decision_recorded") is False for r in rows),
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
    return Step234ValidationResult(
        status=STEP234_VALIDATION_OK if not failures else "STEP234_V5_ENABLEMENT_SUBMIT_DECISION_STUB_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
