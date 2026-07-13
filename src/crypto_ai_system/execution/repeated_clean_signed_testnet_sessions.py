from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P8_REPEATED_CLEAN_SIGNED_TESTNET_SESSIONS_VERSION = "p8_repeated_clean_signed_testnet_sessions_v1"
P8_REPEATED_CLEAN_SIGNED_TESTNET_SESSIONS_REGISTRY_NAME = "p8_repeated_clean_signed_testnet_sessions_registry"

STATUS_WAITING_REVIEW_ONLY = "P8_REPEATED_CLEAN_SIGNED_TESTNET_SESSIONS_WAITING_REVIEW_ONLY"
STATUS_VALIDATED_REVIEW_ONLY = "P8_REPEATED_CLEAN_SIGNED_TESTNET_SESSIONS_VALIDATED_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P8_REPEATED_CLEAN_SIGNED_TESTNET_SESSIONS_BLOCKED_FAIL_CLOSED"

MIN_CLEAN_SESSION_COUNT = 5
MAX_RECONCILIATION_MISMATCH_COUNT = 0
MAX_API_ERROR_RATE = 0.20
MAX_REJECTION_RATE = 0.35
MAX_TIMEOUT_RATE = 0.25
MAX_RATE_LIMIT_RATE = 0.25
MAX_AVG_LATENCY_MS = 2_500
MAX_ABS_AVG_SLIPPAGE_BPS = 15.0

REQUIRED_SESSION_SCENARIOS = {
    "long_filled",
    "short_filled",
    "partial_fill_reconciled",
    "rejected_reconciled",
    "cancel_reconciled",
    "timeout_reconciled",
    "api_error_retry_reconciled",
    "rate_limit_retry_reconciled",
    "kill_switch_blocked",
}

_ALLOWED_SCENARIOS = REQUIRED_SESSION_SCENARIOS | {"accepted_filled"}
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
    "signed_testnet_unlock_authority": False,
    "live_trading_allowed_by_this_module": False,
    "live_order_executed": False,
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


def _disabled_payload() -> dict[str, Any]:
    payload = default_execution_flag_state()
    payload.update(_ALWAYS_DISABLED_FLAGS)
    payload.update(
        {
            "phase10_session_validation_started": False,
            "live_canary_preparation_may_begin": False,
            "live_canary_preparation_allowed": False,
            "live_canary_approval_packet_created": False,
            "live_canary_order_allowed": False,
            "actual_live_order_submitted": False,
        }
    )
    return payload


@dataclass(frozen=True)
class SignedTestnetSessionEvidence:
    session_id: str
    scenario: str
    side: str = "BUY"
    symbol: str = "BTCUSDT"
    environment: str = "testnet"
    exchange: str = "binance_futures_testnet"
    final_status: str = "FILLED"
    p7_post_submit_evidence_intake_sha256: str = field(default_factory=lambda: "7" * 64)
    evidence_origin: str = "real_signed_testnet_external_runtime"
    session_evidence_source: str = "p7_real_post_submit_evidence"
    redacted_evidence_bundle_hash: str = field(default_factory=lambda: "8" * 64)
    p7_real_evidence_validated: bool = True
    fixture_evidence: bool = False
    mock_evidence: bool = False
    synthetic_evidence: bool = False
    post_submit_chain_complete: bool = True
    signed_testnet_session_closed_clean_review_only: bool = True
    actual_testnet_order_submitted: bool = True
    order_count: int = 1
    idempotency_key: str = "p8_session_idempotency_key"
    exchange_order_id: str = "testnet_order_session"
    reconciliation_mismatch_count: int = 0
    api_error_count: int = 0
    retry_count: int = 0
    rate_limit_retry_count: int = 0
    rejected: bool = False
    timeout_observed: bool = False
    cancel_boundary_exercised: bool = False
    manual_override_count: int = 0
    kill_switch_tested: bool = True
    kill_switch_blocked_submit: bool = False
    latency_ms: int = 500
    slippage_bps: float = 1.0
    fee_bps: float = 4.0
    secret_value_logged: bool = False
    api_key_value_logged: bool = False
    api_secret_value_logged: bool = False
    mainnet_key_scope_allowed: bool = False
    live_canary_preparation_allowed: bool = False
    signed_testnet_promotion_allowed: bool = False
    live_canary_execution_enabled: bool = False
    live_scaled_execution_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["signed_testnet_session_evidence_sha256"] = sha256_json(payload)
        return payload


