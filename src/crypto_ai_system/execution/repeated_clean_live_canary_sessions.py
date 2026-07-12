from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_VERSION = "p12_repeated_clean_live_canary_sessions_v1"
P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_REGISTRY_NAME = "p12_repeated_clean_live_canary_sessions_registry"

STATUS_WAITING_REVIEW_ONLY = "P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_WAITING_REVIEW_ONLY"
STATUS_VALIDATED_REVIEW_ONLY = "P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_VALIDATED_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_BLOCKED_FAIL_CLOSED"

MIN_CLEAN_LIVE_CANARY_SESSION_COUNT = 5
MAX_RECONCILIATION_MISMATCH_COUNT = 0
MAX_API_ERROR_RATE = 0.20
MAX_REJECTION_RATE = 0.30
MAX_TIMEOUT_RATE = 0.20
MAX_RATE_LIMIT_RATE = 0.20
MAX_AVG_LATENCY_MS = 2_000
MAX_ABS_AVG_SLIPPAGE_BPS = 10.0
MAX_MANUAL_OVERRIDE_COUNT = 0
MAX_INCIDENT_COUNT = 0

REQUIRED_LIVE_CANARY_SESSION_SCENARIOS = {
    "live_long_filled",
    "live_short_filled",
    "live_partial_fill_reconciled",
    "live_rejected_reconciled",
    "live_cancel_reconciled",
    "live_timeout_reconciled",
    "live_api_error_retry_reconciled",
    "live_rate_limit_retry_reconciled",
    "live_kill_switch_blocked",
}

_ALLOWED_SCENARIOS = REQUIRED_LIVE_CANARY_SESSION_SCENARIOS | {"live_accepted_filled"}
_ALLOWED_FINAL_STATUSES = {"FILLED", "PARTIALLY_FILLED", "REJECTED", "CANCELED", "EXPIRED", "BLOCKED_BY_KILL_SWITCH"}

