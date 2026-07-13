from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import (
    persist_phase9_1_single_signed_testnet_enablement_intake_report,
)

PHASE9_2_VERSION = "phase9_2_single_testnet_order_submit_v1"
PHASE9_2_REGISTRY_NAME = "phase9_2_single_testnet_order_submit_registry"
STATUS_RECORDED_BLOCKED_REVIEW_ONLY = "PHASE9_2_SINGLE_TESTNET_ORDER_SUBMIT_BLOCKED_REVIEW_ONLY"
STATUS_RECORDED_REVIEW_ONLY = "PHASE9_2_SINGLE_TESTNET_ORDER_SUBMIT_RECORDED_REVIEW_ONLY"

REQUIRED_PHASE9_2_SOURCE_FILES = {
    "phase9_1_report": "phase9_1_single_signed_testnet_enablement_intake_report.json",
    "phase9_1_intake": "single_signed_testnet_enablement_intake_REVIEW_ONLY.json",
    "phase9_1_guard": "single_signed_testnet_enablement_intake_guard_report.json",
    "phase8_3_hot_path_gate": "hot_path_preorder_risk_gate_review_only.json",
    "phase8_3_hot_path_guard": "hot_path_preorder_risk_gate_guard_report.json",
}

REQUIRED_PHASE9_2_SUBMIT_FIELDS = [
    "submit_attempt_type",
    "phase9_2_version",
    "source_phase9_1_intake_id",
    "source_phase9_1_intake_hash",
    "source_phase8_3_risk_gate_id",
    "source_phase8_3_risk_gate_hash",
    "single_order_scope",
    "max_order_count",
    "order_count_requested",
    "small_max_notional",
    "daily_loss_cap",
    "operator_decision",
    "operator_signature_present",
    "testnet_key_fingerprint_sha256_present",
    "kill_switch_confirmed_for_submit",
    "fresh_preorder_risk_gate_evidence_present",
    "idempotency_key_preview",
    "phase9_2_order_submission_authorized",
    "testnet_order_submission_allowed",
    "order_endpoint_called",
    "http_request_sent",
    "signature_created",
    "actual_order_submission_performed",
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
    "phase9_order_submission_authorized",
    "phase9_2_order_submission_authorized",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
]

FALSE_FLAGS = [
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
    "phase9_order_submission_authorized",
    "phase9_2_order_submission_authorized",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
]

