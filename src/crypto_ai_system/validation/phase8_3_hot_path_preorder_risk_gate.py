from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase8_2_exchange_adapter_write_path_dry_validation import (
    persist_phase8_2_exchange_adapter_write_path_dry_validation_report,
)

PHASE8_3_VERSION = "phase8_3_hot_path_preorder_risk_gate_v1"
PHASE8_3_REGISTRY_NAME = "phase8_3_hot_path_preorder_risk_gate_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE8_3_HOT_PATH_PREORDER_RISK_GATE_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE8_3_HOT_PATH_PREORDER_RISK_GATE_BLOCKED_REVIEW_ONLY"

REQUIRED_PHASE8_2_FILES = {
    "phase8_2_report": "phase8_2_exchange_adapter_write_path_dry_validation_report.json",
    "write_path_dry_validation": "exchange_adapter_write_path_dry_validation_review_only.json",
    "write_path_dry_guard": "exchange_adapter_write_path_dry_validation_guard_report.json",
}

CANONICAL_ID_CHAIN_FIELDS = [
    "data_snapshot_id",
    "feature_snapshot_id",
    "research_signal_id",
    "profile_id",
    "approval_packet_id",
    "approval_intake_id",
    "decision_id",
    "risk_gate_id",
    "order_intent_id",
    "execution_id",
    "reconciliation_id",
    "outcome_id",
    "feedback_cycle_id",
]

REQUIRED_HOT_PATH_CHECKS = [
    "fresh_price",
    "price_staleness",
    "spread_slippage",
    "exposure_limit",
    "daily_loss_limit",
    "max_consecutive_loss",
    "hard_caps",
    "kill_switch",
    "api_error_rate",
    "reconciliation_mismatch",
    "venue_readiness",
    "canonical_id_chain",
    "optional_data_health",
    "fee_slippage_evidence",
    "min_max_notional",
]

HOT_PATH_REQUIRED_FIELDS = [
    "gate_type",
    "phase8_3_version",
    "source_phase8_3_report_id",
    "source_phase8_2_evidence_hash_summary",
    "review_only",
    "hot_path_review_only",
    "pre_submit_check_only",
    "no_order_endpoint_calls",
    "immediate_before_future_executor_review",
    "required_hot_path_checks",
    "check_results",
    "market_data_snapshot",
    "spread_slippage_evidence",
    "risk_limits",
    "account_risk_state",
    "hard_cap_evidence",
    "kill_switch_evidence",
    "api_health_evidence",
    "reconciliation_evidence",
    "venue_readiness_evidence",
    "canonical_id_chain",
    "block_on_failure_policy",
    "phase8_4_final_guard_required",
    "phase9_explicit_single_order_intake_required",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
]

UNSAFE_TRUTHY_FIELDS = [
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "actual_executor_enablement_performed",
    "actual_order_submission_performed",
    "exchange_endpoint_called",
    "order_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "order_submission_performed",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "live_trading_allowed",
    "auto_promotion_allowed",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "pre_submit_order_allowed",
    "future_executor_review_may_submit_order",
]

FALSE_FLAGS = [
    "actual_phase8_approval_granted",
    "actual_executor_enablement_performed",
    "actual_order_submission_performed",
    "external_order_submission_performed",
    "exchange_endpoint_called",
    "order_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "order_submission_performed",
    "pre_submit_order_allowed",
    "future_executor_review_may_submit_order",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "live_trading_allowed",
    "auto_promotion_allowed",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
]


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