_ALWAYS_DISABLED_FLAGS = {
    "ready_for_signed_testnet_execution": False,
    "testnet_order_submission_allowed": False,
    "signed_testnet_promotion_allowed": False,
    "external_order_submission_allowed": False,
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
    "live_scaled_readiness_allowed": False,
    "live_scaled_promotion_allowed": False,
    "live_scaled_auto_trading_allowed": False,
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


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sha_from(payload: Mapping[str, Any], *keys: str) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in keys:
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _disabled_payload() -> dict[str, Any]:
    payload = default_execution_flag_state()
    payload.update(_ALWAYS_DISABLED_FLAGS)
    payload.update(
        {
            "repeated_live_canary_session_validation_started": False,
            "live_scaled_readiness_candidate_evidence_created": False,
            "live_scaled_readiness_may_begin": False,
            "live_scaled_readiness_allowed": False,
            "live_scaled_approval_required": True,
            "separate_live_scaled_approval_present": False,
            "limited_live_scaled_auto_trading_allowed": False,
            "actual_live_order_submitted_by_this_module": False,
        }
    )
    return payload


@dataclass(frozen=True)
class LiveCanarySessionEvidence:
    session_id: str
    scenario: str
    side: str = "BUY"
    symbol: str = "BTCUSDT"
    environment: str = "live_canary"
    exchange: str = "binance_futures_live"
    final_status: str = "FILLED"
    p11_live_canary_post_submit_evidence_review_sha256: str = field(default_factory=lambda: "b" * 64)
    live_canary_post_submit_chain_complete: bool = True
    live_canary_reconciliation_clean: bool = True
    canary_outcome_review_completed: bool = True
    canary_outcome_clean: bool = True
    post_submit_relock_confirmed: bool = True
    actual_live_order_submitted: bool = True
    live_order_endpoint_called: bool = True
    order_count: int = 1
    idempotency_key: str = "p12_live_canary_idempotency_key"
    exchange_order_id: str = "live_canary_order_session"
    reconciliation_mismatch_count: int = 0
    api_error_count: int = 0
    retry_count: int = 0
    rate_limit_retry_count: int = 0
    rejected: bool = False
    timeout_observed: bool = False
    cancel_boundary_exercised: bool = False
    manual_override_count: int = 0
    incident_count: int = 0
    critical_alert_count: int = 0
    kill_switch_tested: bool = True
    kill_switch_blocked_submit: bool = False
    latency_ms: int = 450
    slippage_bps: float = 1.0
    fee_bps: float = 4.0
    notional_usdt: float = 5.0
    max_notional_usdt: float = 5.0
    secret_value_logged: bool = False
    api_key_value_logged: bool = False
    api_secret_value_logged: bool = False
    secret_value_accessed: bool = False
    mainnet_key_scope_allowed: bool = False
    withdrawal_permission_allowed: bool = False
    transfer_permission_allowed: bool = False
    admin_permission_allowed: bool = False
    live_scaled_readiness_allowed: bool = False
    live_scaled_promotion_allowed: bool = False
    live_scaled_execution_enabled: bool = False
    live_canary_execution_enabled: bool = False
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    auto_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["live_canary_session_evidence_sha256"] = sha256_json(payload)
        return payload


def build_required_live_canary_session_fixture_set() -> list[LiveCanarySessionEvidence]:
    return [
        LiveCanarySessionEvidence(session_id="p12_live_canary_session_001", scenario="live_long_filled", side="BUY", final_status="FILLED", idempotency_key="p12_live_idem_001", exchange_order_id="live_order_001"),
        LiveCanarySessionEvidence(session_id="p12_live_canary_session_002", scenario="live_short_filled", side="SELL", final_status="FILLED", idempotency_key="p12_live_idem_002", exchange_order_id="live_order_002"),
        LiveCanarySessionEvidence(session_id="p12_live_canary_session_003", scenario="live_partial_fill_reconciled", side="BUY", final_status="PARTIALLY_FILLED", idempotency_key="p12_live_idem_003", exchange_order_id="live_order_003"),
        LiveCanarySessionEvidence(session_id="p12_live_canary_session_004", scenario="live_rejected_reconciled", side="SELL", final_status="REJECTED", rejected=True, idempotency_key="p12_live_idem_004", exchange_order_id="live_order_004"),
        LiveCanarySessionEvidence(session_id="p12_live_canary_session_005", scenario="live_cancel_reconciled", side="BUY", final_status="CANCELED", cancel_boundary_exercised=True, idempotency_key="p12_live_idem_005", exchange_order_id="live_order_005"),
        LiveCanarySessionEvidence(session_id="p12_live_canary_session_006", scenario="live_timeout_reconciled", side="SELL", final_status="EXPIRED", timeout_observed=True, idempotency_key="p12_live_idem_006", exchange_order_id="live_order_006"),
        LiveCanarySessionEvidence(session_id="p12_live_canary_session_007", scenario="live_api_error_retry_reconciled", side="BUY", final_status="FILLED", api_error_count=1, retry_count=1, idempotency_key="p12_live_idem_007", exchange_order_id="live_order_007"),
        LiveCanarySessionEvidence(session_id="p12_live_canary_session_008", scenario="live_rate_limit_retry_reconciled", side="SELL", final_status="FILLED", retry_count=1, rate_limit_retry_count=1, idempotency_key="p12_live_idem_008", exchange_order_id="live_order_008"),
        LiveCanarySessionEvidence(
            session_id="p12_live_canary_session_009",
            scenario="live_kill_switch_blocked",
            side="BUY",
            final_status="BLOCKED_BY_KILL_SWITCH",
            actual_live_order_submitted=False,
            live_order_endpoint_called=False,
            order_count=0,
            exchange_order_id="kill_switch_blocked_no_live_order",
            idempotency_key="p12_live_idem_009_kill_switch",
            kill_switch_blocked_submit=True,
        ),
    ]


def validate_single_live_canary_session_evidence(evidence: Mapping[str, Any] | LiveCanarySessionEvidence) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, LiveCanarySessionEvidence) else dict(evidence or {})
    blockers: list[str] = []
    session_id = str(payload.get("session_id") or "")
    prefix = "P12_SESSION"
    if not _nonempty(session_id):
        blockers.append(f"{prefix}_ID_MISSING")
    if payload.get("environment") != "live_canary":
        blockers.append(f"{prefix}_ENVIRONMENT_NOT_LIVE_CANARY")
    if payload.get("symbol") != "BTCUSDT":
        blockers.append(f"{prefix}_SYMBOL_NOT_BTCUSDT")
    scenario = str(payload.get("scenario") or "")
    if scenario not in _ALLOWED_SCENARIOS:
        blockers.append(f"{prefix}_SCENARIO_NOT_ALLOWED")
    side = str(payload.get("side") or "").upper()
    if side not in {"BUY", "SELL"}:
        blockers.append(f"{prefix}_SIDE_INVALID")
    final_status = str(payload.get("final_status") or "").upper()
    if final_status not in _ALLOWED_FINAL_STATUSES:
        blockers.append(f"{prefix}_FINAL_STATUS_INVALID")
    if not _nonempty(payload.get("p11_live_canary_post_submit_evidence_review_sha256")):
        blockers.append(f"{prefix}_SOURCE_P11_HASH_MISSING")
    kill_switch_session = scenario == "live_kill_switch_blocked"
    if not kill_switch_session:
        for key, reason in (
            ("live_canary_post_submit_chain_complete", f"{prefix}_POST_SUBMIT_CHAIN_INCOMPLETE"),
            ("live_canary_reconciliation_clean", f"{prefix}_RECONCILIATION_NOT_CLEAN"),
            ("canary_outcome_review_completed", f"{prefix}_OUTCOME_REVIEW_NOT_COMPLETED"),
            ("canary_outcome_clean", f"{prefix}_OUTCOME_NOT_CLEAN"),
            ("post_submit_relock_confirmed", f"{prefix}_POST_SUBMIT_RELOCK_NOT_CONFIRMED"),
            ("actual_live_order_submitted", f"{prefix}_ACTUAL_LIVE_ORDER_NOT_SUBMITTED"),
            ("live_order_endpoint_called", f"{prefix}_LIVE_ORDER_ENDPOINT_NOT_CALLED_IN_EXTERNAL_SESSION"),
        ):
            if payload.get(key) is not True:
                blockers.append(reason)
        if payload.get("order_count") != 1:
            blockers.append(f"{prefix}_ORDER_COUNT_NOT_ONE")
        if not _nonempty(payload.get("exchange_order_id")):
            blockers.append(f"{prefix}_EXCHANGE_ORDER_ID_MISSING")
    else:
        if payload.get("kill_switch_blocked_submit") is not True:
            blockers.append(f"{prefix}_KILL_SWITCH_BLOCKED_SUBMIT_NOT_TRUE")
        if payload.get("actual_live_order_submitted") is not False:
            blockers.append(f"{prefix}_KILL_SWITCH_SESSION_SUBMITTED_ORDER")
        if payload.get("live_order_endpoint_called") is not False:
            blockers.append(f"{prefix}_KILL_SWITCH_SESSION_ENDPOINT_CALLED")
        if payload.get("order_count") not in {0, "0"}:
            blockers.append(f"{prefix}_KILL_SWITCH_SESSION_ORDER_COUNT_NOT_ZERO")
    if _as_int(payload.get("reconciliation_mismatch_count"), 999) != 0:
        blockers.append(f"{prefix}_RECONCILIATION_MISMATCH_COUNT_NONZERO")
    if _as_int(payload.get("api_error_count"), 0) < 0:
        blockers.append(f"{prefix}_API_ERROR_COUNT_INVALID")
    if _as_int(payload.get("retry_count"), 0) < 0 or _as_int(payload.get("retry_count"), 0) > 2:
        blockers.append(f"{prefix}_RETRY_COUNT_OUT_OF_POLICY")
    if _as_int(payload.get("rate_limit_retry_count"), 0) < 0 or _as_int(payload.get("rate_limit_retry_count"), 0) > 2:
        blockers.append(f"{prefix}_RATE_LIMIT_RETRY_COUNT_OUT_OF_POLICY")
    if _as_int(payload.get("manual_override_count"), 0) != 0:
        blockers.append(f"{prefix}_MANUAL_OVERRIDE_COUNT_NONZERO")
    if _as_int(payload.get("incident_count"), 0) != 0:
        blockers.append(f"{prefix}_INCIDENT_COUNT_NONZERO")
    if _as_int(payload.get("critical_alert_count"), 0) != 0:
        blockers.append(f"{prefix}_CRITICAL_ALERT_COUNT_NONZERO")
    if payload.get("kill_switch_tested") is not True:
        blockers.append(f"{prefix}_KILL_SWITCH_NOT_TESTED")
    if _as_float(payload.get("notional_usdt"), 0.0) > _as_float(payload.get("max_notional_usdt"), 0.0):
        blockers.append(f"{prefix}_NOTIONAL_EXCEEDS_CAP")
    if _as_int(payload.get("latency_ms"), 0) < 0:
        blockers.append(f"{prefix}_LATENCY_INVALID")
    if abs(_as_float(payload.get("slippage_bps"), 0.0)) > 1000:
        blockers.append(f"{prefix}_SLIPPAGE_OUT_OF_SANITY_RANGE")
    if _as_float(payload.get("fee_bps"), 0.0) < 0:
        blockers.append(f"{prefix}_FEE_INVALID")
    for key, reason in (
        ("secret_value_logged", f"{prefix}_SECRET_VALUE_LOGGED"),
        ("api_key_value_logged", f"{prefix}_API_KEY_VALUE_LOGGED"),
        ("api_secret_value_logged", f"{prefix}_API_SECRET_VALUE_LOGGED"),
        ("secret_value_accessed", f"{prefix}_SECRET_VALUE_ACCESSED"),
        ("mainnet_key_scope_allowed", f"{prefix}_MAINNET_KEY_SCOPE_ALLOWED"),
        ("withdrawal_permission_allowed", f"{prefix}_WITHDRAWAL_PERMISSION_ALLOWED"),
        ("transfer_permission_allowed", f"{prefix}_TRANSFER_PERMISSION_ALLOWED"),
        ("admin_permission_allowed", f"{prefix}_ADMIN_PERMISSION_ALLOWED"),
        ("live_scaled_readiness_allowed", f"{prefix}_LIVE_SCALED_READINESS_ALLOWED"),
        ("live_scaled_promotion_allowed", f"{prefix}_LIVE_SCALED_PROMOTION_ALLOWED"),
        ("live_scaled_execution_enabled", f"{prefix}_LIVE_SCALED_EXECUTION_ENABLED"),
        ("live_canary_execution_enabled", f"{prefix}_LIVE_CANARY_EXECUTION_ENABLED"),
        ("runtime_settings_mutated", f"{prefix}_RUNTIME_SETTINGS_MUTATED"),
        ("score_weights_mutated", f"{prefix}_SCORE_WEIGHTS_MUTATED"),
        ("auto_promotion_allowed", f"{prefix}_AUTO_PROMOTION_ALLOWED"),
    ):
        if payload.get(key) is True:
            blockers.append(reason)
    validation = {
        "single_live_canary_session_evidence_valid": not blockers,
        "single_live_canary_session_block_reasons": sorted(dict.fromkeys(blockers)),
        "session_id": session_id,
        "scenario": scenario,
        "side": side,
        "final_status": final_status,
        "is_kill_switch_session": kill_switch_session,
        "actual_live_order_submitted": payload.get("actual_live_order_submitted") is True,
        "reconciliation_mismatch_count": _as_int(payload.get("reconciliation_mismatch_count"), 0),
        "api_error_count": _as_int(payload.get("api_error_count"), 0),
        "retry_count": _as_int(payload.get("retry_count"), 0),
        "rate_limit_retry_count": _as_int(payload.get("rate_limit_retry_count"), 0),
        "manual_override_count": _as_int(payload.get("manual_override_count"), 0),
        "incident_count": _as_int(payload.get("incident_count"), 0),
        "critical_alert_count": _as_int(payload.get("critical_alert_count"), 0),
        "latency_ms": _as_int(payload.get("latency_ms"), 0),
        "slippage_bps": _as_float(payload.get("slippage_bps"), 0.0),
        "fee_bps": _as_float(payload.get("fee_bps"), 0.0),
    }
    validation["single_live_canary_session_validation_sha256"] = sha256_json(validation)
    return validation


