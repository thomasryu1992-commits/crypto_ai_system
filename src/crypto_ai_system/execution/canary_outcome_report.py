from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

STEP318_CANARY_OUTCOME_REPORT_VERSION = "step318_canary_outcome_report_v1"
CANARY_OUTCOME_REPORT_REGISTRY_NAME = "canary_outcome_report_registry"

STATUS_RECORDED_REVIEW_ONLY = "CANARY_OUTCOME_REPORT_REVIEW_ONLY_RECORDED"
STATUS_BLOCKED = "CANARY_OUTCOME_REPORT_BLOCKED"
STATUS_BLOCKED_UNSAFE_SIDE_EFFECT = "CANARY_OUTCOME_REPORT_BLOCKED_UNSAFE_SIDE_EFFECT"

RECOMMENDATION_BLOCK_LIVE_SCALED = "block_live_scaled_readiness"
RECOMMENDATION_EXPAND_CANARY = "expand_live_canary_validation_review_only"
RECOMMENDATION_CREATE_READINESS_CANDIDATE = "create_live_scaled_readiness_gate_candidate_review_only"

BLOCK_MISSING_LIVE_CANARY_RECONCILIATION = "STEP318_BLOCK_MISSING_LIVE_CANARY_RECONCILIATION"
BLOCK_LIVE_CANARY_RECONCILIATION_PROMOTION_BLOCKER = "STEP318_BLOCK_LIVE_CANARY_RECONCILIATION_PROMOTION_BLOCKER"
BLOCK_NO_LIVE_CANARY_SUBMISSION = "STEP318_BLOCK_NO_LIVE_CANARY_SUBMISSION"
BLOCK_MISSING_MONITORING_ALERTING = "STEP318_BLOCK_MISSING_MONITORING_ALERTING"
BLOCK_MONITORING_CRITICAL_ALERTS = "STEP318_BLOCK_MONITORING_CRITICAL_ALERTS"
BLOCK_MISSING_DEPLOYMENT_RUNBOOK = "STEP318_BLOCK_MISSING_DEPLOYMENT_RUNBOOK"
BLOCK_DEPLOYMENT_RUNBOOK_NOT_REVIEW_ONLY = "STEP318_BLOCK_DEPLOYMENT_RUNBOOK_NOT_REVIEW_ONLY"
BLOCK_UNSAFE_SIDE_EFFECT = "STEP318_BLOCK_UNSAFE_SIDE_EFFECT"
BLOCK_LIVE_SCALED_PROMOTION_ATTEMPT = "STEP318_BLOCK_LIVE_SCALED_PROMOTION_ATTEMPT"
BLOCK_RUNTIME_MUTATION = "STEP318_BLOCK_RUNTIME_MUTATION"
BLOCK_SECRET_VALUE_ACCESS = "STEP318_BLOCK_SECRET_VALUE_ACCESS"
BLOCK_LIVE_EXECUTION_BY_THIS_MODULE = "STEP318_BLOCK_LIVE_EXECUTION_BY_THIS_MODULE"

NO_LIVE_CANARY_PROMOTION_BLOCKER = "NO_LIVE_CANARY_PROMOTION_BLOCKER"
LIVE_CANARY_RECONCILED_REVIEW_ONLY = "LIVE_CANARY_RECONCILED_REVIEW_ONLY"
MONITORING_RECORDED = "MONITORING_ALERTING_REVIEW_ONLY_RECORDED"
DEPLOYMENT_RUNBOOK_RECORDED = "DEPLOYMENT_RUNBOOK_REVIEW_ONLY_RECORDED"


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


def _drop_hashes(payload: Mapping[str, Any], *hash_fields: str) -> dict[str, Any]:
    drop = set(hash_fields) | {"created_at_utc"}
    return {k: v for k, v in dict(payload).items() if k not in drop}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


