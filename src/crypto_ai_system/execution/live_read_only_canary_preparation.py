from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.deployment_runbook import STATUS_RECORDED_REVIEW_ONLY as DEPLOYMENT_RUNBOOK_OK
from crypto_ai_system.execution.live_key_scope_validator import LIVE_KEY_SCOPE_VALIDATOR_REGISTRY_NAME
from crypto_ai_system.execution.monitoring_alerting import STATUS_RECORDED_REVIEW_ONLY as MONITORING_OK
from crypto_ai_system.execution.repeated_clean_signed_testnet_sessions import STATUS_VALIDATED_REVIEW_ONLY as P8_VALIDATED
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P9_LIVE_READ_ONLY_CANARY_PREPARATION_VERSION = "p9_live_read_only_canary_preparation_v1"
P9_LIVE_READ_ONLY_CANARY_PREPARATION_REGISTRY_NAME = "p9_live_read_only_canary_preparation_registry"

STATUS_WAITING_REVIEW_ONLY = "P9_LIVE_READ_ONLY_CANARY_PREPARATION_WAITING_REVIEW_ONLY"
STATUS_READY_REVIEW_ONLY = "P9_LIVE_READ_ONLY_CANARY_PREPARATION_READY_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P9_LIVE_READ_ONLY_CANARY_PREPARATION_BLOCKED_FAIL_CLOSED"

LIVE_READ_ONLY_PROBE_OK = "LIVE_READ_ONLY_ADAPTER_PROBE_VALID"
LIVE_KEY_SCOPE_OK = "LIVE_KEY_SCOPE_VALIDATED_METADATA_ONLY"

_REQUIRED_LIVE_PROBE_FLAGS_FALSE = {
    "place_order_enabled": False,
    "cancel_order_enabled": False,
    "withdrawal_enabled": False,
    "transfer_enabled": False,
    "leverage_mutation_enabled": False,
    "margin_mode_mutation_enabled": False,
    "live_order_submission_allowed": False,
    "external_order_submission_allowed": False,
    "external_order_submission_performed": False,
    "signed_order_executor_enabled": False,
    "live_trading_enabled": False,
    "api_key_value_access_allowed": False,
    "api_secret_value_access_allowed": False,
    "secret_file_access_allowed": False,
    "secret_file_creation_allowed": False,
    "runtime_settings_mutated": False,
    "score_weights_mutated": False,
    "auto_promotion_allowed": False,
}

_ALWAYS_DISABLED = {
    "ready_for_signed_testnet_execution": False,
    "testnet_order_submission_allowed": False,
    "signed_testnet_promotion_allowed": False,
    "external_order_submission_allowed": False,
    "external_order_submission_performed": False,
    "place_order_enabled": False,
    "cancel_order_enabled": False,
    "signed_order_executor_enabled": False,
    "runtime_settings_mutated": False,
    "score_weights_mutated": False,
    "candidate_profile_applied": False,
    "auto_promotion_allowed": False,
    "secret_value_accessed": False,
    "secret_value_logged": False,
    "api_key_value_logged": False,
    "api_secret_value_logged": False,
    "private_key_logged": False,
    "passphrase_logged": False,
    "secret_file_accessed": False,
    "secret_file_created": False,
    "live_canary_execution_enabled": False,
    "live_scaled_execution_enabled": False,
    "live_execution_unlock_authority": False,
    "live_trading_allowed_by_this_module": False,
    "live_order_submission_allowed": False,
    "live_order_endpoint_called": False,
    "live_order_executed": False,
    "actual_live_order_submitted": False,
    "mainnet_key_scope_allowed": False,
    "withdrawal_permission_allowed": False,
    "transfer_permission_allowed": False,
    "admin_permission_allowed": False,
}


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _storage_dir(cfg: AppConfig, rel: str) -> Path:
    path = cfg.root / rel
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _disabled_payload() -> dict[str, Any]:
    payload = default_execution_flag_state()
    payload.update(_ALWAYS_DISABLED)
    payload.update(
        {
            "p9_live_read_only_canary_preparation_ready": False,
            "live_read_only_probe_actual_network_performed": False,
            "live_canary_approval_packet_created": False,
            "live_canary_order_allowed": False,
        }
    )
    return payload