def build_required_session_fixture_set() -> list[SignedTestnetSessionEvidence]:
    return [
        SignedTestnetSessionEvidence(session_id="p8_session_001", scenario="long_filled", side="BUY", final_status="FILLED", idempotency_key="p8_idem_001", exchange_order_id="testnet_order_001"),
        SignedTestnetSessionEvidence(session_id="p8_session_002", scenario="short_filled", side="SELL", final_status="FILLED", idempotency_key="p8_idem_002", exchange_order_id="testnet_order_002"),
        SignedTestnetSessionEvidence(session_id="p8_session_003", scenario="partial_fill_reconciled", side="BUY", final_status="PARTIALLY_FILLED", idempotency_key="p8_idem_003", exchange_order_id="testnet_order_003"),
        SignedTestnetSessionEvidence(session_id="p8_session_004", scenario="rejected_reconciled", side="SELL", final_status="REJECTED", rejected=True, idempotency_key="p8_idem_004", exchange_order_id="testnet_order_004"),
        SignedTestnetSessionEvidence(session_id="p8_session_005", scenario="cancel_reconciled", side="BUY", final_status="CANCELED", cancel_boundary_exercised=True, idempotency_key="p8_idem_005", exchange_order_id="testnet_order_005"),
        SignedTestnetSessionEvidence(session_id="p8_session_006", scenario="timeout_reconciled", side="SELL", final_status="EXPIRED", timeout_observed=True, idempotency_key="p8_idem_006", exchange_order_id="testnet_order_006"),
        SignedTestnetSessionEvidence(session_id="p8_session_007", scenario="api_error_retry_reconciled", side="BUY", final_status="FILLED", api_error_count=1, retry_count=1, idempotency_key="p8_idem_007", exchange_order_id="testnet_order_007"),
        SignedTestnetSessionEvidence(session_id="p8_session_008", scenario="rate_limit_retry_reconciled", side="SELL", final_status="FILLED", retry_count=1, rate_limit_retry_count=1, idempotency_key="p8_idem_008", exchange_order_id="testnet_order_008"),
        SignedTestnetSessionEvidence(
            session_id="p8_session_009",
            scenario="kill_switch_blocked",
            side="BUY",
            final_status="BLOCKED_BY_KILL_SWITCH",
            actual_testnet_order_submitted=False,
            post_submit_chain_complete=True,
            signed_testnet_session_closed_clean_review_only=True,
            order_count=0,
            exchange_order_id="kill_switch_blocked_no_order",
            idempotency_key="p8_idem_009_kill_switch",
            kill_switch_blocked_submit=True,
        ),
    ]


