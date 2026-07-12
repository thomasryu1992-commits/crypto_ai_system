from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.paper_execution_mode_pre_enablement_audit_review import (
    execute_paper_execution_mode_pre_enablement_audit_review,
)

STEP228_STATUS_OK = "STEP228_V5_PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB_REVIEW_ONLY_OK"
STEP228_VALIDATION_OK = "STEP228_V5_PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB_REVIEW_ONLY_VALIDATION_OK"
REQUEST_STUB_MODE = "PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB_ONLY"


@dataclass
class Step228Result:
    status: str
    root: str
    source_step227_result_path: str
    request_stubs_json_path: str
    request_stubs_jsonl_path: str
    request_stubs_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_audit_record_count: int
    source_audit_review_ready_count: int
    request_stub_count: int
    request_stub_review_ready_count: int
    request_stub_blocked_count: int
    request_stub_watchlist_count: int
    paper_execution_enablement_request_stub_review_created: bool
    request_stub_mode: str
    request_stub_only: bool
    enablement_request_created: bool
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
    request_stubs: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step228ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step227_present: bool
    request_stubs_json_exists: bool
    request_stubs_jsonl_exists: bool
    request_stubs_csv_exists: bool
    markdown_report_exists: bool
    source_audit_records_present: bool
    request_stubs_present: bool
    request_stub_review_created: bool
    request_stub_mode_only: bool
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
    fields = list(rows[0].keys()) if rows else ["enablement_request_stub_id", "request_stub_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("request_template", "request_preconditions", "request_limits"):
                out[key] = json.dumps(out.get(key, {}), sort_keys=True)
            for key in ("request_blockers", "request_warnings"):
                out[key] = "|".join(out.get(key, []))
            writer.writerow(out)


def _ensure_step227(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step227_paper_execution_mode_pre_enablement_audit_review_latest.json"
    if not path.exists():
        execute_paper_execution_mode_pre_enablement_audit_review(root, write_output=True)
    return _load_json(path)


def _load_audit_records(step227: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = Path(step227.get("audit_records_json_path", ""))
    if path.exists():
        return list(_load_json(path).get("audit_records", []) or [])
    return list(step227.get("audit_records", []) or [])


def _request_stub(src: Dict[str, Any]) -> Dict[str, Any]:
    preconditions = {
        "source_audit_review_ready": src.get("audit_status") == "PAPER_EXECUTION_PRE_ENABLEMENT_AUDIT_REVIEW_READY",
        "source_audit_mode_review_only": src.get("audit_mode") == "PAPER_EXECUTION_MODE_PRE_ENABLEMENT_AUDIT_REVIEW_ONLY",
        "source_audit_record_created": src.get("audit_record_created") is True,
        "source_pre_enablement_audit_passed_false": src.get("pre_enablement_audit_passed") is False,
        "source_paper_execution_enablement_allowed_false": src.get("paper_execution_enablement_allowed") is False,
        "source_paper_execution_enabled_false": src.get("paper_execution_enabled") is False,
        "source_paper_order_execution_enabled_false": src.get("paper_order_execution_enabled") is False,
        "source_paper_trade_execution_enabled_false": src.get("paper_trade_execution_enabled") is False,
        "source_adapter_routing_enabled_false": src.get("adapter_routing_enabled") is False,
        "source_shadow_execution_enabled_false": src.get("shadow_execution_enabled") is False,
        "source_live_trading_allowed_false": src.get("live_trading_allowed") is False,
    }
    blockers = list(src.get("audit_blockers", []) or [])
    for key, ok in preconditions.items():
        if not ok:
            blockers.append(key.upper() + "_FAILED")
    blockers.append("STEP228_REVIEW_ONLY_NO_ENABLEMENT_REQUEST_SUBMIT")
    blockers = sorted(set(blockers))
    hard = [b for b in blockers if b != "STEP228_REVIEW_ONLY_NO_ENABLEMENT_REQUEST_SUBMIT"]
    status = "PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB_REVIEW_READY" if not hard and all(preconditions.values()) else "PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB_BLOCKED"
    rid = "enreq_" + hashlib.sha1(
        "|".join([
            str(src.get("audit_record_id", "")),
            str(src.get("shadow_ready_decision_id", "")),
            str(src.get("observation_id", "")),
        ]).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "enablement_request_stub_id": rid,
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
        "source_audit_status": str(src.get("audit_status", "")),
        "request_stub_mode": REQUEST_STUB_MODE,
        "request_stub_status": status,
        "request_template": {
            "request_type": "PAPER_EXECUTION_ENABLEMENT_REQUEST_TEMPLATE",
            "request_mode": REQUEST_STUB_MODE,
            "audit_record_id": str(src.get("audit_record_id", "")),
            "observation_id": str(src.get("observation_id", "")),
            "registry_id": str(src.get("registry_id", "")),
            "side": str(src.get("side", "")),
            "requires_operator_final_approval": True,
            "requires_risk_limit_snapshot": True,
            "requires_kill_switch": True,
            "requires_telegram_dry_run_notice": True,
            "paper_only": True,
            "submit_to_runtime": False,
            "live_trading_allowed": False,
        },
        "request_preconditions": preconditions,
        "request_limits": {
            "paper_execution_enabled": False,
            "paper_order_execution_enabled": False,
            "adapter_routing_enabled": False,
            "shadow_execution_enabled": False,
            "live_trading_allowed": False,
        },
        "request_blockers": blockers,
        "request_warnings": sorted(set(list(src.get("audit_warnings", []) or []) + [
            "ENABLEMENT_REQUEST_STUB_ONLY_NO_SUBMIT",
            "STEP229_REQUIRED_FOR_ENABLEMENT_REQUEST_FINAL_VALIDATOR",
        ])),
        "next_required_step": "STEP229_PAPER_EXECUTION_ENABLEMENT_REQUEST_FINAL_VALIDATOR_REVIEW_ONLY" if status.endswith("REVIEW_READY") else "DO_NOT_VALIDATE_ENABLEMENT_REQUEST_UNTIL_BLOCKERS_RESOLVED",
        "request_stub_created": True,
        "enablement_request_created": True,
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
        for blocker in row.get("request_blockers", []):
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _render_md(result: Step228Result) -> str:
    lines = [
        "# Step228 v5 Paper Execution Enablement Request Stub Review-Only",
        "",
        "Step228 creates paper execution enablement request stubs from Step227 pre-enablement audit records.",
        "This is request-stub-only and does not submit requests, enable paper execution, route adapters, or live trade.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_audit_record_count: {result.source_audit_record_count}",
        f"- request_stub_count: {result.request_stub_count}",
        f"- request_stub_review_ready_count: {result.request_stub_review_ready_count}",
        f"- request_stub_blocked_count: {result.request_stub_blocked_count}",
        f"- request_stub_mode: `{result.request_stub_mode}`",
        f"- enablement_request_submitted: {result.enablement_request_submitted}",
        f"- paper_execution_enabled: {result.paper_execution_enabled}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        "",
        "## Request stubs",
    ]
    for row in result.request_stubs:
        blockers = ", ".join(row.get("request_blockers", [])) if row.get("request_blockers") else "NO_BLOCKER"
        lines.append(f"- `{row.get('comparison_group','')}` {row.get('side','')}: status={row.get('request_stub_status')}, submitted={row.get('enablement_request_submitted')}, blockers={blockers}")
    return "\n".join(lines) + "\n"


def execute_paper_execution_enablement_request_stub_review(root: str | Path, *, write_output: bool = True) -> Step228Result:
    root_path = Path(root).resolve()
    step227_path = root_path / "storage/latest/step227_paper_execution_mode_pre_enablement_audit_review_latest.json"
    step227 = _ensure_step227(root_path)
    src_rows = _load_audit_records(step227)
    rows = [_request_stub(r) for r in src_rows]

    json_path = root_path / "data/reports/step228_paper_execution_enablement_request_stubs.json"
    jsonl_path = root_path / "data/stores/step228_paper_execution_enablement_request_stubs.jsonl"
    csv_path = root_path / "data/reports/step228_paper_execution_enablement_request_stubs.csv"
    md_path = root_path / "data/reports/step228_paper_execution_enablement_request_stub_review_report.md"
    latest_path = root_path / "storage/latest/step228_paper_execution_enablement_request_stub_review_latest.json"

    result = Step228Result(
        status=STEP228_STATUS_OK,
        root=str(root_path),
        source_step227_result_path=str(step227_path),
        request_stubs_json_path=str(json_path),
        request_stubs_jsonl_path=str(jsonl_path),
        request_stubs_csv_path=str(csv_path),
        markdown_report_path=str(md_path),
        latest_result_path=str(latest_path),
        source_audit_record_count=len(src_rows),
        source_audit_review_ready_count=sum(1 for r in src_rows if r.get("audit_status") == "PAPER_EXECUTION_PRE_ENABLEMENT_AUDIT_REVIEW_READY"),
        request_stub_count=len(rows),
        request_stub_review_ready_count=sum(1 for r in rows if r.get("request_stub_status") == "PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB_REVIEW_READY"),
        request_stub_blocked_count=sum(1 for r in rows if r.get("request_stub_status") == "PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB_BLOCKED"),
        request_stub_watchlist_count=sum(1 for r in rows if r.get("request_stub_status") == "PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB_WATCHLIST"),
        paper_execution_enablement_request_stub_review_created=True,
        request_stub_mode=REQUEST_STUB_MODE,
        request_stub_only=True,
        enablement_request_created=True,
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
        request_stubs=rows,
        blocker_summary=_summary(rows),
    )
    payload = result.to_dict()
    result.result_sha256 = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    if write_output:
        _write_json(json_path, {"request_stubs": rows})
        _write_jsonl(jsonl_path, rows)
        _write_csv(csv_path, rows)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_render_md(result), encoding="utf-8")
        _write_json(latest_path, result.to_dict())
    return result


def validate_paper_execution_enablement_request_stub_review(root: str | Path) -> Step228ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step228_paper_execution_enablement_request_stub_review_latest.json"
    if not result_path.exists():
        execute_paper_execution_enablement_request_stub_review(root_path, write_output=True)
    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    rows = list(payload.get("request_stubs", []) or [])
    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step227_present": Path(payload.get("source_step227_result_path", "")).exists(),
        "request_stubs_json_exists": Path(payload.get("request_stubs_json_path", "")).exists(),
        "request_stubs_jsonl_exists": Path(payload.get("request_stubs_jsonl_path", "")).exists(),
        "request_stubs_csv_exists": Path(payload.get("request_stubs_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_audit_records_present": int(payload.get("source_audit_record_count", 0)) > 0,
        "request_stubs_present": int(payload.get("request_stub_count", 0)) > 0 and bool(rows),
        "request_stub_review_created": payload.get("paper_execution_enablement_request_stub_review_created") is True and all(r.get("request_stub_created") is True for r in rows),
        "request_stub_mode_only": payload.get("request_stub_mode") == REQUEST_STUB_MODE and all(r.get("request_stub_mode") == REQUEST_STUB_MODE for r in rows),
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
    return Step228ValidationResult(
        status=STEP228_VALIDATION_OK if not failures else "STEP228_V5_PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
