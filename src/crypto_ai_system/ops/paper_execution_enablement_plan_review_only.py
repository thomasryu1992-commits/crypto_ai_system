from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.operator_approval_intake_validator import (
    execute_operator_approval_intake_validator,
)

STEP220_STATUS_OK = "STEP220_V5_PAPER_EXECUTION_ENABLEMENT_PLAN_REVIEW_ONLY_OK"
STEP220_VALIDATION_OK = "STEP220_V5_PAPER_EXECUTION_ENABLEMENT_PLAN_REVIEW_ONLY_VALIDATION_OK"

PLAN_SCHEMA_VERSION = "step220_v5_paper_execution_enablement_plan_review_only"
EXECUTION_MODE_PLAN_ONLY = "PLAN_ONLY"


@dataclass
class PaperExecutionEnablementPlan:
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
    source_validation_status: str
    source_validation_passed: bool
    execution_mode: str
    plan_status: str
    plan_schema_version: str
    allowed_strategy_ids: List[str]
    allowed_observation_ids: List[str]
    max_paper_notional_usd: float
    max_daily_paper_loss_usd: float
    max_paper_positions: int
    planned_risk_limits: Dict[str, Any]
    planned_pre_trade_checks: List[str]
    plan_blockers: List[str]
    plan_warnings: List[str]
    next_required_step: str
    operator_approval_required: bool
    paper_execution_enablement_plan_created: bool
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
class Step220PaperExecutionEnablementPlanResult:
    status: str
    root: str
    source_step219_result_path: str
    enablement_plans_json_path: str
    enablement_plans_jsonl_path: str
    enablement_plans_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_validation_record_count: int
    validation_passed_count: int
    enablement_plan_count: int
    plan_ready_count: int
    plan_blocked_count: int
    plan_watchlist_count: int
    total_planned_max_paper_notional_usd: float
    total_planned_max_daily_paper_loss_usd: float
    paper_execution_enablement_plan_created: bool
    enablement_plan_review_only: bool
    execution_mode: str
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
    plans: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step220ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step219_present: bool
    enablement_plans_json_exists: bool
    enablement_plans_jsonl_exists: bool
    enablement_plans_csv_exists: bool
    markdown_report_exists: bool
    source_validation_records_present: bool
    enablement_plans_present: bool
    enablement_plan_created: bool
    review_only_mode: bool
    execution_mode_plan_only: bool
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
    fieldnames = list(rows[0].keys()) if rows else ["enablement_plan_id", "plan_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["allowed_strategy_ids"] = "|".join(out.get("allowed_strategy_ids", []))
            out["allowed_observation_ids"] = "|".join(out.get("allowed_observation_ids", []))
            out["planned_pre_trade_checks"] = "|".join(out.get("planned_pre_trade_checks", []))
            out["plan_blockers"] = "|".join(out.get("plan_blockers", []))
            out["plan_warnings"] = "|".join(out.get("plan_warnings", []))
            out["planned_risk_limits"] = json.dumps(out.get("planned_risk_limits", {}), sort_keys=True)
            writer.writerow(out)


def _ensure_step219(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step219_operator_approval_intake_validator_latest.json"
    if not path.exists():
        execute_operator_approval_intake_validator(root, write_output=True)
    return _load_json(path)


def _load_step219_records(step219: Dict[str, Any]) -> List[Dict[str, Any]]:
    records_path = Path(step219.get("validation_records_json_path", ""))
    if records_path.exists():
        return list(_load_json(records_path).get("records", []) or [])
    return list(step219.get("records", []) or [])


def _plan_id(record: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            "step220_paper_execution_enablement_plan",
            str(record.get("approval_validation_id", "")),
            str(record.get("approval_intake_id", "")),
            str(record.get("observation_id", "")),
        ]
    )
    return "peep_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _risk_limits(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "max_paper_notional_usd": float(record.get("max_paper_notional_usd", 0.0)),
        "max_daily_paper_loss_usd": float(record.get("max_daily_paper_loss_usd", 0.0)),
        "max_paper_positions": int(record.get("max_paper_positions", 0)),
        "per_trade_notional_cap_required": True,
        "daily_loss_stop_required": True,
        "position_count_cap_required": True,
        "idempotency_required": True,
        "kill_switch_required": True,
        "telegram_alert_required_before_future_enablement": True,
    }


def _pre_trade_checks(record: Dict[str, Any]) -> List[str]:
    return [
        "Validate approval record is still passed and unexpired in a future step.",
        "Validate allowed observation id before paper execution enablement.",
        "Validate paper risk limits before every order.",
        "Validate DataQuality gate before every order.",
        "Validate ResearchSignal permission gate before every order.",
        "Validate StrategyCondition gate before every order.",
        "Validate RiskGuard before every order.",
        "Validate ExecutionGuard/idempotency before every order.",
        "Require kill-switch and disable flag before any future paper execution mode.",
    ]