def validate_repeated_clean_live_canary_sessions(
    session_evidence: Sequence[Mapping[str, Any] | LiveCanarySessionEvidence] | None,
    *,
    min_clean_session_count: int = MIN_CLEAN_LIVE_CANARY_SESSION_COUNT,
) -> dict[str, Any]:
    sessions = [item.to_dict() if isinstance(item, LiveCanarySessionEvidence) else dict(item or {}) for item in list(session_evidence or [])]
    validations = [validate_single_live_canary_session_evidence(item) for item in sessions]
    blockers: list[str] = []
    if not sessions:
        blockers.append("P12_LIVE_CANARY_SESSION_EVIDENCE_MISSING")
    valid_session_count = sum(1 for validation in validations if validation["single_live_canary_session_evidence_valid"])
    clean_submitted_session_count = sum(
        1
        for validation in validations
        if validation["single_live_canary_session_evidence_valid"] and validation["actual_live_order_submitted"] is True
    )
    if clean_submitted_session_count < min_clean_session_count:
        blockers.append("P12_MIN_CLEAN_LIVE_CANARY_SESSION_COUNT_NOT_MET")
    session_ids = [str(item.get("session_id") or "") for item in sessions]
    if len([sid for sid in session_ids if sid]) != len(set([sid for sid in session_ids if sid])):
        blockers.append("P12_DUPLICATE_SESSION_ID_DETECTED")
    idempotency_keys = [str(item.get("idempotency_key") or "") for item in sessions if item.get("actual_live_order_submitted") is True]
    if len([key for key in idempotency_keys if key]) != len(set([key for key in idempotency_keys if key])):
        blockers.append("P12_DUPLICATE_IDEMPOTENCY_KEY_DETECTED")
    for index, validation in enumerate(validations):
        for reason in validation["single_live_canary_session_block_reasons"]:
            blockers.append(f"P12_SESSION_{index}_{reason}")
    scenario_set = {validation["scenario"] for validation in validations if validation["single_live_canary_session_evidence_valid"]}
    missing_scenarios = sorted(REQUIRED_LIVE_CANARY_SESSION_SCENARIOS - scenario_set)
    for scenario in missing_scenarios:
        blockers.append(f"P12_REQUIRED_SCENARIO_MISSING:{scenario}")
    side_set = {validation["side"] for validation in validations if validation["actual_live_order_submitted"] is True}
    if not {"BUY", "SELL"}.issubset(side_set):
        blockers.append("P12_LONG_SHORT_COVERAGE_MISSING")
    mismatch_count = sum(validation["reconciliation_mismatch_count"] for validation in validations)
    api_error_count = sum(validation["api_error_count"] for validation in validations)
    retry_count = sum(validation["retry_count"] for validation in validations)
    rate_limit_retry_count = sum(validation["rate_limit_retry_count"] for validation in validations)
    manual_override_count = sum(validation["manual_override_count"] for validation in validations)
    incident_count = sum(validation["incident_count"] for validation in validations)
    critical_alert_count = sum(validation["critical_alert_count"] for validation in validations)
    rejection_count = sum(1 for validation in validations if validation["final_status"] == "REJECTED")
    timeout_count = sum(1 for validation in validations if validation["final_status"] == "EXPIRED")
    kill_switch_session_count = sum(1 for validation in validations if validation["is_kill_switch_session"])
    submitted_denominator = max(clean_submitted_session_count, 1)
    total_denominator = max(valid_session_count, 1)
    api_error_rate = api_error_count / submitted_denominator
    rejection_rate = rejection_count / total_denominator
    timeout_rate = timeout_count / total_denominator
    rate_limit_rate = rate_limit_retry_count / submitted_denominator
    avg_latency_ms = sum(validation["latency_ms"] for validation in validations) / max(len(validations), 1)
    avg_abs_slippage_bps = sum(abs(validation["slippage_bps"]) for validation in validations) / max(len(validations), 1)
    avg_fee_bps = sum(validation["fee_bps"] for validation in validations) / max(len(validations), 1)
    if mismatch_count != MAX_RECONCILIATION_MISMATCH_COUNT:
        blockers.append("P12_RECONCILIATION_MISMATCH_COUNT_NONZERO")
    if api_error_rate > MAX_API_ERROR_RATE:
        blockers.append("P12_API_ERROR_RATE_ABOVE_THRESHOLD")
    if rejection_rate > MAX_REJECTION_RATE:
        blockers.append("P12_REJECTION_RATE_ABOVE_THRESHOLD")
    if timeout_rate > MAX_TIMEOUT_RATE:
        blockers.append("P12_TIMEOUT_RATE_ABOVE_THRESHOLD")
    if rate_limit_rate > MAX_RATE_LIMIT_RATE:
        blockers.append("P12_RATE_LIMIT_RATE_ABOVE_THRESHOLD")
    if avg_latency_ms > MAX_AVG_LATENCY_MS:
        blockers.append("P12_AVERAGE_LATENCY_ABOVE_THRESHOLD")
    if avg_abs_slippage_bps > MAX_ABS_AVG_SLIPPAGE_BPS:
        blockers.append("P12_AVERAGE_SLIPPAGE_ABOVE_THRESHOLD")
    if manual_override_count != MAX_MANUAL_OVERRIDE_COUNT:
        blockers.append("P12_MANUAL_OVERRIDE_COUNT_NONZERO")
    if incident_count != MAX_INCIDENT_COUNT:
        blockers.append("P12_INCIDENT_COUNT_NONZERO")
    if critical_alert_count != 0:
        blockers.append("P12_CRITICAL_ALERT_COUNT_NONZERO")
    if kill_switch_session_count < 1:
        blockers.append("P12_KILL_SWITCH_BLOCK_SESSION_MISSING")
    validation = {
        "repeated_clean_live_canary_sessions_valid": not blockers,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "required_min_clean_live_canary_session_count": min_clean_session_count,
        "session_count": len(sessions),
        "valid_session_count": valid_session_count,
        "clean_submitted_session_count": clean_submitted_session_count,
        "required_live_canary_session_scenarios": sorted(REQUIRED_LIVE_CANARY_SESSION_SCENARIOS),
        "observed_live_canary_session_scenarios": sorted(scenario_set),
        "missing_live_canary_session_scenarios": missing_scenarios,
        "long_short_coverage_observed": {"BUY", "SELL"}.issubset(side_set),
        "reconciliation_mismatch_count": mismatch_count,
        "api_error_count": api_error_count,
        "retry_count": retry_count,
        "rate_limit_retry_count": rate_limit_retry_count,
        "manual_override_count": manual_override_count,
        "incident_count": incident_count,
        "critical_alert_count": critical_alert_count,
        "rejection_count": rejection_count,
        "timeout_count": timeout_count,
        "kill_switch_session_count": kill_switch_session_count,
        "api_error_rate": api_error_rate,
        "rejection_rate": rejection_rate,
        "timeout_rate": timeout_rate,
        "rate_limit_rate": rate_limit_rate,
        "average_latency_ms": avg_latency_ms,
        "average_abs_slippage_bps": avg_abs_slippage_bps,
        "average_fee_bps": avg_fee_bps,
        "session_validations": validations,
    }
    validation["repeated_clean_live_canary_sessions_validation_sha256"] = sha256_json(validation)
    return validation


