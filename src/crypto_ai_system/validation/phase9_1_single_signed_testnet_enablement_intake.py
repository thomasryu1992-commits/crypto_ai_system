from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase8_4_signed_testnet_executor_final_guard import (
    persist_phase8_4_signed_testnet_executor_final_guard_report,
)

PHASE9_1_VERSION = "phase9_1_single_signed_testnet_enablement_intake_v1"
PHASE9_1_REGISTRY_NAME = "phase9_1_single_signed_testnet_enablement_intake_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE9_1_SINGLE_SIGNED_TESTNET_ENABLEMENT_INTAKE_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE9_1_SINGLE_SIGNED_TESTNET_ENABLEMENT_INTAKE_BLOCKED_REVIEW_ONLY"

REQUIRED_PHASE9_1_SOURCE_FILES = {
    "phase8_4_report": "phase8_4_signed_testnet_executor_final_guard_report.json",
    "phase8_4_final_guard": "signed_testnet_executor_final_guard_review_only.json",
    "phase8_4_guard_report": "signed_testnet_executor_final_guard_guard_report.json",
    "phase8_4_disabled_flags": "still_disabled_executor_enablement_flags.json",
    "phase8_3_hot_path_gate": "hot_path_preorder_risk_gate_review_only.json",
    "phase8_3_hot_path_guard": "hot_path_preorder_risk_gate_guard_report.json",
}

