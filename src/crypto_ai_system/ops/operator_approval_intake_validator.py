from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.operator_approval_intake_stub import (
    DEFAULT_APPROVAL_DECISION,
    execute_operator_approval_intake_stub,
)

STEP219_STATUS_OK = "STEP219_V5_OPERATOR_APPROVAL_INTAKE_VALIDATOR_OK"
STEP219_VALIDATION_OK = "STEP219_V5_OPERATOR_APPROVAL_INTAKE_VALIDATOR_VALIDATION_OK"

OPERATOR_INPUT_PATH = "config/operator_approval_input.json"
VALIDATION_SCHEMA_VERSION = "step219_v5_operator_approval_intake_validator"


@dataclass
class OperatorApprovalValidationRecord:
    approval_validation_id: str
    approval_intake_id: str
    approval_packet_id: str
    upgrade_review_id: str
    promotion_decision_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    side: str
    template_intake_status: str
    operator_input_present: bool
    operator_approved_requested: bool
    approved_by: str
    approval_time_utc: str
    approval_reason: str
    approval_expiry_time_utc: str
    allowed_strategy_ids: List[str]
    allowed_observation_ids: List[str]
    max_paper_notional_usd: float
    max_daily_paper_loss_usd: float
    max_paper_positions: int
    validation_status: str
    validation_passed: bool
    validation_blockers: List[str]
    validation_warnings: List[str]
    validation_schema_version: str
    validated_at_utc: str
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
class Step219OperatorApprovalIntakeValidatorResult:
    status: str
    root: str
    source_step218_result_path: str
    operator_input_path: str
    validation_records_json_path: str
    validation_records_jsonl_path: str
    validation_records_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_intake_template_count: int
    operator_input_present: bool
    validation_record_count: int
    validation_passed_count: int
    validation_failed_count: int
    validation_not_approved_count: int
    operator_approval_intake_validator_created: bool
    approval_validation_performed: bool
    validated_operator_approval_present: bool
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
    records: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step219ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step218_present: bool
    validation_records_json_exists: bool
    validation_records_jsonl_exists: bool
    validation_records_csv_exists: bool
    markdown_report_exists: bool
    source_intake_templates_present: bool
    validation_records_present: bool
    validator_created: bool
    validation_performed: bool
    no_implicit_approval: bool
    no_approval_recorded: bool
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
    fieldnames = list(rows[0].keys()) if rows else ["approval_validation_id", "validation_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["allowed_strategy_ids"] = "|".join(out.get("allowed_strategy_ids", []))
            out["allowed_observation_ids"] = "|".join(out.get("allowed_observation_ids", []))
            out["validation_blockers"] = "|".join(out.get("validation_blockers", []))
            out["validation_warnings"] = "|".join(out.get("validation_warnings", []))
            writer.writerow(out)


def _ensure_step218(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step218_operator_approval_intake_stub_latest.json"
    if not path.exists():
        execute_operator_approval_intake_stub(root, write_output=True)
    return _load_json(path)


def _load_step218_templates(step218: Dict[str, Any]) -> List[Dict[str, Any]]:
    templates_path = Path(step218.get("approval_intake_templates_json_path", ""))
    if templates_path.exists():
        return list(_load_json(templates_path).get("templates", []) or [])
    return list(step218.get("templates", []) or [])


def _load_operator_input(root: Path) -> Dict[str, Any]:
    path = root / OPERATOR_INPUT_PATH
    if not path.exists():
        return {}
    try:
        payload = _load_json(path)
    except Exception:
        return {"_input_parse_error": True}
    return payload if isinstance(payload, dict) else {"_input_parse_error": True}


def _input_records(operator_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not operator_input:
        return []
    if operator_input.get("_input_parse_error"):
        return [{"_input_parse_error": True}]
    records = operator_input.get("approvals")
    if isinstance(records, list):
        return [record for record in records if isinstance(record, dict)]
    if any(key in operator_input for key in {"approval_intake_id", "operator_approved", "approved_by", "approval_reason"}):
        return [operator_input]
    return []


def _match_input(template: Dict[str, Any], operator_input: Dict[str, Any]) -> Dict[str, Any] | None:
    records = _input_records(operator_input)
    if not records:
        return None
    intake_id = str(template.get("approval_intake_id", ""))
    observation_id = str(template.get("observation_id", ""))
    for record in records:
        if record.get("_input_parse_error"):
            return record
        if str(record.get("approval_intake_id", "")) == intake_id:
            return record
        if observation_id and str(record.get("observation_id", "")) == observation_id:
            return record
    return None


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v)]
    if isinstance(value, tuple) or isinstance(value, set):
        return [str(v) for v in value if str(v)]
    if isinstance(value, str):
        if not value.strip():
            return []
        if "," in value:
            return [v.strip() for v in value.split(",") if v.strip()]
        return [value.strip()]
    return [str(value)]


def _validation_id(template: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            "step219_operator_approval_validation",
            str(template.get("approval_intake_id", "")),
            str(template.get("approval_packet_id", "")),
            str(template.get("observation_id", "")),
        ]
    )
    return "opval_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _template_field(template: Dict[str, Any], key: str, default: Any) -> Any:
    return template.get(key, default)


