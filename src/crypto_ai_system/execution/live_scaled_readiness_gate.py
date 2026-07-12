from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

STEP319_LIVE_SCALED_READINESS_GATE_VERSION = "step319_live_scaled_readiness_gate_v1"
LIVE_SCALED_READINESS_GATE_REGISTRY_NAME = "live_scaled_readiness_gate_registry"

STATUS_READY_REVIEW_ONLY = "LIVE_SCALED_READINESS_REVIEW_ONLY_READY"
STATUS_BLOCKED = "BLOCK_LIVE_SCALED_READINESS"
STATUS_BLOCKED_UNSAFE_SIDE_EFFECT = "BLOCK_LIVE_SCALED_READINESS_UNSAFE_SIDE_EFFECT"

DECISION_BLOCK = "block_live_scaled_readiness"
DECISION_REVIEW_READY = "live_scaled_readiness_review_ready_no_execution"

BLOCK_MISSING_CANARY_OUTCOME_REPORT = "STEP319_BLOCK_MISSING_CANARY_OUTCOME_REPORT"
BLOCK_CANARY_OUTCOME_NOT_READY = "STEP319_BLOCK_CANARY_OUTCOME_NOT_READY"
BLOCK_CANARY_OUTCOME_HAS_BLOCKERS = "STEP319_BLOCK_CANARY_OUTCOME_HAS_BLOCKERS"
BLOCK_NO_LIVE_CANARY_SUBMISSION = "STEP319_BLOCK_NO_LIVE_CANARY_SUBMISSION"
BLOCK_NO_RECONCILED_LIVE_CANARY_ORDER = "STEP319_BLOCK_NO_RECONCILED_LIVE_CANARY_ORDER"
BLOCK_RECONCILIATION_MISMATCH = "STEP319_BLOCK_RECONCILIATION_MISMATCH"
BLOCK_MONITORING_CRITICAL_ALERTS = "STEP319_BLOCK_MONITORING_CRITICAL_ALERTS"
BLOCK_DEPLOYMENT_NOT_LIVE_SCALED_READY = "STEP319_BLOCK_DEPLOYMENT_NOT_LIVE_SCALED_READY"
BLOCK_MISSING_OPERATOR_LIVE_SCALED_REVIEW_REQUEST = "STEP319_BLOCK_MISSING_OPERATOR_LIVE_SCALED_REVIEW_REQUEST"
BLOCK_OPERATOR_REQUEST_NOT_FOR_LIVE_SCALED = "STEP319_BLOCK_OPERATOR_REQUEST_NOT_FOR_LIVE_SCALED"
BLOCK_OPERATOR_ID_MISSING = "STEP319_BLOCK_OPERATOR_ID_MISSING"
BLOCK_OPERATOR_TICKET_OR_SIGNATURE_MISSING = "STEP319_BLOCK_OPERATOR_TICKET_OR_SIGNATURE_MISSING"
BLOCK_OPERATOR_TIMESTAMP_INVALID = "STEP319_BLOCK_OPERATOR_TIMESTAMP_INVALID"
BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_REVIEW_ONLY = "STEP319_BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_REVIEW_ONLY"
BLOCK_OPERATOR_REQUESTS_LIVE_SCALED_EXECUTION = "STEP319_BLOCK_OPERATOR_REQUESTS_LIVE_SCALED_EXECUTION"
BLOCK_UNSAFE_SIDE_EFFECT = "STEP319_BLOCK_UNSAFE_SIDE_EFFECT"
BLOCK_LIVE_SCALED_PROMOTION_ATTEMPT = "STEP319_BLOCK_LIVE_SCALED_PROMOTION_ATTEMPT"
BLOCK_LIVE_EXECUTION_ATTEMPT = "STEP319_BLOCK_LIVE_EXECUTION_ATTEMPT"
BLOCK_RUNTIME_MUTATION = "STEP319_BLOCK_RUNTIME_MUTATION"
BLOCK_SECRET_VALUE_ACCESS = "STEP319_BLOCK_SECRET_VALUE_ACCESS"

