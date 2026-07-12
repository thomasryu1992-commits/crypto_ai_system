from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.operator_approval_packet_review import (
    execute_operator_approval_packet_review,
)

STEP218_STATUS_OK = "STEP218_V5_OPERATOR_APPROVAL_INTAKE_STUB_OK"
STEP218_VALIDATION_OK = "STEP218_V5_OPERATOR_APPROVAL_INTAKE_STUB_VALIDATION_OK"

INTAKE_SCHEMA_VERSION = "step218_v5_operator_approval_intake_stub"
DEFAULT_APPROVAL_DECISION = "NOT_APPROVED"


@dataclass
class OperatorApprovalIntakeTemplate:
    approval_intake_id: str
    approval_packet_id: str
    upgrade_review_id: str
    promotion_decision_id: str
    feedback_review_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    side: str
    source_packet_status: str
    intake_status: str
    intake_schema_version: str
    operator_approved: bool
    approval_recorded: bool
    approved_by: str
    approval_time_utc: str
    approval_reason: str
    approval_expiry_time_utc: str
    approval_decision: str
    allowed_strategy_ids: List[str]
    allowed_observation_ids: List[str]
    max_paper_notional_usd: float
    max_daily_paper_loss_usd: float
    max_paper_positions: int
    approval_constraints: Dict[str, Any]
    required_pre_enablement_checks: List[str]
    intake_blockers: List[str]
    intake_warnings: List[str]
    manual_approval_required: bool
    operator_review_required: bool
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
class Step218OperatorApprovalIntakeStubResult:
    status: str
    root: str
    source_step217_result_path: str
    approval_intake_templates_json_path: str
    approval_intake_templates_jsonl_path: str
    approval_intake_templates_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_approval_packet_count: int
    approval_intake_template_count: int
    not_approved_template_count: int
    blocked_template_count: int
    watchlist_template_count: int
    operator_approval_intake_stub_created: bool
    operator_approval_input_schema_created: bool
    operator_approved: bool
    approval_recorded: bool
    approval_intake_live: bool
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
    templates: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step218ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step217_present: bool
    approval_intake_templates_json_exists: bool
    approval_intake_templates_jsonl_exists: bool
    approval_intake_templates_csv_exists: bool
    markdown_report_exists: bool
    source_approval_packets_present: bool
    approval_intake_templates_present: bool
    intake_stub_created: bool
    input_schema_created: bool
    all_templates_not_approved: bool
    no_operator_approval_recorded: bool
    no_live_approval_intake: bool
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
    fieldnames = list(rows[0].keys()) if rows else ["approval_intake_id", "intake_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["allowed_strategy_ids"] = "|".join(out.get("allowed_strategy_ids", []))
            out["allowed_observation_ids"] = "|".join(out.get("allowed_observation_ids", []))
            out["required_pre_enablement_checks"] = "|".join(out.get("required_pre_enablement_checks", []))
            out["intake_blockers"] = "|".join(out.get("intake_blockers", []))
            out["intake_warnings"] = "|".join(out.get("intake_warnings", []))
            out["approval_constraints"] = json.dumps(out.get("approval_constraints", {}), sort_keys=True)
            writer.writerow(out)


def _ensure_step217(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step217_operator_approval_packet_review_latest.json"
    if not path.exists():
        execute_operator_approval_packet_review(root, write_output=True)
    return _load_json(path)


def _load_step217_packets(step217: Dict[str, Any]) -> List[Dict[str, Any]]:
    packets_path = Path(step217.get("approval_packets_json_path", ""))
    if packets_path.exists():
        return list(_load_json(packets_path).get("packets", []) or [])
    return list(step217.get("packets", []) or [])


def _intake_id(packet: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            "step218_operator_approval_intake",
            str(packet.get("approval_packet_id", "")),
            str(packet.get("observation_id", "")),
            str(packet.get("packet_status", "")),
        ]
    )
    return "opint_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _default_constraints(packet: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "requires_separate_explicit_operator_approval": True,
        "requires_non_empty_approved_by": True,
        "requires_non_empty_approval_reason": True,
        "requires_future_expiry_time": True,
        "requires_positive_max_paper_notional_usd": True,
        "requires_allowed_observation_id_match": True,
        "requires_packet_status_review_ready": str(packet.get("packet_status", "")) == "OPERATOR_PACKET_REVIEW_READY",
        "paper_execution_upgrade_default_denied": True,
        "live_trading_default_denied": True,
    }


