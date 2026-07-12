from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.enablement_submit_gate_review import (
    execute_enablement_submit_gate_review,
)

STEP237_STATUS_OK = "STEP237_V5_ENABLEMENT_SUBMIT_DRY_RUN_REVIEW_ONLY_OK"
STEP237_VALIDATION_OK = "STEP237_V5_ENABLEMENT_SUBMIT_DRY_RUN_REVIEW_ONLY_VALIDATION_OK"
DRY_RUN_MODE = "ENABLEMENT_SUBMIT_DRY_RUN_REVIEW_ONLY"


@dataclass
class Step237Result:
    status: str
    root: str
    source_step236_result_path: str
    dry_run_records_json_path: str
    dry_run_records_jsonl_path: str
    dry_run_records_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_submit_gate_record_count: int
    source_submit_gate_review_ready_count: int
    dry_run_record_count: int
    dry_run_review_ready_count: int
    dry_run_blocked_count: int
    dry_run_watchlist_count: int
    enablement_submit_dry_run_review_created: bool
    dry_run_mode: str
    dry_run_review_only: bool
    dry_run_artifact_created: bool
    dry_run_passed: bool
    submit_gate_passed: bool
    submit_gate_opened: bool
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
    dry_run_records: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step237ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step236_present: bool
    dry_run_records_json_exists: bool
    dry_run_records_jsonl_exists: bool
    dry_run_records_csv_exists: bool
    markdown_report_exists: bool
    source_submit_gate_records_present: bool
    dry_run_records_present: bool
    dry_run_review_created: bool
    dry_run_mode_review_only: bool
    dry_run_artifact_created: bool
    no_dry_run_passed: bool
    no_submit_gate_passed: bool
    no_submit_gate_opened: bool
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
    fields = list(rows[0].keys()) if rows else ["enablement_submit_dry_run_record_id", "dry_run_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("dry_run_checklist", "dry_run_artifact", "dry_run_context"):
                out[key] = json.dumps(out.get(key, {}), sort_keys=True)
            for key in ("dry_run_blockers", "dry_run_warnings"):
                out[key] = "|".join(out.get(key, []))
            writer.writerow(out)


def _ensure_step236(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step236_enablement_submit_gate_review_latest.json"
    if not path.exists():
        execute_enablement_submit_gate_review(root, write_output=True)
    return _load_json(path)


def _load_submit_gate_records(step236: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = Path(step236.get("submit_gate_records_json_path", ""))
    if path.exists():
        return list(_load_json(path).get("submit_gate_records", []) or [])
    return list(step236.get("submit_gate_records", []) or [])


def _dry_run_record(src: Dict[str, Any]) -> Dict[str, Any]:
    gate_payload = src.get("submit_gate_payload", {}) if isinstance(src.get("submit_gate_payload", {}), dict) else {}
    checklist = {
        "source_submit_gate_review_ready": src.get("submit_gate_status") == "ENABLEMENT_SUBMIT_GATE_REVIEW_READY",
        "source_submit_gate_mode_review_only": src.get("submit_gate_mode") == "ENABLEMENT_SUBMIT_GATE_REVIEW_ONLY",
        "source_submit_gate_record_created": src.get("submit_gate_record_created") is True,
        "source_submit_gate_passed_false": src.get("submit_gate_passed") is False,
        "source_submit_gate_opened_false": src.get("submit_gate_opened") is False,
        "source_enablement_request_submit_allowed_false": src.get("enablement_request_submit_allowed") is False,
        "source_enablement_request_submitted_false": src.get("enablement_request_submitted") is False,
        "source_paper_execution_enablement_allowed_false": src.get("paper_execution_enablement_allowed") is False,
        "source_paper_execution_enabled_false": src.get("paper_execution_enabled") is False,
        "source_paper_order_execution_enabled_false": src.get("paper_order_execution_enabled") is False,
        "source_adapter_routing_enabled_false": src.get("adapter_routing_enabled") is False,
        "source_shadow_execution_enabled_false": src.get("shadow_execution_enabled") is False,
        "source_live_trading_allowed_false": src.get("live_trading_allowed") is False,
        "submit_gate_payload_present": bool(gate_payload),
        "gate_payload_submit_false": gate_payload.get("submit_enablement_request") is False,
        "gate_payload_gate_opened_false": gate_payload.get("submit_gate_opened") is False,
        "gate_payload_keeps_execution_disabled": gate_payload.get("enable_paper_execution") is False
        and gate_payload.get("enable_paper_order_execution") is False
        and gate_payload.get("enable_adapter_routing") is False
        and gate_payload.get("enable_shadow_execution") is False
        and gate_payload.get("live_trading_allowed") is False,
    }
    blockers = list(src.get("submit_gate_blockers", []) or [])
    for key, ok in checklist.items():
        if not ok:
            blockers.append(key.upper() + "_FAILED")
    blockers.append("STEP237_REVIEW_ONLY_NO_REAL_ENABLEMENT_SUBMIT")
    blockers = sorted(set(blockers))
    hard = [b for b in blockers if b != "STEP237_REVIEW_ONLY_NO_REAL_ENABLEMENT_SUBMIT"]
    status = "ENABLEMENT_SUBMIT_DRY_RUN_REVIEW_READY" if not hard and all(checklist.values()) else "ENABLEMENT_SUBMIT_DRY_RUN_BLOCKED"
    rid = "submitdry_" + hashlib.sha1(
        "|".join([
            str(src.get("enablement_submit_gate_record_id", "")),
            str(src.get("enablement_request_stub_id", "")),
            str(src.get("observation_id", "")),
        ]).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "enablement_submit_dry_run_record_id": rid,
        "enablement_submit_gate_record_id": str(src.get("enablement_submit_gate_record_id", "")),
        "enablement_submit_decision_intake_record_id": str(src.get("enablement_submit_decision_intake_record_id", "")),
        "enablement_submit_decision_id": str(src.get("enablement_submit_decision_id", "")),
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
        "source_submit_gate_status": str(src.get("submit_gate_status", "")),
        "dry_run_mode": DRY_RUN_MODE,
        "dry_run_status": status,
        "dry_run_checklist": checklist,
        "dry_run_context": {
            "dry_run_artifact_created": True,
            "dry_run_review_only": True,
            "would_submit_enablement_request": False,
            "requires_step238_dry_run_result_validator": True,
            "paper_only": True,
            "live_trading_allowed": False,
        },
        "dry_run_artifact": {
            "dry_run_type": "ENABLEMENT_SUBMIT_DRY_RUN_ARTIFACT",
            "enablement_request_stub_id": str(src.get("enablement_request_stub_id", "")),
            "enablement_submit_gate_record_id": str(src.get("enablement_submit_gate_record_id", "")),
            "observation_id": str(src.get("observation_id", "")),
            "registry_id": str(src.get("registry_id", "")),
            "side": str(src.get("side", "")),
            "dry_run_submit_attempted": False,
            "real_submit_attempted": False,
            "external_api_call_performed": False,
            "submit_endpoint_called": False,
            "paper_execution_enabled": False,
            "paper_order_execution_enabled": False,
            "adapter_routing_enabled": False,
            "shadow_execution_enabled": False,
            "live_trading_allowed": False,
        },
        "dry_run_blockers": blockers,
        "dry_run_warnings": sorted(set(list(src.get("submit_gate_warnings", []) or []) + [
            "ENABLEMENT_SUBMIT_DRY_RUN_REVIEW_ONLY_NO_REAL_SUBMIT",
            "STEP238_REQUIRED_FOR_DRY_RUN_RESULT_VALIDATOR",
        ])),
        "next_required_step": "STEP238_ENABLEMENT_SUBMIT_DRY_RUN_RESULT_VALIDATOR_REVIEW_ONLY" if status.endswith("REVIEW_READY") else "DO_NOT_VALIDATE_DRY_RUN_RESULT_UNTIL_BLOCKERS_RESOLVED",
        "dry_run_record_created": True,
        "dry_run_artifact_created": True,
        "dry_run_passed": False,
        "submit_gate_passed": False,
        "submit_gate_opened": False,
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
        "external_api_call_performed": False,
        "live_order_executed": False,
        "real_adapter_call_performed": False,
        "telegram_real_send": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _summary(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        for blocker in row.get("dry_run_blockers", []):
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _render_md(result: Step237Result) -> str:
    lines = [
        "# Step237 v5 Enablement Submit Dry-Run Review-Only",
        "",
        "Step237 creates enablement submit dry-run records from Step236 submit gate records.",
        "This is dry-run-review-only and does not submit enablement requests, enable paper execution, route adapters, or live trade.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_submit_gate_record_count: {result.source_submit_gate_record_count}",
        f"- source_submit_gate_review_ready_count: {result.source_submit_gate_review_ready_count}",
        f"- dry_run_record_count: {result.dry_run_record_count}",
        f"- dry_run_review_ready_count: {result.dry_run_review_ready_count}",
        f"- dry_run_blocked_count: {result.dry_run_blocked_count}",
        f"- dry_run_mode: `{result.dry_run_mode}`",
        f"- dry_run_artifact_created: {result.dry_run_artifact_created}",
        f"- dry_run_passed: {result.dry_run_passed}",
        f"- enablement_request_submitted: {result.enablement_request_submitted}",
        f"- paper_execution_enabled: {result.paper_execution_enabled}",
        "",
        "## Dry-run records",
    ]
    for row in result.dry_run_records:
        blockers = ", ".join(row.get("dry_run_blockers", [])) if row.get("dry_run_blockers") else "NO_BLOCKER"
        lines.append(f"- `{row.get('comparison_group','')}` {row.get('side','')}: status={row.get('dry_run_status')}, submitted={row.get('enablement_request_submitted')}, blockers={blockers}")
    return "\n".join(lines) + "\n"


def execute_enablement_submit_dry_run_review(root: str | Path, *, write_output: bool = True) -> Step237Result:
    root_path = Path(root).resolve()
    step236_path = root_path / "storage/latest/step236_enablement_submit_gate_review_latest.json"
    step236 = _ensure_step236(root_path)
    src_rows = _load_submit_gate_records(step236)
    rows = [_dry_run_record(r) for r in src_rows]

    json_path = root_path / "data/reports/step237_enablement_submit_dry_run_records.json"
    jsonl_path = root_path / "data/stores/step237_enablement_submit_dry_run_records.jsonl"
    csv_path = root_path / "data/reports/step237_enablement_submit_dry_run_records.csv"
    md_path = root_path / "data/reports/step237_enablement_submit_dry_run_review_report.md"
    latest_path = root_path / "storage/latest/step237_enablement_submit_dry_run_review_latest.json"

    result = Step237Result(
        status=STEP237_STATUS_OK,
        root=str(root_path),
        source_step236_result_path=str(step236_path),
        dry_run_records_json_path=str(json_path),
        dry_run_records_jsonl_path=str(jsonl_path),
        dry_run_records_csv_path=str(csv_path),
        markdown_report_path=str(md_path),
        latest_result_path=str(latest_path),
        source_submit_gate_record_count=len(src_rows),
        source_submit_gate_review_ready_count=sum(1 for r in src_rows if r.get("submit_gate_status") == "ENABLEMENT_SUBMIT_GATE_REVIEW_READY"),
        dry_run_record_count=len(rows),
        dry_run_review_ready_count=sum(1 for r in rows if r.get("dry_run_status") == "ENABLEMENT_SUBMIT_DRY_RUN_REVIEW_READY"),
        dry_run_blocked_count=sum(1 for r in rows if r.get("dry_run_status") == "ENABLEMENT_SUBMIT_DRY_RUN_BLOCKED"),
        dry_run_watchlist_count=sum(1 for r in rows if r.get("dry_run_status") == "ENABLEMENT_SUBMIT_DRY_RUN_WATCHLIST"),
        enablement_submit_dry_run_review_created=True,
        dry_run_mode=DRY_RUN_MODE,
        dry_run_review_only=True,
        dry_run_artifact_created=True,
        dry_run_passed=False,
        submit_gate_passed=False,
        submit_gate_opened=False,
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
        dry_run_records=rows,
        blocker_summary=_summary(rows),
    )
    payload = result.to_dict()
    result.result_sha256 = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    if write_output:
        _write_json(json_path, {"dry_run_records": rows})
        _write_jsonl(jsonl_path, rows)
        _write_csv(csv_path, rows)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_render_md(result), encoding="utf-8")
        _write_json(latest_path, result.to_dict())
    return result


def validate_enablement_submit_dry_run_review(root: str | Path) -> Step237ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step237_enablement_submit_dry_run_review_latest.json"
    if not result_path.exists():
        execute_enablement_submit_dry_run_review(root_path, write_output=True)
    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    rows = list(payload.get("dry_run_records", []) or [])
    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step236_present": Path(payload.get("source_step236_result_path", "")).exists(),
        "dry_run_records_json_exists": Path(payload.get("dry_run_records_json_path", "")).exists(),
        "dry_run_records_jsonl_exists": Path(payload.get("dry_run_records_jsonl_path", "")).exists(),
        "dry_run_records_csv_exists": Path(payload.get("dry_run_records_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_submit_gate_records_present": int(payload.get("source_submit_gate_record_count", 0)) > 0,
        "dry_run_records_present": int(payload.get("dry_run_record_count", 0)) > 0 and bool(rows),
        "dry_run_review_created": payload.get("enablement_submit_dry_run_review_created") is True and all(r.get("dry_run_record_created") is True for r in rows),
        "dry_run_mode_review_only": payload.get("dry_run_mode") == DRY_RUN_MODE and all(r.get("dry_run_mode") == DRY_RUN_MODE for r in rows),
        "dry_run_artifact_created": payload.get("dry_run_artifact_created") is True and all(r.get("dry_run_artifact_created") is True for r in rows),
        "no_dry_run_passed": payload.get("dry_run_passed") is False and all(r.get("dry_run_passed") is False for r in rows),
        "no_submit_gate_passed": payload.get("submit_gate_passed") is False and all(r.get("submit_gate_passed") is False for r in rows),
        "no_submit_gate_opened": payload.get("submit_gate_opened") is False and all(r.get("submit_gate_opened") is False for r in rows),
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
    return Step237ValidationResult(
        status=STEP237_VALIDATION_OK if not failures else "STEP237_V5_ENABLEMENT_SUBMIT_DRY_RUN_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
