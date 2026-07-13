from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase10_signed_testnet_session_validation_blocked_design import (
    STATUS_PHASE10_SESSION_VALIDATION_RECORDED_BLOCKED_REVIEW_ONLY,
    persist_phase10_signed_testnet_session_validation_blocked_design_report,
)

PHASE11_LIVE_CANARY_PREPARATION_VERSION = "phase11_live_canary_preparation_blocked_design_v1"
PHASE11_LIVE_CANARY_PREPARATION_REGISTRY_NAME = "phase11_live_canary_preparation_blocked_design_registry"
STATUS_PHASE11_LIVE_CANARY_PREPARATION_RECORDED_BLOCKED_REVIEW_ONLY = (
    "PHASE11_LIVE_CANARY_PREPARATION_DESIGN_RECORDED_BLOCKED_REVIEW_ONLY"
)
STATUS_PHASE11_LIVE_CANARY_PREPARATION_BLOCKED_REVIEW_ONLY = (
    "PHASE11_LIVE_CANARY_PREPARATION_DESIGN_BLOCKED_REVIEW_ONLY"
)

REQUIRED_PHASE10_FILES = {
    "phase10_session_validation_report": "phase10_signed_testnet_session_validation_blocked_design_report.json",
    "phase10_session_validation_design": "phase10_signed_testnet_session_validation_DESIGN_BLOCKED_REVIEW_ONLY.json",
    "phase10_session_validation_validation": "phase10_signed_testnet_session_validation_validation_report.json",
}

LIVE_READ_ONLY_PROBE_CHECKS_REQUIRED = [
    "venue_reachability",
    "account_read_access",
    "symbol_info",
    "min_notional",
    "fee_tier",
    "balance_read",
    "position_read",
    "open_orders_read",
    "api_error_rate",
    "rate_limit_behavior",
]

LIVE_KEY_SCOPE_CHECKS_REQUIRED = [
    "withdrawal_disabled",
    "transfer_disabled",
    "admin_disabled",
    "leverage_margin_mutation_controlled_or_disabled",
    "live_key_fingerprint_recorded_metadata_only",
    "key_value_never_stored",
]

LIVE_CANARY_APPROVAL_FIELDS_REQUIRED = [
    "single_order_scope",
    "max_order_count_equals_one",
    "small_max_notional",
    "daily_loss_cap",
    "single_symbol_scope",
    "manual_kill_switch",
    "manual_operator_approval_required",
]

