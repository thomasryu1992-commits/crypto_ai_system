from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.dry_run_config_apply_validator_review_only import (
    execute_dry_run_config_apply_validator_review_only,
)

STEP223_STATUS_OK = "STEP223_V5_CONTROLLED_CONFIG_ACTIVATION_REVIEW_ONLY_OK"
STEP223_VALIDATION_OK = "STEP223_V5_CONTROLLED_CONFIG_ACTIVATION_REVIEW_ONLY_VALIDATION_OK"

ACTIVATION_SCHEMA_VERSION = "step223_v5_controlled_config_activation_review_only"
ACTIVATION_MODE_REVIEW_ONLY = "CONTROLLED_ACTIVATION_REVIEW_ONLY"


@dataclass
class ControlledConfigActivationCandidate:
    activation_candidate_id: str
    apply_validation_id: str
    config_draft_id: str
    enablement_plan_id: str
    approval_validation_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    side: str
    source_validation_status: str
    source_validation_passed: bool
    activation_mode: str
    activation_status: str
    activation_schema_version: str
    activation_checklist: Dict[str, bool]
    activation_blockers: List[str]
    activation_warnings: List[str]
    staged_activation_scope: Dict[str, Any]
    staged_runtime_guards: Dict[str, bool]
    staged_disable_flags: Dict[str, bool]
    next_required_step: str
    controlled_activation_candidate_created: bool
    config_activation_allowed: bool
    config_activated: bool
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
    created_at_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step223ControlledConfigActivationResult:
    status: str
    root: str
    source_step222_result_path: str
    activation_candidates_json_path: str
    activation_candidates_jsonl_path: str
    activation_candidates_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_apply_validation_record_count: int
    source_apply_validation_passed_count: int
    activation_candidate_count: int
    activation_review_ready_count: int
    activation_blocked_count: int
    activation_watchlist_count: int
    controlled_config_activation_review_created: bool
    activation_mode: str
    activation_review_only: bool
    config_activation_allowed: bool
    config_activated: bool
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
    candidates: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step223ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step222_present: bool
    activation_candidates_json_exists: bool
    activation_candidates_jsonl_exists: bool
    activation_candidates_csv_exists: bool
    markdown_report_exists: bool
    source_apply_validation_records_present: bool
    activation_candidates_present: bool
    activation_review_created: bool
    activation_mode_review_only: bool
    no_config_activation_allowed: bool
    no_config_activated: bool
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
    fieldnames = list(rows[0].keys()) if rows else ["activation_candidate_id", "activation_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["activation_checklist"] = json.dumps(out.get("activation_checklist", {}), sort_keys=True)
            out["staged_activation_scope"] = json.dumps(out.get("staged_activation_scope", {}), sort_keys=True)
            out["staged_runtime_guards"] = json.dumps(out.get("staged_runtime_guards", {}), sort_keys=True)
            out["staged_disable_flags"] = json.dumps(out.get("staged_disable_flags", {}), sort_keys=True)
            out["activation_blockers"] = "|".join(out.get("activation_blockers", []))
            out["activation_warnings"] = "|".join(out.get("activation_warnings", []))
            writer.writerow(out)


def _ensure_step222(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step222_dry_run_config_apply_validator_review_only_latest.json"
    if not path.exists():
        execute_dry_run_config_apply_validator_review_only(root, write_output=True)
    return _load_json(path)


def _load_step222_records(step222: Dict[str, Any]) -> List[Dict[str, Any]]:
    records_path = Path(step222.get("apply_validation_records_json_path", ""))
    if records_path.exists():
        return list(_load_json(records_path).get("records", []) or [])
    return list(step222.get("records", []) or [])


def _candidate_id(record: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            "step223_controlled_config_activation_candidate",
            str(record.get("apply_validation_id", "")),
            str(record.get("config_draft_id", "")),
            str(record.get("observation_id", "")),
        ]
    )
    return "actcand_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _activation_scope(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "scope_type": "single_observation_candidate",
        "observation_id": str(record.get("observation_id", "")),
        "registry_id": str(record.get("registry_id", "")),
        "comparison_group": str(record.get("comparison_group", "")),
        "side": str(record.get("side", "")),
        "paper_only": True,
        "live_scope_allowed": False,
        "adapter_scope_allowed": False,
        "activation_review_only": True,
    }