REQUIRED_OPERATOR_APPROVAL_BLOCKERS = [
    "PHASE9_2_OPERATOR_DECISION_NOT_EXPLICIT_APPROVAL",
    "PHASE9_2_OPERATOR_SIGNATURE_MISSING",
    "PHASE9_2_TESTNET_KEY_FINGERPRINT_MISSING_OR_PLACEHOLDER",
    "PHASE9_2_KILL_SWITCH_NOT_CONFIRMED_FOR_SUBMIT",
    "PHASE9_2_PHASE9_1_ACTUAL_APPROVAL_INCOMPLETE",
    "PHASE9_2_PHASE9_1_SUBMIT_PERMISSION_FALSE",
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
        "phase9_2_report_sha256",
        "phase9_2_submit_attempt_sha256",
        "phase9_2_submit_guard_report_sha256",
        "phase9_1_report_sha256",
        "phase9_1_single_signed_testnet_enablement_intake_sha256",
        "phase9_1_single_signed_testnet_enablement_intake_guard_report_sha256",
        "hot_path_preorder_risk_gate_sha256",
        "hot_path_preorder_risk_gate_guard_report_sha256",
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
        "status": data.get("status") or data.get("intake_type") or data.get("guard_type") or data.get("gate_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data:
        return False
    if data.get("blocked") is True or data.get("fail_closed") is True:
        return False
    if _unsafe_fields(data):
        return False
    if name == "phase9_1_report":
        return (
            data.get("status") == "PHASE9_1_SINGLE_SIGNED_TESTNET_ENABLEMENT_INTAKE_RECORDED_REVIEW_ONLY"
            and data.get("phase9_1_single_signed_testnet_enablement_intake_ready") is True
            and data.get("phase9_1_actual_enablement_approval_complete") is True
            and data.get("phase9_2_single_testnet_order_submit_may_begin") is True
            and data.get("testnet_order_submission_allowed") is True
        )
    if name == "phase9_1_intake":
        return (
            data.get("intake_type") == "phase9_1_single_signed_testnet_enablement_intake_review_only"
            and data.get("operator_decision") == "approve_single_signed_testnet_order"
            and bool(data.get("operator_signature"))
            and _valid_fingerprint(data.get("testnet_key_fingerprint_sha256"))
            and data.get("actual_operator_approval_recorded") is True
            and data.get("kill_switch_confirmed_for_actual_approval") is True
            and data.get("phase9_2_single_testnet_order_submit_may_begin") is True
            and data.get("testnet_order_submission_allowed") is True
        )
    if name == "phase9_1_guard":
        return (
            data.get("guard_passed") is True
            and data.get("phase9_1_actual_enablement_approval_complete") is True
            and data.get("phase9_2_single_testnet_order_submit_may_begin") is True
        )
    if name == "phase8_3_hot_path_gate":
        return (
            data.get("gate_type") == "phase8_3_hot_path_preorder_risk_gate_review_only"
            and data.get("pre_submit_order_allowed") is False
            and data.get("no_order_endpoint_calls") is True
        )
    if name == "phase8_3_hot_path_guard":
        return data.get("guard_passed") is True
    return True


def _valid_fingerprint(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if len(stripped) < 32:
        return False
    placeholder_terms = {"placeholder", "required", "todo", "pending", "replace_me"}
    if any(term in stripped.lower() for term in placeholder_terms):
        return False
    return True


def _flag_false_payload() -> dict[str, bool]:
    return {field: False for field in FALSE_FLAGS}


def validate_phase9_2_single_testnet_order_submit_attempt(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    missing = [field for field in REQUIRED_PHASE9_2_SUBMIT_FIELDS if field not in data or data.get(field) in (None, "")]
    unsafe = _unsafe_fields(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_PHASE9_2_SUBMIT_FIELDS:" + ",".join(missing))
    if unsafe:
        blockers.append("UNSAFE_PHASE9_2_SUBMIT_FLAGS:" + ",".join(unsafe))
    if data.get("submit_attempt_type") != "phase9_2_single_testnet_order_submit_blocked_review_only":
        blockers.append("INVALID_PHASE9_2_SUBMIT_ATTEMPT_TYPE")
    if data.get("review_only") is not True:
        blockers.append("PHASE9_2_REVIEW_ONLY_NOT_TRUE")
    if data.get("single_order_scope") is not True:
        blockers.append("PHASE9_2_SINGLE_ORDER_SCOPE_NOT_TRUE")
    if int(data.get("max_order_count") or 0) != 1:
        blockers.append("PHASE9_2_MAX_ORDER_COUNT_NOT_ONE")
    if int(data.get("order_count_requested") or 0) != 1:
        blockers.append("PHASE9_2_ORDER_COUNT_REQUESTED_NOT_ONE")
    try:
        small_max_notional = float(data.get("small_max_notional"))
    except (TypeError, ValueError):
        small_max_notional = -1.0
    if not (0 < small_max_notional <= 10.0):
        blockers.append("PHASE9_2_SMALL_MAX_NOTIONAL_INVALID_OR_TOO_HIGH")
    try:
        daily_loss_cap = float(data.get("daily_loss_cap"))
    except (TypeError, ValueError):
        daily_loss_cap = -1.0
    if not (0 < daily_loss_cap <= 15.0):
        blockers.append("PHASE9_2_DAILY_LOSS_CAP_INVALID_OR_TOO_HIGH")
    if data.get("fresh_preorder_risk_gate_evidence_present") is not True:
        blockers.append("PHASE9_2_FRESH_PREORDER_RISK_GATE_EVIDENCE_MISSING")
    if not data.get("idempotency_key_preview"):
        blockers.append("PHASE9_2_IDEMPOTENCY_KEY_PREVIEW_MISSING")
    if data.get("operator_decision") != "approve_single_signed_testnet_order":
        blockers.append("PHASE9_2_OPERATOR_DECISION_NOT_EXPLICIT_APPROVAL")
    if data.get("operator_signature_present") is not True:
        blockers.append("PHASE9_2_OPERATOR_SIGNATURE_MISSING")
    if data.get("testnet_key_fingerprint_sha256_present") is not True:
        blockers.append("PHASE9_2_TESTNET_KEY_FINGERPRINT_MISSING_OR_PLACEHOLDER")
    if data.get("kill_switch_confirmed_for_submit") is not True:
        blockers.append("PHASE9_2_KILL_SWITCH_NOT_CONFIRMED_FOR_SUBMIT")
    if data.get("phase9_1_actual_enablement_approval_complete") is not True:
        blockers.append("PHASE9_2_PHASE9_1_ACTUAL_APPROVAL_INCOMPLETE")
    if data.get("source_phase9_1_submit_permission") is not True:
        blockers.append("PHASE9_2_PHASE9_1_SUBMIT_PERMISSION_FALSE")
    for field in FALSE_FLAGS:
        if data.get(field) is not False:
            blockers.append(f"REQUIRED_PHASE9_2_FALSE_FLAG_NOT_FALSE:{field}")
    valid = not blockers
    return {
        "phase9_2_single_testnet_order_submit_attempt_valid": valid,
        "phase9_2_single_testnet_order_submit_blocked_fail_closed": not valid,
        "phase9_2_submit_attempt_blockers": sorted(dict.fromkeys(blockers)),
        "missing_required_fields": missing,
        "unsafe_truthy_fields": unsafe,
        "phase9_2_order_submission_authorized": False,
        "testnet_order_submission_allowed": False,
        "actual_order_submission_performed": False,
    }


def _build_submit_attempt(*, report_id: str, sources: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    phase9_1_report = dict(sources.get("phase9_1_report") or {})
    phase9_1_intake = dict(sources.get("phase9_1_intake") or {})
    phase8_3_gate = dict(sources.get("phase8_3_hot_path_gate") or {})
    hot_path_chain = dict(phase8_3_gate.get("canonical_id_chain") or {})
    risk_limits = dict(phase8_3_gate.get("risk_limits") or {})
    idempotency_key = stable_id(
        "phase9_2_blocked_idempotency_key_preview",
        {
            "phase9_1_intake_hash": _artifact_hash(phase9_1_intake),
            "phase8_3_gate_hash": _artifact_hash(phase8_3_gate),
            "created_at_utc": created_at_utc,
        },
        24,
    )
    approval_complete = phase9_1_report.get("phase9_1_actual_enablement_approval_complete") is True
    submit_permission = phase9_1_report.get("phase9_2_single_testnet_order_submit_may_begin") is True
    attempt: dict[str, Any] = {
        "submit_attempt_type": "phase9_2_single_testnet_order_submit_blocked_review_only",
        "phase9_2_version": PHASE9_2_VERSION,
        "source_phase9_2_report_id": report_id,
        "source_phase9_1_intake_id": phase9_1_report.get("phase9_1_single_signed_testnet_enablement_intake_id") or phase9_1_intake.get("source_phase9_1_report_id"),
        "source_phase9_1_intake_hash": phase9_1_report.get("phase9_1_single_signed_testnet_enablement_intake_sha256") or phase9_1_intake.get("phase9_1_single_signed_testnet_enablement_intake_sha256"),
        "source_phase9_1_report_hash": phase9_1_report.get("phase9_1_report_sha256"),
        "source_phase8_3_risk_gate_id": phase8_3_gate.get("source_phase8_3_report_id") or phase9_1_intake.get("source_phase8_3_risk_gate_id"),
        "source_phase8_3_risk_gate_hash": phase8_3_gate.get("hot_path_preorder_risk_gate_sha256") or phase9_1_intake.get("source_phase8_3_risk_gate_hash"),
        "source_evidence_hash_summary": {name: _source_summary(name, payload) for name, payload in sources.items()},
        "canonical_id_chain": hot_path_chain,
        "single_order_scope": phase9_1_intake.get("single_order_scope") is True,
        "max_order_count": int(phase9_1_intake.get("max_order_count") or 1),
        "order_count_requested": 1,
        "small_max_notional": str(phase9_1_intake.get("small_max_notional") or risk_limits.get("min_order_notional") or "5.0"),
        "daily_loss_cap": str(phase9_1_intake.get("daily_loss_cap") or risk_limits.get("daily_loss_cap") or "15.0"),
        "operator_decision": phase9_1_intake.get("operator_decision"),
        "operator_signature_present": bool(phase9_1_intake.get("operator_signature")),
        "testnet_key_fingerprint_sha256_present": _valid_fingerprint(phase9_1_intake.get("testnet_key_fingerprint_sha256")),
        "kill_switch_confirmed_for_submit": phase9_1_intake.get("kill_switch_confirmed_for_actual_approval") is True,
        "phase9_1_actual_enablement_approval_complete": approval_complete,
        "source_phase9_1_submit_permission": submit_permission,
        "fresh_preorder_risk_gate_evidence_present": bool(phase8_3_gate),
        "fresh_preorder_risk_gate_refresh_required_immediately_before_real_submit": True,
        "idempotency_key_preview": idempotency_key,
        "idempotency_key_is_preview_only": True,
        "dry_order_payload_preview": {
            "symbol": "BTCUSDT",
            "side": "UNSET_PENDING_OPERATOR_APPROVAL",
            "order_type": "LIMIT_OR_MARKET_UNSET_PENDING_OPERATOR_APPROVAL",
            "notional_cap": str(phase9_1_intake.get("small_max_notional") or "5.0"),
            "reduce_only": False,
            "client_order_id_preview": idempotency_key,
            "no_signature_created": True,
            "no_http_request_sent": True,
            "no_order_endpoint_called": True,
        },
        "phase9_2_order_submission_authorized": False,
        "phase9_2_blocked_until_actual_operator_approval": True,
        "review_only": True,
        "not_runtime_authority": True,
        "blocks_signed_testnet_execution": True,
        "blocks_order_submission": True,
        **_flag_false_payload(),
        "created_at_utc": created_at_utc,
    }
    attempt["phase9_2_submit_attempt_sha256"] = sha256_json(attempt)
    return attempt


def _build_guard_report(*, report_id: str, submit_attempt: Mapping[str, Any], validation_result: Mapping[str, Any], sources_ready: bool, created_at_utc: str) -> dict[str, Any]:
    blocked = True
    guard = {
        "guard_type": "phase9_2_single_testnet_order_submit_guard_report_blocked_review_only",
        "phase9_2_version": PHASE9_2_VERSION,
        "source_phase9_2_report_id": report_id,
        "review_only": True,
        "guard_passed": False,
        "guard_blocked_fail_closed": True,
        "all_required_phase9_1_and_hot_path_evidence_ready_for_actual_submit": sources_ready,
        "submit_attempt_validation_result": dict(validation_result),
        "phase9_2_order_submission_authorized": False,
        "phase9_2_submit_attempt_blocked": blocked,
        "phase9_3_status_polling_may_begin": False,
        "phase9_2_blocked_until_actual_operator_approval": True,
        "required_before_unblocking_phase9_2": REQUIRED_OPERATOR_APPROVAL_BLOCKERS,
        **_flag_false_payload(),
        "created_at_utc": created_at_utc,
    }
    guard["phase9_2_submit_guard_report_sha256"] = sha256_json(guard)
    return guard


def _build_negative_fixture_results(submit_attempt: Mapping[str, Any]) -> dict[str, Any]:
    cases: dict[str, dict[str, Any]] = {
        "operator_approval_missing": {"operator_decision": "pending_explicit_manual_approval"},
        "unsafe_testnet_order_submission_allowed": {"testnet_order_submission_allowed": True},
        "order_endpoint_called_true": {"order_endpoint_called": True},
        "http_request_sent_true": {"http_request_sent": True},
        "signature_created_true": {"signature_created": True},
        "order_count_gt_one": {"order_count_requested": 2},
        "notional_too_high": {"small_max_notional": "1000.0"},
        "missing_fresh_hot_path_risk_gate": {"fresh_preorder_risk_gate_evidence_present": False},
    }
    fixtures: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(submit_attempt)
        payload.update(patch)
        result = validate_phase9_2_single_testnet_order_submit_attempt(payload)
        blockers = result.get("phase9_2_submit_attempt_blockers") or []
        fixtures[name] = {
            "fixture_name": name,
            "blocked": bool(blockers),
            "fail_closed": bool(blockers),
            "block_reasons": blockers,
        }
    all_blocked = all(item["blocked"] is True and item["fail_closed"] is True for item in fixtures.values())
    return {
        "artifact_type": "phase9_2_single_testnet_order_submit_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": fixtures,
        **_flag_false_payload(),
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 9.2 Single Testnet Order Submit - Blocked Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact creates the Phase 9.2 submit guard path but does not submit a signed testnet order. The current Phase 9.1 intake does not contain completed actual operator approval, operator signature, metadata-only testnet key fingerprint, and kill-switch confirmation.",
            "",
            "## Result",
            "",
            f"- Submit attempt recorded: `{report.get('phase9_2_single_testnet_order_submit_attempt_recorded')}`",
            f"- Submit blocked fail-closed: `{report.get('phase9_2_single_testnet_order_submit_blocked_fail_closed')}`",
            f"- Phase 9.3 status polling may begin: `{report.get('phase9_3_status_polling_may_begin')}`",
            "",
            "## Safety Flags",
            "",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `actual_order_submission_performed=false`",
            "- `order_endpoint_called=false`",
            "- `signature_created=false`",
            "- `http_request_sent=false`",
            "",
            "## Blockers",
            "",
            blocker_lines,
            "",
            "## Next Allowed Scope",
            "",
            f"`{report.get('phase9_2_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase9_2_single_testnet_order_submit_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_1_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase9_1_first:
        persist_phase9_1_single_signed_testnet_enablement_intake_report(cfg=cfg)

    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_PHASE9_2_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}

    preliminary_blockers: list[str] = []
    preliminary_blockers.extend([f"MISSING_PHASE9_2_REQUIRED_EVIDENCE:{name}" for name in missing])
    preliminary_blockers.extend([f"PHASE9_2_REQUIRED_EVIDENCE_NOT_READY:{name}" for name in not_ready])
    if unsafe:
        preliminary_blockers.extend([f"UNSAFE_PHASE9_2_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    preliminary_blockers = sorted(dict.fromkeys(str(item) for item in preliminary_blockers if item))
    sources_ready = not preliminary_blockers

    preliminary_id = stable_id("phase9_2_single_testnet_order_submit", {"source_summary": source_summary, "created_at_utc": created}, 24)
    submit_attempt = _build_submit_attempt(report_id=preliminary_id, sources=sources, created_at_utc=created)
    validation_result = validate_phase9_2_single_testnet_order_submit_attempt(submit_attempt)
    guard_report = _build_guard_report(
        report_id=preliminary_id,
        submit_attempt=submit_attempt,
        validation_result=validation_result,
        sources_ready=sources_ready,
        created_at_utc=created,
    )

    blockers = list(preliminary_blockers)
    blockers.extend(validation_result.get("phase9_2_submit_attempt_blockers") or [])
    if guard_report.get("guard_blocked_fail_closed") is not True:
        blockers.append("PHASE9_2_GUARD_DID_NOT_FAIL_CLOSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))

    report_id = stable_id(
        "phase9_2_single_testnet_order_submit",
        {
            "source_summary": source_summary,
            "submit_attempt_hash": sha256_json(submit_attempt),
            "guard_report_hash": sha256_json(guard_report),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    submit_attempt["source_phase9_2_report_id"] = report_id
    submit_attempt["phase9_2_submit_attempt_sha256"] = sha256_json(submit_attempt)
    validation_result = validate_phase9_2_single_testnet_order_submit_attempt(submit_attempt)
    guard_report = _build_guard_report(
        report_id=report_id,
        submit_attempt=submit_attempt,
        validation_result=validation_result,
        sources_ready=sources_ready,
        created_at_utc=created,
    )
    blockers = list(preliminary_blockers)
    blockers.extend(validation_result.get("phase9_2_submit_attempt_blockers") or [])
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    negative_fixture_results = _build_negative_fixture_results(submit_attempt)

    report: dict[str, Any] = {
        "phase9_2_single_testnet_order_submit_id": report_id,
        "phase9_2_version": PHASE9_2_VERSION,
        "status": STATUS_RECORDED_BLOCKED_REVIEW_ONLY,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "phase9_2_single_testnet_order_submit_attempt_recorded": True,
        "phase9_2_single_testnet_order_submit_blocked_fail_closed": True,
        "phase9_2_submit_guard_created": True,
        "phase9_2_submit_guard_passed": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_2_blocked_until_actual_operator_approval": True,
        "phase9_3_status_polling_may_begin": False,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_flags_by_artifact": unsafe,
        "submit_attempt_validation_result": validation_result,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": blockers,
        "phase9_2_allowed_next_scope": "return_to_phase9_1_collect_actual_operator_approval_signature_key_fingerprint_and_kill_switch_confirmation",
        "recommended_next_action": "do_not_submit_order_complete_phase9_1_actual_approval_then_rerun_phase9_2_guard",
        "runtime_permission_source": False,
        "phase9_2_execution_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        **_flag_false_payload(),
        "created_at_utc": created,
    }
    report["phase9_2_submit_attempt_sha256"] = submit_attempt["phase9_2_submit_attempt_sha256"]
    report["phase9_2_submit_guard_report_sha256"] = guard_report["phase9_2_submit_guard_report_sha256"]
    report["phase9_2_report_sha256"] = sha256_json(report)
    return report, submit_attempt, guard_report, negative_fixture_results


def persist_phase9_2_single_testnet_order_submit_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_1_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_single_testnet_order_submit")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, submit_attempt, guard_report, negative_fixture_results = build_phase9_2_single_testnet_order_submit_report(
        cfg=cfg,
        run_phase9_1_first=run_phase9_1_first,
    )
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase9_2_single_testnet_order_submit_report.json", report)
    atomic_write_json(latest / "single_testnet_order_submit_BLOCKED_REVIEW_ONLY.json", submit_attempt)
    atomic_write_json(latest / "single_testnet_order_submit_guard_report.json", guard_report)
    atomic_write_json(latest / "phase9_2_negative_fixture_results.json", negative_fixture_results)
    (latest / "PHASE9_2_SINGLE_TESTNET_ORDER_SUBMIT_HANDOFF_BLOCKED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(signed_testnet_dir / "phase9_2_single_testnet_order_submit_report.json", report)
    atomic_write_json(signed_testnet_dir / "single_testnet_order_submit_BLOCKED_REVIEW_ONLY.json", submit_attempt)
    atomic_write_json(signed_testnet_dir / "single_testnet_order_submit_guard_report.json", guard_report)

    atomic_write_json(phase_dir / "phase9_2_single_testnet_order_submit_report.json", report)
    atomic_write_json(phase_dir / "single_testnet_order_submit_BLOCKED_REVIEW_ONLY.json", submit_attempt)
    atomic_write_json(phase_dir / "single_testnet_order_submit_guard_report.json", guard_report)
    atomic_write_json(phase_dir / "phase9_2_negative_fixture_results.json", negative_fixture_results)
    (phase_dir / "PHASE9_2_SINGLE_TESTNET_ORDER_SUBMIT_HANDOFF_BLOCKED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_REGISTRY_NAME),
        {
            "phase9_2_single_testnet_order_submit_id": report.get("phase9_2_single_testnet_order_submit_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "phase9_2_order_submission_authorized": False,
            "phase9_2_single_testnet_order_submit_blocked_fail_closed": True,
            "phase9_3_status_polling_may_begin": False,
            "actual_executor_enablement_performed": False,
            "actual_order_submission_performed": False,
            "exchange_endpoint_called": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_2_REGISTRY_NAME,
        id_field="phase9_2_single_testnet_order_submit_registry_record_id",
        hash_field="phase9_2_single_testnet_order_submit_registry_record_sha256",
        id_prefix="phase9_2_single_testnet_order_submit_registry_record",
    )
    atomic_write_json(latest / "phase9_2_single_testnet_order_submit_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_single_testnet_order_submit_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_VERSION",
    "STATUS_RECORDED_BLOCKED_REVIEW_ONLY",
    "STATUS_RECORDED_REVIEW_ONLY",
    "validate_phase9_2_single_testnet_order_submit_attempt",
    "build_phase9_2_single_testnet_order_submit_report",
    "persist_phase9_2_single_testnet_order_submit_report",
]