def _artifact_hash(payload: Mapping[str, Any], *keys: str) -> str | None:
    data = dict(payload or {})
    for key in keys:
        if data.get(key):
            return str(data[key])
    if not data:
        return None
    return sha256_json(data)


def _summary(payload: Mapping[str, Any], *, name: str, hash_keys: tuple[str, ...]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status"),
        "sha256": _artifact_hash(data, *hash_keys),
        "block_reasons": list(data.get("block_reasons") or data.get("blocked_reasons") or []),
    }


@dataclass(frozen=True)
class LiveCanaryPreparationRequest:
    requested_stage: str = "live_read_only_probe_and_canary_preparation"
    operator_id: str = "operator_thomas_review_only"
    ticket_or_signature: str = field(default_factory=lambda: f"P9-LIVE-READONLY-{stable_id('p9_ticket', {'stage': 'p9'}, 8)}")
    acknowledged_live_orders_remain_disabled: bool = True
    acknowledged_read_only_probe_only: bool = True
    request_live_order_submission_enabled: bool = False
    request_place_order_enabled: bool = False
    kill_switch_rechecked: bool = True
    manual_kill_switch_active: bool = False
    rollback_runbook_reviewed: bool = True
    monitoring_alerting_reviewed: bool = True
    incident_response_owner_confirmed: bool = True
    max_live_canary_order_count: int = 1
    max_live_canary_notional_usdt: float = 5.0
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_p9_live_read_only_canary_preparation(
    *,
    p8_report: Mapping[str, Any] | None = None,
    live_read_only_probe: Mapping[str, Any] | None = None,
    live_key_scope_validation: Mapping[str, Any] | None = None,
    monitoring_alerting: Mapping[str, Any] | None = None,
    deployment_runbook: Mapping[str, Any] | None = None,
    operator_request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    p8 = dict(p8_report or {})
    probe = dict(live_read_only_probe or {})
    key_scope = dict(live_key_scope_validation or {})
    monitoring = dict(monitoring_alerting or {})
    runbook = dict(deployment_runbook or {})
    request = dict(operator_request or {})

    blockers: list[str] = []
    warnings: list[str] = []

    if p8.get("status") != P8_VALIDATED or p8.get("repeated_clean_signed_testnet_sessions_validated") is not True:
        blockers.append("P9_BLOCK_P8_REPEATED_CLEAN_SIGNED_TESTNET_SESSIONS_NOT_VALIDATED")
    if p8.get("live_canary_execution_enabled") is not False or p8.get("live_scaled_execution_enabled") is not False:
        blockers.append("P9_BLOCK_P8_UNSAFE_LIVE_FLAGS")
    if _bool(p8.get("secret_value_accessed")) or _bool(p8.get("secret_value_logged")):
        blockers.append("P9_BLOCK_P8_SECRET_LEAK")

    if probe.get("status") != LIVE_READ_ONLY_PROBE_OK or probe.get("valid") is not True:
        blockers.append("P9_BLOCK_LIVE_READ_ONLY_PROBE_INVALID_OR_MISSING")
    if probe.get("environment") not in {"live", "mainnet"}:
        blockers.append("P9_BLOCK_LIVE_READ_ONLY_PROBE_ENVIRONMENT_INVALID")
    if probe.get("all_live_read_probes_valid_and_fresh") is not True:
        blockers.append("P9_BLOCK_LIVE_READ_ONLY_PROBES_NOT_ALL_FRESH")
    if probe.get("metadata_only") is not True:
        blockers.append("P9_BLOCK_LIVE_READ_ONLY_PROBE_METADATA_ONLY_FALSE")
    for field, expected in _REQUIRED_LIVE_PROBE_FLAGS_FALSE.items():
        if probe.get(field) not in {expected, None}:
            blockers.append(f"P9_BLOCK_LIVE_READ_ONLY_PROBE_{field.upper()}_NOT_FALSE")
    if _bool(probe.get("order_endpoint_called")) or _bool(probe.get("http_request_sent")):
        blockers.append("P9_BLOCK_LIVE_READ_ONLY_PROBE_ORDER_ENDPOINT_OR_HTTP_SUBMIT_ATTEMPT")
    if probe.get("network_enabled") is False:
        warnings.append("P9_LIVE_READ_ONLY_PROBE_IS_METADATA_STUB_NOT_REAL_NETWORK")

    if key_scope.get("status") != LIVE_KEY_SCOPE_OK or key_scope.get("valid") is not True:
        blockers.append("P9_BLOCK_LIVE_KEY_SCOPE_NOT_VALIDATED")
    if key_scope.get("metadata_only") is not True:
        blockers.append("P9_BLOCK_LIVE_KEY_SCOPE_METADATA_ONLY_FALSE")
    for field in (
        "withdrawal_enabled",
        "transfer_enabled",
        "admin_enabled",
        "write_enabled",
        "trade_enabled",
        "place_order_enabled",
        "cancel_order_enabled",
        "leverage_mutation_enabled",
        "margin_mode_mutation_enabled",
    ):
        if key_scope.get(field) not in {False, None}:
            blockers.append(f"P9_BLOCK_LIVE_KEY_SCOPE_{field.upper()}_NOT_FALSE")
    for field in ("api_key_value_access_allowed", "api_secret_value_access_allowed", "secret_file_access_allowed", "secret_file_creation_allowed", "secret_value_read", "secret_bytes_read"):
        if key_scope.get(field) not in {False, None}:
            blockers.append(f"P9_BLOCK_LIVE_KEY_SCOPE_{field.upper()}_NOT_FALSE")

    if monitoring.get("status") != MONITORING_OK:
        blockers.append("P9_BLOCK_MONITORING_ALERTING_NOT_REVIEW_READY")
    if monitoring.get("heartbeat_ok") is not True:
        blockers.append("P9_BLOCK_MONITORING_HEARTBEAT_NOT_READY")
    if _bool(monitoring.get("external_notification_sent")) or _bool(monitoring.get("telegram_message_sent")):
        blockers.append("P9_BLOCK_MONITORING_EXTERNAL_NOTIFICATION_SENT")
    if _bool(monitoring.get("live_trading_allowed_by_this_module")):
        blockers.append("P9_BLOCK_MONITORING_LIVE_TRADING_ENABLED")

    if runbook.get("status") != DEPLOYMENT_RUNBOOK_OK:
        blockers.append("P9_BLOCK_DEPLOYMENT_RUNBOOK_NOT_REVIEW_READY")
    if runbook.get("review_only") is not True:
        blockers.append("P9_BLOCK_DEPLOYMENT_RUNBOOK_NOT_REVIEW_ONLY")
    if _bool(runbook.get("deployment_ready")) or _bool(runbook.get("server_deployment_performed")):
        blockers.append("P9_BLOCK_DEPLOYMENT_RUNBOOK_ATTEMPTED_DEPLOYMENT")
    if _bool(runbook.get("live_order_submission_allowed")) or _bool(runbook.get("place_order_enabled")):
        blockers.append("P9_BLOCK_DEPLOYMENT_RUNBOOK_LIVE_EXECUTION_ENABLED")

    if not request:
        blockers.append("P9_BLOCK_OPERATOR_LIVE_CANARY_PREPARATION_REQUEST_MISSING")
    else:
        if request.get("requested_stage") != "live_read_only_probe_and_canary_preparation":
            blockers.append("P9_BLOCK_OPERATOR_REQUEST_STAGE_INVALID")
        if not _nonempty(request.get("operator_id")):
            blockers.append("P9_BLOCK_OPERATOR_ID_MISSING")
        if not _nonempty(request.get("ticket_or_signature")):
            blockers.append("P9_BLOCK_OPERATOR_TICKET_OR_SIGNATURE_MISSING")
        if request.get("acknowledged_live_orders_remain_disabled") is not True:
            blockers.append("P9_BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_LIVE_ORDERS_DISABLED")
        if request.get("acknowledged_read_only_probe_only") is not True:
            blockers.append("P9_BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_READ_ONLY_PROBE_ONLY")
        if _bool(request.get("request_live_order_submission_enabled")) or _bool(request.get("request_place_order_enabled")):
            blockers.append("P9_BLOCK_OPERATOR_REQUESTS_LIVE_ORDER_ENABLEMENT")
        if request.get("kill_switch_rechecked") is not True:
            blockers.append("P9_BLOCK_KILL_SWITCH_NOT_RECHECKED")
        if _bool(request.get("manual_kill_switch_active")):
            blockers.append("P9_BLOCK_MANUAL_KILL_SWITCH_ACTIVE")
        if request.get("rollback_runbook_reviewed") is not True:
            blockers.append("P9_BLOCK_ROLLBACK_RUNBOOK_NOT_REVIEWED")
        if request.get("monitoring_alerting_reviewed") is not True:
            blockers.append("P9_BLOCK_MONITORING_ALERTING_NOT_REVIEWED")
        if request.get("incident_response_owner_confirmed") is not True:
            blockers.append("P9_BLOCK_INCIDENT_RESPONSE_OWNER_NOT_CONFIRMED")
        if int(request.get("max_live_canary_order_count") or 0) != 1:
            blockers.append("P9_BLOCK_MAX_LIVE_CANARY_ORDER_COUNT_NOT_ONE")
        try:
            if float(request.get("max_live_canary_notional_usdt") or 0) <= 0 or float(request.get("max_live_canary_notional_usdt") or 0) > 5:
                blockers.append("P9_BLOCK_MAX_LIVE_CANARY_NOTIONAL_INVALID")
        except (TypeError, ValueError):
            blockers.append("P9_BLOCK_MAX_LIVE_CANARY_NOTIONAL_INVALID")

    valid = not blockers
    return {
        "artifact_type": "p9_live_read_only_canary_preparation_validation",
        "valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "warnings": sorted(dict.fromkeys(warnings)),
        "p8_validated": p8.get("status") == P8_VALIDATED,
        "live_read_only_probe_valid": probe.get("status") == LIVE_READ_ONLY_PROBE_OK and probe.get("valid") is True,
        "live_key_scope_validated": key_scope.get("status") == LIVE_KEY_SCOPE_OK and key_scope.get("valid") is True,
        "monitoring_ready": monitoring.get("status") == MONITORING_OK,
        "deployment_runbook_ready": runbook.get("status") == DEPLOYMENT_RUNBOOK_OK,
        **_disabled_payload(),
    }


def build_p9_live_read_only_canary_preparation_report(
    *,
    cfg: AppConfig | None = None,
    p8_report: Mapping[str, Any] | None = None,
    live_read_only_probe: Mapping[str, Any] | None = None,
    live_key_scope_validation: Mapping[str, Any] | None = None,
    monitoring_alerting: Mapping[str, Any] | None = None,
    deployment_runbook: Mapping[str, Any] | None = None,
    operator_request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    p8 = dict(p8_report or _read_latest_json(cfg, "p8_repeated_clean_signed_testnet_sessions_report.json"))
    probe = dict(live_read_only_probe or _read_latest_json(cfg, "live_read_only_adapter_probe.json"))
    key_scope = dict(live_key_scope_validation or _read_latest_json(cfg, "live_key_scope_validation.json"))
    monitoring = dict(monitoring_alerting or _read_latest_json(cfg, "monitoring_alerting_report.json"))
    runbook = dict(deployment_runbook or _read_latest_json(cfg, "deployment_runbook_manifest.json"))
    request = dict(operator_request or {})

    validation = validate_p9_live_read_only_canary_preparation(
        p8_report=p8,
        live_read_only_probe=probe,
        live_key_scope_validation=key_scope,
        monitoring_alerting=monitoring,
        deployment_runbook=runbook,
        operator_request=request,
    )
    p8_missing_or_waiting = p8.get("status") != P8_VALIDATED
    if validation["valid"]:
        status = STATUS_READY_REVIEW_ONLY
        blocked = False
        fail_closed = False
    elif p8_missing_or_waiting:
        status = STATUS_WAITING_REVIEW_ONLY
        blocked = True
        fail_closed = True
    else:
        status = STATUS_BLOCKED_FAIL_CLOSED
        blocked = True
        fail_closed = True

    sources = {
        "p8_repeated_clean_signed_testnet_sessions": _summary(p8, name="p8_repeated_clean_signed_testnet_sessions", hash_keys=("p8_repeated_clean_signed_testnet_sessions_sha256",)),
        "live_read_only_adapter_probe": _summary(probe, name="live_read_only_adapter_probe", hash_keys=("live_read_only_adapter_probe_sha256",)),
        "live_key_scope_validation": _summary(key_scope, name="live_key_scope_validation", hash_keys=("live_key_scope_validation_sha256",)),
        "monitoring_alerting": _summary(monitoring, name="monitoring_alerting", hash_keys=("monitoring_alerting_report_sha256",)),
        "deployment_runbook": _summary(runbook, name="deployment_runbook", hash_keys=("deployment_runbook_sha256",)),
    }
    report = {
        "artifact_type": "p9_live_read_only_canary_preparation",
        "p9_live_read_only_canary_preparation_version": P9_LIVE_READ_ONLY_CANARY_PREPARATION_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": fail_closed,
        "review_only": True,
        "source_evidence_hash_summary": sources,
        "validation": validation,
        "p8_repeated_clean_signed_testnet_sessions_validated": p8.get("status") == P8_VALIDATED and p8.get("repeated_clean_signed_testnet_sessions_validated") is True,
        "live_read_only_probe_evidence_present": bool(probe),
        "live_read_only_probe_valid": validation["live_read_only_probe_valid"],
        "live_read_only_probe_actual_network_performed": bool(probe.get("network_enabled") is True and probe.get("deterministic_stub") is not True),
        "live_key_scope_validation_present": bool(key_scope),
        "live_key_scope_validated": validation["live_key_scope_validated"],
        "monitoring_alerting_ready": validation["monitoring_ready"],
        "deployment_runbook_ready": validation["deployment_runbook_ready"],
        "operator_live_canary_preparation_request_present": bool(request),
        "live_canary_preparation_ready_for_manual_approval_packet": validation["valid"],
        "live_canary_approval_packet_created": False,
        "live_canary_order_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "actual_live_order_submitted": False,
        "live_order_endpoint_called": False,
        "block_reasons": validation["block_reasons"],
        "warnings": validation["warnings"],
        "created_at_utc": utc_now_canonical(),
        **_disabled_payload(),
    }
    report["unsafe_truthy_execution_flags"] = truthy_execution_flags(report)
    if report["unsafe_truthy_execution_flags"]:
        report["status"] = STATUS_BLOCKED_FAIL_CLOSED
        report["blocked"] = True
        report["fail_closed"] = True
        report["live_canary_preparation_ready_for_manual_approval_packet"] = False
        report["block_reasons"] = sorted(dict.fromkeys(report["block_reasons"] + ["P9_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
    report["p9_live_read_only_canary_preparation_id"] = stable_id("p9_live_read_only_canary_preparation", report, 24)
    report["p9_live_read_only_canary_preparation_sha256"] = sha256_json(report)
    return report


def build_valid_p9_fixture_sources() -> dict[str, Any]:
    now = utc_now_canonical()
    p8 = {
        "status": P8_VALIDATED,
        "p8_repeated_clean_signed_testnet_sessions_sha256": "8" * 64,
        "repeated_clean_signed_testnet_sessions_validated": True,
        "live_canary_preparation_candidate_evidence_created": True,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
    }
    probe = {
        "status": LIVE_READ_ONLY_PROBE_OK,
        "valid": True,
        "live_read_only_adapter_probe_sha256": "1" * 64,
        "venue": "binance_futures_live",
        "environment": "live",
        "metadata_only": True,
        "network_enabled": False,
        "deterministic_stub": True,
        "all_live_read_probes_valid_and_fresh": True,
        "created_at_utc": now,
        **_REQUIRED_LIVE_PROBE_FLAGS_FALSE,
        "order_endpoint_called": False,
        "http_request_sent": False,
    }
    key_scope = {
        "status": LIVE_KEY_SCOPE_OK,
        "valid": True,
        "live_key_scope_validation_sha256": "2" * 64,
        "metadata_only": True,
        "environment": "live",
        "venue": "binance_futures_live",
        "scope": ["read_only"],
        "withdrawal_enabled": False,
        "transfer_enabled": False,
        "admin_enabled": False,
        "write_enabled": False,
        "trade_enabled": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "leverage_mutation_enabled": False,
        "margin_mode_mutation_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "secret_value_read": False,
        "secret_bytes_read": False,
    }
    monitoring = {
        "status": MONITORING_OK,
        "monitoring_alerting_report_sha256": "3" * 64,
        "review_only": True,
        "heartbeat_ok": True,
        "external_notification_sent": False,
        "telegram_message_sent": False,
        "live_trading_allowed_by_this_module": False,
    }
    runbook = {
        "status": DEPLOYMENT_RUNBOOK_OK,
        "deployment_runbook_sha256": "4" * 64,
        "review_only": True,
        "deployment_ready": False,
        "server_deployment_performed": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
    }
    return {
        "p8_report": p8,
        "live_read_only_probe": probe,
        "live_key_scope_validation": key_scope,
        "monitoring_alerting": monitoring,
        "deployment_runbook": runbook,
        "operator_request": LiveCanaryPreparationRequest().to_dict(),
    }


def build_p9_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    valid = build_valid_p9_fixture_sources()
    cases: dict[str, dict[str, Any]] = {
        "p8_not_validated": {"p8_report": {**valid["p8_report"], "status": "P8_WAITING", "repeated_clean_signed_testnet_sessions_validated": False}},
        "live_probe_trade_enabled": {"live_read_only_probe": {**valid["live_read_only_probe"], "place_order_enabled": True}},
        "live_probe_http_submit_attempt": {"live_read_only_probe": {**valid["live_read_only_probe"], "http_request_sent": True}},
        "live_key_scope_withdrawal_enabled": {"live_key_scope_validation": {**valid["live_key_scope_validation"], "withdrawal_enabled": True}},
        "live_key_scope_secret_read": {"live_key_scope_validation": {**valid["live_key_scope_validation"], "secret_value_read": True}},
        "monitoring_external_notification_sent": {"monitoring_alerting": {**valid["monitoring_alerting"], "external_notification_sent": True}},
        "runbook_attempted_deployment": {"deployment_runbook": {**valid["deployment_runbook"], "server_deployment_performed": True}},
        "operator_requests_live_order_enablement": {"operator_request": {**valid["operator_request"], "request_place_order_enabled": True}},
        "operator_kill_switch_active": {"operator_request": {**valid["operator_request"], "manual_kill_switch_active": True}},
    }
    results: dict[str, Any] = {}
    for name, patch in cases.items():
        sources = dict(valid)
        sources.update(patch)
        report = build_p9_live_read_only_canary_preparation_report(cfg=cfg, **sources)
        results[name] = {
            "fixture_name": name,
            "blocked_fail_closed": report["blocked"] is True and report["fail_closed"] is True,
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "live_canary_execution_enabled": report["live_canary_execution_enabled"],
            "actual_live_order_submitted": report["actual_live_order_submitted"],
        }
    payload = {
        "artifact_type": "p9_live_read_only_canary_preparation_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()),
        "fixture_results": results,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "actual_live_order_submitted": False,
        **_disabled_payload(),
    }
    payload["p9_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_p9_live_read_only_canary_preparation(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_p9_live_read_only_canary_preparation_report(cfg=cfg)
    negative = build_p9_negative_fixture_results(cfg=cfg)
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p9_live_read_only_canary_preparation")
    registry_record = append_registry_record(
        registry_path(cfg, P9_LIVE_READ_ONLY_CANARY_PREPARATION_REGISTRY_NAME),
        {
            "artifact_type": "p9_live_read_only_canary_preparation_registry_record",
            "status": report["status"],
            "blocked": report["blocked"],
            "p9_live_read_only_canary_preparation_id": report["p9_live_read_only_canary_preparation_id"],
            "p9_live_read_only_canary_preparation_sha256": report["p9_live_read_only_canary_preparation_sha256"],
            "p8_repeated_clean_signed_testnet_sessions_validated": report["p8_repeated_clean_signed_testnet_sessions_validated"],
            "live_read_only_probe_valid": report["live_read_only_probe_valid"],
            "live_key_scope_validated": report["live_key_scope_validated"],
            "monitoring_alerting_ready": report["monitoring_alerting_ready"],
            "deployment_runbook_ready": report["deployment_runbook_ready"],
            "live_canary_preparation_ready_for_manual_approval_packet": report["live_canary_preparation_ready_for_manual_approval_packet"],
            "live_canary_execution_enabled": False,
            "actual_live_order_submitted": False,
            "secret_value_accessed": False,
            "created_at_utc": report["created_at_utc"],
        },
        registry_name=P9_LIVE_READ_ONLY_CANARY_PREPARATION_REGISTRY_NAME,
        id_field="p9_live_read_only_canary_preparation_registry_record_id",
        hash_field="p9_live_read_only_canary_preparation_registry_record_sha256",
        id_prefix="p9_live_read_only_canary_preparation_registry_record",
    )
    report["p9_live_read_only_canary_preparation_registry_record_id"] = registry_record[
        "p9_live_read_only_canary_preparation_registry_record_id"
    ]
    report["p9_live_read_only_canary_preparation_registry_record_sha256"] = registry_record[
        "p9_live_read_only_canary_preparation_registry_record_sha256"
    ]
    report["p9_live_read_only_canary_preparation_sha256"] = sha256_json(report)
    summary = {
        "artifact_type": "p9_live_read_only_canary_preparation_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "p8_repeated_clean_signed_testnet_sessions_validated": report["p8_repeated_clean_signed_testnet_sessions_validated"],
        "live_read_only_probe_valid": report["live_read_only_probe_valid"],
        "live_read_only_probe_actual_network_performed": report["live_read_only_probe_actual_network_performed"],
        "live_key_scope_validated": report["live_key_scope_validated"],
        "monitoring_alerting_ready": report["monitoring_alerting_ready"],
        "deployment_runbook_ready": report["deployment_runbook_ready"],
        "live_canary_preparation_ready_for_manual_approval_packet": report["live_canary_preparation_ready_for_manual_approval_packet"],
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "actual_live_order_submitted": False,
        "secret_value_accessed": False,
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked_fail_closed"],
        "p9_live_read_only_canary_preparation_id": report["p9_live_read_only_canary_preparation_id"],
        "p9_live_read_only_canary_preparation_sha256": report["p9_live_read_only_canary_preparation_sha256"],
    }
    for base in (latest, storage):
        atomic_write_json(base / "p9_live_read_only_canary_preparation_report.json", report)
        atomic_write_json(base / "p9_live_read_only_canary_preparation_summary.json", summary)
        atomic_write_json(base / "p9_live_read_only_canary_preparation_negative_fixture_results.json", negative)
        atomic_write_json(base / "p9_live_read_only_canary_preparation_registry_record.json", registry_record)
    return report


__all__ = [
    "P9_LIVE_READ_ONLY_CANARY_PREPARATION_VERSION",
    "STATUS_WAITING_REVIEW_ONLY",
    "STATUS_READY_REVIEW_ONLY",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "LiveCanaryPreparationRequest",
    "validate_p9_live_read_only_canary_preparation",
    "build_p9_live_read_only_canary_preparation_report",
    "build_p9_negative_fixture_results",
    "build_valid_p9_fixture_sources",
    "persist_p9_live_read_only_canary_preparation",
]