UNSAFE_TRUTHY_FIELDS = list(FALSE_FLAGS) + [
    "phase10_signed_testnet_session_validation_may_begin",
    "phase10_session_validation_started",
    "phase10_promotion_review_packet_created",
    "live_canary_preparation_may_begin",
    "live_read_only_probe_performed",
    "live_key_scope_validation_performed",
    "live_canary_approval_packet_created",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "live_order_submission_allowed",
    "live_order_endpoint_called",
    "live_account_endpoint_called",
    "live_balance_read_performed",
    "live_position_read_performed",
    "live_key_value_read",
    "live_api_secret_value_read",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_order_submission_performed",
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


def _flag_false_payload() -> dict[str, bool]:
    return {field: False for field in FALSE_FLAGS}


def _unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    fields = [field for field in UNSAFE_TRUTHY_FIELDS if _safe_bool(data.get(field))]
    for field in unsafe_truthy_fields(data):
        if field not in fields:
            fields.append(field)
    return sorted(dict.fromkeys(fields))


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase11_live_canary_preparation_design_sha256",
        "phase11_live_canary_preparation_report_sha256",
        "phase10_signed_testnet_session_validation_report_sha256",
        "phase10_signed_testnet_session_validation_design_sha256",
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
        "status": data.get("status") or data.get("artifact_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data or _unsafe_fields(data):
        return False
    if name == "phase10_session_validation_report":
        return (
            data.get("status") == STATUS_PHASE10_SESSION_VALIDATION_RECORDED_BLOCKED_REVIEW_ONLY
            and data.get("phase10_signed_testnet_session_validation_design_recorded") is True
            and data.get("phase10_signed_testnet_session_validation_may_begin") is False
            and data.get("phase10_session_validation_started") is False
            and data.get("live_canary_preparation_may_begin") is False
        )
    if name == "phase10_session_validation_design":
        return (
            data.get("artifact_type") == "phase10_signed_testnet_session_validation_design_blocked_review_only"
            and data.get("review_only") is True
            and data.get("live_canary_preparation_may_begin") is False
            and data.get("phase10_session_validation_started") is False
        )
    if name == "phase10_session_validation_validation":
        return data.get("phase10_signed_testnet_session_validation_design_valid") is True
    return True


def build_phase11_live_canary_preparation_design(
    *, phase10_sources: Mapping[str, Mapping[str, Any]], created_at_utc: str
) -> dict[str, Any]:
    source_summary = {name: _source_summary(name, payload) for name, payload in phase10_sources.items()}
    design = {
        "artifact_type": "phase11_live_canary_preparation_design_blocked_review_only",
        "phase11_live_canary_preparation_version": PHASE11_LIVE_CANARY_PREPARATION_VERSION,
        "review_only": True,
        "blocked_design_artifact": True,
        "source_evidence_hash_summary": source_summary,
        "no_successful_phase10_signed_testnet_sessions_available": True,
        "no_live_read_only_probe_performed": True,
        "no_live_key_scope_validation_performed": True,
        "live_canary_preparation_may_begin": False,
        "live_read_only_probe_performed": False,
        "live_key_scope_validation_performed": False,
        "live_canary_approval_packet_created": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "required_live_read_only_probe_checks": LIVE_READ_ONLY_PROBE_CHECKS_REQUIRED,
        "required_live_key_scope_checks": LIVE_KEY_SCOPE_CHECKS_REQUIRED,
        "required_live_canary_approval_fields": LIVE_CANARY_APPROVAL_FIELDS_REQUIRED,
        "live_read_only_probe_plan": {
            "venue_reachability": "check live venue reachability with read-only request only after Phase 10 evidence exists",
            "account_read_access": "validate account read permission without trading or mutation authority",
            "symbol_info": "read symbol metadata, tick size, quantity step, min notional, and status",
            "min_notional": "record live min notional for proposed single-symbol canary scope",
            "fee_tier": "record fee tier metadata without creating orders",
            "balance_read": "read balances only after live read-only approval and never transfer funds",
            "position_read": "read positions only and never mutate margin or leverage",
            "open_orders_read": "read open orders only and never place/cancel orders in Phase 11 design",
            "api_error_rate": "track read-only API error rate and normalized error classes",
            "rate_limit_behavior": "record observed read-only rate limit behavior",
        },
        "live_key_scope_validation_plan": {
            "withdrawal_disabled": "verify withdrawal permission disabled before any live canary approval packet",
            "transfer_disabled": "verify transfer permission disabled",
            "admin_disabled": "verify admin permission disabled",
            "leverage_margin_mutation_controlled_or_disabled": "verify leverage/margin mutation is disabled or separately controlled",
            "live_key_fingerprint_recorded_metadata_only": "record metadata-only fingerprint; never record key value",
            "key_value_never_stored": "block any key value, secret value, passphrase, or secret file evidence",
        },
        "live_canary_approval_packet_plan": {
            "single_order_scope": True,
            "max_order_count_equals_one": True,
            "small_max_notional_required": True,
            "daily_loss_cap_required": True,
            "single_symbol_scope_required": True,
            "manual_kill_switch_required": True,
            "manual_operator_approval_required": True,
            "phase11_packet_does_not_enable_live_execution": True,
        },
        "requires_before_phase11_may_begin": [
            "multiple_clean_phase10_signed_testnet_sessions",
            "zero_unresolved_phase9_4_or_phase10_reconciliation_mismatch",
            "bounded_slippage_latency_and_api_error_rate",
            "paper_testnet_gap_review",
            "live_read_only_probe_approval",
            "live_key_scope_validation_approval",
        ],
        "live_account_endpoint_called": False,
        "live_balance_read_performed": False,
        "live_position_read_performed": False,
        "live_key_value_read": False,
        "live_api_secret_value_read": False,
        "live_order_endpoint_called": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        **_flag_false_payload(),
        "created_at_utc": created_at_utc,
    }
    design["phase11_live_canary_preparation_design_sha256"] = sha256_json(design)
    return design


def validate_phase11_live_canary_preparation_design(design: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(design or {})
    blockers: list[str] = []
    unsafe = _unsafe_fields(payload)
    if payload.get("artifact_type") != "phase11_live_canary_preparation_design_blocked_review_only":
        blockers.append("PHASE11_LIVE_CANARY_PREPARATION_DESIGN_TYPE_INVALID")
    if payload.get("review_only") is not True:
        blockers.append("PHASE11_LIVE_CANARY_PREPARATION_DESIGN_NOT_REVIEW_ONLY")
    if payload.get("no_successful_phase10_signed_testnet_sessions_available") is not True:
        blockers.append("PHASE11_EXPECTED_NO_SUCCESSFUL_PHASE10_SESSIONS")
    for field in (
        "live_canary_preparation_may_begin",
        "live_read_only_probe_performed",
        "live_key_scope_validation_performed",
        "live_canary_approval_packet_created",
        "live_canary_execution_enabled",
        "live_scaled_execution_enabled",
    ):
        if payload.get(field) is not False:
            blockers.append(f"PHASE11_LIVE_CANARY_PREPARATION_UNSAFE_FIELD:{field}")
    checks = payload.get("required_live_read_only_probe_checks") or []
    for check in LIVE_READ_ONLY_PROBE_CHECKS_REQUIRED:
        if check not in checks:
            blockers.append(f"PHASE11_LIVE_READ_ONLY_PROBE_CHECK_MISSING:{check}")
    key_checks = payload.get("required_live_key_scope_checks") or []
    for check in LIVE_KEY_SCOPE_CHECKS_REQUIRED:
        if check not in key_checks:
            blockers.append(f"PHASE11_LIVE_KEY_SCOPE_CHECK_MISSING:{check}")
    fields = payload.get("required_live_canary_approval_fields") or []
    for field in LIVE_CANARY_APPROVAL_FIELDS_REQUIRED:
        if field not in fields:
            blockers.append(f"PHASE11_LIVE_CANARY_APPROVAL_FIELD_MISSING:{field}")
    plan = payload.get("live_canary_approval_packet_plan") or {}
    for key in (
        "single_order_scope",
        "max_order_count_equals_one",
        "small_max_notional_required",
        "daily_loss_cap_required",
        "single_symbol_scope_required",
        "manual_kill_switch_required",
        "manual_operator_approval_required",
        "phase11_packet_does_not_enable_live_execution",
    ):
        if plan.get(key) is not True:
            blockers.append(f"PHASE11_LIVE_CANARY_APPROVAL_PLAN_MISSING:{key}")
    if unsafe:
        blockers.append("PHASE11_LIVE_CANARY_PREPARATION_UNSAFE_FLAGS:" + ",".join(unsafe))
    valid = not blockers
    return {
        "artifact_type": "phase11_live_canary_preparation_design_validation_report",
        "phase11_live_canary_preparation_design_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_flag_false_payload(),
        "live_canary_preparation_may_begin": False,
        "live_canary_execution_enabled": False,
        "actual_order_submission_performed": False,
    }


def _build_negative_fixture_results(design: Mapping[str, Any]) -> dict[str, Any]:
    cases: dict[str, dict[str, Any]] = {
        "live_canary_preparation_true": {"live_canary_preparation_may_begin": True},
        "live_probe_performed_true": {"live_read_only_probe_performed": True},
        "live_key_scope_validation_true": {"live_key_scope_validation_performed": True},
        "live_canary_execution_enabled_true": {"live_canary_execution_enabled": True},
        "live_scaled_execution_enabled_true": {"live_scaled_execution_enabled": True},
        "live_order_endpoint_called_true": {"live_order_endpoint_called": True},
        "live_key_value_read_true": {"live_key_value_read": True},
        "missing_fee_tier_probe_check": {
            "required_live_read_only_probe_checks": [c for c in LIVE_READ_ONLY_PROBE_CHECKS_REQUIRED if c != "fee_tier"]
        },
        "missing_withdrawal_disabled_key_scope_check": {
            "required_live_key_scope_checks": [c for c in LIVE_KEY_SCOPE_CHECKS_REQUIRED if c != "withdrawal_disabled"]
        },
    }
    results: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(design)
        payload.update(patch)
        validation = validate_phase11_live_canary_preparation_design(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    all_blocked = all(r["blocked"] and r["fail_closed"] for r in results.values())
    payload = {
        "artifact_type": "phase11_live_canary_preparation_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
        "live_canary_preparation_may_begin": False,
        "live_canary_execution_enabled": False,
        "actual_order_submission_performed": False,
    }
    payload["phase11_live_canary_preparation_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def build_phase11_live_canary_preparation_blocked_design_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase10_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    if run_phase10_first:
        persist_phase10_signed_testnet_session_validation_blocked_design_report(cfg=cfg, run_phase9_3_9_4_first=True)
    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_PHASE10_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if payload and not _source_ready(name, payload)]
    unsafe_source_flags = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    created = utc_now_canonical()
    design = build_phase11_live_canary_preparation_design(phase10_sources=sources, created_at_utc=created)
    validation = validate_phase11_live_canary_preparation_design(design)
    negative_fixture_results = _build_negative_fixture_results(design)
    blockers: list[str] = []
    if missing:
        blockers.extend(f"PHASE11_REQUIRED_SOURCE_MISSING:{name}" for name in missing)
    if not_ready:
        blockers.extend(f"PHASE11_REQUIRED_SOURCE_NOT_READY:{name}" for name in not_ready)
    if validation["blocked"]:
        blockers.extend(validation["block_reasons"])
    if not negative_fixture_results["all_negative_fixtures_blocked_fail_closed"]:
        blockers.append("PHASE11_NEGATIVE_FIXTURES_DID_NOT_ALL_BLOCK_FAIL_CLOSED")
    blockers.append("PHASE11_BLOCKED_UNTIL_PHASE10_MULTIPLE_CLEAN_SIGNED_TESTNET_SESSIONS_EXIST")
    report = {
        "phase11_live_canary_preparation_id": stable_id("phase11_live_canary_preparation", source_summary),
        "phase11_live_canary_preparation_version": PHASE11_LIVE_CANARY_PREPARATION_VERSION,
        "status": STATUS_PHASE11_LIVE_CANARY_PREPARATION_RECORDED_BLOCKED_REVIEW_ONLY,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "phase11_live_canary_preparation_design_recorded": True,
        "phase11_live_canary_preparation_design_valid": validation["phase11_live_canary_preparation_design_valid"],
        "live_canary_preparation_may_begin": False,
        "live_read_only_probe_performed": False,
        "live_key_scope_validation_performed": False,
        "live_canary_approval_packet_created": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe_source_flags,
        "required_live_read_only_probe_checks": LIVE_READ_ONLY_PROBE_CHECKS_REQUIRED,
        "required_live_key_scope_checks": LIVE_KEY_SCOPE_CHECKS_REQUIRED,
        "required_live_canary_approval_fields": LIVE_CANARY_APPROVAL_FIELDS_REQUIRED,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "recommended_next_action": "complete_real_phase9_2_submit_phase9_3_status_cancel_phase9_4_reconciliation_and_phase10_session_validation_before_live_canary_preparation",
        **_flag_false_payload(),
        "live_order_endpoint_called": False,
        "live_account_endpoint_called": False,
        "live_balance_read_performed": False,
        "live_position_read_performed": False,
        "live_key_value_read": False,
        "live_api_secret_value_read": False,
        "actual_order_submission_performed": False,
        "created_at_utc": created,
    }
    report["phase11_live_canary_preparation_report_sha256"] = sha256_json(report)
    return report, design, validation, negative_fixture_results


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 11 Live Canary Preparation Design - Blocked Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact defines the live canary preparation model while Phase 9.2/9.3/9.4/10 remain without real signed testnet session evidence.",
            "",
            "## Result",
            "",
            f"- Live canary preparation may begin: `{report.get('live_canary_preparation_may_begin')}`",
            f"- Live read-only probe performed: `{report.get('live_read_only_probe_performed')}`",
            f"- Live key scope validation performed: `{report.get('live_key_scope_validation_performed')}`",
            f"- Live canary execution enabled: `{report.get('live_canary_execution_enabled')}`",
            "",
            "## Required before Phase 11",
            "",
            "- Real Phase 9.2 single signed testnet order evidence",
            "- Phase 9.3 final status/cancel evidence",
            "- Phase 9.4 reconciliation without unresolved mismatch",
            "- Multiple clean Phase 10 signed testnet sessions",
            "- Bounded slippage, latency, API error, and paper/testnet gap evidence",
            "",
            "## Still Disabled",
            "",
            "- `live_canary_preparation_may_begin=false`",
            "- `live_canary_execution_enabled=false`",
            "- `live_scaled_execution_enabled=false`",
            "- `actual_order_submission_performed=false`",
            "- `runtime_mutation_performed=false`",
            "",
        ]
    )


def persist_phase11_live_canary_preparation_blocked_design_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase10_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase11_live_canary_preparation_blocked_design")
    live_canary_dir = _storage_dir(cfg, "storage/live_canary")
    report, design, validation, negative_fixture_results = build_phase11_live_canary_preparation_blocked_design_report(
        cfg=cfg,
        run_phase10_first=run_phase10_first,
    )
    handoff = _build_handoff_markdown(report)
    for base in (latest, phase_dir, live_canary_dir):
        atomic_write_json(base / "phase11_live_canary_preparation_blocked_design_report.json", report)
        atomic_write_json(base / "phase11_live_canary_preparation_DESIGN_BLOCKED_REVIEW_ONLY.json", design)
        atomic_write_json(base / "phase11_live_canary_preparation_validation_report.json", validation)
        atomic_write_json(base / "phase11_live_canary_preparation_negative_fixture_results.json", negative_fixture_results)
        (base / "PHASE11_LIVE_CANARY_PREPARATION_HANDOFF_BLOCKED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE11_LIVE_CANARY_PREPARATION_REGISTRY_NAME),
        {
            "phase11_live_canary_preparation_id": report.get("phase11_live_canary_preparation_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "phase11_live_canary_preparation_design_recorded": report.get("phase11_live_canary_preparation_design_recorded"),
            "live_canary_preparation_may_begin": False,
            "live_canary_execution_enabled": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE11_LIVE_CANARY_PREPARATION_REGISTRY_NAME,
        id_field="phase11_live_canary_preparation_registry_record_id",
        hash_field="phase11_live_canary_preparation_registry_record_sha256",
        id_prefix="phase11_live_canary_preparation_registry_record",
    )
    atomic_write_json(latest / "phase11_live_canary_preparation_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase11_live_canary_preparation_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE11_LIVE_CANARY_PREPARATION_VERSION",
    "STATUS_PHASE11_LIVE_CANARY_PREPARATION_RECORDED_BLOCKED_REVIEW_ONLY",
    "STATUS_PHASE11_LIVE_CANARY_PREPARATION_BLOCKED_REVIEW_ONLY",
    "LIVE_READ_ONLY_PROBE_CHECKS_REQUIRED",
    "LIVE_KEY_SCOPE_CHECKS_REQUIRED",
    "LIVE_CANARY_APPROVAL_FIELDS_REQUIRED",
    "build_phase11_live_canary_preparation_blocked_design_report",
    "persist_phase11_live_canary_preparation_blocked_design_report",
    "validate_phase11_live_canary_preparation_design",
]