def _operator_field(template: Dict[str, Any], operator_record: Dict[str, Any] | None, key: str, default: Any) -> Any:
    if operator_record and key in operator_record:
        return operator_record.get(key, default)
    return _template_field(template, key, default)


def _validation_blockers(template: Dict[str, Any], operator_record: Dict[str, Any] | None) -> List[str]:
    blockers: List[str] = []
    if operator_record is None:
        blockers.append("OPERATOR_INPUT_FILE_MISSING_OR_NO_MATCH")
    elif operator_record.get("_input_parse_error"):
        blockers.append("OPERATOR_INPUT_PARSE_ERROR")

    operator_approved = bool(_operator_field(template, operator_record, "operator_approved", False))
    approved_by = str(_operator_field(template, operator_record, "approved_by", "") or "")
    approval_time_utc = str(_operator_field(template, operator_record, "approval_time_utc", "") or "")
    approval_reason = str(_operator_field(template, operator_record, "approval_reason", "") or "")
    approval_expiry_time_utc = str(_operator_field(template, operator_record, "approval_expiry_time_utc", "") or "")
    allowed_observation_ids = _as_str_list(_operator_field(template, operator_record, "allowed_observation_ids", []))
    max_paper_notional = _to_float(_operator_field(template, operator_record, "max_paper_notional_usd", 0.0))
    max_daily_loss = _to_float(_operator_field(template, operator_record, "max_daily_paper_loss_usd", 0.0))
    max_positions = _to_int(_operator_field(template, operator_record, "max_paper_positions", 0))
    observation_id = str(template.get("observation_id", ""))

    if not operator_approved:
        blockers.append("OPERATOR_APPROVED_FALSE")
    if not approved_by:
        blockers.append("APPROVED_BY_REQUIRED")
    if not approval_time_utc:
        blockers.append("APPROVAL_TIME_REQUIRED")
    if not approval_reason:
        blockers.append("APPROVAL_REASON_REQUIRED")
    if not approval_expiry_time_utc:
        blockers.append("APPROVAL_EXPIRY_REQUIRED")
    if max_paper_notional <= 0:
        blockers.append("MAX_PAPER_NOTIONAL_REQUIRED")
    if max_daily_loss <= 0:
        blockers.append("MAX_DAILY_PAPER_LOSS_REQUIRED")
    if max_positions <= 0:
        blockers.append("MAX_PAPER_POSITIONS_REQUIRED")
    if observation_id and observation_id not in allowed_observation_ids:
        blockers.append("ALLOWED_OBSERVATION_ID_MISMATCH")
    if str(template.get("source_packet_status", "")) != "OPERATOR_PACKET_REVIEW_READY":
        blockers.append("SOURCE_PACKET_NOT_REVIEW_READY")
    if str(template.get("intake_status", "")) == "OPERATOR_APPROVAL_INTAKE_BLOCKED":
        blockers.append("SOURCE_INTAKE_TEMPLATE_BLOCKED")

    # This validator never grants execution permission; it only validates that a future step may consider approval.
    blockers.append("STEP219_REVIEW_ONLY_NO_ENABLEMENT")
    return sorted(set(str(b) for b in blockers if str(b)))