def validate_single_signed_testnet_session_evidence(evidence: Mapping[str, Any] | SignedTestnetSessionEvidence) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, SignedTestnetSessionEvidence) else dict(evidence or {})
    blockers: list[str] = []
    session_id = str(payload.get("session_id") or "")
    prefix = "P8_SESSION"
    if not _nonempty(session_id):
        blockers.append(f"{prefix}_ID_MISSING")
    if payload.get("environment") != "testnet":
        blockers.append(f"{prefix}_ENVIRONMENT_NOT_TESTNET")
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
    if not _nonempty(payload.get("p7_post_submit_evidence_intake_sha256")):
        blockers.append(f"{prefix}_SOURCE_P7_HASH_MISSING")
    if str(payload.get("evidence_origin") or "") != "real_signed_testnet_external_runtime":
        blockers.append(f"{prefix}_EVIDENCE_ORIGIN_NOT_REAL_SIGNED_TESTNET_EXTERNAL_RUNTIME")
    if str(payload.get("session_evidence_source") or "") != "p7_real_post_submit_evidence":
        blockers.append(f"{prefix}_EVIDENCE_SOURCE_NOT_P7_REAL_POST_SUBMIT")
    if not _nonempty(payload.get("redacted_evidence_bundle_hash")):
        blockers.append(f"{prefix}_REDACTED_EVIDENCE_BUNDLE_HASH_MISSING")
    if payload.get("p7_real_evidence_validated") is not True:
        blockers.append(f"{prefix}_P7_REAL_EVIDENCE_NOT_VALIDATED")
    for key, reason in (
        ("fixture_evidence", f"{prefix}_FIXTURE_EVIDENCE_NOT_ALLOWED_AS_REAL_SESSION"),
        ("mock_evidence", f"{prefix}_MOCK_EVIDENCE_NOT_ALLOWED_AS_REAL_SESSION"),
        ("synthetic_evidence", f"{prefix}_SYNTHETIC_EVIDENCE_NOT_ALLOWED_AS_REAL_SESSION"),
    ):
        if payload.get(key) is True:
            blockers.append(reason)
    kill_switch_session = scenario == "kill_switch_blocked"
    if not kill_switch_session:
        if payload.get("post_submit_chain_complete") is not True:
            blockers.append(f"{prefix}_POST_SUBMIT_CHAIN_INCOMPLETE")
        if payload.get("signed_testnet_session_closed_clean_review_only") is not True:
            blockers.append(f"{prefix}_NOT_CLOSED_CLEAN_REVIEW_ONLY")
        if payload.get("actual_testnet_order_submitted") is not True:
            blockers.append(f"{prefix}_ACTUAL_TESTNET_ORDER_NOT_SUBMITTED")
        if payload.get("order_count") != 1:
            blockers.append(f"{prefix}_ORDER_COUNT_NOT_ONE")
        if not _nonempty(payload.get("exchange_order_id")):
            blockers.append(f"{prefix}_EXCHANGE_ORDER_ID_MISSING")
    else:
        if payload.get("kill_switch_blocked_submit") is not True:
            blockers.append(f"{prefix}_KILL_SWITCH_BLOCKED_SUBMIT_NOT_TRUE")
        if payload.get("actual_testnet_order_submitted") is not False:
            blockers.append(f"{prefix}_KILL_SWITCH_SESSION_SUBMITTED_ORDER")
        if payload.get("order_count") not in {0, "0"}:
            blockers.append(f"{prefix}_KILL_SWITCH_SESSION_ORDER_COUNT_NOT_ZERO")
    if _as_int(payload.get("reconciliation_mismatch_count"), 999) != 0:
        blockers.append(f"{prefix}_RECONCILIATION_MISMATCH_COUNT_NONZERO")
    if _as_int(payload.get("api_error_count"), 0) < 0:
        blockers.append(f"{prefix}_API_ERROR_COUNT_INVALID")
    if _as_int(payload.get("retry_count"), 0) < 0 or _as_int(payload.get("retry_count"), 0) > 3:
        blockers.append(f"{prefix}_RETRY_COUNT_OUT_OF_POLICY")
    if _as_int(payload.get("rate_limit_retry_count"), 0) < 0 or _as_int(payload.get("rate_limit_retry_count"), 0) > 3:
        blockers.append(f"{prefix}_RATE_LIMIT_RETRY_COUNT_OUT_OF_POLICY")
    if _as_int(payload.get("manual_override_count"), 0) != 0:
        blockers.append(f"{prefix}_MANUAL_OVERRIDE_COUNT_NONZERO")
    if payload.get("kill_switch_tested") is not True:
        blockers.append(f"{prefix}_KILL_SWITCH_NOT_TESTED")
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
        ("mainnet_key_scope_allowed", f"{prefix}_MAINNET_KEY_SCOPE_ALLOWED"),
        ("live_canary_preparation_allowed", f"{prefix}_LIVE_CANARY_PREPARATION_ALLOWED"),
        ("signed_testnet_promotion_allowed", f"{prefix}_SIGNED_TESTNET_PROMOTION_ALLOWED"),
        ("live_canary_execution_enabled", f"{prefix}_LIVE_CANARY_EXECUTION_ENABLED"),
        ("live_scaled_execution_enabled", f"{prefix}_LIVE_SCALED_EXECUTION_ENABLED"),
    ):
        if payload.get(key) is True:
            blockers.append(reason)
    validation = {
        "single_session_evidence_valid": not blockers,
        "single_session_block_reasons": sorted(dict.fromkeys(blockers)),
        "session_id": session_id,
        "scenario": scenario,
        "side": side,
        "final_status": final_status,
        "is_kill_switch_session": kill_switch_session,
        "evidence_origin": payload.get("evidence_origin"),
        "session_evidence_source": payload.get("session_evidence_source"),
        "p7_real_evidence_validated": payload.get("p7_real_evidence_validated") is True,
        "actual_testnet_order_submitted": payload.get("actual_testnet_order_submitted") is True,
        "reconciliation_mismatch_count": _as_int(payload.get("reconciliation_mismatch_count"), 0),
        "api_error_count": _as_int(payload.get("api_error_count"), 0),
        "retry_count": _as_int(payload.get("retry_count"), 0),
        "rate_limit_retry_count": _as_int(payload.get("rate_limit_retry_count"), 0),
        "latency_ms": _as_int(payload.get("latency_ms"), 0),
        "slippage_bps": _as_float(payload.get("slippage_bps"), 0.0),
        "fee_bps": _as_float(payload.get("fee_bps"), 0.0),
    }
    validation["single_session_validation_sha256"] = sha256_json(validation)
    return validation