@dataclass(frozen=True)
class CanaryOutcomeReportPolicy:
    review_only: bool = True
    require_live_canary_reconciliation: bool = True
    require_live_canary_reconciled: bool = True
    require_live_canary_submission: bool = True
    require_monitoring_alerting: bool = True
    require_no_monitoring_critical_alerts: bool = True
    require_deployment_runbook: bool = True
    require_deployment_runbook_review_only: bool = True
    max_allowed_paper_live_gap: float = 0.0
    max_allowed_api_error_count: int = 0
    max_allowed_manual_override_count: int = 0
    live_scaled_readiness_allowed: bool = False
    live_scaled_promotion_allowed: bool = False
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


def _unsafe_side_effects(policy: CanaryOutcomeReportPolicy, sources: Sequence[Mapping[str, Any]]) -> dict[str, bool]:
    return {
        "live_scaled_readiness_allowed": policy.live_scaled_readiness_allowed or any(_bool(src.get("live_scaled_readiness_allowed")) for src in sources),
        "live_scaled_promotion_allowed": policy.live_scaled_promotion_allowed or any(_bool(src.get("live_scaled_promotion_allowed")) for src in sources),
        "live_scaled_promotion_allowed_by_this_module": any(_bool(src.get("live_scaled_promotion_allowed_by_this_module")) for src in sources),
        "live_trading_enabled": policy.live_trading_enabled or any(_bool(src.get("live_trading_enabled")) for src in sources),
        "live_order_submission_allowed": policy.live_order_submission_allowed or any(_bool(src.get("live_order_submission_allowed")) for src in sources),
        "external_order_submission_allowed": policy.external_order_submission_allowed or any(_bool(src.get("external_order_submission_allowed")) for src in sources),
        "place_order_enabled": policy.place_order_enabled or any(_bool(src.get("place_order_enabled")) for src in sources),
        "cancel_order_enabled": policy.cancel_order_enabled or any(_bool(src.get("cancel_order_enabled")) for src in sources),
        "api_key_value_access_allowed": policy.api_key_value_access_allowed or any(_bool(src.get("api_key_value_access_allowed")) for src in sources),
        "api_secret_value_access_allowed": policy.api_secret_value_access_allowed or any(_bool(src.get("api_secret_value_access_allowed")) for src in sources),
        "secret_file_access_allowed": policy.secret_file_access_allowed or any(_bool(src.get("secret_file_access_allowed")) for src in sources),
        "secret_file_creation_allowed": policy.secret_file_creation_allowed or any(_bool(src.get("secret_file_creation_allowed")) for src in sources),
        "runtime_settings_mutated": policy.runtime_settings_mutated or any(_bool(src.get("runtime_settings_mutated")) for src in sources),
        "score_weights_mutated": policy.score_weights_mutated or any(_bool(src.get("score_weights_mutated")) for src in sources),
        "auto_promotion_allowed": policy.auto_promotion_allowed or any(_bool(src.get("auto_promotion_allowed")) for src in sources),
        # Historical live submission can be analyzed, but this module must never perform it.
        "external_order_submission_performed_by_this_module": any(_bool(src.get("external_order_submission_performed_by_this_module")) for src in sources) or policy.external_order_submission_performed,
        "live_order_executed_by_this_module": any(_bool(src.get("live_order_executed_by_this_module")) for src in sources),
    }


