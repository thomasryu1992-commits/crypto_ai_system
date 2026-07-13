from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P16_LIMITED_LIVE_SCALED_LOOP_DRY_RUN_VERSION = "p16_limited_live_scaled_loop_dry_run_harness_v1"
P16_LIMITED_LIVE_SCALED_LOOP_DRY_RUN_REGISTRY_NAME = "p16_limited_live_scaled_loop_dry_run_harness_registry"

STATUS_WAITING_REVIEW_ONLY = "P16_LIMITED_LIVE_SCALED_LOOP_DRY_RUN_WAITING_REVIEW_ONLY"
STATUS_VALID_REVIEW_ONLY_NO_EXECUTION = "P16_LIMITED_LIVE_SCALED_LOOP_DRY_RUN_VALID_REVIEW_ONLY_NO_EXECUTION"
STATUS_BLOCKED_FAIL_CLOSED = "P16_LIMITED_LIVE_SCALED_LOOP_DRY_RUN_BLOCKED_FAIL_CLOSED"

MIN_DRY_RUN_TICKS = 3
DRY_RUN_STAGE = "limited_live_scaled"
DRY_RUN_SYMBOL = "BTCUSDT"

_REQUIRED_TICK_TRUE_FLAGS = {
    "dry_run_only",
    "scheduler_tick_started_review_only",
    "current_stage_policy_loaded",
    "fresh_market_data_loaded",
    "source_qa_passed",
    "data_snapshot_created",
    "feature_lineage_created",
    "research_signal_v2_created",
    "signal_qa_passed",
    "trading_decision_created",
    "hot_path_preorder_risk_gate_passed",
    "hot_path_preorder_risk_gate_fresh",
    "order_intent_after_risk_gate",
    "hard_caps_checked",
    "hard_caps_passed",
    "duplicate_submit_lock_engaged",
    "idempotency_key_required",
    "would_submit_evidence_created",
    "would_submit_only",
    "post_submit_relock_required",
    "post_submit_relock_confirmed",
    "status_polling_required",
    "reconciliation_required",
    "outcome_feedback_required",
    "daily_report_required",
    "incident_report_required",
    "monitoring_alerting_required",
    "rollback_full_shutdown_available",
    "canonical_id_chain_present_review_only",
    "all_orders_must_reconcile",
    "kill_switch_global_checked",
    "kill_switch_manual_checked",
    "kill_switch_daily_loss_checked",
    "kill_switch_consecutive_loss_checked",
    "kill_switch_api_error_checked",
    "kill_switch_reconciliation_mismatch_checked",
    "kill_switch_stale_data_checked",
    "kill_switch_missing_required_source_checked",
    "kill_switch_safe",
}

_UNSAFE_TICK_FLAGS = {
    "runtime_scheduler_enabled",
    "runtime_loop_started",
    "live_scaled_execution_enabled",
    "live_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "actual_live_order_submitted",
    "actual_live_order_submitted_by_this_module",
    "live_order_endpoint_called",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "secret_value_accessed",
    "secret_value_logged",
    "api_key_value_logged",
    "api_secret_value_logged",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "auto_promotion_allowed",
    "withdrawal_permission_allowed",
    "transfer_permission_allowed",
    "admin_permission_allowed",
}

_ALWAYS_DISABLED_FLAGS = {
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
    "mainnet_key_scope_allowed": False,
    "withdrawal_permission_allowed": False,
    "transfer_permission_allowed": False,
    "admin_permission_allowed": False,
    "live_canary_execution_enabled": False,
    "live_scaled_execution_enabled": False,
    "live_execution_unlock_authority": False,
    "live_trading_allowed_by_this_module": False,
    "live_order_submission_allowed": False,
    "live_order_submission_allowed_by_this_module": False,
    "live_scaled_readiness_allowed": False,
    "live_scaled_promotion_allowed": False,
    "live_scaled_promotion_allowed_by_this_module": False,
    "live_scaled_auto_trading_allowed": False,
    "limited_live_scaled_auto_trading_allowed": False,
    "limited_live_scaled_auto_trading_allowed_by_this_module": False,
    "live_scaled_runtime_enablement_allowed": False,
    "live_scaled_runtime_enablement_performed": False,
    "runtime_scheduler_enabled": False,
    "runtime_loop_started": False,
    "actual_live_order_submitted": False,
    "actual_live_order_submitted_by_this_module": False,
    "live_order_endpoint_called": False,
    "order_endpoint_called": False,
    "order_status_endpoint_called": False,
    "cancel_endpoint_called": False,
    "http_request_sent": False,
    "signature_created": False,
    "signed_request_created": False,
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
            "p16_limited_live_scaled_loop_dry_run_harness_valid_review_only": False,
            "p16_scheduler_tick_simulation_valid_review_only": False,
            "p16_would_submit_evidence_chain_valid_review_only": False,
            "p16_reconciliation_report_chain_valid_review_only": False,
            "p16_daily_incident_reporting_valid_review_only": False,
        }
    )
    return payload