def validate_repeated_clean_signed_testnet_sessions(
    session_evidence: Sequence[Mapping[str, Any] | SignedTestnetSessionEvidence] | None,
    *,
    min_clean_session_count: int = MIN_CLEAN_SESSION_COUNT,
) -> dict[str, Any]:
    sessions = [item.to_dict() if isinstance(item, SignedTestnetSessionEvidence) else dict(item or {}) for item in list(session_evidence or [])]
    validations = [validate_single_signed_testnet_session_evidence(item) for item in sessions]
    blockers: list[str] = []
    if not sessions:
        blockers.append("P8_SIGNED_TESTNET_SESSION_EVIDENCE_MISSING")
    valid_session_count = sum(1 for validation in validations if validation["single_session_evidence_valid"])
    clean_submitted_session_count = sum(
        1
        for validation in validations
        if validation["single_session_evidence_valid"] and validation["actual_testnet_order_submitted"] is True
    )
    if clean_submitted_session_count < min_clean_session_count:
        blockers.append("P8_MIN_CLEAN_SIGNED_TESTNET_SESSION_COUNT_NOT_MET")
    session_ids = [str(item.get("session_id") or "") for item in sessions]
    if len([sid for sid in session_ids if sid]) != len(set([sid for sid in session_ids if sid])):
        blockers.append("P8_DUPLICATE_SESSION_ID_DETECTED")
    idempotency_keys = [str(item.get("idempotency_key") or "") for item in sessions if item.get("actual_testnet_order_submitted") is True]
    if len([key for key in idempotency_keys if key]) != len(set([key for key in idempotency_keys if key])):
        blockers.append("P8_DUPLICATE_IDEMPOTENCY_KEY_DETECTED")
    for index, validation in enumerate(validations):
        for reason in validation["single_session_block_reasons"]:
            blockers.append(f"P8_SESSION_{index}_{reason}")
    scenario_set = {validation["scenario"] for validation in validations if validation["single_session_evidence_valid"]}
    missing_scenarios = sorted(REQUIRED_SESSION_SCENARIOS - scenario_set)
    for scenario in missing_scenarios:
        blockers.append(f"P8_REQUIRED_SCENARIO_MISSING:{scenario}")
    side_set = {validation["side"] for validation in validations if validation["actual_testnet_order_submitted"] is True}
    if not {"BUY", "SELL"}.issubset(side_set):
        blockers.append("P8_LONG_SHORT_COVERAGE_MISSING")
    mismatch_count = sum(validation["reconciliation_mismatch_count"] for validation in validations)
    api_error_count = sum(validation["api_error_count"] for validation in validations)
    retry_count = sum(validation["retry_count"] for validation in validations)
    rate_limit_retry_count = sum(validation["rate_limit_retry_count"] for validation in validations)
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
        blockers.append("P8_RECONCILIATION_MISMATCH_COUNT_NONZERO")
    if api_error_rate > MAX_API_ERROR_RATE:
        blockers.append("P8_API_ERROR_RATE_ABOVE_THRESHOLD")
    if rejection_rate > MAX_REJECTION_RATE:
        blockers.append("P8_REJECTION_RATE_ABOVE_THRESHOLD")
    if timeout_rate > MAX_TIMEOUT_RATE:
        blockers.append("P8_TIMEOUT_RATE_ABOVE_THRESHOLD")
    if rate_limit_rate > MAX_RATE_LIMIT_RATE:
        blockers.append("P8_RATE_LIMIT_RATE_ABOVE_THRESHOLD")
    if avg_latency_ms > MAX_AVG_LATENCY_MS:
        blockers.append("P8_AVERAGE_LATENCY_ABOVE_THRESHOLD")
    if avg_abs_slippage_bps > MAX_ABS_AVG_SLIPPAGE_BPS:
        blockers.append("P8_AVERAGE_SLIPPAGE_ABOVE_THRESHOLD")
    if kill_switch_session_count < 1:
        blockers.append("P8_KILL_SWITCH_BLOCK_SESSION_MISSING")
    validation = {
        "repeated_clean_signed_testnet_sessions_valid": not blockers,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "required_min_clean_session_count": min_clean_session_count,
        "session_count": len(sessions),
        "valid_session_count": valid_session_count,
        "clean_submitted_session_count": clean_submitted_session_count,
        "required_session_scenarios": sorted(REQUIRED_SESSION_SCENARIOS),
        "observed_session_scenarios": sorted(scenario_set),
        "missing_session_scenarios": missing_scenarios,
        "long_short_coverage_observed": sorted(side_set),
        "reconciliation_mismatch_count": mismatch_count,
        "api_error_count": api_error_count,
        "retry_count": retry_count,
        "rate_limit_retry_count": rate_limit_retry_count,
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
        "single_session_validations": validations,
        "thresholds": {
            "max_reconciliation_mismatch_count": MAX_RECONCILIATION_MISMATCH_COUNT,
            "max_api_error_rate": MAX_API_ERROR_RATE,
            "max_rejection_rate": MAX_REJECTION_RATE,
            "max_timeout_rate": MAX_TIMEOUT_RATE,
            "max_rate_limit_rate": MAX_RATE_LIMIT_RATE,
            "max_average_latency_ms": MAX_AVG_LATENCY_MS,
            "max_average_abs_slippage_bps": MAX_ABS_AVG_SLIPPAGE_BPS,
        },
    }
    validation["repeated_clean_signed_testnet_sessions_validation_sha256"] = sha256_json(validation)
    return validation