def _runtime_guards(record: Dict[str, Any]) -> Dict[str, bool]:
    checklist = record.get("checklist", {}) if isinstance(record.get("checklist", {}), dict) else {}
    return {
        "source_apply_validation_passed_required": bool(record.get("validation_passed", False)),
        "risk_limits_valid_required": bool(checklist.get("risk_limits_valid", False)),
        "runtime_guards_valid_required": bool(checklist.get("runtime_guards_valid", False)),
        "disable_flags_valid_required": bool(checklist.get("disable_flags_valid", False)),
        "operator_recheck_required": True,
        "kill_switch_required": True,
        "paper_mode_only_required": True,
        "idempotency_required": True,
    }


def _disable_flags() -> Dict[str, bool]:
    return {
        "config_activation_allowed": False,
        "config_activated": False,
        "config_apply_allowed": False,
        "config_applied": False,
        "paper_execution_enabled": False,
        "paper_order_execution_enabled": False,
        "paper_trade_execution_enabled": False,
        "adapter_routing_enabled": False,
        "shadow_execution_enabled": False,
        "limited_live_review_allowed": False,
        "live_trading_allowed": False,
        "strategy_registry_write_allowed": False,
        "promotion_allowed": False,
        "telegram_real_send": False,
    }


def _activation_checklist(record: Dict[str, Any], guards: Dict[str, bool], disables: Dict[str, bool]) -> Dict[str, bool]:
    return {
        "source_validation_passed": bool(record.get("validation_passed", False)),
        "source_validation_status_passed": str(record.get("validation_status", "")) == "DRY_RUN_CONFIG_APPLY_VALIDATION_PASSED_REVIEW_ONLY",
        "source_config_apply_validation_created": record.get("config_apply_validation_created") is True,
        "source_config_apply_allowed_false": record.get("config_apply_allowed") is False,
        "source_config_applied_false": record.get("config_applied") is False,
        "source_paper_execution_enabled_false": record.get("paper_execution_enabled") is False,
        "staged_runtime_guards_valid": all(guards.values()) if guards else False,
        "staged_disable_flags_valid": all(disables.values()) if disables else False,
        "activation_scope_paper_only": True,
        "activation_review_only": True,
    }


def _activation_blockers(record: Dict[str, Any], checklist: Dict[str, bool], guards: Dict[str, bool], disables: Dict[str, bool]) -> List[str]:
    blockers = list(record.get("validation_blockers", []) or [])
    if not checklist.get("source_validation_passed", False):
        blockers.append("SOURCE_APPLY_VALIDATION_NOT_PASSED")
    if not checklist.get("source_validation_status_passed", False):
        blockers.append("SOURCE_APPLY_VALIDATION_STATUS_NOT_PASSED")
    if not checklist.get("source_config_apply_allowed_false", False):
        blockers.append("SOURCE_CONFIG_APPLY_ALLOWED_NOT_FALSE")
    if not checklist.get("source_config_applied_false", False):
        blockers.append("SOURCE_CONFIG_APPLIED_NOT_FALSE")
    if not checklist.get("source_paper_execution_enabled_false", False):
        blockers.append("SOURCE_PAPER_EXECUTION_ENABLED_NOT_FALSE")
    for key, ok in guards.items():
        if not ok:
            blockers.append(f"ACTIVATION_GUARD_INVALID:{key}")
    for key, ok in disables.items():
        if not ok:
            blockers.append(f"ACTIVATION_DISABLE_FLAG_INVALID:{key}")
    blockers.append("STEP223_REVIEW_ONLY_NO_ACTIVATION")
    return sorted(set(str(b) for b in blockers if str(b)))