def _validation_warnings(template: Dict[str, Any], operator_record: Dict[str, Any] | None) -> List[str]:
    warnings = list(template.get("intake_warnings", []) or [])
    if operator_record is None:
        warnings.append("USING_TEMPLATE_DEFAULT_NOT_APPROVED_VALUES")
    warnings.append("VALIDATION_RESULT_DOES_NOT_ENABLE_PAPER_EXECUTION")
    warnings.append("STEP220_REQUIRED_FOR_ENABLEMENT_PLAN")
    return sorted(set(str(w) for w in warnings if str(w)))


def _validation_status(blockers: List[str], operator_record: Dict[str, Any] | None) -> str:
    if "OPERATOR_INPUT_FILE_MISSING_OR_NO_MATCH" in blockers:
        return "OPERATOR_APPROVAL_VALIDATION_NOT_APPROVED"
    if any(blocker in blockers for blocker in {"OPERATOR_INPUT_PARSE_ERROR", "SOURCE_PACKET_NOT_REVIEW_READY", "SOURCE_INTAKE_TEMPLATE_BLOCKED"}):
        return "OPERATOR_APPROVAL_VALIDATION_BLOCKED"
    approval_requirements = [
        "OPERATOR_APPROVED_FALSE",
        "APPROVED_BY_REQUIRED",
        "APPROVAL_TIME_REQUIRED",
        "APPROVAL_REASON_REQUIRED",
        "APPROVAL_EXPIRY_REQUIRED",
        "MAX_PAPER_NOTIONAL_REQUIRED",
        "MAX_DAILY_PAPER_LOSS_REQUIRED",
        "MAX_PAPER_POSITIONS_REQUIRED",
        "ALLOWED_OBSERVATION_ID_MISMATCH",
    ]
    if any(blocker in blockers for blocker in approval_requirements):
        return "OPERATOR_APPROVAL_VALIDATION_NOT_APPROVED"
    return "OPERATOR_APPROVAL_VALIDATION_PASSED_REVIEW_ONLY"