def _source_p7_state(p7_report: Mapping[str, Any]) -> tuple[bool, bool, list[str]]:
    data = dict(p7_report or {})
    blockers: list[str] = []
    if not data:
        return False, False, ["P8_SOURCE_P7_REPORT_MISSING"]
    p7_waiting = data.get("status") == "P7_POST_SUBMIT_EVIDENCE_INTAKE_WAITING_FOR_EXTERNAL_SUBMIT_REVIEW_ONLY"
    p7_complete = data.get("post_submit_chain_complete") is True and data.get("signed_testnet_session_closed_clean_review_only") is True
    if not p7_waiting and not p7_complete:
        blockers.append("P8_SOURCE_P7_STATUS_NOT_WAITING_OR_COMPLETE")
    if data.get("secret_value_accessed") is True or data.get("secret_value_logged") is True:
        blockers.append("P8_SOURCE_P7_SECRET_LEAK_FLAG_TRUE")
    if data.get("signed_testnet_promotion_allowed") is True:
        blockers.append("P8_SOURCE_P7_PROMOTION_ALLOWED_TRUE")
    if data.get("live_canary_execution_enabled") is True or data.get("live_scaled_execution_enabled") is True:
        blockers.append("P8_SOURCE_P7_LIVE_EXECUTION_FLAG_TRUE")
    return p7_complete, p7_waiting, blockers