def _required_checks(packet: Dict[str, Any]) -> List[str]:
    return [
        "Verify Step217 packet status and safety attestations.",
        "Confirm operator identity outside the automated pipeline.",
        "Confirm approval reason and risk limits are manually supplied.",
        "Confirm approval expiry time is set before any future enablement.",
        "Confirm paper execution upgrade remains disabled in this step.",
        "Confirm no live or limited-live permission is granted by this intake template.",
    ]


def _intake_blockers(packet: Dict[str, Any]) -> List[str]:
    blockers = list(packet.get("approval_blockers", []) or [])
    if str(packet.get("packet_status", "")) != "OPERATOR_PACKET_REVIEW_READY":
        blockers.append("SOURCE_OPERATOR_PACKET_NOT_REVIEW_READY")
    if bool(packet.get("operator_approved", False)):
        blockers.append("SOURCE_PACKET_ALREADY_APPROVED_UNEXPECTED")
    if bool(packet.get("approval_recorded", False)):
        blockers.append("SOURCE_PACKET_APPROVAL_RECORDED_UNEXPECTED")
    blockers.append("OPERATOR_APPROVAL_NOT_PROVIDED")
    blockers.append("APPROVED_BY_NOT_PROVIDED")
    blockers.append("APPROVAL_REASON_NOT_PROVIDED")
    blockers.append("APPROVAL_EXPIRY_NOT_PROVIDED")
    blockers.append("PAPER_RISK_LIMITS_NOT_PROVIDED")
    return sorted(set(str(b) for b in blockers if str(b)))


def _intake_warnings(packet: Dict[str, Any]) -> List[str]:
    warnings = list(packet.get("approval_warnings", []) or [])
    warnings.append("INTAKE_TEMPLATE_ONLY_NO_APPROVAL_RECORDED")
    warnings.append("FUTURE_APPROVAL_MUST_BE_EXPLICIT_AND_SEPARATE")
    warnings.append("NO_EXECUTION_PERMISSION_GRANTED_BY_STEP218")
    return sorted(set(str(w) for w in warnings if str(w)))


def _intake_status(packet: Dict[str, Any], blockers: List[str]) -> str:
    if "SOURCE_OPERATOR_PACKET_NOT_REVIEW_READY" in blockers:
        return "OPERATOR_APPROVAL_INTAKE_BLOCKED"
    if blockers:
        return "OPERATOR_APPROVAL_INTAKE_NOT_APPROVED"
    return "OPERATOR_APPROVAL_INTAKE_READY_FOR_MANUAL_INPUT"