@dataclass(frozen=True)
class LimitedLiveScaledDryRunTick:
    tick_index: int
    source_p15_limited_live_scaled_runtime_enablement_boundary_sha256: str = field(default_factory=lambda: "f" * 64)
    stage: str = DRY_RUN_STAGE
    symbol: str = DRY_RUN_SYMBOL
    side: str = "BUY"
    dry_run_only: bool = True
    scheduler_tick_started_review_only: bool = True
    scheduler_interval_seconds: int = 60
    current_stage_policy_loaded: bool = True
    fresh_market_data_loaded: bool = True
    source_qa_passed: bool = True
    data_snapshot_created: bool = True
    data_snapshot_id: str = field(default_factory=lambda: stable_id("p16_data_snapshot", {"kind": "dry_run"}, 12))
    feature_lineage_created: bool = True
    feature_snapshot_id: str = field(default_factory=lambda: stable_id("p16_feature_snapshot", {"kind": "dry_run"}, 12))
    research_signal_v2_created: bool = True
    research_signal_id: str = field(default_factory=lambda: stable_id("p16_research_signal", {"kind": "dry_run"}, 12))
    signal_qa_passed: bool = True
    trading_decision_created: bool = True
    decision_id: str = field(default_factory=lambda: stable_id("p16_decision", {"kind": "dry_run"}, 12))
    hot_path_preorder_risk_gate_passed: bool = True
    hot_path_preorder_risk_gate_fresh: bool = True
    risk_gate_id: str = field(default_factory=lambda: stable_id("p16_risk_gate", {"kind": "dry_run"}, 12))
    order_intent_after_risk_gate: bool = True
    order_intent_id: str = field(default_factory=lambda: stable_id("p16_order_intent", {"kind": "dry_run"}, 12))
    hard_caps_checked: bool = True
    hard_caps_passed: bool = True
    duplicate_submit_lock_engaged: bool = True
    idempotency_key_required: bool = True
    idempotency_key: str = field(default_factory=lambda: stable_id("p16_idempotency", {"kind": "dry_run"}, 16))
    idempotency_key_seen_before: bool = False
    would_submit_evidence_created: bool = True
    would_submit_only: bool = True
    would_submit_evidence_id: str = field(default_factory=lambda: stable_id("p16_would_submit", {"kind": "dry_run"}, 12))
    post_submit_relock_required: bool = True
    post_submit_relock_confirmed: bool = True
    status_polling_required: bool = True
    reconciliation_required: bool = True
    reconciliation_id: str = field(default_factory=lambda: stable_id("p16_reconciliation", {"kind": "dry_run"}, 12))
    outcome_feedback_required: bool = True
    outcome_id: str = field(default_factory=lambda: stable_id("p16_outcome", {"kind": "dry_run"}, 12))
    daily_report_required: bool = True
    incident_report_required: bool = True
    monitoring_alerting_required: bool = True
    rollback_full_shutdown_available: bool = True
    canonical_id_chain_present_review_only: bool = True
    all_orders_must_reconcile: bool = True
    kill_switch_global_checked: bool = True
    kill_switch_manual_checked: bool = True
    kill_switch_daily_loss_checked: bool = True
    kill_switch_consecutive_loss_checked: bool = True
    kill_switch_api_error_checked: bool = True
    kill_switch_reconciliation_mismatch_checked: bool = True
    kill_switch_stale_data_checked: bool = True
    kill_switch_missing_required_source_checked: bool = True
    kill_switch_safe: bool = True
    simulated_order_blocked_before_http: bool = True
    runtime_scheduler_enabled: bool = False
    runtime_loop_started: bool = False
    live_scaled_execution_enabled: bool = False
    live_order_submission_allowed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    actual_live_order_submitted: bool = False
    actual_live_order_submitted_by_this_module: bool = False
    live_order_endpoint_called: bool = False
    order_endpoint_called: bool = False
    order_status_endpoint_called: bool = False
    cancel_endpoint_called: bool = False
    http_request_sent: bool = False
    signature_created: bool = False
    signed_request_created: bool = False
    secret_value_accessed: bool = False
    secret_value_logged: bool = False
    api_key_value_logged: bool = False
    api_secret_value_logged: bool = False
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    auto_promotion_allowed: bool = False
    withdrawal_permission_allowed: bool = False
    transfer_permission_allowed: bool = False
    admin_permission_allowed: bool = False
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tick_id"] = stable_id("p16_dry_run_tick", payload, 18)
        payload["p16_dry_run_tick_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class LimitedLiveScaledDryRunDailyReport:
    source_p15_limited_live_scaled_runtime_enablement_boundary_sha256: str = field(default_factory=lambda: "f" * 64)
    dry_run_daily_report_id: str = "p16_limited_live_scaled_dry_run_daily_report_review_only"
    dry_run_only: bool = True
    scheduler_tick_count: int = MIN_DRY_RUN_TICKS
    all_ticks_reconciled: bool = True
    all_would_submit_only: bool = True
    daily_order_count_observed: int = 0
    daily_loss_observed_usdt: float = 0.0
    api_error_count: int = 0
    reconciliation_mismatch_count: int = 0
    incident_count: int = 0
    critical_alert_count: int = 0
    daily_report_created: bool = True
    incident_report_created: bool = True
    live_order_submission_allowed: bool = False
    live_scaled_execution_enabled: bool = False
    runtime_scheduler_enabled: bool = False
    runtime_loop_started: bool = False
    secret_value_accessed: bool = False
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p16_dry_run_daily_report_sha256"] = sha256_json(payload)
        return payload


def build_review_only_dry_run_ticks(p15_report: Mapping[str, Any], *, tick_count: int = MIN_DRY_RUN_TICKS) -> list[dict[str, Any]]:
    p15_sha = _sha_from(p15_report, "p15_limited_live_scaled_runtime_enablement_boundary_sha256") or "f" * 64
    ticks: list[dict[str, Any]] = []
    for idx in range(tick_count):
        side = "BUY" if idx % 2 == 0 else "SELL"
        tick = LimitedLiveScaledDryRunTick(
            tick_index=idx,
            side=side,
            source_p15_limited_live_scaled_runtime_enablement_boundary_sha256=p15_sha,
            data_snapshot_id=stable_id("p16_data_snapshot", {"idx": idx, "source": p15_sha}, 12),
            feature_snapshot_id=stable_id("p16_feature_snapshot", {"idx": idx, "source": p15_sha}, 12),
            research_signal_id=stable_id("p16_research_signal", {"idx": idx, "source": p15_sha}, 12),
            decision_id=stable_id("p16_decision", {"idx": idx, "source": p15_sha}, 12),
            risk_gate_id=stable_id("p16_risk_gate", {"idx": idx, "source": p15_sha}, 12),
            order_intent_id=stable_id("p16_order_intent", {"idx": idx, "source": p15_sha}, 12),
            idempotency_key=stable_id("p16_idempotency", {"idx": idx, "source": p15_sha}, 16),
            would_submit_evidence_id=stable_id("p16_would_submit", {"idx": idx, "source": p15_sha}, 12),
            reconciliation_id=stable_id("p16_reconciliation", {"idx": idx, "source": p15_sha}, 12),
            outcome_id=stable_id("p16_outcome", {"idx": idx, "source": p15_sha}, 12),
        )
        ticks.append(tick.to_dict())
    return ticks


def build_review_only_dry_run_daily_report(
    p15_report: Mapping[str, Any], ticks: Sequence[Mapping[str, Any]] | None = None
) -> dict[str, Any]:
    p15_sha = _sha_from(p15_report, "p15_limited_live_scaled_runtime_enablement_boundary_sha256") or "f" * 64
    tick_count = len(ticks or []) or MIN_DRY_RUN_TICKS
    return LimitedLiveScaledDryRunDailyReport(
        source_p15_limited_live_scaled_runtime_enablement_boundary_sha256=p15_sha,
        scheduler_tick_count=tick_count,
    ).to_dict()


def _validate_p15_source(p15_report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(p15_report or {})
    waiting_reasons: list[str] = []
    block_reasons: list[str] = []
    if not data:
        waiting_reasons.append("P16_SOURCE_P15_REPORT_MISSING")
    elif not _bool(data.get("p15_limited_live_scaled_runtime_boundary_valid_review_only")):
        waiting_reasons.append("P16_SOURCE_P15_RUNTIME_BOUNDARY_NOT_VALID")
    else:
        if not _bool(data.get("runtime_stage_policy_valid_review_only")):
            block_reasons.append("P16_SOURCE_P15_STAGE_POLICY_NOT_VALID")
        if not _bool(data.get("runtime_loop_controls_valid_review_only")):
            block_reasons.append("P16_SOURCE_P15_LOOP_CONTROLS_NOT_VALID")
        if not _bool(data.get("operator_runtime_enablement_request_valid_review_only")):
            block_reasons.append("P16_SOURCE_P15_OPERATOR_REQUEST_NOT_VALID")
    for field_name in _UNSAFE_TICK_FLAGS | {
        "limited_live_scaled_auto_trading_allowed",
        "live_scaled_runtime_enablement_allowed",
        "live_scaled_runtime_enablement_performed",
    }:
        if _bool(data.get(field_name)):
            block_reasons.append(f"P16_SOURCE_P15_UNSAFE_FLAG_TRUE:{field_name}")
    return {
        "p15_source_present": bool(data),
        "p15_source_waiting": bool(waiting_reasons),
        "p15_source_blocked": bool(block_reasons),
        "p15_source_waiting_reasons": sorted(set(waiting_reasons)),
        "p15_source_block_reasons": sorted(set(block_reasons)),
        "p15_runtime_boundary_valid_review_only": _bool(data.get("p15_limited_live_scaled_runtime_boundary_valid_review_only")),
        "p15_runtime_stage_policy_valid_review_only": _bool(data.get("runtime_stage_policy_valid_review_only")),
        "p15_runtime_loop_controls_valid_review_only": _bool(data.get("runtime_loop_controls_valid_review_only")),
        "p15_operator_runtime_enablement_request_valid_review_only": _bool(data.get("operator_runtime_enablement_request_valid_review_only")),
        "p15_report_sha256": _sha_from(data, "p15_limited_live_scaled_runtime_enablement_boundary_sha256"),
    }


def _validate_ticks(ticks: Sequence[Mapping[str, Any]], p15_validation: Mapping[str, Any]) -> dict[str, Any]:
    tick_list = [dict(tick or {}) for tick in ticks or []]
    waiting_reasons: list[str] = []
    block_reasons: list[str] = []
    if not tick_list:
        waiting_reasons.append("P16_DRY_RUN_TICKS_MISSING")
    elif len(tick_list) < MIN_DRY_RUN_TICKS:
        block_reasons.append("P16_DRY_RUN_TICK_COUNT_BELOW_MINIMUM")
    seen_tick_ids: set[str] = set()
    seen_idempotency: set[str] = set()
    p15_sha = p15_validation.get("p15_report_sha256")
    for index, tick in enumerate(tick_list):
        prefix = f"P16_TICK_{index}"
        if str(tick.get("stage") or "") != DRY_RUN_STAGE:
            block_reasons.append(f"{prefix}_STAGE_INVALID")
        if str(tick.get("symbol") or "") != DRY_RUN_SYMBOL:
            block_reasons.append(f"{prefix}_SYMBOL_NOT_BTCUSDT")
        if p15_sha and tick.get("source_p15_limited_live_scaled_runtime_enablement_boundary_sha256") != p15_sha:
            block_reasons.append(f"{prefix}_P15_HASH_MISMATCH")
        tick_id = str(tick.get("tick_id") or "")
        if not _nonempty(tick_id):
            block_reasons.append(f"{prefix}_TICK_ID_MISSING")
        elif tick_id in seen_tick_ids:
            block_reasons.append(f"{prefix}_DUPLICATE_TICK_ID")
        seen_tick_ids.add(tick_id)
        idem = str(tick.get("idempotency_key") or "")
        if not _nonempty(idem):
            block_reasons.append(f"{prefix}_IDEMPOTENCY_KEY_MISSING")
        elif idem in seen_idempotency or _bool(tick.get("idempotency_key_seen_before")):
            block_reasons.append(f"{prefix}_DUPLICATE_IDEMPOTENCY_KEY")
        seen_idempotency.add(idem)
        for field_name in sorted(_REQUIRED_TICK_TRUE_FLAGS):
            if not _bool(tick.get(field_name)):
                block_reasons.append(f"{prefix}_REQUIRED_FIELD_FALSE:{field_name}")
        required_ids = [
            "data_snapshot_id",
            "feature_snapshot_id",
            "research_signal_id",
            "decision_id",
            "risk_gate_id",
            "order_intent_id",
            "would_submit_evidence_id",
            "reconciliation_id",
            "outcome_id",
        ]
        for field_name in required_ids:
            if not _nonempty(tick.get(field_name)):
                block_reasons.append(f"{prefix}_REQUIRED_ID_MISSING:{field_name}")
        for field_name in sorted(_UNSAFE_TICK_FLAGS):
            if _bool(tick.get(field_name)):
                block_reasons.append(f"{prefix}_UNSAFE_FLAG_TRUE:{field_name}")
    return {
        "dry_run_tick_count": len(tick_list),
        "dry_run_ticks_present": bool(tick_list),
        "dry_run_ticks_waiting": bool(waiting_reasons),
        "dry_run_ticks_blocked": bool(block_reasons),
        "dry_run_tick_waiting_reasons": sorted(set(waiting_reasons)),
        "dry_run_tick_block_reasons": sorted(set(block_reasons)),
        "unique_idempotency_key_count": len(seen_idempotency),
        "p16_scheduler_tick_simulation_valid_review_only": bool(tick_list) and not block_reasons,
        "p16_would_submit_evidence_chain_valid_review_only": bool(tick_list) and not block_reasons,
        "tick_hashes": [str(tick.get("p16_dry_run_tick_sha256")) for tick in tick_list if tick.get("p16_dry_run_tick_sha256")],
    }


def _validate_daily_report(report: Mapping[str, Any], ticks_validation: Mapping[str, Any], p15_validation: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(report or {})
    waiting_reasons: list[str] = []
    block_reasons: list[str] = []
    if not data:
        waiting_reasons.append("P16_DRY_RUN_DAILY_REPORT_MISSING")
    else:
        p15_sha = p15_validation.get("p15_report_sha256")
        if p15_sha and data.get("source_p15_limited_live_scaled_runtime_enablement_boundary_sha256") != p15_sha:
            block_reasons.append("P16_DAILY_REPORT_P15_HASH_MISMATCH")
        if _as_int(data.get("scheduler_tick_count"), -1) != int(ticks_validation.get("dry_run_tick_count") or 0):
            block_reasons.append("P16_DAILY_REPORT_TICK_COUNT_MISMATCH")
        required_true = [
            "dry_run_only",
            "all_ticks_reconciled",
            "all_would_submit_only",
            "daily_report_created",
            "incident_report_created",
        ]
        for field_name in required_true:
            if not _bool(data.get(field_name)):
                block_reasons.append(f"P16_DAILY_REPORT_REQUIRED_FIELD_FALSE:{field_name}")
        zero_fields = [
            "daily_order_count_observed",
            "daily_loss_observed_usdt",
            "api_error_count",
            "reconciliation_mismatch_count",
            "incident_count",
            "critical_alert_count",
        ]
        for field_name in zero_fields:
            if float(data.get(field_name) or 0) != 0.0:
                block_reasons.append(f"P16_DAILY_REPORT_NONZERO_FIELD:{field_name}")
        unsafe_fields = [
            "live_order_submission_allowed",
            "live_scaled_execution_enabled",
            "runtime_scheduler_enabled",
            "runtime_loop_started",
            "secret_value_accessed",
        ]
        for field_name in unsafe_fields:
            if _bool(data.get(field_name)):
                block_reasons.append(f"P16_DAILY_REPORT_UNSAFE_FLAG_TRUE:{field_name}")
    return {
        "dry_run_daily_report_present": bool(data),
        "dry_run_daily_report_waiting": bool(waiting_reasons),
        "dry_run_daily_report_blocked": bool(block_reasons),
        "dry_run_daily_report_waiting_reasons": sorted(set(waiting_reasons)),
        "dry_run_daily_report_block_reasons": sorted(set(block_reasons)),
        "dry_run_daily_report_sha256": _sha_from(data, "p16_dry_run_daily_report_sha256"),
        "p16_reconciliation_report_chain_valid_review_only": bool(data) and not block_reasons,
        "p16_daily_incident_reporting_valid_review_only": bool(data) and not block_reasons,
    }


def build_limited_live_scaled_loop_dry_run_harness_report(
    *,
    cfg: AppConfig | None = None,
    p15_report: Mapping[str, Any] | None = None,
    dry_run_ticks: Sequence[Mapping[str, Any]] | None = None,
    dry_run_daily_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if cfg is not None:
        if p15_report is None:
            p15_report = _read_latest_json(cfg, "p15_limited_live_scaled_runtime_enablement_boundary_report.json")
        if dry_run_ticks is None:
            ticks_payload = read_json(_latest_dir(cfg) / "p16_limited_live_scaled_dry_run_ticks.json", default=[])
            dry_run_ticks = ticks_payload if isinstance(ticks_payload, list) else []
        if dry_run_daily_report is None:
            dry_run_daily_report = _read_latest_json(cfg, "p16_limited_live_scaled_dry_run_daily_report.json")

    p15_validation = _validate_p15_source(p15_report or {})
    tick_validation = _validate_ticks(list(dry_run_ticks or []), p15_validation)
    daily_validation = _validate_daily_report(dry_run_daily_report or {}, tick_validation, p15_validation)

    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    block_reasons.extend(p15_validation["p15_source_block_reasons"])
    block_reasons.extend(tick_validation["dry_run_tick_block_reasons"])
    block_reasons.extend(daily_validation["dry_run_daily_report_block_reasons"])
    waiting_reasons.extend(p15_validation["p15_source_waiting_reasons"])
    waiting_reasons.extend(tick_validation["dry_run_tick_waiting_reasons"])
    waiting_reasons.extend(daily_validation["dry_run_daily_report_waiting_reasons"])

    blocked = bool(block_reasons)
    waiting = bool(waiting_reasons) and not blocked
    valid = not blocked and not waiting
    status = STATUS_BLOCKED_FAIL_CLOSED if blocked else (STATUS_WAITING_REVIEW_ONLY if waiting else STATUS_VALID_REVIEW_ONLY_NO_EXECUTION)
    report_id_source = {
        "status": status,
        "p15": p15_validation.get("p15_report_sha256"),
        "ticks": tick_validation.get("tick_hashes"),
        "daily": daily_validation.get("dry_run_daily_report_sha256"),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
    }
    disabled = _disabled_payload()
    report: dict[str, Any] = {
        "version": P16_LIMITED_LIVE_SCALED_LOOP_DRY_RUN_VERSION,
        "p16_limited_live_scaled_loop_dry_run_harness_id": stable_id("p16_limited_live_scaled_loop_dry_run_harness", report_id_source, 24),
        "status": status,
        "review_only": True,
        "dry_run_only": True,
        "blocked": blocked,
        "waiting": waiting,
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "p15_source_validation": p15_validation,
        "dry_run_tick_validation": tick_validation,
        "dry_run_daily_report_validation": daily_validation,
        "source_p15_limited_live_scaled_runtime_enablement_boundary_sha256": p15_validation.get("p15_report_sha256"),
        "dry_run_tick_count": tick_validation["dry_run_tick_count"],
        "p16_limited_live_scaled_loop_dry_run_harness_valid_review_only": valid,
        "p16_scheduler_tick_simulation_valid_review_only": valid and tick_validation["p16_scheduler_tick_simulation_valid_review_only"],
        "p16_would_submit_evidence_chain_valid_review_only": valid and tick_validation["p16_would_submit_evidence_chain_valid_review_only"],
        "p16_reconciliation_report_chain_valid_review_only": valid and daily_validation["p16_reconciliation_report_chain_valid_review_only"],
        "p16_daily_incident_reporting_valid_review_only": valid and daily_validation["p16_daily_incident_reporting_valid_review_only"],
        "scheduler_tick_simulation_performed_review_only": valid,
        "would_submit_evidence_created_review_only": valid,
        "post_submit_relock_simulated_review_only": valid,
        "reconciliation_required_per_tick": True,
        "daily_report_required": True,
        "incident_report_required": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "actual_live_order_submitted": False,
        "actual_live_order_submitted_by_this_module": False,
        "live_order_endpoint_called": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "withdrawal_permission_allowed": False,
        "transfer_permission_allowed": False,
        "admin_permission_allowed": False,
        "review_notes": [
            "p16_simulates_limited_live_scaled_loop_without_enabling_scheduler",
            "p16_creates_would_submit_evidence_only_and_blocks_before_http",
            "p16_requires_reconciliation_daily_and_incident_reports_for_every_dry_run_cycle",
        ],
        **disabled,
    }
    # Preserve P16 review booleans after merging disabled defaults.
    report["p16_limited_live_scaled_loop_dry_run_harness_valid_review_only"] = valid
    report["p16_scheduler_tick_simulation_valid_review_only"] = valid and tick_validation["p16_scheduler_tick_simulation_valid_review_only"]
    report["p16_would_submit_evidence_chain_valid_review_only"] = valid and tick_validation["p16_would_submit_evidence_chain_valid_review_only"]
    report["p16_reconciliation_report_chain_valid_review_only"] = valid and daily_validation["p16_reconciliation_report_chain_valid_review_only"]
    report["p16_daily_incident_reporting_valid_review_only"] = valid and daily_validation["p16_daily_incident_reporting_valid_review_only"]
    report["limited_live_scaled_auto_trading_allowed"] = False
    report["live_scaled_runtime_enablement_allowed"] = False
    report["runtime_scheduler_enabled"] = False
    report["runtime_loop_started"] = False
    report["unsafe_truthy_execution_flags"] = truthy_execution_flags(report)
    report["p16_limited_live_scaled_loop_dry_run_harness_sha256"] = sha256_json(report)
    return report


def build_p16_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    valid_p15 = {
        "status": "P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_BOUNDARY_VALID_REVIEW_ONLY_NO_EXECUTION",
        "p15_limited_live_scaled_runtime_enablement_boundary_sha256": "f" * 64,
        "p15_limited_live_scaled_runtime_boundary_valid_review_only": True,
        "runtime_stage_policy_valid_review_only": True,
        "runtime_loop_controls_valid_review_only": True,
        "operator_runtime_enablement_request_valid_review_only": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
    }
    valid_ticks = build_review_only_dry_run_ticks(valid_p15)
    valid_daily = build_review_only_dry_run_daily_report(valid_p15, valid_ticks)
    fixtures: dict[str, tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]] = {
        "p15_not_valid": ({**valid_p15, "p15_limited_live_scaled_runtime_boundary_valid_review_only": False}, valid_ticks, valid_daily),
        "missing_min_tick_count": (valid_p15, valid_ticks[:1], valid_daily),
        "tick_missing_fresh_data": (valid_p15, [{**valid_ticks[0], "fresh_market_data_loaded": False}, *valid_ticks[1:]], valid_daily),
        "signal_qa_failed": (valid_p15, [{**valid_ticks[0], "signal_qa_passed": False}, *valid_ticks[1:]], valid_daily),
        "risk_gate_failed": (valid_p15, [{**valid_ticks[0], "hot_path_preorder_risk_gate_passed": False}, *valid_ticks[1:]], valid_daily),
        "duplicate_idempotency": (valid_p15, [{**valid_ticks[0], "idempotency_key_seen_before": True}, *valid_ticks[1:]], valid_daily),
        "hard_cap_failed": (valid_p15, [{**valid_ticks[0], "hard_caps_passed": False}, *valid_ticks[1:]], valid_daily),
        "kill_switch_active": (valid_p15, [{**valid_ticks[0], "kill_switch_safe": False}, *valid_ticks[1:]], valid_daily),
        "would_submit_not_dry_run": (valid_p15, [{**valid_ticks[0], "would_submit_only": False}, *valid_ticks[1:]], valid_daily),
        "endpoint_called": (valid_p15, [{**valid_ticks[0], "live_order_endpoint_called": True}, *valid_ticks[1:]], valid_daily),
        "post_submit_relock_missing": (valid_p15, [{**valid_ticks[0], "post_submit_relock_confirmed": False}, *valid_ticks[1:]], valid_daily),
        "reconciliation_not_required": (valid_p15, [{**valid_ticks[0], "reconciliation_required": False}, *valid_ticks[1:]], valid_daily),
        "daily_report_missing": (valid_p15, valid_ticks, {}),
        "daily_report_nonzero_api_error": (valid_p15, valid_ticks, {**valid_daily, "api_error_count": 1}),
        "incident_report_missing": (valid_p15, valid_ticks, {**valid_daily, "incident_report_created": False}),
        "scheduler_enabled": (valid_p15, [{**valid_ticks[0], "runtime_scheduler_enabled": True}, *valid_ticks[1:]], valid_daily),
        "live_order_allowed": (valid_p15, [{**valid_ticks[0], "live_order_submission_allowed": True}, *valid_ticks[1:]], valid_daily),
        "secret_leak": (valid_p15, [{**valid_ticks[0], "secret_value_logged": True}, *valid_ticks[1:]], valid_daily),
        "runtime_mutation": (valid_p15, [{**valid_ticks[0], "runtime_settings_mutated": True}, *valid_ticks[1:]], valid_daily),
    }
    results: dict[str, Any] = {}
    for name, (p15, ticks, daily) in fixtures.items():
        report = build_limited_live_scaled_loop_dry_run_harness_report(
            cfg=cfg,
            p15_report=p15,
            dry_run_ticks=ticks,
            dry_run_daily_report=daily,
        )
        results[name] = {
            "status": report["status"],
            "blocked_fail_closed": report["status"] == STATUS_BLOCKED_FAIL_CLOSED or bool(report["block_reasons"]) or bool(report["waiting_reasons"]),
            "waiting": report["waiting"],
            "p16_limited_live_scaled_loop_dry_run_harness_valid_review_only": report[
                "p16_limited_live_scaled_loop_dry_run_harness_valid_review_only"
            ],
            "block_reasons": report["block_reasons"],
            "waiting_reasons": report["waiting_reasons"],
            "limited_live_scaled_auto_trading_allowed": report["limited_live_scaled_auto_trading_allowed"],
            "runtime_scheduler_enabled": report["runtime_scheduler_enabled"],
            "live_order_submission_allowed": report["live_order_submission_allowed"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    payload = {
        "version": P16_LIMITED_LIVE_SCALED_LOOP_DRY_RUN_VERSION,
        "fixture_results": results,
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()),
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
    }
    payload["p16_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_limited_live_scaled_loop_dry_run_harness(
    *,
    cfg: AppConfig | None = None,
    p15_report: Mapping[str, Any] | None = None,
    dry_run_ticks: Sequence[Mapping[str, Any]] | None = None,
    dry_run_daily_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    if p15_report is None:
        p15_report = _read_latest_json(cfg, "p15_limited_live_scaled_runtime_enablement_boundary_report.json")
    p15_validation = _validate_p15_source(p15_report or {})
    if p15_validation["p15_runtime_boundary_valid_review_only"] and not p15_validation["p15_source_blocked"]:
        if dry_run_ticks is None:
            loaded_ticks = read_json(latest / "p16_limited_live_scaled_dry_run_ticks.json", default=[])
            dry_run_ticks = loaded_ticks if isinstance(loaded_ticks, list) else []
        if not dry_run_ticks:
            dry_run_ticks = build_review_only_dry_run_ticks(p15_report or {})
            atomic_write_json(latest / "p16_limited_live_scaled_dry_run_ticks.json", list(dry_run_ticks))
        if dry_run_daily_report is None:
            dry_run_daily_report = _read_latest_json(cfg, "p16_limited_live_scaled_dry_run_daily_report.json")
        if not dry_run_daily_report:
            dry_run_daily_report = build_review_only_dry_run_daily_report(p15_report or {}, list(dry_run_ticks or []))
            atomic_write_json(latest / "p16_limited_live_scaled_dry_run_daily_report.json", dry_run_daily_report)

    report = build_limited_live_scaled_loop_dry_run_harness_report(
        cfg=cfg,
        p15_report=p15_report,
        dry_run_ticks=dry_run_ticks,
        dry_run_daily_report=dry_run_daily_report,
    )
    negative = build_p16_negative_fixture_results(cfg=cfg)
    atomic_write_json(latest / "p16_limited_live_scaled_loop_dry_run_harness_report.json", report)
    summary = {
        "version": P16_LIMITED_LIVE_SCALED_LOOP_DRY_RUN_VERSION,
        "status": report["status"],
        "blocked": report["blocked"],
        "waiting": report["waiting"],
        "p16_limited_live_scaled_loop_dry_run_harness_valid_review_only": report[
            "p16_limited_live_scaled_loop_dry_run_harness_valid_review_only"
        ],
        "p16_scheduler_tick_simulation_valid_review_only": report["p16_scheduler_tick_simulation_valid_review_only"],
        "p16_would_submit_evidence_chain_valid_review_only": report["p16_would_submit_evidence_chain_valid_review_only"],
        "p16_reconciliation_report_chain_valid_review_only": report["p16_reconciliation_report_chain_valid_review_only"],
        "p16_daily_incident_reporting_valid_review_only": report["p16_daily_incident_reporting_valid_review_only"],
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
        "block_reasons": report["block_reasons"],
        "waiting_reasons": report["waiting_reasons"],
        "p16_limited_live_scaled_loop_dry_run_harness_sha256": report["p16_limited_live_scaled_loop_dry_run_harness_sha256"],
    }
    atomic_write_json(latest / "p16_limited_live_scaled_loop_dry_run_harness_summary.json", summary)
    atomic_write_json(latest / "p16_limited_live_scaled_loop_dry_run_harness_negative_fixture_results.json", negative)
    archive_dir = _storage_dir(cfg, "storage/p16_limited_live_scaled_loop_dry_run_harness")
    atomic_write_json(archive_dir / "p16_limited_live_scaled_loop_dry_run_harness_report.json", report)
    registry_record = {
        "version": P16_LIMITED_LIVE_SCALED_LOOP_DRY_RUN_VERSION,
        "status": report["status"],
        "blocked": report["blocked"],
        "waiting": report["waiting"],
        "p16_limited_live_scaled_loop_dry_run_harness_valid_review_only": report[
            "p16_limited_live_scaled_loop_dry_run_harness_valid_review_only"
        ],
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
        "report_sha256": report["p16_limited_live_scaled_loop_dry_run_harness_sha256"],
    }
    registry_record = append_registry_record(
        registry_path(cfg, P16_LIMITED_LIVE_SCALED_LOOP_DRY_RUN_REGISTRY_NAME),
        registry_record,
        registry_name=P16_LIMITED_LIVE_SCALED_LOOP_DRY_RUN_REGISTRY_NAME,
        id_field="p16_limited_live_scaled_loop_dry_run_harness_record_id",
        hash_field="p16_limited_live_scaled_loop_dry_run_harness_registry_record_sha256",
        id_prefix="p16_limited_live_scaled_loop_dry_run_harness",
    )
    atomic_write_json(latest / "p16_limited_live_scaled_loop_dry_run_harness_registry_record.json", registry_record)
    return report


__all__ = [
    "DRY_RUN_STAGE",
    "DRY_RUN_SYMBOL",
    "MIN_DRY_RUN_TICKS",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "STATUS_VALID_REVIEW_ONLY_NO_EXECUTION",
    "STATUS_WAITING_REVIEW_ONLY",
    "LimitedLiveScaledDryRunDailyReport",
    "LimitedLiveScaledDryRunTick",
    "build_limited_live_scaled_loop_dry_run_harness_report",
    "build_p16_negative_fixture_results",
    "build_review_only_dry_run_daily_report",
    "build_review_only_dry_run_ticks",
    "persist_limited_live_scaled_loop_dry_run_harness",
]