def _valid_p11_complete_fixture() -> dict[str, Any]:
    return {
        "status": "P11_LIVE_CANARY_POST_SUBMIT_EVIDENCE_REVIEW_OUTCOME_REVIEW_RECORDED_REVIEW_ONLY",
        "p11_live_canary_post_submit_evidence_review_sha256": "b" * 64,
        "external_live_canary_submit_evidence_present": True,
        "live_canary_post_submit_chain_complete": True,
        "live_canary_reconciliation_clean": True,
        "canary_outcome_review_completed": True,
        "post_submit_relock_confirmed": True,
        "actual_live_order_submitted": True,
        "live_order_endpoint_called": True,
        "order_status_endpoint_called": True,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "live_canary_execution_enabled": False,
        "live_scaled_readiness_allowed": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_execution_enabled": False,
    }


def _p11_source_state(source_p11: Mapping[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if not source_p11:
        blockers.append("P12_SOURCE_P11_LIVE_CANARY_OUTCOME_REVIEW_MISSING")
        return False, blockers
    if source_p11.get("status") != "P11_LIVE_CANARY_POST_SUBMIT_EVIDENCE_REVIEW_OUTCOME_REVIEW_RECORDED_REVIEW_ONLY":
        blockers.append("P12_SOURCE_P11_OUTCOME_REVIEW_NOT_RECORDED")
    for key, reason in (
        ("external_live_canary_submit_evidence_present", "P12_SOURCE_P11_EXTERNAL_SUBMIT_EVIDENCE_MISSING"),
        ("live_canary_post_submit_chain_complete", "P12_SOURCE_P11_POST_SUBMIT_CHAIN_INCOMPLETE"),
        ("live_canary_reconciliation_clean", "P12_SOURCE_P11_RECONCILIATION_NOT_CLEAN"),
        ("canary_outcome_review_completed", "P12_SOURCE_P11_OUTCOME_REVIEW_NOT_COMPLETED"),
        ("post_submit_relock_confirmed", "P12_SOURCE_P11_POST_SUBMIT_RELOCK_NOT_CONFIRMED"),
    ):
        if source_p11.get(key) is not True:
            blockers.append(reason)
    for key, reason in (
        ("secret_value_accessed", "P12_SOURCE_P11_SECRET_VALUE_ACCESSED"),
        ("secret_value_logged", "P12_SOURCE_P11_SECRET_VALUE_LOGGED"),
        ("live_canary_execution_enabled", "P12_SOURCE_P11_LIVE_CANARY_EXECUTION_ENABLED"),
        ("live_scaled_readiness_allowed", "P12_SOURCE_P11_LIVE_SCALED_READINESS_ALLOWED"),
        ("live_scaled_promotion_allowed", "P12_SOURCE_P11_LIVE_SCALED_PROMOTION_ALLOWED"),
        ("live_scaled_execution_enabled", "P12_SOURCE_P11_LIVE_SCALED_EXECUTION_ENABLED"),
    ):
        if source_p11.get(key) is True:
            blockers.append(reason)
    return not blockers, sorted(dict.fromkeys(blockers))


def build_repeated_clean_live_canary_sessions_report(
    *,
    cfg: AppConfig | None = None,
    p11_report: Mapping[str, Any] | None = None,
    session_evidence: Sequence[Mapping[str, Any] | LiveCanarySessionEvidence] | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    source_p11 = dict(p11_report or _read_latest_json(cfg, "p11_live_canary_post_submit_evidence_review_report.json"))
    source_p11_sha256 = _sha_from(source_p11, "p11_live_canary_post_submit_evidence_review_sha256", "p11_summary_sha256", "report_sha256")
    p11_ready, p11_blockers = _p11_source_state(source_p11)

    if not session_evidence:
        unsafe_p11_wait_blockers = [
            reason for reason in p11_blockers
            if reason not in {
                "P12_SOURCE_P11_LIVE_CANARY_OUTCOME_REVIEW_MISSING",
                "P12_SOURCE_P11_OUTCOME_REVIEW_NOT_RECORDED",
                "P12_SOURCE_P11_EXTERNAL_SUBMIT_EVIDENCE_MISSING",
                "P12_SOURCE_P11_POST_SUBMIT_CHAIN_INCOMPLETE",
                "P12_SOURCE_P11_RECONCILIATION_NOT_CLEAN",
                "P12_SOURCE_P11_OUTCOME_REVIEW_NOT_COMPLETED",
                "P12_SOURCE_P11_POST_SUBMIT_RELOCK_NOT_CONFIRMED",
            }
        ]
        report = {
            "artifact_type": "p12_repeated_clean_live_canary_sessions",
            "p12_repeated_clean_live_canary_sessions_version": P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_VERSION,
            "status": STATUS_WAITING_REVIEW_ONLY if not unsafe_p11_wait_blockers else STATUS_BLOCKED_FAIL_CLOSED,
            "blocked": bool(unsafe_p11_wait_blockers),
            "fail_closed": bool(unsafe_p11_wait_blockers),
            "review_only": True,
            "source_p11_live_canary_post_submit_review_present": bool(source_p11),
            "source_p11_live_canary_post_submit_review_status": source_p11.get("status"),
            "source_p11_live_canary_post_submit_review_sha256": source_p11_sha256,
            "repeated_live_canary_session_evidence_present": False,
            "repeated_clean_live_canary_sessions_validated": False,
            "live_scaled_readiness_candidate_evidence_created": False,
            "live_scaled_readiness_allowed": False,
            "live_scaled_promotion_allowed": False,
            "live_scaled_execution_enabled": False,
            "next_required_action": "WAIT_FOR_MULTIPLE_SEPARATELY_APPROVED_CLEAN_LIVE_CANARY_SESSION_EVIDENCE",
            "block_reasons": sorted(dict.fromkeys(unsafe_p11_wait_blockers)),
            "created_at_utc": created_at_utc,
            **_disabled_payload(),
        }
        report["unsafe_truthy_execution_flags"] = truthy_execution_flags(report)
        if report["unsafe_truthy_execution_flags"]:
            report["status"] = STATUS_BLOCKED_FAIL_CLOSED
            report["blocked"] = True
            report["fail_closed"] = True
            report["block_reasons"] = sorted(dict.fromkeys(report["block_reasons"] + ["P12_UNSAFE_TRUTHY_EXECUTION_FLAGS_IN_WAITING_STATE"]))
        report["p12_repeated_clean_live_canary_sessions_id"] = stable_id("p12_repeated_clean_live_canary_sessions", report, 24)
        report["p12_repeated_clean_live_canary_sessions_sha256"] = sha256_json(report)
        return report

    repeated_validation = validate_repeated_clean_live_canary_sessions(session_evidence)
    blockers = sorted(dict.fromkeys(p11_blockers + list(repeated_validation["block_reasons"])))
    validated = bool(p11_ready and repeated_validation["repeated_clean_live_canary_sessions_valid"] and not blockers)
    status = STATUS_VALIDATED_REVIEW_ONLY if validated else STATUS_BLOCKED_FAIL_CLOSED
    report = {
        "artifact_type": "p12_repeated_clean_live_canary_sessions",
        "p12_repeated_clean_live_canary_sessions_version": P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_VERSION,
        "status": status,
        "blocked": status == STATUS_BLOCKED_FAIL_CLOSED,
        "fail_closed": status == STATUS_BLOCKED_FAIL_CLOSED,
        "review_only": True,
        "source_p11_live_canary_post_submit_review_present": bool(source_p11),
        "source_p11_live_canary_post_submit_review_status": source_p11.get("status"),
        "source_p11_live_canary_post_submit_review_sha256": source_p11_sha256,
        "repeated_live_canary_session_evidence_present": True,
        "repeated_clean_live_canary_sessions_validated": validated,
        "live_scaled_readiness_candidate_evidence_created": validated,
        "live_scaled_readiness_allowed": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_execution_enabled": False,
        "separate_live_scaled_approval_present": False,
        "next_required_action": "CREATE_LIVE_SCALED_READINESS_REVIEW_PACKET_WITH_SEPARATE_MANUAL_APPROVAL" if validated else "RESOLVE_P12_FAIL_CLOSED_BLOCKERS",
        "block_reasons": blockers,
        "repeated_clean_live_canary_sessions_validation": repeated_validation,
        "session_count": repeated_validation["session_count"],
        "clean_submitted_live_canary_session_count": repeated_validation["clean_submitted_session_count"],
        "reconciliation_mismatch_count": repeated_validation["reconciliation_mismatch_count"],
        "api_error_rate": repeated_validation["api_error_rate"],
        "rejection_rate": repeated_validation["rejection_rate"],
        "timeout_rate": repeated_validation["timeout_rate"],
        "rate_limit_rate": repeated_validation["rate_limit_rate"],
        "average_latency_ms": repeated_validation["average_latency_ms"],
        "average_abs_slippage_bps": repeated_validation["average_abs_slippage_bps"],
        "manual_override_count": repeated_validation["manual_override_count"],
        "incident_count": repeated_validation["incident_count"],
        "kill_switch_session_count": repeated_validation["kill_switch_session_count"],
        "created_at_utc": created_at_utc,
        **_disabled_payload(),
    }
    report["repeated_live_canary_session_validation_started"] = bool(session_evidence)
    report["live_scaled_readiness_candidate_evidence_created"] = validated
    report["live_scaled_readiness_may_begin"] = False
    report["live_scaled_readiness_allowed"] = False
    report["live_scaled_promotion_allowed"] = False
    report["live_scaled_execution_enabled"] = False
    report["unsafe_truthy_execution_flags"] = truthy_execution_flags(report)
    if report["unsafe_truthy_execution_flags"]:
        report["status"] = STATUS_BLOCKED_FAIL_CLOSED
        report["blocked"] = True
        report["fail_closed"] = True
        report["repeated_clean_live_canary_sessions_validated"] = False
        report["live_scaled_readiness_candidate_evidence_created"] = False
        report["block_reasons"] = sorted(dict.fromkeys(report["block_reasons"] + ["P12_UNSAFE_TRUTHY_EXECUTION_FLAGS_DETECTED"]))
    report["p12_repeated_clean_live_canary_sessions_id"] = stable_id("p12_repeated_clean_live_canary_sessions", report, 24)
    report["p12_repeated_clean_live_canary_sessions_sha256"] = sha256_json(report)
    return report


def build_p12_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    p11 = _valid_p11_complete_fixture()
    valid_sessions = build_required_live_canary_session_fixture_set()
    cases: dict[str, tuple[Mapping[str, Any], list[Mapping[str, Any] | LiveCanarySessionEvidence]]] = {
        "missing_min_session_count": (p11, valid_sessions[:4]),
        "missing_required_scenario": (p11, [s for s in valid_sessions if s.scenario != "live_timeout_reconciled"]),
        "reconciliation_mismatch": (p11, [{**valid_sessions[0].to_dict(), "reconciliation_mismatch_count": 1}] + valid_sessions[1:]),
        "slippage_above_threshold": (p11, [{**s.to_dict(), "slippage_bps": 50.0} if i < 3 else s for i, s in enumerate(valid_sessions)]),
        "latency_above_threshold": (p11, [{**s.to_dict(), "latency_ms": 10_000} if i < 3 else s for i, s in enumerate(valid_sessions)]),
        "api_error_rate_too_high": (p11, [{**s.to_dict(), "api_error_count": 3, "retry_count": 1} if i < 3 else s for i, s in enumerate(valid_sessions)]),
        "manual_override_nonzero": (p11, [{**valid_sessions[0].to_dict(), "manual_override_count": 1}] + valid_sessions[1:]),
        "incident_required": (p11, [{**valid_sessions[0].to_dict(), "incident_count": 1}] + valid_sessions[1:]),
        "duplicate_idempotency": (p11, [{**valid_sessions[0].to_dict(), "idempotency_key": "dupe"}, {**valid_sessions[1].to_dict(), "idempotency_key": "dupe"}] + [s for s in valid_sessions[2:]]),
        "secret_leak": (p11, [{**valid_sessions[0].to_dict(), "secret_value_logged": True}] + valid_sessions[1:]),
        "live_scaled_enabled_in_session": (p11, [{**valid_sessions[0].to_dict(), "live_scaled_execution_enabled": True}] + valid_sessions[1:]),
        "p11_not_clean": ({**p11, "live_canary_reconciliation_clean": False}, valid_sessions),
    }
    fixture_results: dict[str, Any] = {}
    for name, (p11_source, sessions) in cases.items():
        report = build_repeated_clean_live_canary_sessions_report(cfg=cfg, p11_report=p11_source, session_evidence=sessions)
        fixture_results[name] = {
            "fixture_name": name,
            "blocked_fail_closed": report["blocked"] is True and report["fail_closed"] is True,
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "repeated_clean_live_canary_sessions_validated": report.get("repeated_clean_live_canary_sessions_validated", False),
            "live_scaled_readiness_candidate_evidence_created": report.get("live_scaled_readiness_candidate_evidence_created", False),
            "live_scaled_readiness_allowed": report.get("live_scaled_readiness_allowed", False),
            "live_scaled_execution_enabled": report.get("live_scaled_execution_enabled", False),
        }
    payload = {
        "artifact_type": "p12_repeated_clean_live_canary_sessions_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in fixture_results.values()),
        "fixture_results": fixture_results,
        "live_scaled_readiness_allowed": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_execution_enabled": False,
        **_disabled_payload(),
    }
    payload["p12_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_repeated_clean_live_canary_sessions(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_repeated_clean_live_canary_sessions_report(cfg=cfg)
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p12_repeated_clean_live_canary_sessions")
    negative = build_p12_negative_fixture_results(cfg=cfg)
    registry_record = append_registry_record(
        registry_path(cfg, P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_REGISTRY_NAME),
        {
            "artifact_type": "p12_repeated_clean_live_canary_sessions_registry_record",
            "status": report["status"],
            "blocked": report["blocked"],
            "p12_repeated_clean_live_canary_sessions_id": report["p12_repeated_clean_live_canary_sessions_id"],
            "p12_repeated_clean_live_canary_sessions_sha256": report["p12_repeated_clean_live_canary_sessions_sha256"],
            "source_p11_live_canary_post_submit_review_sha256": report.get("source_p11_live_canary_post_submit_review_sha256"),
            "repeated_live_canary_session_evidence_present": report["repeated_live_canary_session_evidence_present"],
            "repeated_clean_live_canary_sessions_validated": report["repeated_clean_live_canary_sessions_validated"],
            "live_scaled_readiness_candidate_evidence_created": report["live_scaled_readiness_candidate_evidence_created"],
            "live_scaled_readiness_allowed": report.get("live_scaled_readiness_allowed", False),
            "live_scaled_promotion_allowed": report.get("live_scaled_promotion_allowed", False),
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
            "secret_value_accessed": report["secret_value_accessed"],
        },
        registry_name=P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_REGISTRY_NAME,
        id_field="p12_repeated_clean_live_canary_sessions_registry_record_id",
        hash_field="p12_repeated_clean_live_canary_sessions_registry_record_sha256",
        id_prefix="p12_repeated_clean_live_canary_sessions_registry_record",
    )
    report["p12_repeated_clean_live_canary_sessions_registry_record_id"] = registry_record[
        "p12_repeated_clean_live_canary_sessions_registry_record_id"
    ]
    report["p12_repeated_clean_live_canary_sessions_registry_record_sha256"] = registry_record[
        "p12_repeated_clean_live_canary_sessions_registry_record_sha256"
    ]
    report["p12_repeated_clean_live_canary_sessions_sha256"] = sha256_json(report)
    summary = {
        "artifact_type": "p12_repeated_clean_live_canary_sessions_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "repeated_live_canary_session_evidence_present": report["repeated_live_canary_session_evidence_present"],
        "repeated_clean_live_canary_sessions_validated": report["repeated_clean_live_canary_sessions_validated"],
        "live_scaled_readiness_candidate_evidence_created": report["live_scaled_readiness_candidate_evidence_created"],
        "live_scaled_readiness_allowed": report.get("live_scaled_readiness_allowed", False),
        "live_scaled_promotion_allowed": report.get("live_scaled_promotion_allowed", False),
        "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
        "secret_value_accessed": report["secret_value_accessed"],
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked_fail_closed"],
        "p12_repeated_clean_live_canary_sessions_id": report["p12_repeated_clean_live_canary_sessions_id"],
        "p12_repeated_clean_live_canary_sessions_sha256": report["p12_repeated_clean_live_canary_sessions_sha256"],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p12_summary_sha256"] = sha256_json(summary)
    for path in [
        latest / "p12_repeated_clean_live_canary_sessions_report.json",
        storage / "p12_repeated_clean_live_canary_sessions_report.json",
    ]:
        atomic_write_json(path, report)
    atomic_write_json(latest / "p12_repeated_clean_live_canary_sessions_negative_fixture_results.json", negative)
    atomic_write_json(storage / "p12_repeated_clean_live_canary_sessions_negative_fixture_results.json", negative)
    atomic_write_json(latest / "p12_repeated_clean_live_canary_sessions_registry_record.json", registry_record)
    atomic_write_json(storage / "p12_repeated_clean_live_canary_sessions_registry_record.json", registry_record)
    atomic_write_json(latest / "p12_repeated_clean_live_canary_sessions_summary.json", summary)
    atomic_write_json(storage / "p12_repeated_clean_live_canary_sessions_summary.json", summary)
    return report


__all__ = [
    "P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_VERSION",
    "STATUS_WAITING_REVIEW_ONLY",
    "STATUS_VALIDATED_REVIEW_ONLY",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "MIN_CLEAN_LIVE_CANARY_SESSION_COUNT",
    "REQUIRED_LIVE_CANARY_SESSION_SCENARIOS",
    "LiveCanarySessionEvidence",
    "build_required_live_canary_session_fixture_set",
    "validate_single_live_canary_session_evidence",
    "validate_repeated_clean_live_canary_sessions",
    "build_repeated_clean_live_canary_sessions_report",
    "build_p12_negative_fixture_results",
    "persist_repeated_clean_live_canary_sessions",
]