CANARY_STATUS_READY = "CANARY_OUTCOME_REPORT_REVIEW_ONLY_RECORDED"
CANARY_RECOMMENDATION_READY = "create_live_scaled_readiness_gate_candidate_review_only"


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _numeric(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _drop_hashes(payload: Mapping[str, Any], *hash_fields: str) -> dict[str, Any]:
    drop = set(hash_fields) | {"created_at_utc"}
    return {k: v for k, v in dict(payload).items() if k not in drop}


@dataclass(frozen=True)
class LiveScaledReadinessGatePolicy:
    review_only: bool = True
    require_canary_outcome_report: bool = True
    require_canary_outcome_ready: bool = True
    require_no_canary_blockers: bool = True
    require_live_canary_submission: bool = True
    require_live_canary_reconciled_order: bool = True
    require_no_reconciliation_mismatch: bool = True
    require_no_monitoring_critical_alerts: bool = True
    require_live_scaled_deployment_ready: bool = True
    require_operator_live_scaled_review_request: bool = True
    max_allowed_paper_live_gap: float = 0.0
    max_allowed_slippage: float = 0.0
    max_allowed_latency_ms: float = 0.0
    max_allowed_api_error_count: int = 0
    max_allowed_manual_override_count: int = 0
    live_scaled_promotion_allowed: bool = False
    live_scaled_execution_enabled: bool = False
    live_trading_enabled: bool = False
    live_order_submission_allowed: bool = False
    external_order_submission_allowed: bool = False
    external_order_submission_performed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    api_key_value_access_allowed: bool = False
    api_secret_value_access_allowed: bool = False
    secret_file_access_allowed: bool = False
    secret_file_creation_allowed: bool = False
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    auto_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unsafe_side_effects(policy: LiveScaledReadinessGatePolicy, sources: Sequence[Mapping[str, Any]]) -> dict[str, bool]:
    return {
        "live_scaled_promotion_allowed": policy.live_scaled_promotion_allowed or any(_bool(src.get("live_scaled_promotion_allowed")) for src in sources),
        "live_scaled_promotion_allowed_by_this_module": any(_bool(src.get("live_scaled_promotion_allowed_by_this_module")) for src in sources),
        "live_scaled_execution_enabled": policy.live_scaled_execution_enabled or any(_bool(src.get("live_scaled_execution_enabled")) for src in sources),
        "live_scaled_execution_enabled_by_this_module": any(_bool(src.get("live_scaled_execution_enabled_by_this_module")) for src in sources),
        "live_trading_enabled": policy.live_trading_enabled or any(_bool(src.get("live_trading_enabled")) for src in sources),
        "live_trading_allowed_by_this_module": any(_bool(src.get("live_trading_allowed_by_this_module")) for src in sources),
        "live_order_submission_allowed": policy.live_order_submission_allowed or any(_bool(src.get("live_order_submission_allowed")) for src in sources),
        "external_order_submission_allowed": policy.external_order_submission_allowed or any(_bool(src.get("external_order_submission_allowed")) for src in sources),
        "external_order_submission_performed": policy.external_order_submission_performed or any(_bool(src.get("external_order_submission_performed")) for src in sources),
        "external_order_submission_performed_by_this_module": any(_bool(src.get("external_order_submission_performed_by_this_module")) for src in sources),
        "place_order_enabled": policy.place_order_enabled or any(_bool(src.get("place_order_enabled")) for src in sources),
        "cancel_order_enabled": policy.cancel_order_enabled or any(_bool(src.get("cancel_order_enabled")) for src in sources),
        "api_key_value_access_allowed": policy.api_key_value_access_allowed or any(_bool(src.get("api_key_value_access_allowed")) for src in sources),
        "api_secret_value_access_allowed": policy.api_secret_value_access_allowed or any(_bool(src.get("api_secret_value_access_allowed")) for src in sources),
        "secret_file_access_allowed": policy.secret_file_access_allowed or any(_bool(src.get("secret_file_access_allowed")) for src in sources),
        "secret_file_creation_allowed": policy.secret_file_creation_allowed or any(_bool(src.get("secret_file_creation_allowed")) for src in sources),
        "runtime_settings_mutated": policy.runtime_settings_mutated or any(_bool(src.get("runtime_settings_mutated")) for src in sources),
        "score_weights_mutated": policy.score_weights_mutated or any(_bool(src.get("score_weights_mutated")) for src in sources),
        "auto_promotion_allowed": policy.auto_promotion_allowed or any(_bool(src.get("auto_promotion_allowed")) for src in sources),
    }


def _valid_operator_request(req: Mapping[str, Any], blockers: list[str]) -> None:
    if not req:
        blockers.append(BLOCK_MISSING_OPERATOR_LIVE_SCALED_REVIEW_REQUEST)
        return
    target = _text(req.get("target_stage") or req.get("requested_stage"))
    if target not in {"live_scaled", "live_scaled_readiness"}:
        blockers.append(BLOCK_OPERATOR_REQUEST_NOT_FOR_LIVE_SCALED)
    if not _text(req.get("operator_id")):
        blockers.append(BLOCK_OPERATOR_ID_MISSING)
    if not (_text(req.get("ticket_or_signature")) or _text(req.get("signature")) or _text(req.get("ticket"))):
        blockers.append(BLOCK_OPERATOR_TICKET_OR_SIGNATURE_MISSING)
    timestamp = _text(req.get("canonical_utc_timestamp") or req.get("created_at_utc"))
    if not (timestamp.endswith("Z") and "T" in timestamp):
        blockers.append(BLOCK_OPERATOR_TIMESTAMP_INVALID)
    if not _bool(req.get("acknowledge_review_only_gate")):
        blockers.append(BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_REVIEW_ONLY)
    if any(
        _bool(req.get(name))
        for name in [
            "request_live_scaled_promotion_allowed",
            "request_live_scaled_execution_enabled",
            "request_live_order_submission_allowed",
            "request_live_trading_enabled",
            "request_place_order_enabled",
        ]
    ):
        blockers.append(BLOCK_OPERATOR_REQUESTS_LIVE_SCALED_EXECUTION)


def build_live_scaled_readiness_gate(
    *,
    canary_outcome_report: Mapping[str, Any] | None = None,
    operator_live_scaled_review_request: Mapping[str, Any] | None = None,
    policy: LiveScaledReadinessGatePolicy | None = None,
) -> dict[str, Any]:
    policy = policy or LiveScaledReadinessGatePolicy()
    canary = dict(canary_outcome_report or {})
    operator_request = dict(operator_live_scaled_review_request or {})
    sources = [canary, operator_request]
    blockers: list[str] = []
    warnings: list[str] = []

    if policy.require_canary_outcome_report and not canary:
        blockers.append(BLOCK_MISSING_CANARY_OUTCOME_REPORT)
    canary_status = _text(canary.get("status"))
    canary_recommendation = _text(canary.get("live_scaled_readiness_recommendation"))
    canary_blockers = _list(canary.get("blocked_reasons"))
    orders_submitted = int(_numeric(canary.get("orders_submitted_count")))
    orders_reconciled = int(_numeric(canary.get("orders_reconciled_count")))
    mismatch_count = int(_numeric(canary.get("reconciliation_mismatch_count")))
    critical_alert_count = int(_numeric(canary.get("monitoring_critical_alert_count")))
    deployment_ready = _bool(canary.get("live_scaled_deployment_ready"))

    if canary:
        if policy.require_canary_outcome_ready and not (
            canary_status == CANARY_STATUS_READY and canary_recommendation == CANARY_RECOMMENDATION_READY
        ):
            blockers.append(BLOCK_CANARY_OUTCOME_NOT_READY)
        if policy.require_no_canary_blockers and canary_blockers:
            blockers.append(BLOCK_CANARY_OUTCOME_HAS_BLOCKERS)
        if policy.require_live_canary_submission and orders_submitted < 1:
            blockers.append(BLOCK_NO_LIVE_CANARY_SUBMISSION)
        if policy.require_live_canary_reconciled_order and orders_reconciled < 1:
            blockers.append(BLOCK_NO_RECONCILED_LIVE_CANARY_ORDER)
        if policy.require_no_reconciliation_mismatch and mismatch_count > 0:
            blockers.append(BLOCK_RECONCILIATION_MISMATCH)
        if policy.require_no_monitoring_critical_alerts and critical_alert_count > 0:
            blockers.append(BLOCK_MONITORING_CRITICAL_ALERTS)
        if policy.require_live_scaled_deployment_ready and not deployment_ready:
            blockers.append(BLOCK_DEPLOYMENT_NOT_LIVE_SCALED_READY)

    if policy.require_operator_live_scaled_review_request:
        _valid_operator_request(operator_request, blockers)

    paper_live_gap = _numeric(canary.get("paper_live_gap"), 0.0)
    slippage = _numeric(canary.get("slippage"), 0.0)
    latency_ms = _numeric(canary.get("latency_ms"), 0.0)
    api_error_count = int(_numeric(canary.get("api_error_count")))
    manual_override_count = int(_numeric(canary.get("manual_override_count")))
    if paper_live_gap > policy.max_allowed_paper_live_gap:
        warnings.append("paper_live_gap_above_live_scaled_gate_threshold")
    if slippage > policy.max_allowed_slippage:
        warnings.append("slippage_above_live_scaled_gate_threshold")
    if latency_ms > policy.max_allowed_latency_ms:
        warnings.append("latency_above_live_scaled_gate_threshold")
    if api_error_count > policy.max_allowed_api_error_count:
        warnings.append("api_error_count_above_live_scaled_gate_threshold")
    if manual_override_count > policy.max_allowed_manual_override_count:
        warnings.append("manual_override_count_above_live_scaled_gate_threshold")

    unsafe_flags = _unsafe_side_effects(policy, sources)
    if any(unsafe_flags.values()):
        blockers.append(BLOCK_UNSAFE_SIDE_EFFECT)
    if any(unsafe_flags[name] for name in ["live_scaled_promotion_allowed", "live_scaled_promotion_allowed_by_this_module"]):
        blockers.append(BLOCK_LIVE_SCALED_PROMOTION_ATTEMPT)
    if any(
        unsafe_flags[name]
        for name in [
            "live_scaled_execution_enabled",
            "live_scaled_execution_enabled_by_this_module",
            "live_trading_enabled",
            "live_trading_allowed_by_this_module",
            "live_order_submission_allowed",
            "external_order_submission_allowed",
            "external_order_submission_performed",
            "external_order_submission_performed_by_this_module",
            "place_order_enabled",
            "cancel_order_enabled",
        ]
    ):
        blockers.append(BLOCK_LIVE_EXECUTION_ATTEMPT)
    if any(unsafe_flags[name] for name in ["runtime_settings_mutated", "score_weights_mutated", "auto_promotion_allowed"]):
        blockers.append(BLOCK_RUNTIME_MUTATION)
    if any(unsafe_flags[name] for name in ["api_key_value_access_allowed", "api_secret_value_access_allowed", "secret_file_access_allowed", "secret_file_creation_allowed"]):
        blockers.append(BLOCK_SECRET_VALUE_ACCESS)

    blocked_reasons = sorted(set(blockers))
    status = STATUS_BLOCKED_UNSAFE_SIDE_EFFECT if BLOCK_UNSAFE_SIDE_EFFECT in blocked_reasons else (STATUS_BLOCKED if blocked_reasons else STATUS_READY_REVIEW_ONLY)
    readiness_passed_review_only = status == STATUS_READY_REVIEW_ONLY
    gate_decision = DECISION_REVIEW_READY if readiness_passed_review_only else DECISION_BLOCK
    gate_id_source = {
        "canary_outcome_report_id": canary.get("canary_outcome_report_id"),
        "operator_id": operator_request.get("operator_id"),
        "status": status,
        "blocked_reasons": blocked_reasons,
    }
    report = {
        "version": STEP319_LIVE_SCALED_READINESS_GATE_VERSION,
        "live_scaled_readiness_gate_id": stable_id("step319_live_scaled_readiness_gate", gate_id_source, 24),
        "status": status,
        "review_only": True,
        "readiness_passed_review_only": readiness_passed_review_only,
        "gate_decision": gate_decision,
        "canary_outcome_report_id": canary.get("canary_outcome_report_id"),
        "canary_outcome_report_status": canary_status,
        "canary_outcome_report_recommendation": canary_recommendation,
        "canary_outcome_report_blocked_reasons": canary_blockers,
        "operator_live_scaled_review_request_id": operator_request.get("operator_live_scaled_review_request_id") or operator_request.get("request_id"),
        "operator_id": operator_request.get("operator_id"),
        "orders_submitted_count": orders_submitted,
        "orders_reconciled_count": orders_reconciled,
        "reconciliation_mismatch_count": mismatch_count,
        "monitoring_critical_alert_count": critical_alert_count,
        "live_scaled_deployment_ready": deployment_ready,
        "paper_live_gap": paper_live_gap,
        "slippage": slippage,
        "latency_ms": latency_ms,
        "api_error_count": api_error_count,
        "manual_override_count": manual_override_count,
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "unsafe_side_effect_evidence": unsafe_flags,
        "live_scaled_readiness_candidate_created": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_promotion_allowed_by_this_module": False,
        "live_scaled_execution_enabled": False,
        "live_scaled_execution_enabled_by_this_module": False,
        "live_trading_allowed_by_this_module": False,
        "live_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed_by_this_module": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    report["live_scaled_readiness_gate_sha256"] = sha256_json(_drop_hashes(report, "live_scaled_readiness_gate_sha256"))
    return report


def build_live_scaled_readiness_gate_registry_record(report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(report)
    record = {
        "version": STEP319_LIVE_SCALED_READINESS_GATE_VERSION,
        "live_scaled_readiness_gate_id": data.get("live_scaled_readiness_gate_id"),
        "live_scaled_readiness_gate_sha256": data.get("live_scaled_readiness_gate_sha256"),
        "status": data.get("status"),
        "review_only": True,
        "readiness_passed_review_only": data.get("readiness_passed_review_only"),
        "gate_decision": data.get("gate_decision"),
        "canary_outcome_report_id": data.get("canary_outcome_report_id"),
        "canary_outcome_report_status": data.get("canary_outcome_report_status"),
        "operator_live_scaled_review_request_id": data.get("operator_live_scaled_review_request_id"),
        "orders_submitted_count": data.get("orders_submitted_count"),
        "orders_reconciled_count": data.get("orders_reconciled_count"),
        "reconciliation_mismatch_count": data.get("reconciliation_mismatch_count"),
        "monitoring_critical_alert_count": data.get("monitoring_critical_alert_count"),
        "live_scaled_deployment_ready": data.get("live_scaled_deployment_ready"),
        "blocked_reasons": list(data.get("blocked_reasons") or []),
        "warnings": list(data.get("warnings") or []),
        "live_scaled_readiness_candidate_created": False,
        "live_scaled_promotion_allowed_by_this_module": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": data.get("created_at_utc") or utc_now_canonical(),
    }
    record["live_scaled_readiness_gate_registry_record_id"] = stable_id("step319_live_scaled_readiness_gate_registry", record, 24)
    record["live_scaled_readiness_gate_registry_record_sha256"] = sha256_json(record)
    return record


def persist_live_scaled_readiness_gate(cfg: AppConfig, report: Mapping[str, Any]) -> dict[str, Any]:
    latest_dir = cfg.root / "storage" / "latest"
    out_dir = cfg.root / "storage" / "live_scaled_readiness_gate"
    latest_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(report)
    registry_record = build_live_scaled_readiness_gate_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, LIVE_SCALED_READINESS_GATE_REGISTRY_NAME),
        registry_record,
        registry_name=LIVE_SCALED_READINESS_GATE_REGISTRY_NAME,
        id_field="live_scaled_readiness_gate_registry_record_id",
        hash_field="live_scaled_readiness_gate_registry_record_sha256",
        id_prefix="step319_live_scaled_readiness_gate_registry",
    )
    payload["live_scaled_readiness_gate_registry_record_id"] = persisted.get("live_scaled_readiness_gate_registry_record_id")
    payload["live_scaled_readiness_gate_registry_record_sha256"] = persisted.get("live_scaled_readiness_gate_registry_record_sha256")
    atomic_write_json(latest_dir / "live_scaled_readiness_gate.json", payload)
    atomic_write_json(latest_dir / "live_scaled_readiness_gate_registry_record.json", persisted)
    atomic_write_json(out_dir / "live_scaled_readiness_gate.json", payload)
    return payload


def _latest_json(path: Path) -> dict[str, Any]:
    data = read_json(path, default={})
    return data if isinstance(data, dict) else {}


def run_live_scaled_readiness_gate_latest(
    project_root: str | Path | None = None,
    *,
    canary_outcome_report: Mapping[str, Any] | None = None,
    operator_live_scaled_review_request: Mapping[str, Any] | None = None,
    policy: LiveScaledReadinessGatePolicy | None = None,
) -> dict[str, Any]:
    cfg = load_config(project_root)
    latest = cfg.root / "storage" / "latest"
    canary = dict(canary_outcome_report or _latest_json(latest / "canary_outcome_report.json"))
    operator_request = dict(operator_live_scaled_review_request or _latest_json(latest / "operator_live_scaled_review_request.json"))
    report = build_live_scaled_readiness_gate(
        canary_outcome_report=canary,
        operator_live_scaled_review_request=operator_request,
        policy=policy,
    )
    return persist_live_scaled_readiness_gate(cfg, report)