def _build_template(packet: Dict[str, Any]) -> OperatorApprovalIntakeTemplate:
    blockers = _intake_blockers(packet)
    warnings = _intake_warnings(packet)
    status = _intake_status(packet, blockers)
    observation_id = str(packet.get("observation_id", ""))

    return OperatorApprovalIntakeTemplate(
        approval_intake_id=_intake_id(packet),
        approval_packet_id=str(packet.get("approval_packet_id", "")),
        upgrade_review_id=str(packet.get("upgrade_review_id", "")),
        promotion_decision_id=str(packet.get("promotion_decision_id", "")),
        feedback_review_id=str(packet.get("feedback_review_id", "")),
        observation_id=observation_id,
        registry_id=str(packet.get("registry_id", "")),
        comparison_group=str(packet.get("comparison_group", "")),
        side=str(packet.get("side", "")),
        source_packet_status=str(packet.get("packet_status", "")),
        intake_status=status,
        intake_schema_version=INTAKE_SCHEMA_VERSION,
        operator_approved=False,
        approval_recorded=False,
        approved_by="",
        approval_time_utc="",
        approval_reason="",
        approval_expiry_time_utc="",
        approval_decision=DEFAULT_APPROVAL_DECISION,
        allowed_strategy_ids=[],
        allowed_observation_ids=[observation_id] if observation_id else [],
        max_paper_notional_usd=0.0,
        max_daily_paper_loss_usd=0.0,
        max_paper_positions=0,
        approval_constraints=_default_constraints(packet),
        required_pre_enablement_checks=_required_checks(packet),
        intake_blockers=blockers,
        intake_warnings=warnings,
        manual_approval_required=True,
        operator_review_required=True,
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


def _blocker_summary(templates: List[OperatorApprovalIntakeTemplate]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for template in templates:
        if not template.intake_blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in template.intake_blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step218OperatorApprovalIntakeStubResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step218OperatorApprovalIntakeStubResult) -> str:
    lines = [
        "# Step218 v5 Operator Approval Intake Stub",
        "",
        "Step218 creates operator approval intake templates from Step217 operator approval packets.",
        "This step is a schema/template stub only. It does not record approval, enable paper execution, route adapters, submit orders, approve limited-live review, write strategy registry state, send Telegram messages, or enable live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_approval_packet_count: {result.source_approval_packet_count}",
        f"- approval_intake_template_count: {result.approval_intake_template_count}",
        f"- not_approved_template_count: {result.not_approved_template_count}",
        f"- blocked_template_count: {result.blocked_template_count}",
        f"- watchlist_template_count: {result.watchlist_template_count}",
        f"- operator_approved: {result.operator_approved}",
        f"- approval_recorded: {result.approval_recorded}",
        f"- approval_intake_live: {result.approval_intake_live}",
        f"- paper_execution_upgrade_allowed: {result.paper_execution_upgrade_allowed}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        f"- limited_live_review_allowed: {result.limited_live_review_allowed}",
        f"- live_trading_allowed: {result.live_trading_allowed}",
        "",
        "## Approval intake templates",
    ]
    for template in result.templates:
        blockers = ", ".join(template.get("intake_blockers", [])) if template.get("intake_blockers") else "NO_BLOCKER"
        warnings = ", ".join(template.get("intake_warnings", [])) if template.get("intake_warnings") else "NO_WARNING"
        lines.append(
            "- `{group}` {side}: status={status}, decision={decision}, operator_approved={approved}, "
            "max_notional={notional}, blockers={blockers}, warnings={warnings}".format(
                group=template.get("comparison_group", ""),
                side=template.get("side", ""),
                status=template.get("intake_status", ""),
                decision=template.get("approval_decision", ""),
                approved=template.get("operator_approved", False),
                notional=float(template.get("max_paper_notional_usd", 0.0)),
                blockers=blockers,
                warnings=warnings,
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step218 creates approval intake templates only.",
            "- `operator_approved` remains false.",
            "- `approval_recorded` remains false.",
            "- Risk limits default to zero.",
            "- Paper execution upgrade remains disabled.",
            "- Paper order execution, adapter routing, limited-live review, and live trading remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_operator_approval_intake_stub(root: str | Path, *, write_output: bool = True) -> Step218OperatorApprovalIntakeStubResult:
    root_path = Path(root).resolve()
    step217_path = root_path / "storage/latest/step217_operator_approval_packet_review_latest.json"
    step217 = _ensure_step217(root_path)
    packets = _load_step217_packets(step217)
    templates = [_build_template(packet) for packet in packets]
    template_dicts = [template.to_dict() for template in templates]

    approval_intake_templates_json_path = root_path / "data/reports/step218_operator_approval_intake_templates.json"
    approval_intake_templates_jsonl_path = root_path / "data/stores/step218_operator_approval_intake_templates.jsonl"
    approval_intake_templates_csv_path = root_path / "data/reports/step218_operator_approval_intake_templates.csv"
    markdown_report_path = root_path / "data/reports/step218_operator_approval_intake_stub_report.md"
    latest_result_path = root_path / "storage/latest/step218_operator_approval_intake_stub_latest.json"

    result = Step218OperatorApprovalIntakeStubResult(
        status=STEP218_STATUS_OK,
        root=str(root_path),
        source_step217_result_path=str(step217_path),
        approval_intake_templates_json_path=str(approval_intake_templates_json_path),
        approval_intake_templates_jsonl_path=str(approval_intake_templates_jsonl_path),
        approval_intake_templates_csv_path=str(approval_intake_templates_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        source_approval_packet_count=len(packets),
        approval_intake_template_count=len(templates),
        not_approved_template_count=sum(1 for template in templates if template.operator_approved is False),
        blocked_template_count=sum(1 for template in templates if template.intake_status == "OPERATOR_APPROVAL_INTAKE_BLOCKED"),
        watchlist_template_count=sum(1 for template in templates if template.intake_status == "OPERATOR_APPROVAL_INTAKE_NOT_APPROVED"),
        operator_approval_intake_stub_created=True,
        operator_approval_input_schema_created=True,
        operator_approved=False,
        approval_recorded=False,
        approval_intake_live=False,
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
        templates=template_dicts,
        blocker_summary=_blocker_summary(templates),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(approval_intake_templates_json_path, {"templates": template_dicts})
        _write_jsonl(approval_intake_templates_jsonl_path, template_dicts)
        _write_csv(approval_intake_templates_csv_path, template_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def validate_operator_approval_intake_stub(root: str | Path) -> Step218ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step218_operator_approval_intake_stub_latest.json"
    if not result_path.exists():
        execute_operator_approval_intake_stub(root_path, write_output=True)

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    templates = list(payload.get("templates", []) or [])

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step217_present": Path(payload.get("source_step217_result_path", "")).exists(),
        "approval_intake_templates_json_exists": Path(payload.get("approval_intake_templates_json_path", "")).exists(),
        "approval_intake_templates_jsonl_exists": Path(payload.get("approval_intake_templates_jsonl_path", "")).exists(),
        "approval_intake_templates_csv_exists": Path(payload.get("approval_intake_templates_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_approval_packets_present": int(payload.get("source_approval_packet_count", 0)) > 0,
        "approval_intake_templates_present": int(payload.get("approval_intake_template_count", 0)) > 0 and bool(templates),
        "intake_stub_created": payload.get("operator_approval_intake_stub_created") is True,
        "input_schema_created": payload.get("operator_approval_input_schema_created") is True,
        "all_templates_not_approved": bool(templates)
        and all(template.get("operator_approved") is False for template in templates)
        and all(template.get("approval_decision") == DEFAULT_APPROVAL_DECISION for template in templates),
        "no_operator_approval_recorded": payload.get("operator_approved") is False
        and payload.get("approval_recorded") is False
        and all(template.get("approval_recorded") is False for template in templates)
        and all(template.get("approved_by") == "" for template in templates)
        and all(template.get("approval_time_utc") == "" for template in templates)
        and all(template.get("approval_reason") == "" for template in templates),
        "no_live_approval_intake": payload.get("approval_intake_live") is False,
        "no_paper_execution_upgrade": payload.get("paper_execution_upgrade_allowed") is False
        and all(template.get("paper_execution_upgrade_allowed") is False for template in templates),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False
        and all(template.get("paper_order_execution_enabled") is False for template in templates),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False
        and all(template.get("adapter_routing_enabled") is False for template in templates),
        "no_shadow_execution": payload.get("shadow_execution_enabled") is False
        and all(template.get("shadow_execution_enabled") is False for template in templates),
        "no_limited_live_review": payload.get("limited_live_review_allowed") is False
        and all(template.get("limited_live_review_allowed") is False for template in templates),
        "no_live_trading": payload.get("live_trading_allowed") is False
        and all(template.get("live_trading_allowed") is False for template in templates),
        "no_strategy_registry_write": payload.get("strategy_registry_write_allowed") is False
        and all(template.get("strategy_registry_write_allowed") is False for template in templates),
        "no_promotion_allowed": payload.get("promotion_allowed") is False
        and all(template.get("promotion_allowed") is False for template in templates),
        "no_auto_strategy_promotion": payload.get("auto_strategy_promotion") is False,
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False
        and payload.get("real_adapter_call_performed") is False
        and payload.get("telegram_real_send") is False
        and all(template.get("live_order_executed") is False for template in templates),
        "no_production_cutover": payload.get("production_cutover_executable") is False
        and payload.get("live_mode_enable_allowed") is False,
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step218ValidationResult(
        status=STEP218_VALIDATION_OK if not failures else "STEP218_V5_OPERATOR_APPROVAL_INTAKE_STUB_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
