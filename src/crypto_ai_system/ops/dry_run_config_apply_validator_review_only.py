from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.dry_run_paper_execution_config_review import (
    execute_dry_run_paper_execution_config_review,
)

STEP222_STATUS_OK = "STEP222_V5_DRY_RUN_CONFIG_APPLY_VALIDATOR_REVIEW_ONLY_OK"
STEP222_VALIDATION_OK = "STEP222_V5_DRY_RUN_CONFIG_APPLY_VALIDATOR_REVIEW_ONLY_VALIDATION_OK"

VALIDATOR_SCHEMA_VERSION = "step222_v5_dry_run_config_apply_validator_review_only"


@dataclass
class DryRunConfigApplyValidationRecord:
    apply_validation_id: str
    config_draft_id: str
    enablement_plan_id: str
    approval_validation_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    side: str
    source_config_status: str
    source_config_mode: str
    validation_status: str
    validation_passed: bool
    validation_schema_version: str
    checklist: Dict[str, bool]
    risk_limit_validation: Dict[str, bool]
    runtime_guard_validation: Dict[str, bool]
    disable_flag_validation: Dict[str, bool]
    validation_blockers: List[str]
    validation_warnings: List[str]
    next_required_step: str
    config_apply_validation_created: bool
    config_apply_validation_passed: bool
    config_apply_allowed: bool
    config_applied: bool
    paper_execution_enabled: bool
    paper_execution_enablement_allowed: bool
    paper_execution_upgrade_allowed: bool
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    adapter_routing_enabled: bool
    shadow_execution_enabled: bool
    limited_live_review_allowed: bool
    live_trading_allowed: bool
    strategy_registry_write_allowed: bool
    promotion_allowed: bool
    live_order_executed: bool
    validated_at_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step222DryRunConfigApplyValidatorResult:
    status: str
    root: str
    source_step221_result_path: str
    apply_validation_records_json_path: str
    apply_validation_records_jsonl_path: str
    apply_validation_records_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_config_draft_count: int
    source_config_review_ready_count: int
    apply_validation_record_count: int
    apply_validation_passed_count: int
    apply_validation_blocked_count: int
    apply_validation_watchlist_count: int
    dry_run_config_apply_validator_created: bool
    config_apply_validation_performed: bool
    config_apply_allowed: bool
    config_applied: bool
    paper_execution_enabled: bool
    paper_execution_enablement_allowed: bool
    paper_execution_upgrade_allowed: bool
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    adapter_routing_enabled: bool
    shadow_execution_enabled: bool
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
    records: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step222ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step221_present: bool
    apply_validation_records_json_exists: bool
    apply_validation_records_jsonl_exists: bool
    apply_validation_records_csv_exists: bool
    markdown_report_exists: bool
    source_config_drafts_present: bool
    apply_validation_records_present: bool
    apply_validator_created: bool
    validation_performed: bool
    no_config_apply_allowed: bool
    no_config_applied: bool
    no_paper_execution_enabled: bool
    no_enablement_allowed: bool
    no_paper_execution_upgrade: bool
    no_paper_order_execution: bool
    no_adapter_routing: bool
    no_shadow_execution: bool
    no_limited_live_review: bool
    no_live_trading: bool
    no_strategy_registry_write: bool
    no_promotion_allowed: bool
    no_auto_strategy_promotion: bool
    no_external_api_calls: bool
    no_live_side_effects: bool
    no_production_cutover: bool
    blocking_failure_count: int
    blocking_failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["apply_validation_id", "validation_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["checklist"] = json.dumps(out.get("checklist", {}), sort_keys=True)
            out["risk_limit_validation"] = json.dumps(out.get("risk_limit_validation", {}), sort_keys=True)
            out["runtime_guard_validation"] = json.dumps(out.get("runtime_guard_validation", {}), sort_keys=True)
            out["disable_flag_validation"] = json.dumps(out.get("disable_flag_validation", {}), sort_keys=True)
            out["validation_blockers"] = "|".join(out.get("validation_blockers", []))
            out["validation_warnings"] = "|".join(out.get("validation_warnings", []))
            writer.writerow(out)


def _ensure_step221(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step221_dry_run_paper_execution_config_review_only_latest.json"
    if not path.exists():
        execute_dry_run_paper_execution_config_review(root, write_output=True)
    return _load_json(path)


def _load_step221_drafts(step221: Dict[str, Any]) -> List[Dict[str, Any]]:
    drafts_path = Path(step221.get("config_drafts_json_path", ""))
    if drafts_path.exists():
        return list(_load_json(drafts_path).get("drafts", []) or [])
    return list(step221.get("drafts", []) or [])


def _validation_id(draft: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            "step222_dry_run_config_apply_validation",
            str(draft.get("config_draft_id", "")),
            str(draft.get("enablement_plan_id", "")),
            str(draft.get("observation_id", "")),
        ]
    )
    return "cfgval_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _risk_limit_validation(draft: Dict[str, Any]) -> Dict[str, bool]:
    limits = draft.get("risk_limits", {}) if isinstance(draft.get("risk_limits", {}), dict) else {}
    return {
        "max_paper_notional_positive": float(limits.get("max_paper_notional_usd", 0.0)) > 0,
        "max_daily_paper_loss_positive": float(limits.get("max_daily_paper_loss_usd", 0.0)) > 0,
        "max_paper_positions_positive": int(limits.get("max_paper_positions", 0)) > 0,
        "per_trade_notional_cap_required": limits.get("per_trade_notional_cap_required") is True,
        "daily_loss_stop_required": limits.get("daily_loss_stop_required") is True,
        "position_count_cap_required": limits.get("position_count_cap_required") is True,
        "idempotency_required": limits.get("idempotency_required") is True,
        "kill_switch_required": limits.get("kill_switch_required") is True,
    }


def _runtime_guard_validation(draft: Dict[str, Any]) -> Dict[str, bool]:
    guards = draft.get("required_runtime_guards", {}) if isinstance(draft.get("required_runtime_guards", {}), dict) else {}
    required = [
        "data_quality_gate_required",
        "research_signal_gate_required",
        "strategy_condition_gate_required",
        "risk_guard_required",
        "execution_guard_required",
        "idempotency_required",
        "kill_switch_required",
        "operator_disable_flag_required",
        "paper_mode_only_required",
    ]
    return {key: guards.get(key) is True for key in required}


def _disable_flag_validation(draft: Dict[str, Any]) -> Dict[str, bool]:
    flags = draft.get("disable_flags", {}) if isinstance(draft.get("disable_flags", {}), dict) else {}
    expected_false = [
        "config_apply_allowed",
        "config_applied",
        "paper_execution_enabled",
        "paper_order_execution_enabled",
        "paper_trade_execution_enabled",
        "adapter_routing_enabled",
        "shadow_execution_enabled",
        "limited_live_review_allowed",
        "live_trading_allowed",
        "strategy_registry_write_allowed",
        "promotion_allowed",
        "telegram_real_send",
    ]
    return {key: flags.get(key) is False for key in expected_false}


def _checklist(draft: Dict[str, Any], risk: Dict[str, bool], guards: Dict[str, bool], disables: Dict[str, bool]) -> Dict[str, bool]:
    return {
        "source_config_review_ready": str(draft.get("config_status", "")) == "DRY_RUN_PAPER_CONFIG_REVIEW_READY",
        "source_config_mode_draft_only": str(draft.get("config_mode", "")) == "DRY_RUN_CONFIG_DRAFT_ONLY",
        "config_draft_created": draft.get("config_draft_created") is True,
        "allowed_observation_ids_present": bool(draft.get("allowed_observation_ids", [])),
        "required_pre_trade_checks_present": bool(draft.get("required_pre_trade_checks", [])),
        "risk_limits_valid": all(risk.values()) if risk else False,
        "runtime_guards_valid": all(guards.values()) if guards else False,
        "disable_flags_valid": all(disables.values()) if disables else False,
        "config_apply_allowed_false": draft.get("config_apply_allowed") is False,
        "config_applied_false": draft.get("config_applied") is False,
        "paper_execution_enabled_false": draft.get("paper_execution_enabled") is False,
        "paper_order_execution_enabled_false": draft.get("paper_order_execution_enabled") is False,
        "adapter_routing_enabled_false": draft.get("adapter_routing_enabled") is False,
        "live_trading_allowed_false": draft.get("live_trading_allowed") is False,
    }


def _validation_blockers(draft: Dict[str, Any], checklist: Dict[str, bool], risk: Dict[str, bool], guards: Dict[str, bool], disables: Dict[str, bool]) -> List[str]:
    blockers = list(draft.get("config_blockers", []) or [])
    if not checklist.get("source_config_review_ready", False):
        blockers.append("SOURCE_CONFIG_NOT_REVIEW_READY")
    if not checklist.get("source_config_mode_draft_only", False):
        blockers.append("SOURCE_CONFIG_MODE_NOT_DRAFT_ONLY")
    if not checklist.get("allowed_observation_ids_present", False):
        blockers.append("ALLOWED_OBSERVATION_IDS_MISSING")
    if not checklist.get("required_pre_trade_checks_present", False):
        blockers.append("PRE_TRADE_CHECKS_MISSING")
    for key, ok in risk.items():
        if not ok:
            blockers.append(f"RISK_LIMIT_INVALID:{key}")
    for key, ok in guards.items():
        if not ok:
            blockers.append(f"RUNTIME_GUARD_INVALID:{key}")
    for key, ok in disables.items():
        if not ok:
            blockers.append(f"DISABLE_FLAG_INVALID:{key}")
    if not checklist.get("config_apply_allowed_false", False):
        blockers.append("CONFIG_APPLY_ALLOWED_NOT_FALSE")
    if not checklist.get("config_applied_false", False):
        blockers.append("CONFIG_APPLIED_NOT_FALSE")
    if not checklist.get("paper_execution_enabled_false", False):
        blockers.append("PAPER_EXECUTION_ENABLED_NOT_FALSE")
    if not checklist.get("paper_order_execution_enabled_false", False):
        blockers.append("PAPER_ORDER_EXECUTION_ENABLED_NOT_FALSE")
    if not checklist.get("adapter_routing_enabled_false", False):
        blockers.append("ADAPTER_ROUTING_ENABLED_NOT_FALSE")
    if not checklist.get("live_trading_allowed_false", False):
        blockers.append("LIVE_TRADING_ALLOWED_NOT_FALSE")
    blockers.append("STEP222_REVIEW_ONLY_NO_CONFIG_APPLY")
    return sorted(set(str(b) for b in blockers if str(b)))


def _validation_warnings(draft: Dict[str, Any]) -> List[str]:
    warnings = list(draft.get("config_warnings", []) or [])
    warnings.append("CONFIG_APPLY_VALIDATION_ONLY_NO_CONFIG_APPLY")
    warnings.append("STEP223_REQUIRED_FOR_CONTROLLED_CONFIG_ACTIVATION_REVIEW")
    warnings.append("OPERATOR_APPROVAL_MUST_BE_RECHECKED_BEFORE_ANY_CONFIG_APPLY")
    return sorted(set(str(w) for w in warnings if str(w)))


def _validation_status(blockers: List[str], checklist: Dict[str, bool]) -> str:
    hard_prefixes = ("RISK_LIMIT_INVALID:", "RUNTIME_GUARD_INVALID:", "DISABLE_FLAG_INVALID:")
    hard_exact = {
        "SOURCE_CONFIG_NOT_REVIEW_READY",
        "SOURCE_CONFIG_MODE_NOT_DRAFT_ONLY",
        "ALLOWED_OBSERVATION_IDS_MISSING",
        "PRE_TRADE_CHECKS_MISSING",
        "CONFIG_APPLY_ALLOWED_NOT_FALSE",
        "CONFIG_APPLIED_NOT_FALSE",
        "PAPER_EXECUTION_ENABLED_NOT_FALSE",
        "PAPER_ORDER_EXECUTION_ENABLED_NOT_FALSE",
        "ADAPTER_ROUTING_ENABLED_NOT_FALSE",
        "LIVE_TRADING_ALLOWED_NOT_FALSE",
    }
    if any(b in hard_exact or b.startswith(hard_prefixes) for b in blockers):
        return "DRY_RUN_CONFIG_APPLY_VALIDATION_BLOCKED"
    if all(checklist.values()):
        return "DRY_RUN_CONFIG_APPLY_VALIDATION_PASSED_REVIEW_ONLY"
    return "DRY_RUN_CONFIG_APPLY_VALIDATION_WATCHLIST"


def _next_required_step(status: str) -> str:
    if status == "DRY_RUN_CONFIG_APPLY_VALIDATION_PASSED_REVIEW_ONLY":
        return "STEP223_CONTROLLED_CONFIG_ACTIVATION_REVIEW_ONLY"
    if status == "DRY_RUN_CONFIG_APPLY_VALIDATION_WATCHLIST":
        return "REVIEW_CONFIG_DRAFT_BEFORE_CONTROLLED_ACTIVATION"
    return "DO_NOT_CREATE_CONTROLLED_ACTIVATION_UNTIL_BLOCKERS_RESOLVED"


def _build_record(draft: Dict[str, Any]) -> DryRunConfigApplyValidationRecord:
    risk = _risk_limit_validation(draft)
    guards = _runtime_guard_validation(draft)
    disables = _disable_flag_validation(draft)
    checklist = _checklist(draft, risk, guards, disables)
    blockers = _validation_blockers(draft, checklist, risk, guards, disables)
    status = _validation_status(blockers, checklist)
    passed = status == "DRY_RUN_CONFIG_APPLY_VALIDATION_PASSED_REVIEW_ONLY"

    return DryRunConfigApplyValidationRecord(
        apply_validation_id=_validation_id(draft),
        config_draft_id=str(draft.get("config_draft_id", "")),
        enablement_plan_id=str(draft.get("enablement_plan_id", "")),
        approval_validation_id=str(draft.get("approval_validation_id", "")),
        observation_id=str(draft.get("observation_id", "")),
        registry_id=str(draft.get("registry_id", "")),
        comparison_group=str(draft.get("comparison_group", "")),
        side=str(draft.get("side", "")),
        source_config_status=str(draft.get("config_status", "")),
        source_config_mode=str(draft.get("config_mode", "")),
        validation_status=status,
        validation_passed=passed,
        validation_schema_version=VALIDATOR_SCHEMA_VERSION,
        checklist=checklist,
        risk_limit_validation=risk,
        runtime_guard_validation=guards,
        disable_flag_validation=disables,
        validation_blockers=blockers,
        validation_warnings=_validation_warnings(draft),
        next_required_step=_next_required_step(status),
        config_apply_validation_created=True,
        config_apply_validation_passed=passed,
        config_apply_allowed=False,
        config_applied=False,
        paper_execution_enabled=False,
        paper_execution_enablement_allowed=False,
        paper_execution_upgrade_allowed=False,
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        adapter_routing_enabled=False,
        shadow_execution_enabled=False,
        limited_live_review_allowed=False,
        live_trading_allowed=False,
        strategy_registry_write_allowed=False,
        promotion_allowed=False,
        live_order_executed=False,
        validated_at_utc=_utc_now(),
    )


def _blocker_summary(records: List[DryRunConfigApplyValidationRecord]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for record in records:
        if not record.validation_blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in record.validation_blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step222DryRunConfigApplyValidatorResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step222DryRunConfigApplyValidatorResult) -> str:
    lines = [
        "# Step222 v5 Dry-Run Config Apply Validator Review-Only",
        "",
        "Step222 validates Step221 dry-run paper execution config drafts before any future controlled activation step.",
        "This step is validation-only. It does not apply config, enable paper execution, route adapters, submit orders, approve limited-live review, write strategy registry state, send Telegram messages, or enable live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_config_draft_count: {result.source_config_draft_count}",
        f"- source_config_review_ready_count: {result.source_config_review_ready_count}",
        f"- apply_validation_record_count: {result.apply_validation_record_count}",
        f"- apply_validation_passed_count: {result.apply_validation_passed_count}",
        f"- apply_validation_blocked_count: {result.apply_validation_blocked_count}",
        f"- apply_validation_watchlist_count: {result.apply_validation_watchlist_count}",
        f"- config_apply_allowed: {result.config_apply_allowed}",
        f"- config_applied: {result.config_applied}",
        f"- paper_execution_enabled: {result.paper_execution_enabled}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        f"- live_trading_allowed: {result.live_trading_allowed}",
        "",
        "## Apply validation records",
    ]
    for record in result.records:
        blockers = ", ".join(record.get("validation_blockers", [])) if record.get("validation_blockers") else "NO_BLOCKER"
        warnings = ", ".join(record.get("validation_warnings", [])) if record.get("validation_warnings") else "NO_WARNING"
        lines.append(
            "- `{group}` {side}: status={status}, passed={passed}, source_config={source}, blockers={blockers}, warnings={warnings}".format(
                group=record.get("comparison_group", ""),
                side=record.get("side", ""),
                status=record.get("validation_status", ""),
                passed=record.get("validation_passed", False),
                source=record.get("source_config_status", ""),
                blockers=blockers,
                warnings=warnings,
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step222 validates config apply readiness only.",
            "- `config_apply_allowed` remains false.",
            "- `config_applied` remains false.",
            "- `paper_execution_enabled` remains false.",
            "- Step223 or later must explicitly create any future controlled activation review.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_dry_run_config_apply_validator_review_only(root: str | Path, *, write_output: bool = True) -> Step222DryRunConfigApplyValidatorResult:
    root_path = Path(root).resolve()
    step221_path = root_path / "storage/latest/step221_dry_run_paper_execution_config_review_only_latest.json"
    step221 = _ensure_step221(root_path)
    drafts = _load_step221_drafts(step221)
    records = [_build_record(draft) for draft in drafts]
    record_dicts = [record.to_dict() for record in records]

    apply_validation_records_json_path = root_path / "data/reports/step222_dry_run_config_apply_validation_records.json"
    apply_validation_records_jsonl_path = root_path / "data/stores/step222_dry_run_config_apply_validation_records.jsonl"
    apply_validation_records_csv_path = root_path / "data/reports/step222_dry_run_config_apply_validation_records.csv"
    markdown_report_path = root_path / "data/reports/step222_dry_run_config_apply_validator_review_only_report.md"
    latest_result_path = root_path / "storage/latest/step222_dry_run_config_apply_validator_review_only_latest.json"

    result = Step222DryRunConfigApplyValidatorResult(
        status=STEP222_STATUS_OK,
        root=str(root_path),
        source_step221_result_path=str(step221_path),
        apply_validation_records_json_path=str(apply_validation_records_json_path),
        apply_validation_records_jsonl_path=str(apply_validation_records_jsonl_path),
        apply_validation_records_csv_path=str(apply_validation_records_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        source_config_draft_count=len(drafts),
        source_config_review_ready_count=sum(1 for draft in drafts if draft.get("config_status") == "DRY_RUN_PAPER_CONFIG_REVIEW_READY"),
        apply_validation_record_count=len(records),
        apply_validation_passed_count=sum(1 for record in records if record.validation_passed),
        apply_validation_blocked_count=sum(1 for record in records if record.validation_status == "DRY_RUN_CONFIG_APPLY_VALIDATION_BLOCKED"),
        apply_validation_watchlist_count=sum(1 for record in records if record.validation_status == "DRY_RUN_CONFIG_APPLY_VALIDATION_WATCHLIST"),
        dry_run_config_apply_validator_created=True,
        config_apply_validation_performed=True,
        config_apply_allowed=False,
        config_applied=False,
        paper_execution_enabled=False,
        paper_execution_enablement_allowed=False,
        paper_execution_upgrade_allowed=False,
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        adapter_routing_enabled=False,
        shadow_execution_enabled=False,
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
        records=record_dicts,
        blocker_summary=_blocker_summary(records),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(apply_validation_records_json_path, {"records": record_dicts})
        _write_jsonl(apply_validation_records_jsonl_path, record_dicts)
        _write_csv(apply_validation_records_csv_path, record_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def validate_dry_run_config_apply_validator_review_only(root: str | Path) -> Step222ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step222_dry_run_config_apply_validator_review_only_latest.json"
    if not result_path.exists():
        execute_dry_run_config_apply_validator_review_only(root_path, write_output=True)

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    records = list(payload.get("records", []) or [])

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step221_present": Path(payload.get("source_step221_result_path", "")).exists(),
        "apply_validation_records_json_exists": Path(payload.get("apply_validation_records_json_path", "")).exists(),
        "apply_validation_records_jsonl_exists": Path(payload.get("apply_validation_records_jsonl_path", "")).exists(),
        "apply_validation_records_csv_exists": Path(payload.get("apply_validation_records_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_config_drafts_present": int(payload.get("source_config_draft_count", 0)) > 0,
        "apply_validation_records_present": int(payload.get("apply_validation_record_count", 0)) > 0 and bool(records),
        "apply_validator_created": payload.get("dry_run_config_apply_validator_created") is True
        and all(record.get("config_apply_validation_created") is True for record in records),
        "validation_performed": payload.get("config_apply_validation_performed") is True,
        "no_config_apply_allowed": payload.get("config_apply_allowed") is False
        and all(record.get("config_apply_allowed") is False for record in records),
        "no_config_applied": payload.get("config_applied") is False
        and all(record.get("config_applied") is False for record in records),
        "no_paper_execution_enabled": payload.get("paper_execution_enabled") is False
        and all(record.get("paper_execution_enabled") is False for record in records),
        "no_enablement_allowed": payload.get("paper_execution_enablement_allowed") is False
        and all(record.get("paper_execution_enablement_allowed") is False for record in records),
        "no_paper_execution_upgrade": payload.get("paper_execution_upgrade_allowed") is False
        and all(record.get("paper_execution_upgrade_allowed") is False for record in records),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False
        and all(record.get("paper_order_execution_enabled") is False for record in records),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False
        and all(record.get("adapter_routing_enabled") is False for record in records),
        "no_shadow_execution": payload.get("shadow_execution_enabled") is False
        and all(record.get("shadow_execution_enabled") is False for record in records),
        "no_limited_live_review": payload.get("limited_live_review_allowed") is False
        and all(record.get("limited_live_review_allowed") is False for record in records),
        "no_live_trading": payload.get("live_trading_allowed") is False
        and all(record.get("live_trading_allowed") is False for record in records),
        "no_strategy_registry_write": payload.get("strategy_registry_write_allowed") is False
        and all(record.get("strategy_registry_write_allowed") is False for record in records),
        "no_promotion_allowed": payload.get("promotion_allowed") is False
        and all(record.get("promotion_allowed") is False for record in records),
        "no_auto_strategy_promotion": payload.get("auto_strategy_promotion") is False,
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False
        and payload.get("real_adapter_call_performed") is False
        and payload.get("telegram_real_send") is False
        and all(record.get("live_order_executed") is False for record in records),
        "no_production_cutover": payload.get("production_cutover_executable") is False
        and payload.get("live_mode_enable_allowed") is False,
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step222ValidationResult(
        status=STEP222_VALIDATION_OK if not failures else "STEP222_V5_DRY_RUN_CONFIG_APPLY_VALIDATOR_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