def _plan_blockers(record: Dict[str, Any]) -> List[str]:
    blockers = list(record.get("validation_blockers", []) or [])
    if not bool(record.get("validation_passed", False)):
        blockers.append("SOURCE_APPROVAL_VALIDATION_NOT_PASSED")
    if str(record.get("validation_status", "")) != "OPERATOR_APPROVAL_VALIDATION_PASSED_REVIEW_ONLY":
        blockers.append("SOURCE_APPROVAL_STATUS_NOT_PASSED")
    if float(record.get("max_paper_notional_usd", 0.0)) <= 0:
        blockers.append("PLAN_MAX_PAPER_NOTIONAL_MISSING")
    if float(record.get("max_daily_paper_loss_usd", 0.0)) <= 0:
        blockers.append("PLAN_MAX_DAILY_LOSS_MISSING")
    if int(record.get("max_paper_positions", 0)) <= 0:
        blockers.append("PLAN_MAX_POSITIONS_MISSING")
    if not record.get("allowed_observation_ids", []):
        blockers.append("PLAN_ALLOWED_OBSERVATION_IDS_MISSING")
    blockers.append("STEP220_REVIEW_ONLY_NO_ENABLEMENT")
    return sorted(set(str(b) for b in blockers if str(b)))


def _plan_warnings(record: Dict[str, Any]) -> List[str]:
    warnings = list(record.get("validation_warnings", []) or [])
    warnings.append("ENABLEMENT_PLAN_ONLY_NO_EXECUTION_PERMISSION")
    warnings.append("STEP221_REQUIRED_FOR_DRY_RUN_ENABLEMENT_CONFIG")
    warnings.append("OPERATOR_APPROVAL_MUST_BE_RECHECKED_BEFORE_ENABLEMENT")
    return sorted(set(str(w) for w in warnings if str(w)))


def _plan_status(record: Dict[str, Any], blockers: List[str]) -> str:
    hard = {
        "SOURCE_APPROVAL_VALIDATION_NOT_PASSED",
        "SOURCE_APPROVAL_STATUS_NOT_PASSED",
        "PLAN_MAX_PAPER_NOTIONAL_MISSING",
        "PLAN_MAX_DAILY_LOSS_MISSING",
        "PLAN_MAX_POSITIONS_MISSING",
        "PLAN_ALLOWED_OBSERVATION_IDS_MISSING",
    }
    if any(blocker in hard for blocker in blockers):
        return "PAPER_EXECUTION_ENABLEMENT_PLAN_BLOCKED"
    if bool(record.get("validation_passed", False)):
        return "PAPER_EXECUTION_ENABLEMENT_PLAN_READY_REVIEW_ONLY"
    return "PAPER_EXECUTION_ENABLEMENT_PLAN_WATCHLIST"


def _next_required_step(status: str) -> str:
    if status == "PAPER_EXECUTION_ENABLEMENT_PLAN_READY_REVIEW_ONLY":
        return "STEP221_DRY_RUN_PAPER_EXECUTION_CONFIG_REVIEW_ONLY"
    if status == "PAPER_EXECUTION_ENABLEMENT_PLAN_WATCHLIST":
        return "REVALIDATE_OPERATOR_APPROVAL_BEFORE_ENABLEMENT_PLAN"
    return "DO_NOT_CREATE_ENABLEMENT_CONFIG_UNTIL_BLOCKERS_RESOLVED"