def _activation_warnings(record: Dict[str, Any]) -> List[str]:
    warnings = list(record.get("validation_warnings", []) or [])
    warnings.append("CONTROLLED_ACTIVATION_REVIEW_ONLY_NO_ACTIVATION")
    warnings.append("STEP224_REQUIRED_FOR_ACTIVATION_APPLY_STUB")
    warnings.append("OPERATOR_APPROVAL_MUST_BE_RECHECKED_BEFORE_ANY_ACTIVATION")
    return sorted(set(str(w) for w in warnings if str(w)))


def _activation_status(record: Dict[str, Any], blockers: List[str], checklist: Dict[str, bool]) -> str:
    hard = {
        "SOURCE_APPLY_VALIDATION_NOT_PASSED",
        "SOURCE_APPLY_VALIDATION_STATUS_NOT_PASSED",
        "SOURCE_CONFIG_APPLY_ALLOWED_NOT_FALSE",
        "SOURCE_CONFIG_APPLIED_NOT_FALSE",
        "SOURCE_PAPER_EXECUTION_ENABLED_NOT_FALSE",
    }
    if any(b in hard or b.startswith("ACTIVATION_GUARD_INVALID:") or b.startswith("ACTIVATION_DISABLE_FLAG_INVALID:") for b in blockers):
        return "CONTROLLED_CONFIG_ACTIVATION_BLOCKED"
    if all(checklist.values()):
        return "CONTROLLED_CONFIG_ACTIVATION_REVIEW_READY"
    return "CONTROLLED_CONFIG_ACTIVATION_WATCHLIST"


def _next_required_step(status: str) -> str:
    if status == "CONTROLLED_CONFIG_ACTIVATION_REVIEW_READY":
        return "STEP224_CONFIG_ACTIVATION_APPLY_STUB_REVIEW_ONLY"
    if status == "CONTROLLED_CONFIG_ACTIVATION_WATCHLIST":
        return "REVIEW_CONFIG_ACTIVATION_CANDIDATE"
    return "DO_NOT_CREATE_ACTIVATION_APPLY_STUB_UNTIL_BLOCKERS_RESOLVED"


def _build_candidate(record: Dict[str, Any]) -> ControlledConfigActivationCandidate:
    guards = _runtime_guards(record)
    disables = _disable_flags()
    checklist = _activation_checklist(record, guards, disables)
    blockers = _activation_blockers(record, checklist, guards, disables)
    status = _activation_status(record, blockers, checklist)

    return ControlledConfigActivationCandidate(
        activation_candidate_id=_candidate_id(record),
        apply_validation_id=str(record.get("apply_validation_id", "")),
        config_draft_id=str(record.get("config_draft_id", "")),
        enablement_plan_id=str(record.get("enablement_plan_id", "")),
        approval_validation_id=str(record.get("approval_validation_id", "")),
        observation_id=str(record.get("observation_id", "")),
        registry_id=str(record.get("registry_id", "")),
        comparison_group=str(record.get("comparison_group", "")),
        side=str(record.get("side", "")),
        source_validation_status=str(record.get("validation_status", "")),
        source_validation_passed=bool(record.get("validation_passed", False)),
        activation_mode=ACTIVATION_MODE_REVIEW_ONLY,
        activation_status=status,
        activation_schema_version=ACTIVATION_SCHEMA_VERSION,
        activation_checklist=checklist,
        activation_blockers=blockers,
        activation_warnings=_activation_warnings(record),
        staged_activation_scope=_activation_scope(record),
        staged_runtime_guards=guards,
        staged_disable_flags=disables,
        next_required_step=_next_required_step(status),
        controlled_activation_candidate_created=True,
        config_activation_allowed=False,
        config_activated=False,
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
        created_at_utc=_utc_now(),
    )