def _metric_summary(
    *,
    reconciliation: Mapping[str, Any],
    monitoring_alerting: Mapping[str, Any],
    deployment_runbook: Mapping[str, Any],
) -> dict[str, Any]:
    submitted = _bool(reconciliation.get("submitted_to_exchange"))
    failed_checks = _list(reconciliation.get("failed_check_names"))
    api_error_count = int(_numeric(reconciliation.get("api_error_count"))) + int(_numeric(monitoring_alerting.get("api_error_count")))
    critical_alert_count = int(_numeric(monitoring_alerting.get("critical_alert_count")))
    manual_override_count = int(_numeric(reconciliation.get("manual_override_count"))) + int(_numeric(monitoring_alerting.get("manual_override_count")))
    unexpected_fills = 1 if (not submitted and _text(reconciliation.get("exchange_order_id"))) else 0
    return {
        "orders_submitted_count": 1 if submitted else 0,
        "orders_reconciled_count": 1 if reconciliation.get("status") == LIVE_CANARY_RECONCILED_REVIEW_ONLY else 0,
        "orders_not_submitted_count": 0 if submitted else 1,
        "reconciliation_mismatch_count": 1 if "MISMATCH" in _text(reconciliation.get("status")) else 0,
        "reconciliation_evidence_missing_count": 1 if "EVIDENCE_MISSING" in _text(reconciliation.get("status")) else 0,
        "paper_live_gap": _numeric(reconciliation.get("paper_live_gap"), 0.0),
        "slippage": _numeric(reconciliation.get("slippage"), 0.0),
        "latency_ms": _numeric(reconciliation.get("latency_ms"), 0.0),
        "api_error_count": api_error_count,
        "manual_override_count": manual_override_count,
        "unexpected_fill_count": unexpected_fills,
        "drawdown": _numeric(reconciliation.get("drawdown"), 0.0),
        "risk_rule_breach_count": len([name for name in failed_checks if "RISK" in str(name).upper() or "LIMIT" in str(name).upper()]),
        "monitoring_alert_count": int(_numeric(monitoring_alerting.get("alert_count"))),
        "monitoring_critical_alert_count": critical_alert_count,
        "deployment_ready": _bool(deployment_runbook.get("deployment_ready")),
        "live_canary_deployment_ready": _bool(deployment_runbook.get("live_canary_deployment_ready")),
        "live_scaled_deployment_ready": _bool(deployment_runbook.get("live_scaled_deployment_ready")),
    }