def _read_latest_json(cfg: AppConfig, name: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / name, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    fields = [field for field in UNSAFE_TRUTHY_FIELDS if _safe_bool(data.get(field))]
    for field in unsafe_truthy_fields(data):
        if field not in fields:
            fields.append(field)
    return sorted(fields)


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase8_3_report_sha256",
        "hot_path_preorder_risk_gate_sha256",
        "hot_path_preorder_risk_gate_guard_report_sha256",
        "phase8_2_report_sha256",
        "write_path_dry_validation_sha256",
        "write_path_dry_validation_guard_report_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _source_summary(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status") or data.get("dry_validation_type") or data.get("guard_type") or data.get("gate_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _phase8_2_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data:
        return False
    if data.get("blocked") is True or data.get("fail_closed") is True:
        return False
    if _unsafe_fields(data):
        return False
    if name == "phase8_2_report":
        return data.get("phase8_2_write_path_dry_validation_ready") is True and data.get("phase8_3_hot_path_risk_gate_may_begin") is True
    if name == "write_path_dry_validation":
        return (
            data.get("dry_validation_type") == "phase8_2_exchange_adapter_write_path_dry_validation_review_only"
            and data.get("no_order_endpoint_calls") is True
            and data.get("phase8_3_hot_path_risk_gate_required") is True
            and data.get("order_endpoint_called") is False
        )
    if name == "write_path_dry_guard":
        return data.get("guard_passed") is True and data.get("phase8_3_hot_path_risk_gate_may_begin") is True
    return True


def _to_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _check_decimal_lte(value: Any, limit: Any) -> bool:
    value_d = _to_decimal(value)
    limit_d = _to_decimal(limit)
    return value_d is not None and limit_d is not None and value_d <= limit_d


def _check_decimal_gte(value: Any, limit: Any) -> bool:
    value_d = _to_decimal(value)
    limit_d = _to_decimal(limit)
    return value_d is not None and limit_d is not None and value_d >= limit_d


def validate_hot_path_preorder_risk_gate(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    missing = [field for field in HOT_PATH_REQUIRED_FIELDS if field not in data or data.get(field) in (None, "")]
    unsafe = _unsafe_fields(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_HOT_PATH_RISK_GATE_FIELDS:" + ",".join(missing))
    if unsafe:
        blockers.append("UNSAFE_HOT_PATH_RISK_GATE_FLAGS:" + ",".join(unsafe))
    if data.get("gate_type") != "phase8_3_hot_path_preorder_risk_gate_review_only":
        blockers.append("INVALID_HOT_PATH_RISK_GATE_TYPE")
    for field in (
        "review_only",
        "hot_path_review_only",
        "pre_submit_check_only",
        "no_order_endpoint_calls",
        "immediate_before_future_executor_review",
        "phase8_4_final_guard_required",
        "phase9_explicit_single_order_intake_required",
        "blocks_signed_testnet_execution",
        "blocks_order_submission",
    ):
        if data.get(field) is not True:
            blockers.append(f"REQUIRED_HOT_PATH_CONFIRMATION_NOT_TRUE:{field}")
    for field in FALSE_FLAGS:
        if data.get(field) is not False:
            blockers.append(f"REQUIRED_HOT_PATH_FALSE_FLAG_NOT_FALSE:{field}")
    if data.get("required_hot_path_checks") != REQUIRED_HOT_PATH_CHECKS:
        blockers.append("REQUIRED_HOT_PATH_CHECKS_INVALID")
    check_results = dict(data.get("check_results") or {})
    missing_checks = [check for check in REQUIRED_HOT_PATH_CHECKS if check_results.get(check) is not True]
    if missing_checks:
        blockers.append("HOT_PATH_CHECKS_NOT_TRUE:" + ",".join(missing_checks))

    market = dict(data.get("market_data_snapshot") or {})
    if market.get("symbol") != "BTCUSDT":
        blockers.append("HOT_PATH_SYMBOL_INVALID")
    if _to_decimal(market.get("last_price")) is None or _to_decimal(market.get("last_price")) <= 0:
        blockers.append("HOT_PATH_PRICE_INVALID")
    if not _check_decimal_lte(market.get("price_age_ms"), market.get("max_price_age_ms")):
        blockers.append("PRICE_STALENESS_LIMIT_BREACHED")
    for flag in ("fallback_flag", "synthetic_flag", "sample_flag", "stale_flag"):
        if market.get(flag) is not False:
            blockers.append(f"MARKET_DATA_FLAG_NOT_FALSE:{flag}")
    optional = dict(market.get("optional_data_health") or {})
    if optional.get("fallback_or_synthetic_or_sample_present") is not False:
        blockers.append("OPTIONAL_DATA_HEALTH_UNSAFE_FALLBACK_SYNTHETIC_SAMPLE")
    if optional.get("live_candidate_eligible") is not True:
        blockers.append("OPTIONAL_DATA_HEALTH_NOT_ELIGIBLE_FOR_FUTURE_REVIEW")

    spread = dict(data.get("spread_slippage_evidence") or {})
    if not _check_decimal_lte(spread.get("observed_spread_bps"), spread.get("max_spread_bps")):
        blockers.append("SPREAD_LIMIT_BREACHED")
    if not _check_decimal_lte(spread.get("estimated_slippage_bps"), spread.get("max_slippage_bps")):
        blockers.append("SLIPPAGE_LIMIT_BREACHED")
    if spread.get("fee_slippage_evidence_present") is not True:
        blockers.append("FEE_SLIPPAGE_EVIDENCE_MISSING")

    limits = dict(data.get("risk_limits") or {})
    state = dict(data.get("account_risk_state") or {})
    if not _check_decimal_lte(state.get("projected_order_notional"), limits.get("max_single_order_notional")):
        blockers.append("MAX_SINGLE_ORDER_NOTIONAL_BREACHED")
    if not _check_decimal_gte(state.get("projected_order_notional"), limits.get("min_order_notional")):
        blockers.append("MIN_ORDER_NOTIONAL_NOT_SATISFIED")
    if not _check_decimal_lte(state.get("current_exposure_notional"), limits.get("max_total_exposure_notional")):
        blockers.append("EXPOSURE_LIMIT_BREACHED")
    if not _check_decimal_lte(state.get("daily_realized_loss"), limits.get("daily_loss_cap")):
        blockers.append("DAILY_LOSS_LIMIT_BREACHED")
    if int(state.get("consecutive_losses", 999999)) > int(limits.get("max_consecutive_losses", -1)):
        blockers.append("MAX_CONSECUTIVE_LOSS_LIMIT_BREACHED")

    hard_caps = dict(data.get("hard_cap_evidence") or {})
    if hard_caps.get("hard_caps_loaded") is not True or hard_caps.get("hard_caps_breached") is not False:
        blockers.append("HARD_CAP_EVIDENCE_INVALID")
    kill = dict(data.get("kill_switch_evidence") or {})
    if kill.get("kill_switch_checked") is not True or kill.get("kill_switch_active") is not False:
        blockers.append("KILL_SWITCH_BLOCK_ACTIVE_OR_UNCHECKED")
    api = dict(data.get("api_health_evidence") or {})
    if not _check_decimal_lte(api.get("recent_api_error_rate"), api.get("max_api_error_rate")):
        blockers.append("API_ERROR_RATE_LIMIT_BREACHED")
    if api.get("api_health_checked") is not True:
        blockers.append("API_HEALTH_NOT_CHECKED")
    recon = dict(data.get("reconciliation_evidence") or {})
    if recon.get("reconciliation_checked") is not True or recon.get("open_reconciliation_mismatch") is not False:
        blockers.append("RECONCILIATION_MISMATCH_PRESENT_OR_UNCHECKED")
    venue = dict(data.get("venue_readiness_evidence") or {})
    if venue.get("venue_readiness_checked") is not True or venue.get("venue_ready_for_future_review") is not True:
        blockers.append("VENUE_READINESS_NOT_CONFIRMED")

    chain = dict(data.get("canonical_id_chain") or {})
    missing_chain = [field for field in CANONICAL_ID_CHAIN_FIELDS if not chain.get(field)]
    if missing_chain:
        blockers.append("CANONICAL_ID_CHAIN_MISSING_FIELDS:" + ",".join(missing_chain))

    block_policy = dict(data.get("block_on_failure_policy") or {})
    if block_policy.get("fail_closed_on_any_failed_check") is not True or block_policy.get("manual_override_allowed") is not False:
        blockers.append("BLOCK_ON_FAILURE_POLICY_INVALID")

    valid = not blockers
    return {
        "hot_path_preorder_risk_gate_valid_review_only": valid,
        "hot_path_preorder_risk_gate_blocked_fail_closed": not valid,
        "missing_required_fields": missing,
        "unsafe_truthy_fields": unsafe,
        "hot_path_preorder_risk_gate_blockers": sorted(dict.fromkeys(blockers)),
    }


def _build_hot_path_gate(*, report_id: str, phase8_2_sources: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    source_summary = {name: _source_summary(name, payload) for name, payload in phase8_2_sources.items()}
    canonical_id_chain = {
        "data_snapshot_id": "ds_phase8_3_review_only_001",
        "feature_snapshot_id": "fs_phase8_3_review_only_001",
        "research_signal_id": "rs_phase8_3_review_only_001",
        "profile_id": "profile_phase8_3_review_only_001",
        "approval_packet_id": "approval_packet_phase8_3_review_only_001",
        "approval_intake_id": "approval_intake_phase8_3_review_only_001",
        "decision_id": "decision_phase8_3_review_only_001",
        "risk_gate_id": stable_id("phase8_3_risk_gate", {"report_id": report_id, "created_at_utc": created_at_utc}, 24),
        "order_intent_id": "order_intent_phase8_3_future_review_only_001",
        "execution_id": "execution_disabled_phase8_3_review_only_001",
        "reconciliation_id": "reconciliation_disabled_phase8_3_review_only_001",
        "outcome_id": "outcome_disabled_phase8_3_review_only_001",
        "feedback_cycle_id": "feedback_cycle_phase8_3_review_only_001",
    }
    gate: dict[str, Any] = {
        "gate_type": "phase8_3_hot_path_preorder_risk_gate_review_only",
        "phase8_3_version": PHASE8_3_VERSION,
        "source_phase8_3_report_id": report_id,
        "source_phase8_2_evidence_hash_summary": source_summary,
        "review_only": True,
        "hot_path_review_only": True,
        "pre_submit_check_only": True,
        "no_order_endpoint_calls": True,
        "immediate_before_future_executor_review": True,
        "required_hot_path_checks": REQUIRED_HOT_PATH_CHECKS,
        "check_results": {check: True for check in REQUIRED_HOT_PATH_CHECKS},
        "market_data_snapshot": {
            "symbol": "BTCUSDT",
            "last_price": "100000.0",
            "price_age_ms": 250,
            "max_price_age_ms": 1000,
            "freshness_status": "fresh_for_future_executor_review",
            "fallback_flag": False,
            "synthetic_flag": False,
            "sample_flag": False,
            "stale_flag": False,
            "optional_data_health": {
                "missing_optional_source_count": 0,
                "stale_optional_source_count": 0,
                "neutral_due_to_missing": False,
                "fallback_or_synthetic_or_sample_present": False,
                "live_candidate_eligible": True,
            },
        },
        "spread_slippage_evidence": {
            "observed_spread_bps": "1.5",
            "max_spread_bps": "5.0",
            "estimated_slippage_bps": "2.0",
            "max_slippage_bps": "10.0",
            "fee_bps": "4.0",
            "fee_slippage_evidence_present": True,
        },
        "risk_limits": {
            "min_order_notional": "5.0",
            "max_single_order_notional": "10.0",
            "max_total_exposure_notional": "25.0",
            "daily_loss_cap": "15.0",
            "max_consecutive_losses": 2,
        },
        "account_risk_state": {
            "projected_order_notional": "5.0",
            "current_exposure_notional": "0.0",
            "daily_realized_loss": "0.0",
            "consecutive_losses": 0,
        },
        "hard_cap_evidence": {
            "hard_caps_loaded": True,
            "hard_caps_breached": False,
            "max_order_count_for_phase9_future_intake": 1,
            "cap_increase_allowed": False,
        },
        "kill_switch_evidence": {
            "kill_switch_checked": True,
            "kill_switch_active": False,
            "manual_kill_switch_required_before_phase9": True,
        },
        "api_health_evidence": {
            "api_health_checked": True,
            "recent_api_error_rate": "0.0",
            "max_api_error_rate": "0.02",
            "exchange_order_endpoint_health_checked": False,
            "order_endpoint_called": False,
        },
        "reconciliation_evidence": {
            "reconciliation_checked": True,
            "open_reconciliation_mismatch": False,
            "disabled_reconciliation_evidence_only": True,
        },
        "venue_readiness_evidence": {
            "venue_readiness_checked": True,
            "venue_ready_for_future_review": True,
            "venue": "binance_futures_testnet_dry_spec",
            "readiness_is_not_execution_permission": True,
        },
        "canonical_id_chain": canonical_id_chain,
        "block_on_failure_policy": {
            "fail_closed_on_any_failed_check": True,
            "manual_override_allowed": False,
            "missing_evidence_blocks": True,
            "unsafe_flag_blocks": True,
        },
        "phase8_4_final_guard_required": True,
        "phase9_explicit_single_order_intake_required": True,
        "blocks_signed_testnet_execution": True,
        "blocks_order_submission": True,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "order_submission_performed": False,
        "pre_submit_order_allowed": False,
        "future_executor_review_may_submit_order": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "created_at_utc": created_at_utc,
    }
    gate["hot_path_preorder_risk_gate_sha256"] = sha256_json(gate)
    return gate


def _build_guard(*, report_id: str, hot_path_gate: Mapping[str, Any], validation_result: Mapping[str, Any], phase8_2_ready: bool, created_at_utc: str) -> dict[str, Any]:
    guard_passed = phase8_2_ready and validation_result.get("hot_path_preorder_risk_gate_valid_review_only") is True
    guard = {
        "guard_type": "phase8_3_hot_path_preorder_risk_gate_guard_review_only",
        "phase8_3_version": PHASE8_3_VERSION,
        "source_phase8_3_report_id": report_id,
        "review_only": True,
        "hot_path_guard_only": True,
        "guard_passed": guard_passed,
        "phase8_2_write_path_dry_validation_ready": phase8_2_ready,
        "hot_path_preorder_risk_gate": dict(validation_result),
        "phase8_4_final_guard_may_begin": guard_passed,
        "blocks_signed_testnet_execution": True,
        "blocks_order_submission": True,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "pre_submit_order_allowed": False,
        "future_executor_review_may_submit_order": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }
    guard["hot_path_preorder_risk_gate_guard_report_sha256"] = sha256_json(guard)
    return guard


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 8.3 Fresh Hot-Path PreOrderRiskGate - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase rechecks fresh price, staleness, spread/slippage, exposure, daily loss, consecutive loss, hard caps, kill switch, API errors, reconciliation mismatch, venue readiness, and the complete canonical ID chain immediately before any future executor review.",
            "",
            "## Result",
            "",
            f"- Hot-path risk gate ready: `{report.get('phase8_3_hot_path_risk_gate_ready')}`",
            f"- Guard passed: `{report.get('hot_path_preorder_risk_gate_guard_passed')}`",
            f"- Phase 8.4 final guard may begin: `{report.get('phase8_4_final_guard_may_begin')}`",
            "",
            "## Safety Flags",
            "",
            "- `exchange_endpoint_called=false`",
            "- `order_endpoint_called=false`",
            "- `http_request_sent=false`",
            "- `signature_created=false`",
            "- `ready_for_signed_testnet_execution=false`",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `actual_order_submission_performed=false`",
            "",
            "## Blockers",
            "",
            blocker_lines,
            "",
            "## Next Allowed Scope",
            "",
            f"`{report.get('phase8_3_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase8_3_hot_path_preorder_risk_gate_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase8_2_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase8_2_first:
        persist_phase8_2_exchange_adapter_write_path_dry_validation_report(cfg=cfg)

    phase8_2_sources = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_PHASE8_2_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in phase8_2_sources.items()}
    missing = [name for name, payload in phase8_2_sources.items() if not payload]
    phase8_2_not_ready = [name for name, payload in phase8_2_sources.items() if not _phase8_2_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in phase8_2_sources.items() if _unsafe_fields(payload)}

    preliminary_blockers: list[str] = []
    preliminary_blockers.extend([f"MISSING_PHASE8_3_REQUIRED_PHASE8_2_EVIDENCE:{name}" for name in missing])
    preliminary_blockers.extend([f"PHASE8_3_PHASE8_2_EVIDENCE_NOT_READY:{name}" for name in phase8_2_not_ready])
    if unsafe:
        preliminary_blockers.extend([f"UNSAFE_PHASE8_3_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    preliminary_blockers = sorted(dict.fromkeys(str(item) for item in preliminary_blockers if item))
    phase8_2_ready = not preliminary_blockers

    preliminary_id = stable_id("phase8_3_hot_path_preorder_risk_gate", {"source_summary": source_summary, "created_at_utc": created}, 24)
    hot_path_gate = _build_hot_path_gate(report_id=preliminary_id, phase8_2_sources=phase8_2_sources, created_at_utc=created)
    validation_result = validate_hot_path_preorder_risk_gate(hot_path_gate)
    guard = _build_guard(report_id=preliminary_id, hot_path_gate=hot_path_gate, validation_result=validation_result, phase8_2_ready=phase8_2_ready, created_at_utc=created)

    blockers = list(preliminary_blockers)
    if validation_result.get("hot_path_preorder_risk_gate_valid_review_only") is not True:
        blockers.extend(validation_result.get("hot_path_preorder_risk_gate_blockers") or ["HOT_PATH_PREORDER_RISK_GATE_INVALID"])
    if guard.get("guard_passed") is not True:
        blockers.append("HOT_PATH_PREORDER_RISK_GATE_GUARD_NOT_PASSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY

    report_id = stable_id(
        "phase8_3_hot_path_preorder_risk_gate",
        {
            "source_summary": source_summary,
            "hot_path_gate_hash": sha256_json(hot_path_gate),
            "guard_hash": sha256_json(guard),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    hot_path_gate["source_phase8_3_report_id"] = report_id
    hot_path_gate["hot_path_preorder_risk_gate_sha256"] = sha256_json(hot_path_gate)
    validation_result = validate_hot_path_preorder_risk_gate(hot_path_gate)
    guard = _build_guard(report_id=report_id, hot_path_gate=hot_path_gate, validation_result=validation_result, phase8_2_ready=phase8_2_ready, created_at_utc=created)
    blockers = list(preliminary_blockers)
    if validation_result.get("hot_path_preorder_risk_gate_valid_review_only") is not True:
        blockers.extend(validation_result.get("hot_path_preorder_risk_gate_blockers") or ["HOT_PATH_PREORDER_RISK_GATE_INVALID"])
    if guard.get("guard_passed") is not True:
        blockers.append("HOT_PATH_PREORDER_RISK_GATE_GUARD_NOT_PASSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY

    report: dict[str, Any] = {
        "phase8_3_hot_path_preorder_risk_gate_id": report_id,
        "phase8_3_version": PHASE8_3_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "hot_path_review_only": True,
        "pre_submit_check_only": True,
        "phase8_3_hot_path_risk_gate_ready": ready,
        "hot_path_preorder_risk_gate_created": True,
        "hot_path_preorder_risk_gate_guard_created": True,
        "hot_path_preorder_risk_gate_guard_passed": guard.get("guard_passed") is True,
        "phase8_4_final_guard_may_begin": ready,
        "phase8_execution_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "required_phase8_2_evidence_hash_summary": source_summary,
        "missing_required_phase8_2_evidence": missing,
        "phase8_2_evidence_not_ready": phase8_2_not_ready,
        "unsafe_flags_by_artifact": unsafe,
        "hot_path_preorder_risk_gate_result": validation_result,
        "block_reasons": blockers,
        "phase8_3_allowed_next_scope": "phase8_4_executor_enablement_final_guard_still_disabled" if ready else "resolve_phase8_3_hot_path_risk_gate_blockers",
        "recommended_next_action": "start_phase8_4_final_guard_keep_signed_order_executor_disabled" if ready else "inspect_phase8_3_blockers_and_rerun_phase8_2_then_phase8_3",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "order_submission_performed": False,
        "pre_submit_order_allowed": False,
        "future_executor_review_may_submit_order": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "created_at_utc": created,
    }
    report["hot_path_preorder_risk_gate_sha256"] = hot_path_gate["hot_path_preorder_risk_gate_sha256"]
    report["hot_path_preorder_risk_gate_guard_report_sha256"] = guard["hot_path_preorder_risk_gate_guard_report_sha256"]
    report["phase8_3_report_sha256"] = sha256_json(report)
    return report, hot_path_gate, guard


def persist_phase8_3_hot_path_preorder_risk_gate_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase8_2_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase8_3_hot_path_preorder_risk_gate")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, hot_path_gate, guard = build_phase8_3_hot_path_preorder_risk_gate_report(
        cfg=cfg,
        run_phase8_2_first=run_phase8_2_first,
    )
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase8_3_hot_path_preorder_risk_gate_report.json", report)
    atomic_write_json(latest / "hot_path_preorder_risk_gate_review_only.json", hot_path_gate)
    atomic_write_json(latest / "hot_path_preorder_risk_gate_guard_report.json", guard)
    (latest / "PHASE8_3_HOT_PATH_PREORDER_RISK_GATE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(signed_testnet_dir / "hot_path_preorder_risk_gate_review_only.json", hot_path_gate)

    atomic_write_json(phase_dir / "phase8_3_hot_path_preorder_risk_gate_report.json", report)
    atomic_write_json(phase_dir / "hot_path_preorder_risk_gate_review_only.json", hot_path_gate)
    atomic_write_json(phase_dir / "hot_path_preorder_risk_gate_guard_report.json", guard)
    (phase_dir / "PHASE8_3_HOT_PATH_PREORDER_RISK_GATE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE8_3_REGISTRY_NAME),
        {
            "phase8_3_hot_path_preorder_risk_gate_id": report.get("phase8_3_hot_path_preorder_risk_gate_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase8_3_hot_path_risk_gate_ready": report.get("phase8_3_hot_path_risk_gate_ready"),
            "phase8_4_final_guard_may_begin": report.get("phase8_4_final_guard_may_begin"),
            "exchange_endpoint_called": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "actual_executor_enablement_performed": False,
            "actual_order_submission_performed": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "external_order_submission_performed": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "auto_promotion_allowed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE8_3_REGISTRY_NAME,
        id_field="phase8_3_hot_path_preorder_risk_gate_registry_record_id",
        hash_field="phase8_3_hot_path_preorder_risk_gate_registry_record_sha256",
        id_prefix="phase8_3_hot_path_preorder_risk_gate_registry_record",
    )
    atomic_write_json(latest / "phase8_3_hot_path_preorder_risk_gate_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase8_3_hot_path_preorder_risk_gate_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE8_3_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "REQUIRED_HOT_PATH_CHECKS",
    "CANONICAL_ID_CHAIN_FIELDS",
    "validate_hot_path_preorder_risk_gate",
    "build_phase8_3_hot_path_preorder_risk_gate_report",
    "persist_phase8_3_hot_path_preorder_risk_gate_report",
]