REQUIRED_PHASE9_1_INTAKE_FIELDS = [
    "intake_type",
    "phase9_1_version",
    "source_phase8_4_final_guard_id",
    "source_phase8_4_final_guard_hash",
    "source_phase8_3_risk_gate_id",
    "source_phase8_3_risk_gate_hash",
    "operator_decision",
    "operator_signature_placeholder",
    "approval_scope",
    "single_order_scope",
    "max_order_count",
    "small_max_notional",
    "daily_loss_cap",
    "kill_switch_confirmation_required",
    "kill_switch_confirmed_for_actual_approval",
    "testnet_only_key_fingerprint_required",
    "testnet_key_fingerprint_sha256",
    "fresh_preorder_risk_gate_evidence_required",
    "fresh_preorder_risk_gate_evidence_present",
    "phase9_2_single_testnet_order_submit_may_begin",
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
    "phase9_2_single_testnet_order_submit_may_begin",
    "phase9_order_submission_authorized",
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
    "phase9_2_single_testnet_order_submit_may_begin",
    "phase9_order_submission_authorized",
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

PENDING_ACTUAL_APPROVAL_CONDITIONS = [
    "explicit_operator_decision_approve_single_testnet_order_required",
    "operator_signature_required",
    "testnet_only_key_fingerprint_sha256_required",
    "manual_kill_switch_confirmation_required",
    "fresh_preorder_risk_gate_refresh_required_immediately_before_phase9_2",
    "phase9_2_single_order_submit_script_must_still_be_separately_reviewed",
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
        "phase9_1_report_sha256",
        "phase9_1_single_signed_testnet_enablement_intake_sha256",
        "phase9_1_single_signed_testnet_enablement_intake_guard_report_sha256",
        "phase8_4_report_sha256",
        "signed_testnet_executor_final_guard_sha256",
        "signed_testnet_executor_final_guard_guard_report_sha256",
        "still_disabled_execution_flags_sha256",
        "phase8_3_report_sha256",
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
        "status": data.get("status") or data.get("guard_type") or data.get("gate_type") or data.get("artifact_type"),
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
    if name == "phase8_4_report":
        return (
            data.get("status") == "PHASE8_4_SIGNED_TESTNET_EXECUTOR_FINAL_GUARD_RECORDED_REVIEW_ONLY"
            and data.get("phase8_4_signed_testnet_executor_final_guard_ready") is True
            and data.get("phase9_1_single_signed_testnet_enablement_intake_may_begin") is True
            and data.get("phase9_order_submission_not_authorized_by_phase8_4") is True
        )
    if name == "phase8_4_final_guard":
        return (
            data.get("guard_type") == "phase8_4_signed_testnet_executor_final_guard_review_only"
            and data.get("phase8_4_passes_for_phase9_intake_preparation_only") is True
            and data.get("phase9_explicit_single_order_operator_intake_required") is True
            and data.get("phase9_order_submission_not_authorized_by_phase8_4") is True
        )
    if name == "phase8_4_guard_report":
        return data.get("guard_passed") is True and data.get("phase9_1_single_signed_testnet_enablement_intake_may_begin") is True
    if name == "phase8_4_disabled_flags":
        return data.get("artifact_type") == "phase8_4_still_disabled_executor_enablement_flags"
    if name == "phase8_3_hot_path_gate":
        return (
            data.get("gate_type") == "phase8_3_hot_path_preorder_risk_gate_review_only"
            and data.get("phase9_explicit_single_order_intake_required") is True
            and data.get("no_order_endpoint_calls") is True
            and data.get("pre_submit_order_allowed") is False
            and data.get("future_executor_review_may_submit_order") is False
        )
    if name == "phase8_3_hot_path_guard":
        return data.get("guard_passed") is True and data.get("phase8_4_final_guard_may_begin") is True
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


def validate_phase9_1_single_signed_testnet_enablement_intake(
    payload: Mapping[str, Any], *, require_actual_operator_approval: bool = False
) -> dict[str, Any]:
    data = dict(payload or {})
    missing = [field for field in REQUIRED_PHASE9_1_INTAKE_FIELDS if field not in data or data.get(field) in (None, "")]
    unsafe = _unsafe_fields(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_PHASE9_1_INTAKE_FIELDS:" + ",".join(missing))
    if unsafe:
        blockers.append("UNSAFE_PHASE9_1_INTAKE_FLAGS:" + ",".join(unsafe))
    if data.get("intake_type") != "phase9_1_single_signed_testnet_enablement_intake_review_only":
        blockers.append("INVALID_PHASE9_1_INTAKE_TYPE")
    if data.get("review_only") is not True:
        blockers.append("PHASE9_1_INTAKE_REVIEW_ONLY_NOT_TRUE")
    if data.get("single_order_scope") is not True:
        blockers.append("PHASE9_1_SINGLE_ORDER_SCOPE_NOT_TRUE")
    if int(data.get("max_order_count") or 0) != 1:
        blockers.append("PHASE9_1_MAX_ORDER_COUNT_NOT_ONE")
    try:
        small_max_notional = float(data.get("small_max_notional"))
    except (TypeError, ValueError):
        small_max_notional = -1.0
    if not (0 < small_max_notional <= 10.0):
        blockers.append("PHASE9_1_SMALL_MAX_NOTIONAL_INVALID_OR_TOO_HIGH")
    try:
        daily_loss_cap = float(data.get("daily_loss_cap"))
    except (TypeError, ValueError):
        daily_loss_cap = -1.0
    if not (0 < daily_loss_cap <= 15.0):
        blockers.append("PHASE9_1_DAILY_LOSS_CAP_INVALID_OR_TOO_HIGH")
    if data.get("approval_scope") not in {"single_signed_testnet_order_intake_only", "review_only_single_signed_testnet_order_preparation"}:
        blockers.append("PHASE9_1_APPROVAL_SCOPE_INVALID")
    if data.get("fresh_preorder_risk_gate_evidence_present") is not True:
        blockers.append("PHASE9_1_FRESH_PREORDER_RISK_GATE_EVIDENCE_MISSING")
    if data.get("kill_switch_confirmation_required") is not True:
        blockers.append("PHASE9_1_KILL_SWITCH_CONFIRMATION_REQUIREMENT_MISSING")
    for field in FALSE_FLAGS:
        if data.get(field) is not False:
            blockers.append(f"REQUIRED_PHASE9_1_FALSE_FLAG_NOT_FALSE:{field}")
    actual_approval_blockers: list[str] = []
    if data.get("operator_decision") != "approve_single_signed_testnet_order":
        actual_approval_blockers.append("PHASE9_1_OPERATOR_DECISION_NOT_EXPLICIT_APPROVAL")
    if not data.get("operator_signature"):
        actual_approval_blockers.append("PHASE9_1_OPERATOR_SIGNATURE_MISSING")
    if data.get("kill_switch_confirmed_for_actual_approval") is not True:
        actual_approval_blockers.append("PHASE9_1_KILL_SWITCH_NOT_CONFIRMED_FOR_ACTUAL_APPROVAL")
    if not _valid_fingerprint(data.get("testnet_key_fingerprint_sha256")):
        actual_approval_blockers.append("PHASE9_1_TESTNET_KEY_FINGERPRINT_MISSING_OR_PLACEHOLDER")
    if data.get("actual_operator_approval_recorded") is not True:
        actual_approval_blockers.append("PHASE9_1_ACTUAL_OPERATOR_APPROVAL_NOT_RECORDED")
    if require_actual_operator_approval:
        blockers.extend(actual_approval_blockers)
    valid_template = not blockers
    return {
        "phase9_1_single_signed_testnet_enablement_intake_valid_review_only": valid_template,
        "phase9_1_single_signed_testnet_enablement_intake_blocked_fail_closed": not valid_template,
        "phase9_1_actual_enablement_approval_complete": not actual_approval_blockers,
        "phase9_1_actual_approval_blockers": sorted(dict.fromkeys(actual_approval_blockers)),
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "missing_required_fields": missing,
        "unsafe_truthy_fields": unsafe,
        "phase9_1_intake_blockers": sorted(dict.fromkeys(blockers)),
    }


def _build_intake(*, report_id: str, sources: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    phase8_4_report = dict(sources.get("phase8_4_report") or {})
    phase8_4_final_guard = dict(sources.get("phase8_4_final_guard") or {})
    phase8_3_gate = dict(sources.get("phase8_3_hot_path_gate") or {})
    risk_limits = dict(phase8_3_gate.get("risk_limits") or {})
    hot_path_chain = dict(phase8_3_gate.get("canonical_id_chain") or {})
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    intake: dict[str, Any] = {
        "intake_type": "phase9_1_single_signed_testnet_enablement_intake_review_only",
        "phase9_1_version": PHASE9_1_VERSION,
        "source_phase9_1_report_id": report_id,
        "source_phase8_4_final_guard_id": phase8_4_report.get("phase8_4_signed_testnet_executor_final_guard_id") or phase8_4_final_guard.get("source_phase8_4_report_id"),
        "source_phase8_4_final_guard_hash": phase8_4_report.get("phase8_4_report_sha256") or phase8_4_final_guard.get("signed_testnet_executor_final_guard_sha256"),
        "source_phase8_3_risk_gate_id": phase8_3_gate.get("source_phase8_3_report_id"),
        "source_phase8_3_risk_gate_hash": phase8_3_gate.get("hot_path_preorder_risk_gate_sha256"),
        "source_evidence_hash_summary": source_summary,
        "canonical_id_chain": hot_path_chain,
        "operator_decision": "pending_explicit_manual_approval",
        "actual_operator_approval_recorded": False,
        "operator_signature": None,
        "operator_signature_placeholder": "REQUIRED_EXPLICIT_OPERATOR_SIGNATURE_BEFORE_PHASE9_2",
        "approval_scope": "single_signed_testnet_order_intake_only",
        "single_order_scope": True,
        "max_order_count": 1,
        "small_max_notional": str(risk_limits.get("min_order_notional") or "5.0"),
        "daily_loss_cap": str(risk_limits.get("daily_loss_cap") or "15.0"),
        "kill_switch_confirmation_required": True,
        "kill_switch_confirmed_for_actual_approval": False,
        "testnet_only_key_fingerprint_required": True,
        "testnet_key_fingerprint_sha256": "REQUIRED_OPERATOR_SUPPLIED_METADATA_ONLY_TESTNET_KEY_FINGERPRINT_SHA256",
        "fresh_preorder_risk_gate_evidence_required": True,
        "fresh_preorder_risk_gate_evidence_present": bool(phase8_3_gate),
        "fresh_preorder_risk_gate_refresh_required_immediately_before_phase9_2": True,
        "idempotency_key_required_for_phase9_2": True,
        "complete_canonical_id_chain_required_for_phase9_2": True,
        "phase9_2_order_submit_script_required": True,
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "phase9_2_order_submission_not_authorized_by_phase9_1_template": True,
        "review_only": True,
        "intake_template_only_until_operator_values_are_supplied": True,
        "not_runtime_authority": True,
        "blocks_signed_testnet_execution": True,
        "blocks_order_submission": True,
        "pending_actual_approval_conditions": PENDING_ACTUAL_APPROVAL_CONDITIONS,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "order_submission_performed": False,
        "phase9_order_submission_authorized": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "created_at_utc": created_at_utc,
    }
    intake["phase9_1_single_signed_testnet_enablement_intake_sha256"] = sha256_json(intake)
    return intake


def _build_guard_report(*, report_id: str, intake: Mapping[str, Any], validation_result: Mapping[str, Any], sources_ready: bool, created_at_utc: str) -> dict[str, Any]:
    guard_passed = sources_ready and validation_result.get("phase9_1_single_signed_testnet_enablement_intake_valid_review_only") is True
    guard = {
        "guard_type": "phase9_1_single_signed_testnet_enablement_intake_guard_report_review_only",
        "phase9_1_version": PHASE9_1_VERSION,
        "source_phase9_1_report_id": report_id,
        "review_only": True,
        "guard_passed": guard_passed,
        "all_required_phase8_4_and_hot_path_evidence_ready": sources_ready,
        "intake_validation_result": dict(validation_result),
        "phase9_1_intake_template_ready": guard_passed,
        "phase9_1_actual_enablement_approval_complete": False,
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "phase9_2_order_submission_not_authorized_by_phase9_1": True,
        "blocks_signed_testnet_execution": True,
        "blocks_order_submission": True,
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
        "created_at_utc": created_at_utc,
    }
    guard["phase9_1_single_signed_testnet_enablement_intake_guard_report_sha256"] = sha256_json(guard)
    return guard


def _build_negative_fixture_results(intake: Mapping[str, Any]) -> dict[str, Any]:
    fixtures: dict[str, dict[str, Any]] = {}
    cases: dict[str, dict[str, Any]] = {
        "max_order_count_gt_one": {"max_order_count": 2},
        "small_max_notional_too_high": {"small_max_notional": "1000.0"},
        "missing_key_fingerprint": {"testnet_key_fingerprint_sha256": "REQUIRED_OPERATOR_SUPPLIED_METADATA_ONLY_TESTNET_KEY_FINGERPRINT_SHA256"},
        "kill_switch_not_confirmed_for_actual_approval": {"operator_decision": "approve_single_signed_testnet_order", "operator_signature": "operator_sig_example", "actual_operator_approval_recorded": True, "kill_switch_confirmed_for_actual_approval": False, "testnet_key_fingerprint_sha256": "a" * 64},
        "unsafe_order_submission_flag_true": {"testnet_order_submission_allowed": True},
        "phase9_2_submit_flag_true": {"phase9_2_single_testnet_order_submit_may_begin": True},
    }
    for name, patch in cases.items():
        payload = dict(intake)
        payload.update(patch)
        require_actual = name in {"missing_key_fingerprint", "kill_switch_not_confirmed_for_actual_approval"}
        result = validate_phase9_1_single_signed_testnet_enablement_intake(payload, require_actual_operator_approval=require_actual)
        blockers = result.get("phase9_1_intake_blockers") or result.get("phase9_1_actual_approval_blockers") or []
        fixtures[name] = {
            "fixture_name": name,
            "blocked": bool(blockers) or result.get("phase9_1_actual_enablement_approval_complete") is False,
            "fail_closed": bool(blockers) or result.get("phase9_1_actual_enablement_approval_complete") is False,
            "block_reasons": sorted(dict.fromkeys(list(blockers) + list(result.get("phase9_1_actual_approval_blockers") or []))),
        }
    all_blocked = all(item["blocked"] is True and item["fail_closed"] is True for item in fixtures.values())
    return {
        "artifact_type": "phase9_1_single_signed_testnet_enablement_intake_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": fixtures,
        "actual_order_submission_performed": False,
        "testnet_order_submission_allowed": False,
        "signed_order_executor_enabled": False,
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 9.1 Single Signed Testnet Enablement Intake - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact records the Phase 9.1 intake boundary for a future single signed testnet order. It does not submit an order and does not enable executor runtime switches.",
            "",
            "## Result",
            "",
            f"- Intake template ready: `{report.get('phase9_1_single_signed_testnet_enablement_intake_ready')}`",
            f"- Actual operator approval complete: `{report.get('phase9_1_actual_enablement_approval_complete')}`",
            f"- Phase 9.2 order submit may begin: `{report.get('phase9_2_single_testnet_order_submit_may_begin')}`",
            "",
            "## Required Before Phase 9.2",
            "",
            "- Explicit operator decision: `approve_single_signed_testnet_order`",
            "- Operator signature",
            "- Testnet-only key fingerprint metadata",
            "- Manual kill switch confirmation",
            "- Fresh PreOrderRiskGate evidence immediately before submit",
            "- Separate Phase 9.2 submit module and guard review",
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
            f"`{report.get('phase9_1_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase9_1_single_signed_testnet_enablement_intake_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase8_4_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase8_4_first:
        persist_phase8_4_signed_testnet_executor_final_guard_report(cfg=cfg)

    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_PHASE9_1_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}

    preliminary_blockers: list[str] = []
    preliminary_blockers.extend([f"MISSING_PHASE9_1_REQUIRED_EVIDENCE:{name}" for name in missing])
    preliminary_blockers.extend([f"PHASE9_1_REQUIRED_EVIDENCE_NOT_READY:{name}" for name in not_ready])
    if unsafe:
        preliminary_blockers.extend([f"UNSAFE_PHASE9_1_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    preliminary_blockers = sorted(dict.fromkeys(str(item) for item in preliminary_blockers if item))
    sources_ready = not preliminary_blockers

    preliminary_id = stable_id("phase9_1_single_signed_testnet_enablement_intake", {"source_summary": source_summary, "created_at_utc": created}, 24)
    intake = _build_intake(report_id=preliminary_id, sources=sources, created_at_utc=created)
    validation_result = validate_phase9_1_single_signed_testnet_enablement_intake(intake)
    guard_report = _build_guard_report(report_id=preliminary_id, intake=intake, validation_result=validation_result, sources_ready=sources_ready, created_at_utc=created)

    blockers = list(preliminary_blockers)
    if validation_result.get("phase9_1_single_signed_testnet_enablement_intake_valid_review_only") is not True:
        blockers.extend(validation_result.get("phase9_1_intake_blockers") or ["PHASE9_1_INTAKE_INVALID"])
    if guard_report.get("guard_passed") is not True:
        blockers.append("PHASE9_1_INTAKE_GUARD_NOT_PASSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY

    report_id = stable_id(
        "phase9_1_single_signed_testnet_enablement_intake",
        {
            "source_summary": source_summary,
            "intake_hash": sha256_json(intake),
            "guard_report_hash": sha256_json(guard_report),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    intake["source_phase9_1_report_id"] = report_id
    intake["phase9_1_single_signed_testnet_enablement_intake_sha256"] = sha256_json(intake)
    validation_result = validate_phase9_1_single_signed_testnet_enablement_intake(intake)
    guard_report = _build_guard_report(report_id=report_id, intake=intake, validation_result=validation_result, sources_ready=sources_ready, created_at_utc=created)
    blockers = list(preliminary_blockers)
    if validation_result.get("phase9_1_single_signed_testnet_enablement_intake_valid_review_only") is not True:
        blockers.extend(validation_result.get("phase9_1_intake_blockers") or ["PHASE9_1_INTAKE_INVALID"])
    if guard_report.get("guard_passed") is not True:
        blockers.append("PHASE9_1_INTAKE_GUARD_NOT_PASSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    negative_fixture_results = _build_negative_fixture_results(intake)

    report: dict[str, Any] = {
        "phase9_1_single_signed_testnet_enablement_intake_id": report_id,
        "phase9_1_version": PHASE9_1_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "intake_template_only_until_operator_values_are_supplied": True,
        "phase9_1_single_signed_testnet_enablement_intake_ready": ready,
        "phase9_1_intake_template_created": True,
        "phase9_1_intake_guard_created": True,
        "phase9_1_intake_guard_passed": guard_report.get("guard_passed") is True,
        "phase9_1_actual_enablement_approval_complete": False,
        "phase9_1_actual_approval_blockers": validation_result.get("phase9_1_actual_approval_blockers") or [],
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "phase9_2_order_submission_not_authorized_by_phase9_1": True,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_flags_by_artifact": unsafe,
        "intake_validation_result": validation_result,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": blockers,
        "phase9_1_allowed_next_scope": "collect_actual_operator_approval_values_and_rerun_phase9_1_validation" if ready else "resolve_phase9_1_intake_blockers",
        "recommended_next_action": "do_not_submit_order_collect_explicit_operator_approval_signature_key_fingerprint_kill_switch_confirmation" if ready else "inspect_phase9_1_blockers_and_rerun_phase8_4_to_phase9_1",
        "runtime_permission_source": False,
        "phase9_1_execution_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "order_submission_performed": False,
        "phase9_order_submission_authorized": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "created_at_utc": created,
    }
    report["phase9_1_single_signed_testnet_enablement_intake_sha256"] = intake["phase9_1_single_signed_testnet_enablement_intake_sha256"]
    report["phase9_1_single_signed_testnet_enablement_intake_guard_report_sha256"] = guard_report["phase9_1_single_signed_testnet_enablement_intake_guard_report_sha256"]
    report["phase9_1_report_sha256"] = sha256_json(report)
    return report, intake, guard_report, negative_fixture_results


def persist_phase9_1_single_signed_testnet_enablement_intake_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase8_4_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_1_single_signed_testnet_enablement_intake")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, intake, guard_report, negative_fixture_results = build_phase9_1_single_signed_testnet_enablement_intake_report(
        cfg=cfg,
        run_phase8_4_first=run_phase8_4_first,
    )
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase9_1_single_signed_testnet_enablement_intake_report.json", report)
    atomic_write_json(latest / "single_signed_testnet_enablement_intake_REVIEW_ONLY.json", intake)
    atomic_write_json(latest / "single_signed_testnet_enablement_intake_guard_report.json", guard_report)
    atomic_write_json(latest / "phase9_1_negative_fixture_results.json", negative_fixture_results)
    (latest / "PHASE9_1_SINGLE_SIGNED_TESTNET_ENABLEMENT_INTAKE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(signed_testnet_dir / "single_signed_testnet_enablement_intake_REVIEW_ONLY.json", intake)
    atomic_write_json(signed_testnet_dir / "phase9_1_single_signed_testnet_enablement_intake_report.json", report)

    atomic_write_json(phase_dir / "phase9_1_single_signed_testnet_enablement_intake_report.json", report)
    atomic_write_json(phase_dir / "single_signed_testnet_enablement_intake_REVIEW_ONLY.json", intake)
    atomic_write_json(phase_dir / "single_signed_testnet_enablement_intake_guard_report.json", guard_report)
    atomic_write_json(phase_dir / "phase9_1_negative_fixture_results.json", negative_fixture_results)
    (phase_dir / "PHASE9_1_SINGLE_SIGNED_TESTNET_ENABLEMENT_INTAKE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_1_REGISTRY_NAME),
        {
            "phase9_1_single_signed_testnet_enablement_intake_id": report.get("phase9_1_single_signed_testnet_enablement_intake_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase9_1_single_signed_testnet_enablement_intake_ready": report.get("phase9_1_single_signed_testnet_enablement_intake_ready"),
            "phase9_1_actual_enablement_approval_complete": False,
            "phase9_2_single_testnet_order_submit_may_begin": False,
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
        registry_name=PHASE9_1_REGISTRY_NAME,
        id_field="phase9_1_single_signed_testnet_enablement_intake_registry_record_id",
        hash_field="phase9_1_single_signed_testnet_enablement_intake_registry_record_sha256",
        id_prefix="phase9_1_single_signed_testnet_enablement_intake_registry_record",
    )
    atomic_write_json(latest / "phase9_1_single_signed_testnet_enablement_intake_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_1_single_signed_testnet_enablement_intake_registry_record.json", registry_record)
    return report


# Phase 9.1 hardening extension: explicit actual operator approval intake template and validator.
PHASE9_1_ACTUAL_APPROVAL_HARDENING_VERSION = "phase9_1_actual_operator_approval_intake_hardening_v1"
PHASE9_1_ACTUAL_APPROVAL_REGISTRY_NAME = "phase9_1_actual_operator_approval_intake_registry"
STATUS_ACTUAL_APPROVAL_HARDENED_REVIEW_ONLY = "PHASE9_1_ACTUAL_APPROVAL_INTAKE_HARDENED_REVIEW_ONLY"
STATUS_ACTUAL_APPROVAL_HARDENING_BLOCKED_REVIEW_ONLY = "PHASE9_1_ACTUAL_APPROVAL_INTAKE_HARDENING_BLOCKED_REVIEW_ONLY"

REQUIRED_PHASE9_1_ACTUAL_APPROVAL_FIELDS = [
    "actual_approval_intake_type",
    "phase9_1_actual_approval_hardening_version",
    "source_phase9_1_intake_id",
    "source_phase9_1_intake_hash",
    "source_phase9_1_guard_hash",
    "operator_decision_required",
    "operator_decision",
    "operator_signature_required",
    "operator_signature_placeholder",
    "approval_scope",
    "single_order_scope",
    "max_order_count",
    "small_max_notional",
    "daily_loss_cap",
    "kill_switch_confirmation_required",
    "kill_switch_confirmed_for_actual_approval",
    "testnet_only_key_fingerprint_required",
    "testnet_key_fingerprint_sha256",
    "testnet_key_scope",
    "fresh_preorder_risk_gate_evidence_required",
    "fresh_preorder_risk_gate_evidence_present",
    "actual_operator_approval_recorded",
    "phase9_1_actual_enablement_approval_complete",
    "phase9_2_single_testnet_order_submit_may_begin",
    "testnet_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
]

SECRET_LIKE_FIELD_NAMES = {
    "api_key",
    "api_key_value",
    "api_secret",
    "api_secret_value",
    "secret",
    "secret_value",
    "private_key",
    "passphrase",
    "password",
}


def _contains_secret_like_fields(payload: Mapping[str, Any], prefix: str = "") -> list[str]:
    findings: list[str] = []
    for key, value in dict(payload or {}).items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        lower = str(key).lower()
        if lower in SECRET_LIKE_FIELD_NAMES or lower.endswith("_secret") or lower.endswith("_private_key"):
            if value not in (None, "", "REDACTED", "METADATA_ONLY", "NOT_STORED"):
                findings.append(full_key)
        if isinstance(value, Mapping):
            findings.extend(_contains_secret_like_fields(value, full_key))
    return sorted(dict.fromkeys(findings))


def _phase9_1_source_artifact_ready(payload: Mapping[str, Any], *, expected_status: str | None = None) -> bool:
    data = dict(payload or {})
    if not data:
        return False
    if data.get("blocked") is True or data.get("fail_closed") is True:
        return False
    if _unsafe_fields(data):
        return False
    if expected_status and data.get("status") != expected_status:
        return False
    return True


def _build_actual_operator_approval_intake_template(
    *,
    report: Mapping[str, Any],
    intake: Mapping[str, Any],
    guard_report: Mapping[str, Any],
    created_at_utc: str,
) -> dict[str, Any]:
    source_report = dict(report or {})
    source_intake = dict(intake or {})
    source_guard = dict(guard_report or {})
    key_scope = {
        "testnet_only_key_required": True,
        "live_mainnet_key_prohibited": True,
        "withdrawal_permission_allowed": False,
        "transfer_permission_allowed": False,
        "admin_permission_allowed": False,
        "leverage_margin_mutation_allowed": False,
        "read_scope_metadata_allowed": True,
        "trade_scope_testnet_only_may_be_requested_for_phase9_2": True,
        "key_value_storage_allowed": False,
        "key_value_logging_allowed": False,
        "secret_file_read_allowed": False,
        "secret_file_creation_allowed": False,
    }
    template: dict[str, Any] = {
        "actual_approval_intake_type": "phase9_1_actual_operator_approval_intake_template_review_only",
        "phase9_1_actual_approval_hardening_version": PHASE9_1_ACTUAL_APPROVAL_HARDENING_VERSION,
        "source_phase9_1_intake_id": source_report.get("phase9_1_single_signed_testnet_enablement_intake_id") or source_intake.get("source_phase9_1_report_id"),
        "source_phase9_1_intake_hash": source_report.get("phase9_1_single_signed_testnet_enablement_intake_sha256") or source_intake.get("phase9_1_single_signed_testnet_enablement_intake_sha256"),
        "source_phase9_1_report_hash": source_report.get("phase9_1_report_sha256"),
        "source_phase9_1_guard_hash": source_guard.get("phase9_1_single_signed_testnet_enablement_intake_guard_report_sha256") or source_report.get("phase9_1_single_signed_testnet_enablement_intake_guard_report_sha256"),
        "source_phase8_4_final_guard_id": source_intake.get("source_phase8_4_final_guard_id"),
        "source_phase8_4_final_guard_hash": source_intake.get("source_phase8_4_final_guard_hash"),
        "source_phase8_3_risk_gate_id": source_intake.get("source_phase8_3_risk_gate_id"),
        "source_phase8_3_risk_gate_hash": source_intake.get("source_phase8_3_risk_gate_hash"),
        "canonical_id_chain": source_intake.get("canonical_id_chain") or {},
        "operator_decision_required": "approve_single_signed_testnet_order",
        "operator_decision": "pending_explicit_manual_approval",
        "actual_operator_approval_recorded": False,
        "operator_approval_ticket_or_record_id": None,
        "operator_approval_timestamp_utc": None,
        "operator_signature_required": True,
        "operator_signature": None,
        "operator_signature_placeholder": "REQUIRED_EXPLICIT_OPERATOR_SIGNATURE_BEFORE_PHASE9_2",
        "operator_signature_hash_sha256": None,
        "approval_scope": "single_signed_testnet_order_only",
        "single_order_scope": True,
        "max_order_count": int(source_intake.get("max_order_count") or 1),
        "small_max_notional": str(source_intake.get("small_max_notional") or "5.0"),
        "daily_loss_cap": str(source_intake.get("daily_loss_cap") or "15.0"),
        "kill_switch_confirmation_required": True,
        "kill_switch_confirmed_for_actual_approval": False,
        "kill_switch_confirmation_timestamp_utc": None,
        "testnet_only_key_fingerprint_required": True,
        "testnet_key_fingerprint_sha256": "REQUIRED_OPERATOR_SUPPLIED_METADATA_ONLY_TESTNET_KEY_FINGERPRINT_SHA256",
        "testnet_key_scope": key_scope,
        "fresh_preorder_risk_gate_evidence_required": True,
        "fresh_preorder_risk_gate_evidence_present": source_intake.get("fresh_preorder_risk_gate_evidence_present") is True,
        "fresh_preorder_risk_gate_refresh_required_immediately_before_phase9_2": True,
        "fresh_preorder_risk_gate_refresh_window_seconds": 60,
        "idempotency_key_required_for_phase9_2": True,
        "complete_canonical_id_chain_required_for_phase9_2": True,
        "phase9_1_actual_enablement_approval_complete": False,
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "phase9_2_requires_separate_submit_guard": True,
        "review_only": True,
        "not_runtime_authority": True,
        "metadata_only_key_reference_policy": True,
        "secret_values_forbidden": True,
        "blocks_signed_testnet_execution_until_phase9_2_guard": True,
        "blocks_order_submission": True,
        **{field: False for field in FALSE_FLAGS},
        "created_at_utc": created_at_utc,
    }
    template["phase9_1_actual_operator_approval_intake_template_sha256"] = sha256_json(template)
    return template


def validate_phase9_1_actual_operator_approval_intake_template(
    payload: Mapping[str, Any], *, require_complete_approval: bool = False
) -> dict[str, Any]:
    data = dict(payload or {})
    missing = [field for field in REQUIRED_PHASE9_1_ACTUAL_APPROVAL_FIELDS if field not in data or data.get(field) in (None, "")]
    unsafe = _unsafe_fields(data)
    secret_like = _contains_secret_like_fields(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_PHASE9_1_ACTUAL_APPROVAL_FIELDS:" + ",".join(missing))
    if unsafe:
        blockers.append("UNSAFE_PHASE9_1_ACTUAL_APPROVAL_FLAGS:" + ",".join(unsafe))
    if secret_like:
        blockers.append("SECRET_LIKE_FIELDS_PRESENT:" + ",".join(secret_like))
    if data.get("actual_approval_intake_type") != "phase9_1_actual_operator_approval_intake_template_review_only":
        blockers.append("INVALID_PHASE9_1_ACTUAL_APPROVAL_INTAKE_TYPE")
    if data.get("review_only") is not True:
        blockers.append("PHASE9_1_ACTUAL_APPROVAL_REVIEW_ONLY_NOT_TRUE")
    if data.get("not_runtime_authority") is not True:
        blockers.append("PHASE9_1_ACTUAL_APPROVAL_RUNTIME_AUTHORITY_NOT_DISABLED")
    if data.get("single_order_scope") is not True:
        blockers.append("PHASE9_1_ACTUAL_APPROVAL_SINGLE_ORDER_SCOPE_NOT_TRUE")
    try:
        max_order_count = int(data.get("max_order_count") or 0)
    except (TypeError, ValueError):
        max_order_count = 0
    if max_order_count != 1:
        blockers.append("PHASE9_1_ACTUAL_APPROVAL_MAX_ORDER_COUNT_NOT_ONE")
    try:
        small_max_notional = float(data.get("small_max_notional"))
    except (TypeError, ValueError):
        small_max_notional = -1.0
    if not (0 < small_max_notional <= 10.0):
        blockers.append("PHASE9_1_ACTUAL_APPROVAL_SMALL_MAX_NOTIONAL_INVALID_OR_TOO_HIGH")
    try:
        daily_loss_cap = float(data.get("daily_loss_cap"))
    except (TypeError, ValueError):
        daily_loss_cap = -1.0
    if not (0 < daily_loss_cap <= 15.0):
        blockers.append("PHASE9_1_ACTUAL_APPROVAL_DAILY_LOSS_CAP_INVALID_OR_TOO_HIGH")
    if data.get("approval_scope") != "single_signed_testnet_order_only":
        blockers.append("PHASE9_1_ACTUAL_APPROVAL_SCOPE_INVALID")
    if data.get("fresh_preorder_risk_gate_evidence_present") is not True:
        blockers.append("PHASE9_1_ACTUAL_APPROVAL_FRESH_RISK_GATE_EVIDENCE_MISSING")
    key_scope = dict(data.get("testnet_key_scope") or {})
    required_true_scope = [
        "testnet_only_key_required",
        "live_mainnet_key_prohibited",
        "read_scope_metadata_allowed",
        "trade_scope_testnet_only_may_be_requested_for_phase9_2",
    ]
    for field in required_true_scope:
        if key_scope.get(field) is not True:
            blockers.append(f"PHASE9_1_ACTUAL_APPROVAL_KEY_SCOPE_TRUE_REQUIRED:{field}")
    required_false_scope = [
        "withdrawal_permission_allowed",
        "transfer_permission_allowed",
        "admin_permission_allowed",
        "leverage_margin_mutation_allowed",
        "key_value_storage_allowed",
        "key_value_logging_allowed",
        "secret_file_read_allowed",
        "secret_file_creation_allowed",
    ]
    for field in required_false_scope:
        if key_scope.get(field) is not False:
            blockers.append(f"PHASE9_1_ACTUAL_APPROVAL_KEY_SCOPE_FALSE_REQUIRED:{field}")
    for field in FALSE_FLAGS:
        if data.get(field) is not False:
            blockers.append(f"REQUIRED_PHASE9_1_ACTUAL_APPROVAL_FALSE_FLAG_NOT_FALSE:{field}")
    actual_approval_blockers: list[str] = []
    if data.get("operator_decision") != "approve_single_signed_testnet_order":
        actual_approval_blockers.append("PHASE9_1_ACTUAL_APPROVAL_OPERATOR_DECISION_NOT_EXPLICIT_APPROVAL")
    if not data.get("operator_signature"):
        actual_approval_blockers.append("PHASE9_1_ACTUAL_APPROVAL_OPERATOR_SIGNATURE_MISSING")
    if data.get("actual_operator_approval_recorded") is not True:
        actual_approval_blockers.append("PHASE9_1_ACTUAL_APPROVAL_NOT_RECORDED")
    if not data.get("operator_approval_ticket_or_record_id"):
        actual_approval_blockers.append("PHASE9_1_ACTUAL_APPROVAL_TICKET_OR_RECORD_ID_MISSING")
    if data.get("kill_switch_confirmed_for_actual_approval") is not True:
        actual_approval_blockers.append("PHASE9_1_ACTUAL_APPROVAL_KILL_SWITCH_NOT_CONFIRMED")
    if not _valid_fingerprint(data.get("testnet_key_fingerprint_sha256")):
        actual_approval_blockers.append("PHASE9_1_ACTUAL_APPROVAL_TESTNET_KEY_FINGERPRINT_MISSING_OR_PLACEHOLDER")
    if not data.get("operator_approval_timestamp_utc"):
        actual_approval_blockers.append("PHASE9_1_ACTUAL_APPROVAL_TIMESTAMP_MISSING")
    if require_complete_approval:
        blockers.extend(actual_approval_blockers)
    template_valid = not blockers
    approval_values_complete = not actual_approval_blockers
    return {
        "phase9_1_actual_operator_approval_template_valid_review_only": template_valid,
        "phase9_1_actual_operator_approval_template_blocked_fail_closed": not template_valid,
        "phase9_1_actual_operator_approval_values_complete": approval_values_complete,
        "phase9_1_actual_operator_approval_blockers": sorted(dict.fromkeys(actual_approval_blockers)),
        "phase9_1_actual_operator_approval_validation_blockers": sorted(dict.fromkeys(blockers)),
        "missing_required_fields": missing,
        "unsafe_truthy_fields": unsafe,
        "secret_like_fields": secret_like,
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "testnet_order_submission_allowed": False,
        **{field: False for field in FALSE_FLAGS},
        "actual_order_submission_performed": False,
    }


def _build_phase9_1_actual_approval_negative_fixture_results(template: Mapping[str, Any]) -> dict[str, Any]:
    fixtures: dict[str, dict[str, Any]] = {}
    cases: dict[str, tuple[dict[str, Any], bool]] = {
        "missing_operator_signature": ({"operator_decision": "approve_single_signed_testnet_order", "operator_signature": None, "actual_operator_approval_recorded": True, "operator_approval_ticket_or_record_id": "ticket-001", "operator_approval_timestamp_utc": "2026-01-01T00:00:00Z", "kill_switch_confirmed_for_actual_approval": True, "testnet_key_fingerprint_sha256": "a" * 64}, True),
        "missing_key_fingerprint": ({"operator_decision": "approve_single_signed_testnet_order", "operator_signature": "operator_signature_fixture", "actual_operator_approval_recorded": True, "operator_approval_ticket_or_record_id": "ticket-001", "operator_approval_timestamp_utc": "2026-01-01T00:00:00Z", "kill_switch_confirmed_for_actual_approval": True, "testnet_key_fingerprint_sha256": "REQUIRED_OPERATOR_SUPPLIED_METADATA_ONLY_TESTNET_KEY_FINGERPRINT_SHA256"}, True),
        "kill_switch_not_confirmed": ({"operator_decision": "approve_single_signed_testnet_order", "operator_signature": "operator_signature_fixture", "actual_operator_approval_recorded": True, "operator_approval_ticket_or_record_id": "ticket-001", "operator_approval_timestamp_utc": "2026-01-01T00:00:00Z", "kill_switch_confirmed_for_actual_approval": False, "testnet_key_fingerprint_sha256": "a" * 64}, True),
        "max_order_count_gt_one": ({"max_order_count": 2}, False),
        "mainnet_key_scope_allowed": ({"testnet_key_scope": {**dict(template.get("testnet_key_scope") or {}), "live_mainnet_key_prohibited": False}}, False),
        "unsafe_submit_permission_true": ({"testnet_order_submission_allowed": True, "phase9_2_single_testnet_order_submit_may_begin": True}, False),
        "raw_secret_value_present": ({"api_secret_value": "raw-secret-value-must-not-appear"}, False),
    }
    for name, (patch, require_complete) in cases.items():
        payload = dict(template)
        payload.update(patch)
        result = validate_phase9_1_actual_operator_approval_intake_template(payload, require_complete_approval=require_complete)
        reasons = list(result.get("phase9_1_actual_operator_approval_validation_blockers") or []) + list(result.get("phase9_1_actual_operator_approval_blockers") or [])
        fixtures[name] = {
            "fixture_name": name,
            "blocked": bool(reasons),
            "fail_closed": bool(reasons),
            "block_reasons": sorted(dict.fromkeys(str(item) for item in reasons if item)),
        }
    all_blocked = all(item["blocked"] is True and item["fail_closed"] is True for item in fixtures.values())
    return {
        "artifact_type": "phase9_1_actual_operator_approval_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": fixtures,
        **{field: False for field in FALSE_FLAGS},
    }


def _build_actual_operator_approval_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("phase9_1_actual_operator_approval_blockers") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 9.1 Actual Operator Approval Intake Hardening - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact adds the explicit operator approval intake template and validator required before a future Phase 9.2 single signed testnet order submit guard can be reconsidered.",
            "",
            "## Result",
            "",
            f"- Actual approval template ready: `{report.get('phase9_1_actual_operator_approval_template_ready')}`",
            f"- Actual approval values complete: `{report.get('phase9_1_actual_operator_approval_values_complete')}`",
            f"- Phase 9.2 submit may begin: `{report.get('phase9_2_single_testnet_order_submit_may_begin')}`",
            "",
            "## Required Operator Values",
            "",
            "- `operator_decision=approve_single_signed_testnet_order`",
            "- Operator signature or ticket record",
            "- Metadata-only testnet key fingerprint SHA256",
            "- Manual kill switch confirmation",
            "- Fresh PreOrderRiskGate refresh immediately before Phase 9.2",
            "",
            "## Still Disabled",
            "",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `actual_order_submission_performed=false`",
            "",
            "## Pending Approval Blockers",
            "",
            blocker_lines,
            "",
        ]
    )


def build_phase9_1_actual_operator_approval_intake_hardening_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_1_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase9_1_first:
        persist_phase9_1_single_signed_testnet_enablement_intake_report(cfg=cfg)
    latest = _latest_dir(cfg)
    source_report = _read_latest_json(cfg, "phase9_1_single_signed_testnet_enablement_intake_report.json")
    source_intake = _read_latest_json(cfg, "single_signed_testnet_enablement_intake_REVIEW_ONLY.json")
    source_guard = _read_latest_json(cfg, "single_signed_testnet_enablement_intake_guard_report.json")
    source_summary = {
        "phase9_1_report": _source_summary("phase9_1_report", source_report),
        "phase9_1_intake": _source_summary("phase9_1_intake", source_intake),
        "phase9_1_guard": _source_summary("phase9_1_guard", source_guard),
    }
    source_blockers: list[str] = []
    if not _phase9_1_source_artifact_ready(source_report, expected_status=STATUS_RECORDED_REVIEW_ONLY):
        source_blockers.append("PHASE9_1_ACTUAL_APPROVAL_SOURCE_REPORT_NOT_READY")
    if not source_intake or source_intake.get("intake_type") != "phase9_1_single_signed_testnet_enablement_intake_review_only":
        source_blockers.append("PHASE9_1_ACTUAL_APPROVAL_SOURCE_INTAKE_MISSING_OR_INVALID")
    if not source_guard or source_guard.get("guard_passed") is not True:
        source_blockers.append("PHASE9_1_ACTUAL_APPROVAL_SOURCE_GUARD_NOT_PASSED")
    for name, payload in {"phase9_1_report": source_report, "phase9_1_intake": source_intake, "phase9_1_guard": source_guard}.items():
        flags = _unsafe_fields(payload)
        if flags:
            source_blockers.append(f"UNSAFE_PHASE9_1_ACTUAL_APPROVAL_SOURCE_FLAGS:{name}:{','.join(flags)}")
    template = _build_actual_operator_approval_intake_template(
        report=source_report,
        intake=source_intake,
        guard_report=source_guard,
        created_at_utc=created,
    )
    validation_report = validate_phase9_1_actual_operator_approval_intake_template(template)
    complete_validation = validate_phase9_1_actual_operator_approval_intake_template(template, require_complete_approval=True)
    negative_fixture_results = _build_phase9_1_actual_approval_negative_fixture_results(template)
    blockers = list(source_blockers)
    if validation_report.get("phase9_1_actual_operator_approval_template_valid_review_only") is not True:
        blockers.extend(validation_report.get("phase9_1_actual_operator_approval_validation_blockers") or ["PHASE9_1_ACTUAL_APPROVAL_TEMPLATE_INVALID"])
    if negative_fixture_results.get("all_negative_fixtures_blocked_fail_closed") is not True:
        blockers.append("PHASE9_1_ACTUAL_APPROVAL_NEGATIVE_FIXTURES_NOT_ALL_BLOCKED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_ACTUAL_APPROVAL_HARDENED_REVIEW_ONLY if ready else STATUS_ACTUAL_APPROVAL_HARDENING_BLOCKED_REVIEW_ONLY
    report: dict[str, Any] = {
        "phase9_1_actual_operator_approval_hardening_id": stable_id(
            "phase9_1_actual_operator_approval_hardening",
            {"source_summary": source_summary, "template_hash": sha256_json(template), "blockers": blockers, "created_at_utc": created},
            24,
        ),
        "phase9_1_actual_approval_hardening_version": PHASE9_1_ACTUAL_APPROVAL_HARDENING_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "phase9_1_actual_operator_approval_template_ready": ready,
        "phase9_1_actual_operator_approval_values_complete": False,
        "phase9_1_actual_operator_approval_blockers": complete_validation.get("phase9_1_actual_operator_approval_blockers") or [],
        "phase9_1_actual_operator_approval_validation_report": validation_report,
        "phase9_1_actual_operator_approval_complete_validation_report": complete_validation,
        "negative_fixture_results": negative_fixture_results,
        "source_evidence_hash_summary": source_summary,
        "block_reasons": blockers,
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "phase9_2_order_submission_authorized": False,
        "recommended_next_action": "collect_explicit_operator_approval_values_then_rerun_phase9_1_actual_approval_validator_keep_order_submission_disabled_until_phase9_2_guard",
        **{field: False for field in FALSE_FLAGS},
        "created_at_utc": created,
    }
    report["phase9_1_actual_operator_approval_intake_template_sha256"] = template["phase9_1_actual_operator_approval_intake_template_sha256"]
    report["phase9_1_actual_operator_approval_validation_report_sha256"] = sha256_json(validation_report)
    report["phase9_1_actual_operator_approval_hardening_report_sha256"] = sha256_json(report)
    return report, template, validation_report, negative_fixture_results


def persist_phase9_1_actual_operator_approval_intake_hardening_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_1_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_1_single_signed_testnet_enablement_intake")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, template, validation_report, negative_fixture_results = build_phase9_1_actual_operator_approval_intake_hardening_report(
        cfg=cfg,
        run_phase9_1_first=run_phase9_1_first,
    )
    handoff = _build_actual_operator_approval_handoff_markdown(report)
    atomic_write_json(latest / "phase9_1_actual_operator_approval_hardening_report.json", report)
    atomic_write_json(latest / "phase9_1_actual_operator_approval_intake_TEMPLATE_REVIEW_ONLY.json", template)
    atomic_write_json(latest / "phase9_1_actual_operator_approval_intake_validation_report.json", validation_report)
    atomic_write_json(latest / "phase9_1_actual_operator_approval_negative_fixture_results.json", negative_fixture_results)
    (latest / "PHASE9_1_ACTUAL_OPERATOR_APPROVAL_INTAKE_HARDENING_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(phase_dir / "phase9_1_actual_operator_approval_hardening_report.json", report)
    atomic_write_json(phase_dir / "phase9_1_actual_operator_approval_intake_TEMPLATE_REVIEW_ONLY.json", template)
    atomic_write_json(phase_dir / "phase9_1_actual_operator_approval_intake_validation_report.json", validation_report)
    atomic_write_json(phase_dir / "phase9_1_actual_operator_approval_negative_fixture_results.json", negative_fixture_results)
    (phase_dir / "PHASE9_1_ACTUAL_OPERATOR_APPROVAL_INTAKE_HARDENING_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(signed_testnet_dir / "phase9_1_actual_operator_approval_hardening_report.json", report)
    atomic_write_json(signed_testnet_dir / "phase9_1_actual_operator_approval_intake_TEMPLATE_REVIEW_ONLY.json", template)
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_1_ACTUAL_APPROVAL_REGISTRY_NAME),
        {
            "phase9_1_actual_operator_approval_hardening_id": report.get("phase9_1_actual_operator_approval_hardening_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase9_1_actual_operator_approval_template_ready": report.get("phase9_1_actual_operator_approval_template_ready"),
            "phase9_1_actual_operator_approval_values_complete": False,
            "phase9_2_single_testnet_order_submit_may_begin": False,
            "actual_order_submission_performed": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_1_ACTUAL_APPROVAL_REGISTRY_NAME,
        id_field="phase9_1_actual_operator_approval_registry_record_id",
        hash_field="phase9_1_actual_operator_approval_registry_record_sha256",
        id_prefix="phase9_1_actual_operator_approval_registry_record",
    )
    atomic_write_json(latest / "phase9_1_actual_operator_approval_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_1_actual_operator_approval_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_1_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "validate_phase9_1_single_signed_testnet_enablement_intake",
    "build_phase9_1_single_signed_testnet_enablement_intake_report",
    "persist_phase9_1_single_signed_testnet_enablement_intake_report",
    "PHASE9_1_ACTUAL_APPROVAL_HARDENING_VERSION",
    "STATUS_ACTUAL_APPROVAL_HARDENED_REVIEW_ONLY",
    "STATUS_ACTUAL_APPROVAL_HARDENING_BLOCKED_REVIEW_ONLY",
    "validate_phase9_1_actual_operator_approval_intake_template",
    "build_phase9_1_actual_operator_approval_intake_hardening_report",
    "persist_phase9_1_actual_operator_approval_intake_hardening_report",
]