def build_canary_outcome_report(
    *,
    live_canary_reconciliation: Mapping[str, Any] | None = None,
    monitoring_alerting: Mapping[str, Any] | None = None,
    deployment_runbook: Mapping[str, Any] | None = None,
    policy: CanaryOutcomeReportPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or CanaryOutcomeReportPolicy()
    reconciliation = dict(live_canary_reconciliation or {})
    monitoring = dict(monitoring_alerting or {})
    runbook = dict(deployment_runbook or {})
    sources = [reconciliation, monitoring, runbook]
    unsafe_flags = _unsafe_side_effects(policy, sources)
    metrics = _metric_summary(reconciliation=reconciliation, monitoring_alerting=monitoring, deployment_runbook=runbook)
    blockers: list[str] = []
    warnings: list[str] = []

    if policy.require_live_canary_reconciliation and not reconciliation:
        blockers.append(BLOCK_MISSING_LIVE_CANARY_RECONCILIATION)
    rec_status = _text(reconciliation.get("status"))
    promotion_blocker = _text(reconciliation.get("promotion_blocker"))
    if policy.require_live_canary_reconciled and reconciliation and rec_status != LIVE_CANARY_RECONCILED_REVIEW_ONLY:
        blockers.append(BLOCK_LIVE_CANARY_RECONCILIATION_PROMOTION_BLOCKER)
    if promotion_blocker and promotion_blocker != NO_LIVE_CANARY_PROMOTION_BLOCKER:
        blockers.append(BLOCK_LIVE_CANARY_RECONCILIATION_PROMOTION_BLOCKER)
    if policy.require_live_canary_submission and reconciliation and not _bool(reconciliation.get("submitted_to_exchange")):
        blockers.append(BLOCK_NO_LIVE_CANARY_SUBMISSION)

    if policy.require_monitoring_alerting and not monitoring:
        blockers.append(BLOCK_MISSING_MONITORING_ALERTING)
    if policy.require_no_monitoring_critical_alerts and metrics["monitoring_critical_alert_count"] > 0:
        blockers.append(BLOCK_MONITORING_CRITICAL_ALERTS)

    if policy.require_deployment_runbook and not runbook:
        blockers.append(BLOCK_MISSING_DEPLOYMENT_RUNBOOK)
    if policy.require_deployment_runbook_review_only and runbook and runbook.get("status") != DEPLOYMENT_RUNBOOK_RECORDED:
        blockers.append(BLOCK_DEPLOYMENT_RUNBOOK_NOT_REVIEW_ONLY)

    if any(unsafe_flags.values()):
        blockers.append(BLOCK_UNSAFE_SIDE_EFFECT)
    if any(unsafe_flags[name] for name in ["live_scaled_readiness_allowed", "live_scaled_promotion_allowed", "live_scaled_promotion_allowed_by_this_module"]):
        blockers.append(BLOCK_LIVE_SCALED_PROMOTION_ATTEMPT)
    if any(unsafe_flags[name] for name in ["runtime_settings_mutated", "score_weights_mutated", "auto_promotion_allowed"]):
        blockers.append(BLOCK_RUNTIME_MUTATION)
    if any(unsafe_flags[name] for name in ["api_key_value_access_allowed", "api_secret_value_access_allowed", "secret_file_access_allowed", "secret_file_creation_allowed"]):
        blockers.append(BLOCK_SECRET_VALUE_ACCESS)
    if any(unsafe_flags[name] for name in ["external_order_submission_performed_by_this_module", "live_order_executed_by_this_module"]):
        blockers.append(BLOCK_LIVE_EXECUTION_BY_THIS_MODULE)

    if metrics["paper_live_gap"] > policy.max_allowed_paper_live_gap:
        warnings.append("paper_live_gap_above_review_threshold")
    if metrics["api_error_count"] > policy.max_allowed_api_error_count:
        warnings.append("api_error_count_above_review_threshold")
    if metrics["manual_override_count"] > policy.max_allowed_manual_override_count:
        warnings.append("manual_override_count_above_review_threshold")

    blocked_reasons = sorted(set(blockers))
    status = STATUS_BLOCKED_UNSAFE_SIDE_EFFECT if BLOCK_UNSAFE_SIDE_EFFECT in blocked_reasons else (STATUS_BLOCKED if blocked_reasons else STATUS_RECORDED_REVIEW_ONLY)
    if blocked_reasons:
        recommendation = RECOMMENDATION_BLOCK_LIVE_SCALED
    elif metrics["orders_submitted_count"] < 1 or metrics["orders_reconciled_count"] < 1:
        recommendation = RECOMMENDATION_EXPAND_CANARY
    else:
        recommendation = RECOMMENDATION_CREATE_READINESS_CANDIDATE

    report_id_source = {
        "reconciliation_id": reconciliation.get("live_canary_reconciliation_id"),
        "monitoring_id": monitoring.get("monitoring_alerting_report_id"),
        "runbook_id": runbook.get("deployment_runbook_id"),
        "status": status,
        "blocked_reasons": blocked_reasons,
    }
    report = {
        "version": STEP318_CANARY_OUTCOME_REPORT_VERSION,
        "canary_outcome_report_id": stable_id("step318_canary_outcome_report", report_id_source, 24),
        "status": status,
        "review_only": True,
        "live_canary_reconciliation_id": reconciliation.get("live_canary_reconciliation_id"),
        "live_canary_reconciliation_status": rec_status,
        "live_canary_reconciliation_promotion_blocker": promotion_blocker,
        "monitoring_alerting_report_id": monitoring.get("monitoring_alerting_report_id"),
        "monitoring_alerting_status": monitoring.get("status"),
        "deployment_runbook_id": runbook.get("deployment_runbook_id"),
        "deployment_runbook_status": runbook.get("status"),
        "metrics": metrics,
        **metrics,
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "unsafe_side_effect_evidence": unsafe_flags,
        "live_scaled_readiness_recommendation": recommendation,
        "live_scaled_readiness_candidate_created": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_promotion_allowed_by_this_module": False,
        "live_scaled_execution_enabled_by_this_module": False,
        "live_canary_promotion_allowed_by_this_module": False,
        "live_trading_allowed_by_this_module": False,
        "external_order_submission_performed_by_this_module": False,
        "live_order_executed_by_this_module": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    report["canary_outcome_report_sha256"] = sha256_json(_drop_hashes(report, "canary_outcome_report_sha256"))
    return report


def build_canary_outcome_report_registry_record(report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(report)
    record = {
        "version": STEP318_CANARY_OUTCOME_REPORT_VERSION,
        "canary_outcome_report_id": data.get("canary_outcome_report_id"),
        "canary_outcome_report_sha256": data.get("canary_outcome_report_sha256"),
        "status": data.get("status"),
        "review_only": True,
        "live_canary_reconciliation_id": data.get("live_canary_reconciliation_id"),
        "live_canary_reconciliation_status": data.get("live_canary_reconciliation_status"),
        "monitoring_alerting_report_id": data.get("monitoring_alerting_report_id"),
        "deployment_runbook_id": data.get("deployment_runbook_id"),
        "orders_submitted_count": data.get("orders_submitted_count"),
        "orders_reconciled_count": data.get("orders_reconciled_count"),
        "reconciliation_mismatch_count": data.get("reconciliation_mismatch_count"),
        "monitoring_critical_alert_count": data.get("monitoring_critical_alert_count"),
        "blocked_reasons": list(data.get("blocked_reasons") or []),
        "warnings": list(data.get("warnings") or []),
        "live_scaled_readiness_recommendation": data.get("live_scaled_readiness_recommendation"),
        "live_scaled_readiness_candidate_created": False,
        "live_scaled_promotion_allowed_by_this_module": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": data.get("created_at_utc") or utc_now_canonical(),
    }
    record["canary_outcome_report_registry_record_id"] = stable_id("step318_canary_outcome_report_registry", record, 24)
    record["canary_outcome_report_registry_record_sha256"] = sha256_json(record)
    return record


def persist_canary_outcome_report(cfg: AppConfig, report: Mapping[str, Any]) -> dict[str, Any]:
    latest_dir = cfg.root / "storage" / "latest"
    out_dir = cfg.root / "storage" / "canary_outcome_report"
    latest_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(report)
    registry_record = build_canary_outcome_report_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, CANARY_OUTCOME_REPORT_REGISTRY_NAME),
        registry_record,
        registry_name=CANARY_OUTCOME_REPORT_REGISTRY_NAME,
        id_field="canary_outcome_report_registry_record_id",
        hash_field="canary_outcome_report_registry_record_sha256",
        id_prefix="step318_canary_outcome_report_registry",
    )
    payload["canary_outcome_report_registry_record_id"] = persisted.get("canary_outcome_report_registry_record_id")
    payload["canary_outcome_report_registry_record_sha256"] = persisted.get("canary_outcome_report_registry_record_sha256")
    atomic_write_json(latest_dir / "canary_outcome_report.json", payload)
    atomic_write_json(latest_dir / "canary_outcome_report_registry_record.json", persisted)
    atomic_write_json(out_dir / "canary_outcome_report.json", payload)
    return payload


def _latest_json(path: Path) -> dict[str, Any]:
    data = read_json(path, default={})
    return data if isinstance(data, dict) else {}


def run_canary_outcome_report_latest(
    project_root: str | Path | None = None,
    *,
    live_canary_reconciliation: Mapping[str, Any] | None = None,
    monitoring_alerting: Mapping[str, Any] | None = None,
    deployment_runbook: Mapping[str, Any] | None = None,
    policy: CanaryOutcomeReportPolicy | None = None,
) -> dict[str, Any]:
    cfg = load_config(project_root)
    latest = cfg.root / "storage" / "latest"
    reconciliation = dict(live_canary_reconciliation or _latest_json(latest / "live_canary_reconciliation_record.json"))
    monitoring = dict(monitoring_alerting or _latest_json(latest / "monitoring_alerting_report.json"))
    runbook = dict(deployment_runbook or _latest_json(latest / "deployment_runbook_manifest.json"))
    report = build_canary_outcome_report(
        live_canary_reconciliation=reconciliation,
        monitoring_alerting=monitoring,
        deployment_runbook=runbook,
        policy=policy,
    )
    return persist_canary_outcome_report(cfg, report)