def build_repeated_clean_signed_testnet_sessions_report(
    *,
    cfg: AppConfig | None = None,
    p7_report: Mapping[str, Any] | None = None,
    session_evidence: Sequence[Mapping[str, Any] | SignedTestnetSessionEvidence] | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    source_p7 = dict(p7_report or _read_latest_json(cfg, "p7_post_submit_evidence_intake_report.json"))
    source_p7_hash = str(
        source_p7.get("p7_post_submit_evidence_intake_sha256")
        or source_p7.get("p7_summary_sha256")
        or (sha256_json(source_p7) if source_p7 else "")
    )
    p7_complete, p7_waiting, p7_blockers = _source_p7_state(source_p7)
    sessions = [item.to_dict() if isinstance(item, SignedTestnetSessionEvidence) else dict(item or {}) for item in list(session_evidence or [])]
    if not sessions:
        status = STATUS_WAITING_REVIEW_ONLY if p7_waiting and not p7_blockers else STATUS_BLOCKED_FAIL_CLOSED
        report = {
            "artifact_type": "p8_repeated_clean_signed_testnet_sessions",
            "p8_repeated_clean_signed_testnet_sessions_version": P8_REPEATED_CLEAN_SIGNED_TESTNET_SESSIONS_VERSION,
            "status": status,
            "blocked": status == STATUS_BLOCKED_FAIL_CLOSED,
            "fail_closed": status == STATUS_BLOCKED_FAIL_CLOSED,
            "review_only": True,
            "source_p7_post_submit_evidence_intake_present": bool(source_p7),
            "source_p7_post_submit_evidence_intake_status": source_p7.get("status"),
            "source_p7_post_submit_evidence_intake_sha256": source_p7_hash,
            "repeated_session_evidence_present": False,
            "repeated_clean_signed_testnet_sessions_validated": False,
            "live_canary_preparation_candidate_evidence_created": False,
            "next_required_action": "COLLECT_MINIMUM_REPEATED_CLEAN_SIGNED_TESTNET_SESSION_EVIDENCE_WITH_OPERATOR_APPROVAL",
            "block_reasons": sorted(dict.fromkeys(p7_blockers)),
            "created_at_utc": created_at_utc,
            **_disabled_payload(),
        }
    else:
        validation = validate_repeated_clean_signed_testnet_sessions(sessions)
        blockers = sorted(dict.fromkeys(p7_blockers + validation["block_reasons"]))
        valid = bool(not blockers and validation["repeated_clean_signed_testnet_sessions_valid"])
        status = STATUS_VALIDATED_REVIEW_ONLY if valid else STATUS_BLOCKED_FAIL_CLOSED
        report = {
            "artifact_type": "p8_repeated_clean_signed_testnet_sessions",
            "p8_repeated_clean_signed_testnet_sessions_version": P8_REPEATED_CLEAN_SIGNED_TESTNET_SESSIONS_VERSION,
            "status": status,
            "blocked": status == STATUS_BLOCKED_FAIL_CLOSED,
            "fail_closed": status == STATUS_BLOCKED_FAIL_CLOSED,
            "review_only": True,
            "source_p7_post_submit_evidence_intake_present": bool(source_p7),
            "source_p7_post_submit_evidence_intake_status": source_p7.get("status"),
            "source_p7_post_submit_evidence_intake_sha256": source_p7_hash,
            "repeated_session_evidence_present": True,
            "repeated_clean_signed_testnet_sessions_validated": valid,
            "repeated_clean_signed_testnet_sessions_validation": validation,
            "session_count": validation["session_count"],
            "clean_submitted_session_count": validation["clean_submitted_session_count"],
            "reconciliation_mismatch_count": validation["reconciliation_mismatch_count"],
            "api_error_rate": validation["api_error_rate"],
            "rejection_rate": validation["rejection_rate"],
            "timeout_rate": validation["timeout_rate"],
            "rate_limit_rate": validation["rate_limit_rate"],
            "average_latency_ms": validation["average_latency_ms"],
            "average_abs_slippage_bps": validation["average_abs_slippage_bps"],
            "kill_switch_session_count": validation["kill_switch_session_count"],
            "live_canary_preparation_candidate_evidence_created": valid,
            "live_canary_preparation_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
            "signed_testnet_promotion_allowed": False,
            "block_reasons": blockers,
            "created_at_utc": created_at_utc,
            **_disabled_payload(),
        }
    report["unsafe_truthy_execution_flags"] = truthy_execution_flags(report)
    if report["unsafe_truthy_execution_flags"]:
        report["status"] = STATUS_BLOCKED_FAIL_CLOSED
        report["blocked"] = True
        report["fail_closed"] = True
        report["block_reasons"] = sorted(dict.fromkeys(list(report.get("block_reasons", [])) + ["P8_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
        report["repeated_clean_signed_testnet_sessions_validated"] = False
        report["live_canary_preparation_candidate_evidence_created"] = False
    report["p8_repeated_clean_signed_testnet_sessions_id"] = stable_id("p8_repeated_clean_signed_testnet_sessions", report, 24)
    report["p8_repeated_clean_signed_testnet_sessions_sha256"] = sha256_json(report)
    return report


def _valid_p7_complete_fixture() -> dict[str, Any]:
    return {
        "status": "P7_POST_SUBMIT_EVIDENCE_INTAKE_RECONCILED_SESSION_CLOSED_REVIEW_ONLY",
        "p7_post_submit_evidence_intake_sha256": "7" * 64,
        "post_submit_chain_complete": True,
        "signed_testnet_session_closed_clean_review_only": True,
        "actual_testnet_order_submitted": True,
        "order_endpoint_called": True,
        "order_status_endpoint_called": True,
        "cancel_endpoint_called": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
    }


def build_p8_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    p7 = _valid_p7_complete_fixture()
    valid_sessions = build_required_session_fixture_set()
    cases: dict[str, list[Mapping[str, Any] | SignedTestnetSessionEvidence]] = {
        "missing_min_session_count": valid_sessions[:4],
        "missing_required_scenario": [s for s in valid_sessions if s.scenario != "timeout_reconciled"],
        "reconciliation_mismatch": [{**valid_sessions[0].to_dict(), "reconciliation_mismatch_count": 1}] + valid_sessions[1:],
        "secret_leak": [{**valid_sessions[0].to_dict(), "secret_value_logged": True}] + valid_sessions[1:],
        "duplicate_idempotency": [{**valid_sessions[0].to_dict(), "idempotency_key": "dupe"}, {**valid_sessions[1].to_dict(), "idempotency_key": "dupe"}] + [s for s in valid_sessions[2:]],
        "kill_switch_missing": [s for s in valid_sessions if s.scenario != "kill_switch_blocked"],
        "live_canary_enabled_in_session": [{**valid_sessions[0].to_dict(), "live_canary_execution_enabled": True}] + valid_sessions[1:],
        "fixture_or_synthetic_session_evidence": [{**valid_sessions[0].to_dict(), "fixture_evidence": True, "evidence_origin": "fixture"}] + valid_sessions[1:],
        "p7_real_evidence_not_validated": [{**valid_sessions[0].to_dict(), "p7_real_evidence_validated": False}] + valid_sessions[1:],
        "api_error_rate_too_high": [
            {**s.to_dict(), "api_error_count": 3, "retry_count": 1} if i < 3 else s
            for i, s in enumerate(valid_sessions)
        ],
    }
    fixture_results: dict[str, Any] = {}
    for name, sessions in cases.items():
        report = build_repeated_clean_signed_testnet_sessions_report(cfg=cfg, p7_report=p7, session_evidence=sessions)
        fixture_results[name] = {
            "fixture_name": name,
            "blocked_fail_closed": report["blocked"] is True and report["fail_closed"] is True,
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "repeated_clean_signed_testnet_sessions_validated": report.get("repeated_clean_signed_testnet_sessions_validated", False),
            "live_canary_preparation_allowed": report.get("live_canary_preparation_allowed", False),
            "live_canary_execution_enabled": report.get("live_canary_execution_enabled", False),
        }
    payload = {
        "artifact_type": "p8_repeated_clean_signed_testnet_sessions_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in fixture_results.values()),
        "fixture_results": fixture_results,
        "live_canary_preparation_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        **_disabled_payload(),
    }
    payload["p8_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_repeated_clean_signed_testnet_sessions(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_repeated_clean_signed_testnet_sessions_report(cfg=cfg)
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p8_repeated_clean_signed_testnet_sessions")
    negative = build_p8_negative_fixture_results(cfg=cfg)
    registry_record = append_registry_record(
        registry_path(cfg, P8_REPEATED_CLEAN_SIGNED_TESTNET_SESSIONS_REGISTRY_NAME),
        {
            "artifact_type": "p8_repeated_clean_signed_testnet_sessions_registry_record",
            "status": report["status"],
            "blocked": report["blocked"],
            "p8_repeated_clean_signed_testnet_sessions_id": report["p8_repeated_clean_signed_testnet_sessions_id"],
            "p8_repeated_clean_signed_testnet_sessions_sha256": report["p8_repeated_clean_signed_testnet_sessions_sha256"],
            "source_p7_post_submit_evidence_intake_sha256": report.get("source_p7_post_submit_evidence_intake_sha256"),
            "repeated_session_evidence_present": report["repeated_session_evidence_present"],
            "repeated_clean_signed_testnet_sessions_validated": report["repeated_clean_signed_testnet_sessions_validated"],
            "live_canary_preparation_candidate_evidence_created": report["live_canary_preparation_candidate_evidence_created"],
            "live_canary_preparation_allowed": report.get("live_canary_preparation_allowed", False),
            "live_canary_execution_enabled": report["live_canary_execution_enabled"],
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
            "secret_value_accessed": report["secret_value_accessed"],
        },
        registry_name=P8_REPEATED_CLEAN_SIGNED_TESTNET_SESSIONS_REGISTRY_NAME,
        id_field="p8_repeated_clean_signed_testnet_sessions_registry_record_id",
        hash_field="p8_repeated_clean_signed_testnet_sessions_registry_record_sha256",
        id_prefix="p8_repeated_clean_signed_testnet_sessions_registry_record",
    )
    report["p8_repeated_clean_signed_testnet_sessions_registry_record_id"] = registry_record[
        "p8_repeated_clean_signed_testnet_sessions_registry_record_id"
    ]
    report["p8_repeated_clean_signed_testnet_sessions_registry_record_sha256"] = registry_record[
        "p8_repeated_clean_signed_testnet_sessions_registry_record_sha256"
    ]
    report["p8_repeated_clean_signed_testnet_sessions_sha256"] = sha256_json(report)
    summary = {
        "artifact_type": "p8_repeated_clean_signed_testnet_sessions_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "repeated_session_evidence_present": report["repeated_session_evidence_present"],
        "repeated_clean_signed_testnet_sessions_validated": report["repeated_clean_signed_testnet_sessions_validated"],
        "live_canary_preparation_candidate_evidence_created": report["live_canary_preparation_candidate_evidence_created"],
        "live_canary_preparation_allowed": report.get("live_canary_preparation_allowed", False),
        "live_canary_execution_enabled": report["live_canary_execution_enabled"],
        "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
        "secret_value_accessed": report["secret_value_accessed"],
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked_fail_closed"],
        "p8_repeated_clean_signed_testnet_sessions_id": report["p8_repeated_clean_signed_testnet_sessions_id"],
        "p8_repeated_clean_signed_testnet_sessions_sha256": report["p8_repeated_clean_signed_testnet_sessions_sha256"],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p8_summary_sha256"] = sha256_json(summary)
    for path in [
        latest / "p8_repeated_clean_signed_testnet_sessions_report.json",
        storage / "p8_repeated_clean_signed_testnet_sessions_report.json",
    ]:
        atomic_write_json(path, report)
    atomic_write_json(latest / "p8_repeated_clean_signed_testnet_sessions_negative_fixture_results.json", negative)
    atomic_write_json(storage / "p8_repeated_clean_signed_testnet_sessions_negative_fixture_results.json", negative)
    atomic_write_json(latest / "p8_repeated_clean_signed_testnet_sessions_registry_record.json", registry_record)
    atomic_write_json(storage / "p8_repeated_clean_signed_testnet_sessions_registry_record.json", registry_record)
    atomic_write_json(latest / "p8_repeated_clean_signed_testnet_sessions_summary.json", summary)
    atomic_write_json(storage / "p8_repeated_clean_signed_testnet_sessions_summary.json", summary)
    return report


__all__ = [
    "P8_REPEATED_CLEAN_SIGNED_TESTNET_SESSIONS_VERSION",
    "STATUS_WAITING_REVIEW_ONLY",
    "STATUS_VALIDATED_REVIEW_ONLY",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "MIN_CLEAN_SESSION_COUNT",
    "REQUIRED_SESSION_SCENARIOS",
    "SignedTestnetSessionEvidence",
    "build_required_session_fixture_set",
    "validate_single_signed_testnet_session_evidence",
    "validate_repeated_clean_signed_testnet_sessions",
    "build_repeated_clean_signed_testnet_sessions_report",
    "build_p8_negative_fixture_results",
    "persist_repeated_clean_signed_testnet_sessions",
]