def _build_record(template: Dict[str, Any], operator_record: Dict[str, Any] | None) -> OperatorApprovalValidationRecord:
    blockers = _validation_blockers(template, operator_record)
    warnings = _validation_warnings(template, operator_record)
    status = _validation_status(blockers, operator_record)
    operator_approved_requested = bool(_operator_field(template, operator_record, "operator_approved", False))

    return OperatorApprovalValidationRecord(
        approval_validation_id=_validation_id(template),
        approval_intake_id=str(template.get("approval_intake_id", "")),
        approval_packet_id=str(template.get("approval_packet_id", "")),
        upgrade_review_id=str(template.get("upgrade_review_id", "")),
        promotion_decision_id=str(template.get("promotion_decision_id", "")),
        observation_id=str(template.get("observation_id", "")),
        registry_id=str(template.get("registry_id", "")),
        comparison_group=str(template.get("comparison_group", "")),
        side=str(template.get("side", "")),
        template_intake_status=str(template.get("intake_status", "")),
        operator_input_present=operator_record is not None and not bool(operator_record.get("_input_parse_error")) if isinstance(operator_record, dict) else False,
        operator_approved_requested=operator_approved_requested,
        approved_by=str(_operator_field(template, operator_record, "approved_by", "") or ""),
        approval_time_utc=str(_operator_field(template, operator_record, "approval_time_utc", "") or ""),
        approval_reason=str(_operator_field(template, operator_record, "approval_reason", "") or ""),
        approval_expiry_time_utc=str(_operator_field(template, operator_record, "approval_expiry_time_utc", "") or ""),
        allowed_strategy_ids=_as_str_list(_operator_field(template, operator_record, "allowed_strategy_ids", [])),
        allowed_observation_ids=_as_str_list(_operator_field(template, operator_record, "allowed_observation_ids", [])),
        max_paper_notional_usd=_to_float(_operator_field(template, operator_record, "max_paper_notional_usd", 0.0)),
        max_daily_paper_loss_usd=_to_float(_operator_field(template, operator_record, "max_daily_paper_loss_usd", 0.0)),
        max_paper_positions=_to_int(_operator_field(template, operator_record, "max_paper_positions", 0)),
        validation_status=status,
        validation_passed=status == "OPERATOR_APPROVAL_VALIDATION_PASSED_REVIEW_ONLY",
        validation_blockers=blockers,
        validation_warnings=warnings,
        validation_schema_version=VALIDATION_SCHEMA_VERSION,
        validated_at_utc=_utc_now(),
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


def _blocker_summary(records: List[OperatorApprovalValidationRecord]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for record in records:
        if not record.validation_blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in record.validation_blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step219OperatorApprovalIntakeValidatorResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step219OperatorApprovalIntakeValidatorResult) -> str:
    lines = [
        "# Step219 v5 Operator Approval Intake Validator",
        "",
        "Step219 validates optional operator approval input against Step218 approval intake templates.",
        "This step is validation-only. It does not record approval, enable paper execution, route adapters, submit orders, approve limited-live review, write strategy registry state, send Telegram messages, or enable live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- operator_input_path: `{result.operator_input_path}`",
        f"- operator_input_present: {result.operator_input_present}",
        f"- source_intake_template_count: {result.source_intake_template_count}",
        f"- validation_record_count: {result.validation_record_count}",
        f"- validation_passed_count: {result.validation_passed_count}",
        f"- validation_failed_count: {result.validation_failed_count}",
        f"- validation_not_approved_count: {result.validation_not_approved_count}",
        f"- validated_operator_approval_present: {result.validated_operator_approval_present}",
        f"- operator_approved: {result.operator_approved}",
        f"- approval_recorded: {result.approval_recorded}",
        f"- paper_execution_upgrade_allowed: {result.paper_execution_upgrade_allowed}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- live_trading_allowed: {result.live_trading_allowed}",
        "",
        "## Validation records",
    ]
    for record in result.records:
        blockers = ", ".join(record.get("validation_blockers", [])) if record.get("validation_blockers") else "NO_BLOCKER"
        warnings = ", ".join(record.get("validation_warnings", [])) if record.get("validation_warnings") else "NO_WARNING"
        lines.append(
            "- `{group}` {side}: status={status}, input_present={input_present}, approved_requested={approved}, "
            "max_notional={notional}, blockers={blockers}, warnings={warnings}".format(
                group=record.get("comparison_group", ""),
                side=record.get("side", ""),
                status=record.get("validation_status", ""),
                input_present=record.get("operator_input_present", False),
                approved=record.get("operator_approved_requested", False),
                notional=float(record.get("max_paper_notional_usd", 0.0)),
                blockers=blockers,
                warnings=warnings,
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step219 validates approval input only.",
            "- `approval_recorded` remains false.",
            "- `paper_execution_upgrade_allowed` remains false.",
            "- A passing validation only allows a future Step220 enablement plan to be considered.",
            "- No paper order, adapter, live exchange, Telegram, or external API side effect is performed.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_operator_approval_intake_validator(root: str | Path, *, write_output: bool = True) -> Step219OperatorApprovalIntakeValidatorResult:
    root_path = Path(root).resolve()
    step218_path = root_path / "storage/latest/step218_operator_approval_intake_stub_latest.json"
    step218 = _ensure_step218(root_path)
    templates = _load_step218_templates(step218)
    operator_input_path = root_path / OPERATOR_INPUT_PATH
    operator_input = _load_operator_input(root_path)
    input_present = operator_input_path.exists() and not bool(operator_input.get("_input_parse_error"))
    records = [_build_record(template, _match_input(template, operator_input)) for template in templates]
    record_dicts = [record.to_dict() for record in records]

    validation_records_json_path = root_path / "data/reports/step219_operator_approval_validation_records.json"
    validation_records_jsonl_path = root_path / "data/stores/step219_operator_approval_validation_records.jsonl"
    validation_records_csv_path = root_path / "data/reports/step219_operator_approval_validation_records.csv"
    markdown_report_path = root_path / "data/reports/step219_operator_approval_intake_validator_report.md"
    latest_result_path = root_path / "storage/latest/step219_operator_approval_intake_validator_latest.json"

    validation_passed_count = sum(1 for record in records if record.validation_passed)
    result = Step219OperatorApprovalIntakeValidatorResult(
        status=STEP219_STATUS_OK,
        root=str(root_path),
        source_step218_result_path=str(step218_path),
        operator_input_path=str(operator_input_path),
        validation_records_json_path=str(validation_records_json_path),
        validation_records_jsonl_path=str(validation_records_jsonl_path),
        validation_records_csv_path=str(validation_records_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        source_intake_template_count=len(templates),
        operator_input_present=input_present,
        validation_record_count=len(records),
        validation_passed_count=validation_passed_count,
        validation_failed_count=sum(1 for record in records if record.validation_status == "OPERATOR_APPROVAL_VALIDATION_BLOCKED"),
        validation_not_approved_count=sum(1 for record in records if record.validation_status == "OPERATOR_APPROVAL_VALIDATION_NOT_APPROVED"),
        operator_approval_intake_validator_created=True,
        approval_validation_performed=True,
        validated_operator_approval_present=validation_passed_count > 0,
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
        records=record_dicts,
        blocker_summary=_blocker_summary(records),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(validation_records_json_path, {"records": record_dicts})
        _write_jsonl(validation_records_jsonl_path, record_dicts)
        _write_csv(validation_records_csv_path, record_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def validate_operator_approval_intake_validator(root: str | Path) -> Step219ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step219_operator_approval_intake_validator_latest.json"
    if not result_path.exists():
        execute_operator_approval_intake_validator(root_path, write_output=True)

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    records = list(payload.get("records", []) or [])

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step218_present": Path(payload.get("source_step218_result_path", "")).exists(),
        "validation_records_json_exists": Path(payload.get("validation_records_json_path", "")).exists(),
        "validation_records_jsonl_exists": Path(payload.get("validation_records_jsonl_path", "")).exists(),
        "validation_records_csv_exists": Path(payload.get("validation_records_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_intake_templates_present": int(payload.get("source_intake_template_count", 0)) > 0,
        "validation_records_present": int(payload.get("validation_record_count", 0)) > 0 and bool(records),
        "validator_created": payload.get("operator_approval_intake_validator_created") is True,
        "validation_performed": payload.get("approval_validation_performed") is True,
        "no_implicit_approval": payload.get("operator_input_present") is False
        and payload.get("validated_operator_approval_present") is False
        and all(record.get("validation_passed") is False for record in records),
        "no_approval_recorded": payload.get("operator_approved") is False and payload.get("approval_recorded") is False,
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
    return Step219ValidationResult(
        status=STEP219_VALIDATION_OK if not failures else "STEP219_V5_OPERATOR_APPROVAL_INTAKE_VALIDATOR_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