def _blocker_summary(candidates: List[ControlledConfigActivationCandidate]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for candidate in candidates:
        if not candidate.activation_blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in candidate.activation_blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step223ControlledConfigActivationResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step223ControlledConfigActivationResult) -> str:
    lines = [
        "# Step223 v5 Controlled Config Activation Review-Only",
        "",
        "Step223 converts Step222 config apply validation records into controlled activation candidates.",
        "This step is review-only. It does not activate config, apply config, enable paper execution, route adapters, submit orders, approve limited-live review, write strategy registry state, send Telegram messages, or enable live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_apply_validation_record_count: {result.source_apply_validation_record_count}",
        f"- source_apply_validation_passed_count: {result.source_apply_validation_passed_count}",
        f"- activation_candidate_count: {result.activation_candidate_count}",
        f"- activation_review_ready_count: {result.activation_review_ready_count}",
        f"- activation_blocked_count: {result.activation_blocked_count}",
        f"- activation_watchlist_count: {result.activation_watchlist_count}",
        f"- activation_mode: `{result.activation_mode}`",
        f"- config_activation_allowed: {result.config_activation_allowed}",
        f"- config_activated: {result.config_activated}",
        f"- paper_execution_enabled: {result.paper_execution_enabled}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        f"- live_trading_allowed: {result.live_trading_allowed}",
        "",
        "## Activation candidates",
    ]
    for candidate in result.candidates:
        blockers = ", ".join(candidate.get("activation_blockers", [])) if candidate.get("activation_blockers") else "NO_BLOCKER"
        warnings = ", ".join(candidate.get("activation_warnings", [])) if candidate.get("activation_warnings") else "NO_WARNING"
        lines.append(
            "- `{group}` {side}: status={status}, source_passed={passed}, blockers={blockers}, warnings={warnings}".format(
                group=candidate.get("comparison_group", ""),
                side=candidate.get("side", ""),
                status=candidate.get("activation_status", ""),
                passed=candidate.get("source_validation_passed", False),
                blockers=blockers,
                warnings=warnings,
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step223 creates controlled activation candidates only.",
            "- `config_activation_allowed` remains false.",
            "- `config_activated` remains false.",
            "- `paper_execution_enabled` remains false.",
            "- Step224 or later must explicitly create any future activation apply stub.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_controlled_config_activation_review_only(root: str | Path, *, write_output: bool = True) -> Step223ControlledConfigActivationResult:
    root_path = Path(root).resolve()
    step222_path = root_path / "storage/latest/step222_dry_run_config_apply_validator_review_only_latest.json"
    step222 = _ensure_step222(root_path)
    records = _load_step222_records(step222)
    candidates = [_build_candidate(record) for record in records]
    candidate_dicts = [candidate.to_dict() for candidate in candidates]

    activation_candidates_json_path = root_path / "data/reports/step223_controlled_config_activation_candidates.json"
    activation_candidates_jsonl_path = root_path / "data/stores/step223_controlled_config_activation_candidates.jsonl"
    activation_candidates_csv_path = root_path / "data/reports/step223_controlled_config_activation_candidates.csv"
    markdown_report_path = root_path / "data/reports/step223_controlled_config_activation_review_only_report.md"
    latest_result_path = root_path / "storage/latest/step223_controlled_config_activation_review_only_latest.json"

    result = Step223ControlledConfigActivationResult(
        status=STEP223_STATUS_OK,
        root=str(root_path),
        source_step222_result_path=str(step222_path),
        activation_candidates_json_path=str(activation_candidates_json_path),
        activation_candidates_jsonl_path=str(activation_candidates_jsonl_path),
        activation_candidates_csv_path=str(activation_candidates_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        source_apply_validation_record_count=len(records),
        source_apply_validation_passed_count=sum(1 for record in records if bool(record.get("validation_passed", False))),
        activation_candidate_count=len(candidates),
        activation_review_ready_count=sum(1 for candidate in candidates if candidate.activation_status == "CONTROLLED_CONFIG_ACTIVATION_REVIEW_READY"),
        activation_blocked_count=sum(1 for candidate in candidates if candidate.activation_status == "CONTROLLED_CONFIG_ACTIVATION_BLOCKED"),
        activation_watchlist_count=sum(1 for candidate in candidates if candidate.activation_status == "CONTROLLED_CONFIG_ACTIVATION_WATCHLIST"),
        controlled_config_activation_review_created=True,
        activation_mode=ACTIVATION_MODE_REVIEW_ONLY,
        activation_review_only=True,
        config_activation_allowed=False,
        config_activated=False,
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
        candidates=candidate_dicts,
        blocker_summary=_blocker_summary(candidates),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(activation_candidates_json_path, {"candidates": candidate_dicts})
        _write_jsonl(activation_candidates_jsonl_path, candidate_dicts)
        _write_csv(activation_candidates_csv_path, candidate_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def validate_controlled_config_activation_review_only(root: str | Path) -> Step223ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step223_controlled_config_activation_review_only_latest.json"
    if not result_path.exists():
        execute_controlled_config_activation_review_only(root_path, write_output=True)

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    candidates = list(payload.get("candidates", []) or [])

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step222_present": Path(payload.get("source_step222_result_path", "")).exists(),
        "activation_candidates_json_exists": Path(payload.get("activation_candidates_json_path", "")).exists(),
        "activation_candidates_jsonl_exists": Path(payload.get("activation_candidates_jsonl_path", "")).exists(),
        "activation_candidates_csv_exists": Path(payload.get("activation_candidates_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_apply_validation_records_present": int(payload.get("source_apply_validation_record_count", 0)) > 0,
        "activation_candidates_present": int(payload.get("activation_candidate_count", 0)) > 0 and bool(candidates),
        "activation_review_created": payload.get("controlled_config_activation_review_created") is True
        and all(candidate.get("controlled_activation_candidate_created") is True for candidate in candidates),
        "activation_mode_review_only": payload.get("activation_mode") == ACTIVATION_MODE_REVIEW_ONLY
        and payload.get("activation_review_only") is True
        and all(candidate.get("activation_mode") == ACTIVATION_MODE_REVIEW_ONLY for candidate in candidates),
        "no_config_activation_allowed": payload.get("config_activation_allowed") is False
        and all(candidate.get("config_activation_allowed") is False for candidate in candidates),
        "no_config_activated": payload.get("config_activated") is False
        and all(candidate.get("config_activated") is False for candidate in candidates),
        "no_config_apply_allowed": payload.get("config_apply_allowed") is False
        and all(candidate.get("config_apply_allowed") is False for candidate in candidates),
        "no_config_applied": payload.get("config_applied") is False
        and all(candidate.get("config_applied") is False for candidate in candidates),
        "no_paper_execution_enabled": payload.get("paper_execution_enabled") is False
        and all(candidate.get("paper_execution_enabled") is False for candidate in candidates),
        "no_enablement_allowed": payload.get("paper_execution_enablement_allowed") is False
        and all(candidate.get("paper_execution_enablement_allowed") is False for candidate in candidates),
        "no_paper_execution_upgrade": payload.get("paper_execution_upgrade_allowed") is False
        and all(candidate.get("paper_execution_upgrade_allowed") is False for candidate in candidates),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False
        and all(candidate.get("paper_order_execution_enabled") is False for candidate in candidates),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False
        and all(candidate.get("adapter_routing_enabled") is False for candidate in candidates),
        "no_shadow_execution": payload.get("shadow_execution_enabled") is False
        and all(candidate.get("shadow_execution_enabled") is False for candidate in candidates),
        "no_limited_live_review": payload.get("limited_live_review_allowed") is False
        and all(candidate.get("limited_live_review_allowed") is False for candidate in candidates),
        "no_live_trading": payload.get("live_trading_allowed") is False
        and all(candidate.get("live_trading_allowed") is False for candidate in candidates),
        "no_strategy_registry_write": payload.get("strategy_registry_write_allowed") is False
        and all(candidate.get("strategy_registry_write_allowed") is False for candidate in candidates),
        "no_promotion_allowed": payload.get("promotion_allowed") is False
        and all(candidate.get("promotion_allowed") is False for candidate in candidates),
        "no_auto_strategy_promotion": payload.get("auto_strategy_promotion") is False,
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False
        and payload.get("real_adapter_call_performed") is False
        and payload.get("telegram_real_send") is False
        and all(candidate.get("live_order_executed") is False for candidate in candidates),
        "no_production_cutover": payload.get("production_cutover_executable") is False
        and payload.get("live_mode_enable_allowed") is False,
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step223ValidationResult(
        status=STEP223_VALIDATION_OK if not failures else "STEP223_V5_CONTROLLED_CONFIG_ACTIVATION_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
