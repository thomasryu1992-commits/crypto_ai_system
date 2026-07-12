from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.paper_execution_enablement_plan_review_only import (
    execute_paper_execution_enablement_plan_review_only,
)

STEP221_STATUS_OK = "STEP221_V5_DRY_RUN_PAPER_EXECUTION_CONFIG_REVIEW_ONLY_OK"
STEP221_VALIDATION_OK = "STEP221_V5_DRY_RUN_PAPER_EXECUTION_CONFIG_REVIEW_ONLY_VALIDATION_OK"

CONFIG_SCHEMA_VERSION = "step221_v5_dry_run_paper_execution_config_review_only"
CONFIG_MODE_DRAFT_ONLY = "DRY_RUN_CONFIG_DRAFT_ONLY"


@dataclass
class DryRunPaperExecutionConfigDraft:
    config_draft_id: str
    enablement_plan_id: str
    approval_validation_id: str
    approval_intake_id: str
    approval_packet_id: str
    upgrade_review_id: str
    promotion_decision_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    side: str
    source_plan_status: str
    source_execution_mode: str
    config_mode: str
    config_status: str
    config_schema_version: str
    allowed_strategy_ids: List[str]
    allowed_observation_ids: List[str]
    risk_limits: Dict[str, Any]
    required_pre_trade_checks: List[str]
    required_runtime_guards: Dict[str, bool]
    disable_flags: Dict[str, bool]
    config_blockers: List[str]
    config_warnings: List[str]
    next_required_step: str
    config_draft_created: bool
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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step221DryRunPaperExecutionConfigResult:
    status: str
    root: str
    source_step220_result_path: str
    config_drafts_json_path: str
    config_drafts_jsonl_path: str
    config_drafts_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_enablement_plan_count: int
    source_plan_ready_count: int
    config_draft_count: int
    config_review_ready_count: int
    config_watchlist_count: int
    config_blocked_count: int
    dry_run_paper_execution_config_review_created: bool
    config_mode: str
    config_draft_only: bool
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
    drafts: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step221ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step220_present: bool
    config_drafts_json_exists: bool
    config_drafts_jsonl_exists: bool
    config_drafts_csv_exists: bool
    markdown_report_exists: bool
    source_enablement_plans_present: bool
    config_drafts_present: bool
    config_review_created: bool
    config_mode_draft_only: bool
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
    fieldnames = list(rows[0].keys()) if rows else ["config_draft_id", "config_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["allowed_strategy_ids"] = "|".join(out.get("allowed_strategy_ids", []))
            out["allowed_observation_ids"] = "|".join(out.get("allowed_observation_ids", []))
            out["required_pre_trade_checks"] = "|".join(out.get("required_pre_trade_checks", []))
            out["config_blockers"] = "|".join(out.get("config_blockers", []))
            out["config_warnings"] = "|".join(out.get("config_warnings", []))
            out["risk_limits"] = json.dumps(out.get("risk_limits", {}), sort_keys=True)
            out["required_runtime_guards"] = json.dumps(out.get("required_runtime_guards", {}), sort_keys=True)
            out["disable_flags"] = json.dumps(out.get("disable_flags", {}), sort_keys=True)
            writer.writerow(out)


def _ensure_step220(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step220_paper_execution_enablement_plan_review_only_latest.json"
    if not path.exists():
        execute_paper_execution_enablement_plan_review_only(root, write_output=True)
    return _load_json(path)


def _load_step220_plans(step220: Dict[str, Any]) -> List[Dict[str, Any]]:
    plans_path = Path(step220.get("enablement_plans_json_path", ""))
    if plans_path.exists():
        return list(_load_json(plans_path).get("plans", []) or [])
    return list(step220.get("plans", []) or [])


def _draft_id(plan: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            "step221_dry_run_paper_execution_config",
            str(plan.get("enablement_plan_id", "")),
            str(plan.get("approval_validation_id", "")),
            str(plan.get("observation_id", "")),
        ]
    )
    return "drypec_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _risk_limits(plan: Dict[str, Any]) -> Dict[str, Any]:
    source = plan.get("planned_risk_limits", {}) if isinstance(plan.get("planned_risk_limits", {}), dict) else {}
    return {
        "max_paper_notional_usd": float(plan.get("max_paper_notional_usd", source.get("max_paper_notional_usd", 0.0))),
        "max_daily_paper_loss_usd": float(plan.get("max_daily_paper_loss_usd", source.get("max_daily_paper_loss_usd", 0.0))),
        "max_paper_positions": int(plan.get("max_paper_positions", source.get("max_paper_positions", 0))),
        "per_trade_notional_cap_required": True,
        "daily_loss_stop_required": True,
        "position_count_cap_required": True,
        "idempotency_required": True,
        "kill_switch_required": True,
        "config_draft_only": True,
    }


def _runtime_guards() -> Dict[str, bool]:
    return {
        "data_quality_gate_required": True,
        "research_signal_gate_required": True,
        "strategy_condition_gate_required": True,
        "risk_guard_required": True,
        "execution_guard_required": True,
        "idempotency_required": True,
        "kill_switch_required": True,
        "operator_disable_flag_required": True,
        "paper_mode_only_required": True,
    }


def _disable_flags() -> Dict[str, bool]:
    return {
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


def _config_blockers(plan: Dict[str, Any]) -> List[str]:
    blockers = list(plan.get("plan_blockers", []) or [])
    if str(plan.get("plan_status", "")) != "PAPER_EXECUTION_ENABLEMENT_PLAN_READY_REVIEW_ONLY":
        blockers.append("SOURCE_ENABLEMENT_PLAN_NOT_READY")
    if str(plan.get("execution_mode", "")) != "PLAN_ONLY":
        blockers.append("SOURCE_EXECUTION_MODE_NOT_PLAN_ONLY")
    if not plan.get("allowed_observation_ids", []):
        blockers.append("CONFIG_ALLOWED_OBSERVATION_IDS_MISSING")
    if float(plan.get("max_paper_notional_usd", 0.0)) <= 0:
        blockers.append("CONFIG_MAX_PAPER_NOTIONAL_MISSING")
    if float(plan.get("max_daily_paper_loss_usd", 0.0)) <= 0:
        blockers.append("CONFIG_MAX_DAILY_LOSS_MISSING")
    if int(plan.get("max_paper_positions", 0)) <= 0:
        blockers.append("CONFIG_MAX_POSITIONS_MISSING")
    return sorted(set(str(b) for b in blockers if str(b)))


def _config_warnings(plan: Dict[str, Any]) -> List[str]:
    warnings = list(plan.get("plan_warnings", []) or [])
    warnings.append("CONFIG_DRAFT_ONLY_NO_APPLY")
    warnings.append("PAPER_EXECUTION_REMAINS_DISABLED")
    warnings.append("STEP222_REQUIRED_FOR_CONFIG_APPLY_VALIDATION")
    warnings.append("OPERATOR_APPROVAL_MUST_BE_RECHECKED_BEFORE_ANY_ENABLEMENT")
    return sorted(set(str(w) for w in warnings if str(w)))


def _config_status(plan: Dict[str, Any], blockers: List[str]) -> str:
    hard = {
        "SOURCE_ENABLEMENT_PLAN_NOT_READY",
        "SOURCE_EXECUTION_MODE_NOT_PLAN_ONLY",
        "CONFIG_ALLOWED_OBSERVATION_IDS_MISSING",
        "CONFIG_MAX_PAPER_NOTIONAL_MISSING",
        "CONFIG_MAX_DAILY_LOSS_MISSING",
        "CONFIG_MAX_POSITIONS_MISSING",
        "SOURCE_APPROVAL_VALIDATION_NOT_PASSED",
        "SOURCE_APPROVAL_STATUS_NOT_PASSED",
    }
    if any(blocker in hard for blocker in blockers):
        return "DRY_RUN_PAPER_CONFIG_BLOCKED"
    if str(plan.get("plan_status", "")) == "PAPER_EXECUTION_ENABLEMENT_PLAN_READY_REVIEW_ONLY":
        return "DRY_RUN_PAPER_CONFIG_REVIEW_READY"
    return "DRY_RUN_PAPER_CONFIG_WATCHLIST"


def _next_required_step(status: str) -> str:
    if status == "DRY_RUN_PAPER_CONFIG_REVIEW_READY":
        return "STEP222_DRY_RUN_CONFIG_APPLY_VALIDATOR_REVIEW_ONLY"
    if status == "DRY_RUN_PAPER_CONFIG_WATCHLIST":
        return "REVIEW_ENABLEMENT_PLAN_BEFORE_CONFIG_APPLY_VALIDATION"
    return "DO_NOT_VALIDATE_CONFIG_APPLY_UNTIL_BLOCKERS_RESOLVED"


def _build_draft(plan: Dict[str, Any]) -> DryRunPaperExecutionConfigDraft:
    blockers = _config_blockers(plan)
    status = _config_status(plan, blockers)
    return DryRunPaperExecutionConfigDraft(
        config_draft_id=_draft_id(plan),
        enablement_plan_id=str(plan.get("enablement_plan_id", "")),
        approval_validation_id=str(plan.get("approval_validation_id", "")),
        approval_intake_id=str(plan.get("approval_intake_id", "")),
        approval_packet_id=str(plan.get("approval_packet_id", "")),
        upgrade_review_id=str(plan.get("upgrade_review_id", "")),
        promotion_decision_id=str(plan.get("promotion_decision_id", "")),
        observation_id=str(plan.get("observation_id", "")),
        registry_id=str(plan.get("registry_id", "")),
        comparison_group=str(plan.get("comparison_group", "")),
        side=str(plan.get("side", "")),
        source_plan_status=str(plan.get("plan_status", "")),
        source_execution_mode=str(plan.get("execution_mode", "")),
        config_mode=CONFIG_MODE_DRAFT_ONLY,
        config_status=status,
        config_schema_version=CONFIG_SCHEMA_VERSION,
        allowed_strategy_ids=[str(v) for v in plan.get("allowed_strategy_ids", [])],
        allowed_observation_ids=[str(v) for v in plan.get("allowed_observation_ids", [])],
        risk_limits=_risk_limits(plan),
        required_pre_trade_checks=[str(v) for v in plan.get("planned_pre_trade_checks", [])],
        required_runtime_guards=_runtime_guards(),
        disable_flags=_disable_flags(),
        config_blockers=blockers,
        config_warnings=_config_warnings(plan),
        next_required_step=_next_required_step(status),
        config_draft_created=True,
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
    )


def _blocker_summary(drafts: List[DryRunPaperExecutionConfigDraft]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for draft in drafts:
        if not draft.config_blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in draft.config_blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step221DryRunPaperExecutionConfigResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step221DryRunPaperExecutionConfigResult) -> str:
    lines = [
        "# Step221 v5 Dry-Run Paper Execution Config Review-Only",
        "",
        "Step221 converts Step220 paper execution enablement plans into dry-run paper execution config drafts.",
        "This step is config-draft-only. It does not apply config, enable paper execution, route adapters, submit orders, approve limited-live review, write strategy registry state, send Telegram messages, or enable live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_enablement_plan_count: {result.source_enablement_plan_count}",
        f"- source_plan_ready_count: {result.source_plan_ready_count}",
        f"- config_draft_count: {result.config_draft_count}",
        f"- config_review_ready_count: {result.config_review_ready_count}",
        f"- config_watchlist_count: {result.config_watchlist_count}",
        f"- config_blocked_count: {result.config_blocked_count}",
        f"- config_mode: `{result.config_mode}`",
        f"- config_apply_allowed: {result.config_apply_allowed}",
        f"- config_applied: {result.config_applied}",
        f"- paper_execution_enabled: {result.paper_execution_enabled}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        f"- live_trading_allowed: {result.live_trading_allowed}",
        "",
        "## Config drafts",
    ]
    for draft in result.drafts:
        blockers = ", ".join(draft.get("config_blockers", [])) if draft.get("config_blockers") else "NO_BLOCKER"
        warnings = ", ".join(draft.get("config_warnings", [])) if draft.get("config_warnings") else "NO_WARNING"
        limits = draft.get("risk_limits", {})
        lines.append(
            "- `{group}` {side}: status={status}, max_notional={notional:.2f}, max_loss={loss:.2f}, "
            "max_positions={positions}, blockers={blockers}, warnings={warnings}".format(
                group=draft.get("comparison_group", ""),
                side=draft.get("side", ""),
                status=draft.get("config_status", ""),
                notional=float(limits.get("max_paper_notional_usd", 0.0)),
                loss=float(limits.get("max_daily_paper_loss_usd", 0.0)),
                positions=int(limits.get("max_paper_positions", 0)),
                blockers=blockers,
                warnings=warnings,
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step221 creates config drafts only.",
            "- `config_apply_allowed` remains false.",
            "- `paper_execution_enabled` remains false.",
            "- Paper order execution, adapter routing, limited-live review, and live trading remain disabled.",
            "- Step222 or later must explicitly validate any future config application.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_dry_run_paper_execution_config_review(root: str | Path, *, write_output: bool = True) -> Step221DryRunPaperExecutionConfigResult:
    root_path = Path(root).resolve()
    step220_path = root_path / "storage/latest/step220_paper_execution_enablement_plan_review_only_latest.json"
    step220 = _ensure_step220(root_path)
    plans = _load_step220_plans(step220)
    drafts = [_build_draft(plan) for plan in plans]
    draft_dicts = [draft.to_dict() for draft in drafts]

    config_drafts_json_path = root_path / "data/reports/step221_dry_run_paper_execution_config_drafts.json"
    config_drafts_jsonl_path = root_path / "data/stores/step221_dry_run_paper_execution_config_drafts.jsonl"
    config_drafts_csv_path = root_path / "data/reports/step221_dry_run_paper_execution_config_drafts.csv"
    markdown_report_path = root_path / "data/reports/step221_dry_run_paper_execution_config_review_only_report.md"
    latest_result_path = root_path / "storage/latest/step221_dry_run_paper_execution_config_review_only_latest.json"

    result = Step221DryRunPaperExecutionConfigResult(
        status=STEP221_STATUS_OK,
        root=str(root_path),
        source_step220_result_path=str(step220_path),
        config_drafts_json_path=str(config_drafts_json_path),
        config_drafts_jsonl_path=str(config_drafts_jsonl_path),
        config_drafts_csv_path=str(config_drafts_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        source_enablement_plan_count=len(plans),
        source_plan_ready_count=sum(1 for plan in plans if plan.get("plan_status") == "PAPER_EXECUTION_ENABLEMENT_PLAN_READY_REVIEW_ONLY"),
        config_draft_count=len(drafts),
        config_review_ready_count=sum(1 for draft in drafts if draft.config_status == "DRY_RUN_PAPER_CONFIG_REVIEW_READY"),
        config_watchlist_count=sum(1 for draft in drafts if draft.config_status == "DRY_RUN_PAPER_CONFIG_WATCHLIST"),
        config_blocked_count=sum(1 for draft in drafts if draft.config_status == "DRY_RUN_PAPER_CONFIG_BLOCKED"),
        dry_run_paper_execution_config_review_created=True,
        config_mode=CONFIG_MODE_DRAFT_ONLY,
        config_draft_only=True,
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
        drafts=draft_dicts,
        blocker_summary=_blocker_summary(drafts),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(config_drafts_json_path, {"drafts": draft_dicts})
        _write_jsonl(config_drafts_jsonl_path, draft_dicts)
        _write_csv(config_drafts_csv_path, draft_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def validate_dry_run_paper_execution_config_review(root: str | Path) -> Step221ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step221_dry_run_paper_execution_config_review_only_latest.json"
    if not result_path.exists():
        execute_dry_run_paper_execution_config_review(root_path, write_output=True)

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    drafts = list(payload.get("drafts", []) or [])

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step220_present": Path(payload.get("source_step220_result_path", "")).exists(),
        "config_drafts_json_exists": Path(payload.get("config_drafts_json_path", "")).exists(),
        "config_drafts_jsonl_exists": Path(payload.get("config_drafts_jsonl_path", "")).exists(),
        "config_drafts_csv_exists": Path(payload.get("config_drafts_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_enablement_plans_present": int(payload.get("source_enablement_plan_count", 0)) > 0,
        "config_drafts_present": int(payload.get("config_draft_count", 0)) > 0 and bool(drafts),
        "config_review_created": payload.get("dry_run_paper_execution_config_review_created") is True
        and all(draft.get("config_draft_created") is True for draft in drafts),
        "config_mode_draft_only": payload.get("config_mode") == CONFIG_MODE_DRAFT_ONLY
        and payload.get("config_draft_only") is True
        and all(draft.get("config_mode") == CONFIG_MODE_DRAFT_ONLY for draft in drafts),
        "no_config_apply_allowed": payload.get("config_apply_allowed") is False
        and all(draft.get("config_apply_allowed") is False for draft in drafts),
        "no_config_applied": payload.get("config_applied") is False
        and all(draft.get("config_applied") is False for draft in drafts),
        "no_paper_execution_enabled": payload.get("paper_execution_enabled") is False
        and all(draft.get("paper_execution_enabled") is False for draft in drafts),
        "no_enablement_allowed": payload.get("paper_execution_enablement_allowed") is False
        and all(draft.get("paper_execution_enablement_allowed") is False for draft in drafts),
        "no_paper_execution_upgrade": payload.get("paper_execution_upgrade_allowed") is False
        and all(draft.get("paper_execution_upgrade_allowed") is False for draft in drafts),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False
        and all(draft.get("paper_order_execution_enabled") is False for draft in drafts),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False
        and all(draft.get("adapter_routing_enabled") is False for draft in drafts),
        "no_shadow_execution": payload.get("shadow_execution_enabled") is False
        and all(draft.get("shadow_execution_enabled") is False for draft in drafts),
        "no_limited_live_review": payload.get("limited_live_review_allowed") is False
        and all(draft.get("limited_live_review_allowed") is False for draft in drafts),
        "no_live_trading": payload.get("live_trading_allowed") is False
        and all(draft.get("live_trading_allowed") is False for draft in drafts),
        "no_strategy_registry_write": payload.get("strategy_registry_write_allowed") is False
        and all(draft.get("strategy_registry_write_allowed") is False for draft in drafts),
        "no_promotion_allowed": payload.get("promotion_allowed") is False
        and all(draft.get("promotion_allowed") is False for draft in drafts),
        "no_auto_strategy_promotion": payload.get("auto_strategy_promotion") is False,
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False
        and payload.get("real_adapter_call_performed") is False
        and payload.get("telegram_real_send") is False
        and all(draft.get("live_order_executed") is False for draft in drafts),
        "no_production_cutover": payload.get("production_cutover_executable") is False
        and payload.get("live_mode_enable_allowed") is False,
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step221ValidationResult(
        status=STEP221_VALIDATION_OK if not failures else "STEP221_V5_DRY_RUN_PAPER_EXECUTION_CONFIG_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
