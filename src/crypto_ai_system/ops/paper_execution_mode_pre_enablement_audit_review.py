from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.paper_execution_mode_shadow_ready_review import (
    execute_paper_execution_mode_shadow_ready_review,
)

STEP227_STATUS_OK = "STEP227_V5_PAPER_EXECUTION_MODE_PRE_ENABLEMENT_AUDIT_REVIEW_ONLY_OK"
STEP227_VALIDATION_OK = "STEP227_V5_PAPER_EXECUTION_MODE_PRE_ENABLEMENT_AUDIT_REVIEW_ONLY_VALIDATION_OK"
PRE_ENABLEMENT_AUDIT_MODE = "PAPER_EXECUTION_MODE_PRE_ENABLEMENT_AUDIT_REVIEW_ONLY"


@dataclass
class Step227Result:
    status: str
    root: str
    source_step226_result_path: str
    audit_records_json_path: str
    audit_records_jsonl_path: str
    audit_records_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_shadow_ready_decision_count: int
    source_shadow_ready_review_ready_count: int
    audit_record_count: int
    audit_review_ready_count: int
    audit_blocked_count: int
    audit_watchlist_count: int
    pre_enablement_audit_review_created: bool
    audit_mode: str
    audit_review_only: bool
    pre_enablement_audit_passed: bool
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
    audit_records: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step227ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step226_present: bool
    audit_records_json_exists: bool
    audit_records_jsonl_exists: bool
    audit_records_csv_exists: bool
    markdown_report_exists: bool
    source_shadow_ready_decisions_present: bool
    audit_records_present: bool
    audit_review_created: bool
    audit_mode_review_only: bool
    no_pre_enablement_audit_passed: bool
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
    fields = list(rows[0].keys()) if rows else ["audit_record_id", "audit_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("audit_checklist", "audit_context"):
                out[key] = json.dumps(out.get(key, {}), sort_keys=True)
            for key in ("audit_blockers", "audit_warnings"):
                out[key] = "|".join(out.get(key, []))
            writer.writerow(out)


def _ensure_step226(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step226_paper_execution_mode_shadow_ready_review_latest.json"
    if not path.exists():
        execute_paper_execution_mode_shadow_ready_review(root, write_output=True)
    return _load_json(path)


def _load_shadow_ready_decisions(step226: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = Path(step226.get("shadow_ready_decisions_json_path", ""))
    if path.exists():
        return list(_load_json(path).get("decisions", []) or [])
    return list(step226.get("decisions", []) or [])


def _audit_record(src: Dict[str, Any]) -> Dict[str, Any]:
    checklist = {
        "source_shadow_ready_review_ready": src.get("shadow_ready_status") == "PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW_READY",
        "source_shadow_ready_mode_review_only": src.get("shadow_ready_mode") == "PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW_ONLY",
        "source_shadow_ready_decision_created": src.get("shadow_ready_decision_created") is True,
        "source_shadow_ready_mode_allowed_false": src.get("shadow_ready_mode_allowed") is False,
        "source_shadow_ready_mode_enabled_false": src.get("shadow_ready_mode_enabled") is False,
        "source_paper_execution_enabled_false": src.get("paper_execution_enabled") is False,
        "source_paper_order_execution_enabled_false": src.get("paper_order_execution_enabled") is False,
        "source_paper_trade_execution_enabled_false": src.get("paper_trade_execution_enabled") is False,
        "source_adapter_routing_enabled_false": src.get("adapter_routing_enabled") is False,
        "source_shadow_execution_enabled_false": src.get("shadow_execution_enabled") is False,
        "source_live_trading_allowed_false": src.get("live_trading_allowed") is False,
        "source_strategy_registry_write_allowed_false": src.get("strategy_registry_write_allowed") is False,
    }
    blockers = list(src.get("shadow_ready_blockers", []) or [])
    for key, ok in checklist.items():
        if not ok:
            blockers.append(key.upper() + "_FAILED")
    blockers.append("STEP227_REVIEW_ONLY_NO_PRE_ENABLEMENT_PASS")
    blockers = sorted(set(blockers))
    hard = [b for b in blockers if b != "STEP227_REVIEW_ONLY_NO_PRE_ENABLEMENT_PASS"]
    status = "PAPER_EXECUTION_PRE_ENABLEMENT_AUDIT_REVIEW_READY" if not hard and all(checklist.values()) else "PAPER_EXECUTION_PRE_ENABLEMENT_AUDIT_BLOCKED"
    rid = "preaudit_" + hashlib.sha1(
        "|".join([
            str(src.get("shadow_ready_decision_id", "")),
            str(src.get("final_gate_decision_id", "")),
            str(src.get("observation_id", "")),
        ]).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "audit_record_id": rid,
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
        "source_shadow_ready_status": str(src.get("shadow_ready_status", "")),
        "audit_mode": PRE_ENABLEMENT_AUDIT_MODE,
        "audit_status": status,
        "audit_checklist": checklist,
        "audit_context": {
            "requires_operator_recheck": True,
            "requires_runtime_disable_flags_check": True,
            "requires_risk_limit_recheck": True,
            "requires_data_quality_gate": True,
            "requires_research_signal_gate": True,
            "requires_telegram_dry_run_alert_before_future_enablement": True,
            "review_only": True,
            "paper_only": True,
            "live_trading_allowed": False,
        },
        "audit_blockers": blockers,
        "audit_warnings": sorted(set(list(src.get("shadow_ready_warnings", []) or []) + [
            "PRE_ENABLEMENT_AUDIT_REVIEW_ONLY_NO_ENABLEMENT",
            "STEP228_REQUIRED_FOR_PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB",
        ])),
        "next_required_step": "STEP228_PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB_REVIEW_ONLY" if status.endswith("REVIEW_READY") else "DO_NOT_CREATE_ENABLEMENT_REQUEST_STUB_UNTIL_BLOCKERS_RESOLVED",
        "audit_record_created": True,
        "pre_enablement_audit_passed": False,
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
        for blocker in row.get("audit_blockers", []):
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _render_md(result: Step227Result) -> str:
    lines = [
        "# Step227 v5 Paper Execution Mode Pre-Enablement Audit Review-Only",
        "",
        "Step227 creates pre-enablement audit records from Step226 shadow-ready review decisions.",
        "This is review-only and does not enable paper execution, order execution, adapter routing, shadow execution, or live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_shadow_ready_decision_count: {result.source_shadow_ready_decision_count}",
        f"- audit_record_count: {result.audit_record_count}",
        f"- audit_review_ready_count: {result.audit_review_ready_count}",
        f"- audit_blocked_count: {result.audit_blocked_count}",
        f"- audit_mode: `{result.audit_mode}`",
        f"- pre_enablement_audit_passed: {result.pre_enablement_audit_passed}",
        f"- paper_execution_enabled: {result.paper_execution_enabled}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        "",
        "## Audit records",
    ]
    for row in result.audit_records:
        blockers = ", ".join(row.get("audit_blockers", [])) if row.get("audit_blockers") else "NO_BLOCKER"
        lines.append(f"- `{row.get('comparison_group','')}` {row.get('side','')}: status={row.get('audit_status')}, blockers={blockers}")
    return "\n".join(lines) + "\n"


def execute_paper_execution_mode_pre_enablement_audit_review(root: str | Path, *, write_output: bool = True) -> Step227Result:
    root_path = Path(root).resolve()
    step226_path = root_path / "storage/latest/step226_paper_execution_mode_shadow_ready_review_latest.json"
    step226 = _ensure_step226(root_path)
    src_rows = _load_shadow_ready_decisions(step226)
    rows = [_audit_record(r) for r in src_rows]

    json_path = root_path / "data/reports/step227_paper_execution_mode_pre_enablement_audit_records.json"
    jsonl_path = root_path / "data/stores/step227_paper_execution_mode_pre_enablement_audit_records.jsonl"
    csv_path = root_path / "data/reports/step227_paper_execution_mode_pre_enablement_audit_records.csv"
    md_path = root_path / "data/reports/step227_paper_execution_mode_pre_enablement_audit_review_report.md"
    latest_path = root_path / "storage/latest/step227_paper_execution_mode_pre_enablement_audit_review_latest.json"

    result = Step227Result(
        status=STEP227_STATUS_OK,
        root=str(root_path),
        source_step226_result_path=str(step226_path),
        audit_records_json_path=str(json_path),
        audit_records_jsonl_path=str(jsonl_path),
        audit_records_csv_path=str(csv_path),
        markdown_report_path=str(md_path),
        latest_result_path=str(latest_path),
        source_shadow_ready_decision_count=len(src_rows),
        source_shadow_ready_review_ready_count=sum(1 for r in src_rows if r.get("shadow_ready_status") == "PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW_READY"),
        audit_record_count=len(rows),
        audit_review_ready_count=sum(1 for r in rows if r.get("audit_status") == "PAPER_EXECUTION_PRE_ENABLEMENT_AUDIT_REVIEW_READY"),
        audit_blocked_count=sum(1 for r in rows if r.get("audit_status") == "PAPER_EXECUTION_PRE_ENABLEMENT_AUDIT_BLOCKED"),
        audit_watchlist_count=sum(1 for r in rows if r.get("audit_status") == "PAPER_EXECUTION_PRE_ENABLEMENT_AUDIT_WATCHLIST"),
        pre_enablement_audit_review_created=True,
        audit_mode=PRE_ENABLEMENT_AUDIT_MODE,
        audit_review_only=True,
        pre_enablement_audit_passed=False,
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
        audit_records=rows,
        blocker_summary=_summary(rows),
    )
    payload = result.to_dict()
    result.result_sha256 = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    if write_output:
        _write_json(json_path, {"audit_records": rows})
        _write_jsonl(jsonl_path, rows)
        _write_csv(csv_path, rows)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_render_md(result), encoding="utf-8")
        _write_json(latest_path, result.to_dict())
    return result


def validate_paper_execution_mode_pre_enablement_audit_review(root: str | Path) -> Step227ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step227_paper_execution_mode_pre_enablement_audit_review_latest.json"
    if not result_path.exists():
        execute_paper_execution_mode_pre_enablement_audit_review(root_path, write_output=True)
    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    rows = list(payload.get("audit_records", []) or [])
    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step226_present": Path(payload.get("source_step226_result_path", "")).exists(),
        "audit_records_json_exists": Path(payload.get("audit_records_json_path", "")).exists(),
        "audit_records_jsonl_exists": Path(payload.get("audit_records_jsonl_path", "")).exists(),
        "audit_records_csv_exists": Path(payload.get("audit_records_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_shadow_ready_decisions_present": int(payload.get("source_shadow_ready_decision_count", 0)) > 0,
        "audit_records_present": int(payload.get("audit_record_count", 0)) > 0 and bool(rows),
        "audit_review_created": payload.get("pre_enablement_audit_review_created") is True and all(r.get("audit_record_created") is True for r in rows),
        "audit_mode_review_only": payload.get("audit_mode") == PRE_ENABLEMENT_AUDIT_MODE and all(r.get("audit_mode") == PRE_ENABLEMENT_AUDIT_MODE for r in rows),
        "no_pre_enablement_audit_passed": payload.get("pre_enablement_audit_passed") is False and all(r.get("pre_enablement_audit_passed") is False for r in rows),
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
    return Step227ValidationResult(
        status=STEP227_VALIDATION_OK if not failures else "STEP227_V5_PAPER_EXECUTION_MODE_PRE_ENABLEMENT_AUDIT_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