def _build_plan(record: Dict[str, Any]) -> PaperExecutionEnablementPlan:
    blockers = _plan_blockers(record)
    status = _plan_status(record, blockers)
    return PaperExecutionEnablementPlan(
        enablement_plan_id=_plan_id(record),
        approval_validation_id=str(record.get("approval_validation_id", "")),
        approval_intake_id=str(record.get("approval_intake_id", "")),
        approval_packet_id=str(record.get("approval_packet_id", "")),
        upgrade_review_id=str(record.get("upgrade_review_id", "")),
        promotion_decision_id=str(record.get("promotion_decision_id", "")),
        observation_id=str(record.get("observation_id", "")),
        registry_id=str(record.get("registry_id", "")),
        comparison_group=str(record.get("comparison_group", "")),
        side=str(record.get("side", "")),
        source_validation_status=str(record.get("validation_status", "")),
        source_validation_passed=bool(record.get("validation_passed", False)),
        execution_mode=EXECUTION_MODE_PLAN_ONLY,
        plan_status=status,
        plan_schema_version=PLAN_SCHEMA_VERSION,
        allowed_strategy_ids=[str(v) for v in record.get("allowed_strategy_ids", [])],
        allowed_observation_ids=[str(v) for v in record.get("allowed_observation_ids", [])],
        max_paper_notional_usd=float(record.get("max_paper_notional_usd", 0.0)),
        max_daily_paper_loss_usd=float(record.get("max_daily_paper_loss_usd", 0.0)),
        max_paper_positions=int(record.get("max_paper_positions", 0)),
        planned_risk_limits=_risk_limits(record),
        planned_pre_trade_checks=_pre_trade_checks(record),
        plan_blockers=blockers,
        plan_warnings=_plan_warnings(record),
        next_required_step=_next_required_step(status),
        operator_approval_required=True,
        paper_execution_enablement_plan_created=True,
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


def _blocker_summary(plans: List[PaperExecutionEnablementPlan]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for plan in plans:
        if not plan.plan_blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in plan.plan_blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step220PaperExecutionEnablementPlanResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step220PaperExecutionEnablementPlanResult) -> str:
    lines = [
        "# Step220 v5 Paper Execution Enablement Plan Review-Only",
        "",
        "Step220 converts Step219 approval validation records into paper execution enablement plans.",
        "This step is plan-only. It does not enable paper execution, route adapters, submit orders, approve limited-live review, write strategy registry state, send Telegram messages, or enable live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_validation_record_count: {result.source_validation_record_count}",
        f"- validation_passed_count: {result.validation_passed_count}",
        f"- enablement_plan_count: {result.enablement_plan_count}",
        f"- plan_ready_count: {result.plan_ready_count}",
        f"- plan_blocked_count: {result.plan_blocked_count}",
        f"- plan_watchlist_count: {result.plan_watchlist_count}",
        f"- execution_mode: `{result.execution_mode}`",
        f"- total_planned_max_paper_notional_usd: {result.total_planned_max_paper_notional_usd:.2f}",
        f"- paper_execution_enablement_allowed: {result.paper_execution_enablement_allowed}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        f"- live_trading_allowed: {result.live_trading_allowed}",
        "",
        "## Enablement plans",
    ]
    for plan in result.plans:
        blockers = ", ".join(plan.get("plan_blockers", [])) if plan.get("plan_blockers") else "NO_BLOCKER"
        warnings = ", ".join(plan.get("plan_warnings", [])) if plan.get("plan_warnings") else "NO_WARNING"
        lines.append(
            "- `{group}` {side}: status={status}, validation_passed={passed}, max_notional={notional:.2f}, "
            "max_loss={loss:.2f}, max_positions={positions}, blockers={blockers}, warnings={warnings}".format(
                group=plan.get("comparison_group", ""),
                side=plan.get("side", ""),
                status=plan.get("plan_status", ""),
                passed=plan.get("source_validation_passed", False),
                notional=float(plan.get("max_paper_notional_usd", 0.0)),
                loss=float(plan.get("max_daily_paper_loss_usd", 0.0)),
                positions=int(plan.get("max_paper_positions", 0)),
                blockers=blockers,
                warnings=warnings,
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step220 creates enablement plans only.",
            "- `execution_mode` is `PLAN_ONLY`.",
            "- `paper_execution_enablement_allowed` remains false.",
            "- Paper order execution, adapter routing, limited-live review, and live trading remain disabled.",
            "- Step221 or later must explicitly create any future enablement config.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_paper_execution_enablement_plan_review_only(root: str | Path, *, write_output: bool = True) -> Step220PaperExecutionEnablementPlanResult:
    root_path = Path(root).resolve()
    step219_path = root_path / "storage/latest/step219_operator_approval_intake_validator_latest.json"
    step219 = _ensure_step219(root_path)
    records = _load_step219_records(step219)
    plans = [_build_plan(record) for record in records]
    plan_dicts = [plan.to_dict() for plan in plans]

    enablement_plans_json_path = root_path / "data/reports/step220_paper_execution_enablement_plans.json"
    enablement_plans_jsonl_path = root_path / "data/stores/step220_paper_execution_enablement_plans.jsonl"
    enablement_plans_csv_path = root_path / "data/reports/step220_paper_execution_enablement_plans.csv"
    markdown_report_path = root_path / "data/reports/step220_paper_execution_enablement_plan_review_only_report.md"
    latest_result_path = root_path / "storage/latest/step220_paper_execution_enablement_plan_review_only_latest.json"

    result = Step220PaperExecutionEnablementPlanResult(
        status=STEP220_STATUS_OK,
        root=str(root_path),
        source_step219_result_path=str(step219_path),
        enablement_plans_json_path=str(enablement_plans_json_path),
        enablement_plans_jsonl_path=str(enablement_plans_jsonl_path),
        enablement_plans_csv_path=str(enablement_plans_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        source_validation_record_count=len(records),
        validation_passed_count=sum(1 for record in records if bool(record.get("validation_passed", False))),
        enablement_plan_count=len(plans),
        plan_ready_count=sum(1 for plan in plans if plan.plan_status == "PAPER_EXECUTION_ENABLEMENT_PLAN_READY_REVIEW_ONLY"),
        plan_blocked_count=sum(1 for plan in plans if plan.plan_status == "PAPER_EXECUTION_ENABLEMENT_PLAN_BLOCKED"),
        plan_watchlist_count=sum(1 for plan in plans if plan.plan_status == "PAPER_EXECUTION_ENABLEMENT_PLAN_WATCHLIST"),
        total_planned_max_paper_notional_usd=sum(plan.max_paper_notional_usd for plan in plans if plan.source_validation_passed),
        total_planned_max_daily_paper_loss_usd=sum(plan.max_daily_paper_loss_usd for plan in plans if plan.source_validation_passed),
        paper_execution_enablement_plan_created=True,
        enablement_plan_review_only=True,
        execution_mode=EXECUTION_MODE_PLAN_ONLY,
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
        plans=plan_dicts,
        blocker_summary=_blocker_summary(plans),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(enablement_plans_json_path, {"plans": plan_dicts})
        _write_jsonl(enablement_plans_jsonl_path, plan_dicts)
        _write_csv(enablement_plans_csv_path, plan_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def validate_paper_execution_enablement_plan_review_only(root: str | Path) -> Step220ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step220_paper_execution_enablement_plan_review_only_latest.json"
    if not result_path.exists():
        execute_paper_execution_enablement_plan_review_only(root_path, write_output=True)

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    plans = list(payload.get("plans", []) or [])

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step219_present": Path(payload.get("source_step219_result_path", "")).exists(),
        "enablement_plans_json_exists": Path(payload.get("enablement_plans_json_path", "")).exists(),
        "enablement_plans_jsonl_exists": Path(payload.get("enablement_plans_jsonl_path", "")).exists(),
        "enablement_plans_csv_exists": Path(payload.get("enablement_plans_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_validation_records_present": int(payload.get("source_validation_record_count", 0)) > 0,
        "enablement_plans_present": int(payload.get("enablement_plan_count", 0)) > 0 and bool(plans),
        "enablement_plan_created": payload.get("paper_execution_enablement_plan_created") is True
        and all(plan.get("paper_execution_enablement_plan_created") is True for plan in plans),
        "review_only_mode": payload.get("enablement_plan_review_only") is True,
        "execution_mode_plan_only": payload.get("execution_mode") == EXECUTION_MODE_PLAN_ONLY
        and all(plan.get("execution_mode") == EXECUTION_MODE_PLAN_ONLY for plan in plans),
        "no_enablement_allowed": payload.get("paper_execution_enablement_allowed") is False
        and all(plan.get("paper_execution_enablement_allowed") is False for plan in plans),
        "no_paper_execution_upgrade": payload.get("paper_execution_upgrade_allowed") is False
        and all(plan.get("paper_execution_upgrade_allowed") is False for plan in plans),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False
        and all(plan.get("paper_order_execution_enabled") is False for plan in plans),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False
        and all(plan.get("adapter_routing_enabled") is False for plan in plans),
        "no_shadow_execution": payload.get("shadow_execution_enabled") is False
        and all(plan.get("shadow_execution_enabled") is False for plan in plans),
        "no_limited_live_review": payload.get("limited_live_review_allowed") is False
        and all(plan.get("limited_live_review_allowed") is False for plan in plans),
        "no_live_trading": payload.get("live_trading_allowed") is False
        and all(plan.get("live_trading_allowed") is False for plan in plans),
        "no_strategy_registry_write": payload.get("strategy_registry_write_allowed") is False
        and all(plan.get("strategy_registry_write_allowed") is False for plan in plans),
        "no_promotion_allowed": payload.get("promotion_allowed") is False
        and all(plan.get("promotion_allowed") is False for plan in plans),
        "no_auto_strategy_promotion": payload.get("auto_strategy_promotion") is False,
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False
        and payload.get("real_adapter_call_performed") is False
        and payload.get("telegram_real_send") is False
        and all(plan.get("live_order_executed") is False for plan in plans),
        "no_production_cutover": payload.get("production_cutover_executable") is False
        and payload.get("live_mode_enable_allowed") is False,
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step220ValidationResult(
        status=STEP220_VALIDATION_OK if not failures else "STEP220_V5_PAPER_EXECUTION_ENABLEMENT_PLAN_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
