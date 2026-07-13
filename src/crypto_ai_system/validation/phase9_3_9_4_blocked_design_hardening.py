from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_3_status_polling_cancel_handling import (
    STATUS_PHASE9_3_DESIGN_RECORDED_BLOCKED_REVIEW_ONLY,
    persist_phase9_3_status_polling_cancel_handling_report,
)

PHASE9_3_9_4_HARDENING_VERSION = "phase9_3_9_4_blocked_design_hardening_v1"
PHASE9_3_9_4_HARDENING_REGISTRY_NAME = "phase9_3_9_4_blocked_design_hardening_registry"
STATUS_PHASE9_3_9_4_HARDENING_RECORDED_BLOCKED_REVIEW_ONLY = (
    "PHASE9_3_9_4_BLOCKED_DESIGN_HARDENING_RECORDED_REVIEW_ONLY"
)
STATUS_PHASE9_3_9_4_HARDENING_BLOCKED_REVIEW_ONLY = "PHASE9_3_9_4_BLOCKED_DESIGN_HARDENING_BLOCKED_REVIEW_ONLY"

REQUIRED_PHASE9_3_FILES = {
    "phase9_3_status_polling_cancel_report": "phase9_3_status_polling_cancel_handling_report.json",
    "phase9_3_status_polling_cancel_design": "status_polling_cancel_handling_DESIGN_BLOCKED_REVIEW_ONLY.json",
    "phase9_3_status_polling_cancel_validation": "phase9_3_status_polling_cancel_handling_validation_report.json",
}

STATUS_STATES_REQUIRED = [
    "not_started_no_real_order_id",
    "submitted",
    "accepted",
    "rejected",
    "partial_fill",
    "full_fill",
    "cancel_requested",
    "cancel_accepted",
    "cancel_rejected",
    "expired",
    "final_status",
]

RECONCILIATION_CHECKS_REQUIRED = [
    "exchange_order_status",
    "local_execution_record",
    "position_delta",
    "balance_delta",
    "fee",
    "slippage",
    "fill_price",
    "expected_notional",
    "actual_notional",
    "partial_fill",
    "rejected_order",
    "cancel_result",
    "api_latency",
    "api_error",
    "mismatch_blocks_promotion",
]

UNSAFE_TRUTHY_FIELDS = list(FALSE_FLAGS) + [
    "phase9_2_order_submission_authorized",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
    "status_polling_started",
    "reconciliation_started",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "cancel_request_sent",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_order_submission_performed",
    "real_order_id_created",
    "exchange_execution_record_present",
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
        "phase9_3_9_4_blocked_design_hardening_report_sha256",
        "phase9_4_testnet_reconciliation_design_sha256",
        "phase9_3_status_cancel_hardened_design_sha256",
        "phase9_3_status_polling_cancel_handling_report_sha256",
        "phase9_3_status_polling_cancel_handling_design_sha256",
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


def _phase9_3_source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data or _unsafe_fields(data):
        return False
    if name == "phase9_3_status_polling_cancel_report":
        return (
            data.get("status") == STATUS_PHASE9_3_DESIGN_RECORDED_BLOCKED_REVIEW_ONLY
            and data.get("phase9_3_design_recorded") is True
            and data.get("phase9_3_status_polling_may_begin") is False
            and data.get("phase9_4_testnet_reconciliation_may_begin") is False
            and data.get("no_real_order_id_available") is True
        )
    if name == "phase9_3_status_polling_cancel_design":
        return (
            data.get("artifact_type") == "phase9_3_status_polling_cancel_handling_design_review_only"
            and data.get("review_only") is True
            and data.get("real_order_id") is None
            and data.get("status_polling_started") is False
        )
    if name == "phase9_3_status_polling_cancel_validation":
        return data.get("phase9_3_status_polling_cancel_handling_design_valid") is True
    return True


def build_phase9_3_status_cancel_hardened_design(
    *, phase9_3_sources: Mapping[str, Mapping[str, Any]], created_at_utc: str
) -> dict[str, Any]:
    source_summary = {name: _source_summary(name, payload) for name, payload in phase9_3_sources.items()}
    design = {
        "artifact_type": "phase9_3_status_cancel_hardened_design_blocked_review_only",
        "phase9_3_9_4_hardening_version": PHASE9_3_9_4_HARDENING_VERSION,
        "review_only": True,
        "blocked_design_artifact": True,
        "source_evidence_hash_summary": source_summary,
        "no_real_order_id_available": True,
        "real_order_id": None,
        "status_polling_started": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "cancel_request_sent": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "status_state_machine": {
            "states": STATUS_STATES_REQUIRED,
            "terminal_states": ["rejected", "full_fill", "cancel_accepted", "cancel_rejected", "expired"],
            "blocked_initial_state": "not_started_no_real_order_id",
            "final_status_required_before_reconciliation": True,
        },
        "polling_safety_controls": {
            "requires_real_order_id": True,
            "requires_status_endpoint_policy": True,
            "requires_rate_limit_budget": True,
            "requires_poll_timeout": True,
            "requires_transient_error_retry_policy": True,
            "requires_duplicate_poll_guard": True,
            "status_endpoint_disabled_until_real_order_id_exists": True,
        },
        "cancel_safety_controls": {
            "requires_real_order_id": True,
            "requires_cancel_endpoint_policy": True,
            "requires_manual_cancel_confirmation": True,
            "requires_idempotency_key": True,
            "requires_duplicate_cancel_guard": True,
            "requires_kill_switch_confirmation": True,
            "cancel_endpoint_disabled_until_real_order_id_exists": True,
        },
        "handoff_to_phase9_4_requires": [
            "real_order_id",
            "final_exchange_order_status",
            "local_execution_record",
            "status_polling_session_close",
            "no_unresolved_api_errors",
        ],
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        **_flag_false_payload(),
        "created_at_utc": created_at_utc,
    }
    design["phase9_3_status_cancel_hardened_design_sha256"] = sha256_json(design)
    return design


def validate_phase9_3_status_cancel_hardened_design(design: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(design or {})
    blockers: list[str] = []
    unsafe = _unsafe_fields(payload)
    if payload.get("artifact_type") != "phase9_3_status_cancel_hardened_design_blocked_review_only":
        blockers.append("PHASE9_3_HARDENED_STATUS_CANCEL_TYPE_INVALID")
    if payload.get("review_only") is not True:
        blockers.append("PHASE9_3_HARDENED_STATUS_CANCEL_NOT_REVIEW_ONLY")
    if payload.get("no_real_order_id_available") is not True:
        blockers.append("PHASE9_3_HARDENED_STATUS_CANCEL_EXPECTED_NO_REAL_ORDER_ID")
    if payload.get("real_order_id") is not None:
        blockers.append("PHASE9_3_HARDENED_STATUS_CANCEL_REAL_ORDER_ID_PRESENT")
    for field in ("status_polling_started", "order_status_endpoint_called", "cancel_endpoint_called", "cancel_request_sent"):
        if payload.get(field) is not False:
            blockers.append(f"PHASE9_3_HARDENED_STATUS_CANCEL_UNSAFE_FIELD:{field}")
    states = ((payload.get("status_state_machine") or {}).get("states") or [])
    for state in STATUS_STATES_REQUIRED:
        if state not in states:
            blockers.append(f"PHASE9_3_HARDENED_STATUS_MODEL_MISSING:{state}")
    controls = payload.get("polling_safety_controls") or {}
    for key in ("requires_real_order_id", "requires_status_endpoint_policy", "requires_poll_timeout", "requires_duplicate_poll_guard"):
        if controls.get(key) is not True:
            blockers.append(f"PHASE9_3_HARDENED_POLLING_CONTROL_MISSING:{key}")
    cancel_controls = payload.get("cancel_safety_controls") or {}
    for key in ("requires_real_order_id", "requires_cancel_endpoint_policy", "requires_manual_cancel_confirmation", "requires_duplicate_cancel_guard"):
        if cancel_controls.get(key) is not True:
            blockers.append(f"PHASE9_3_HARDENED_CANCEL_CONTROL_MISSING:{key}")
    if unsafe:
        blockers.append("PHASE9_3_HARDENED_STATUS_CANCEL_UNSAFE_FLAGS:" + ",".join(unsafe))
    valid = not blockers
    return {
        "artifact_type": "phase9_3_status_cancel_hardened_design_validation_report",
        "phase9_3_status_cancel_hardened_design_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_flag_false_payload(),
    }


def build_phase9_4_testnet_reconciliation_design(
    *, phase9_3_hardened_design: Mapping[str, Any], created_at_utc: str
) -> dict[str, Any]:
    design = {
        "artifact_type": "phase9_4_testnet_reconciliation_design_blocked_review_only",
        "phase9_3_9_4_hardening_version": PHASE9_3_9_4_HARDENING_VERSION,
        "review_only": True,
        "blocked_design_artifact": True,
        "source_phase9_3_hardened_design_hash": _artifact_hash(phase9_3_hardened_design),
        "no_real_order_id_available": True,
        "real_order_id": None,
        "exchange_execution_record_present": False,
        "local_execution_record_present": False,
        "final_exchange_order_status_present": False,
        "reconciliation_started": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "phase10_signed_testnet_session_validation_may_begin": False,
        "reconciliation_checks_required": RECONCILIATION_CHECKS_REQUIRED,
        "reconciliation_plan": {
            "exchange_order_status": "compare final exchange status to local execution state",
            "local_execution_record": "verify local execution_id/order_intent_id/idempotency_key match the exchange order",
            "position_delta": "compare expected versus actual testnet position delta",
            "balance_delta": "compare expected versus actual testnet balance delta",
            "fee": "record fee asset, fee amount, and fee rate",
            "slippage": "record expected versus actual fill slippage",
            "fill_price": "record average fill price and per-fill detail",
            "expected_notional": "record planned capped notional",
            "actual_notional": "record executed notional and block if cap exceeded",
            "partial_fill": "handle cumulative quantity and remaining quantity",
            "rejected_order": "record rejection reason and keep promotion blocked",
            "cancel_result": "record cancel accepted/rejected/final status",
            "api_latency": "record endpoint latency and timeout evidence",
            "api_error": "record normalized API error codes",
            "mismatch_blocks_promotion": "any mismatch blocks Phase 10 promotion review",
        },
        "canonical_id_chain_required": [
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
        ],
        "mismatch_policy": {
            "any_reconciliation_mismatch_blocks_promotion": True,
            "unexpected_position_blocks_next_order": True,
            "unexpected_balance_change_blocks_next_order": True,
            "missing_fee_or_slippage_evidence_blocks_promotion": True,
            "paper_testnet_gap_must_be_recorded": True,
        },
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        **_flag_false_payload(),
        "created_at_utc": created_at_utc,
    }
    design["phase9_4_testnet_reconciliation_design_sha256"] = sha256_json(design)
    return design


def validate_phase9_4_testnet_reconciliation_design(design: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(design or {})
    blockers: list[str] = []
    unsafe = _unsafe_fields(payload)
    if payload.get("artifact_type") != "phase9_4_testnet_reconciliation_design_blocked_review_only":
        blockers.append("PHASE9_4_RECONCILIATION_DESIGN_TYPE_INVALID")
    if payload.get("review_only") is not True:
        blockers.append("PHASE9_4_RECONCILIATION_DESIGN_NOT_REVIEW_ONLY")
    if payload.get("no_real_order_id_available") is not True:
        blockers.append("PHASE9_4_RECONCILIATION_EXPECTED_NO_REAL_ORDER_ID")
    if payload.get("real_order_id") is not None:
        blockers.append("PHASE9_4_RECONCILIATION_REAL_ORDER_ID_PRESENT")
    for field in ("exchange_execution_record_present", "local_execution_record_present", "final_exchange_order_status_present", "reconciliation_started"):
        if payload.get(field) is not False:
            blockers.append(f"PHASE9_4_RECONCILIATION_UNSAFE_FIELD:{field}")
    if payload.get("phase9_4_testnet_reconciliation_may_begin") is not False:
        blockers.append("PHASE9_4_RECONCILIATION_MAY_BEGIN_WITHOUT_REAL_ORDER")
    checks = payload.get("reconciliation_checks_required") or []
    for check in RECONCILIATION_CHECKS_REQUIRED:
        if check not in checks:
            blockers.append(f"PHASE9_4_RECONCILIATION_CHECK_MISSING:{check}")
    plan = payload.get("reconciliation_plan") or {}
    for check in RECONCILIATION_CHECKS_REQUIRED:
        if check not in plan:
            blockers.append(f"PHASE9_4_RECONCILIATION_PLAN_MISSING:{check}")
    policy = payload.get("mismatch_policy") or {}
    for key in (
        "any_reconciliation_mismatch_blocks_promotion",
        "unexpected_position_blocks_next_order",
        "unexpected_balance_change_blocks_next_order",
        "missing_fee_or_slippage_evidence_blocks_promotion",
        "paper_testnet_gap_must_be_recorded",
    ):
        if policy.get(key) is not True:
            blockers.append(f"PHASE9_4_MISMATCH_POLICY_MISSING:{key}")
    if unsafe:
        blockers.append("PHASE9_4_RECONCILIATION_UNSAFE_FLAGS:" + ",".join(unsafe))
    valid = not blockers
    return {
        "artifact_type": "phase9_4_testnet_reconciliation_design_validation_report",
        "phase9_4_testnet_reconciliation_design_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_flag_false_payload(),
    }


def _build_negative_fixture_results(
    phase9_3_design: Mapping[str, Any], phase9_4_design: Mapping[str, Any]
) -> dict[str, Any]:
    cases: dict[str, tuple[str, dict[str, Any]]] = {
        "phase9_3_real_order_id_present": ("phase9_3", {"real_order_id": "fake-order-id", "no_real_order_id_available": False}),
        "phase9_3_status_endpoint_called_true": ("phase9_3", {"order_status_endpoint_called": True}),
        "phase9_3_cancel_endpoint_called_true": ("phase9_3", {"cancel_endpoint_called": True}),
        "phase9_3_cancel_request_sent_true": ("phase9_3", {"cancel_request_sent": True}),
        "phase9_4_reconciliation_started_true": ("phase9_4", {"reconciliation_started": True}),
        "phase9_4_exchange_execution_record_present_true": ("phase9_4", {"exchange_execution_record_present": True}),
        "phase9_4_missing_fee_check": ("phase9_4", {"reconciliation_checks_required": [x for x in RECONCILIATION_CHECKS_REQUIRED if x != "fee"]}),
        "phase9_4_reconciliation_may_begin_true": ("phase9_4", {"phase9_4_testnet_reconciliation_may_begin": True}),
    }
    results: dict[str, dict[str, Any]] = {}
    for name, (target, patch) in cases.items():
        if target == "phase9_3":
            payload = dict(phase9_3_design)
            payload.update(patch)
            validation = validate_phase9_3_status_cancel_hardened_design(payload)
        else:
            payload = dict(phase9_4_design)
            payload.update(patch)
            validation = validate_phase9_4_testnet_reconciliation_design(payload)
        results[name] = {
            "fixture_name": name,
            "target": target,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    all_blocked = all(item["blocked"] and item["fail_closed"] for item in results.values())
    return {
        "artifact_type": "phase9_3_9_4_blocked_design_hardening_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
    }


def build_phase9_3_9_4_blocked_design_hardening_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_3_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase9_3_first:
        persist_phase9_3_status_polling_cancel_handling_report(cfg=cfg, run_phase9_2_blocked_wrapper_first=True)
    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_PHASE9_3_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _phase9_3_source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}

    phase9_3_hardened_design = build_phase9_3_status_cancel_hardened_design(phase9_3_sources=sources, created_at_utc=created)
    phase9_3_validation = validate_phase9_3_status_cancel_hardened_design(phase9_3_hardened_design)
    phase9_4_design = build_phase9_4_testnet_reconciliation_design(
        phase9_3_hardened_design=phase9_3_hardened_design,
        created_at_utc=created,
    )
    phase9_4_validation = validate_phase9_4_testnet_reconciliation_design(phase9_4_design)
    negative_fixture_results = _build_negative_fixture_results(phase9_3_hardened_design, phase9_4_design)

    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_3_9_4_REQUIRED_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_3_9_4_REQUIRED_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_3_9_4_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items())
    blockers.extend(phase9_3_validation.get("block_reasons", []))
    blockers.extend(phase9_4_validation.get("block_reasons", []))
    blockers.append("PHASE9_4_RECONCILIATION_BLOCKED_UNTIL_REAL_PHASE9_2_ORDER_AND_FINAL_STATUS_EXIST")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    recorded = (
        not missing
        and not not_ready
        and not unsafe
        and phase9_3_validation["phase9_3_status_cancel_hardened_design_valid"]
        and phase9_4_validation["phase9_4_testnet_reconciliation_design_valid"]
        and negative_fixture_results["all_negative_fixtures_blocked_fail_closed"]
    )
    status = STATUS_PHASE9_3_9_4_HARDENING_RECORDED_BLOCKED_REVIEW_ONLY if recorded else STATUS_PHASE9_3_9_4_HARDENING_BLOCKED_REVIEW_ONLY
    report = {
        "phase9_3_9_4_blocked_design_hardening_id": stable_id(
            "phase9_3_9_4_blocked_design_hardening",
            {
                "source_summary": source_summary,
                "phase9_3_hardened_hash": sha256_json(phase9_3_hardened_design),
                "phase9_4_design_hash": sha256_json(phase9_4_design),
                "blockers": blockers,
                "created_at_utc": created,
            },
            24,
        ),
        "phase9_3_9_4_hardening_version": PHASE9_3_9_4_HARDENING_VERSION,
        "status": status,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "phase9_3_status_cancel_hardening_recorded": recorded,
        "phase9_4_testnet_reconciliation_design_recorded": recorded,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "phase10_signed_testnet_session_validation_may_begin": False,
        "no_real_order_id_available": True,
        "real_order_id": None,
        "exchange_execution_record_present": False,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe,
        "phase9_3_hardened_validation_report": phase9_3_validation,
        "phase9_4_reconciliation_validation_report": phase9_4_validation,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": blockers,
        "recommended_next_action": "only_start_real_phase9_3_and_phase9_4_after_a_real_single_testnet_order_id_final_status_and_exchange_execution_record_exist",
        **_flag_false_payload(),
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "cancel_request_sent": False,
        "reconciliation_started": False,
        "http_request_sent": False,
        "signature_created": False,
        "actual_order_submission_performed": False,
        "created_at_utc": created,
    }
    report["phase9_3_9_4_blocked_design_hardening_report_sha256"] = sha256_json(report)
    return report, phase9_3_hardened_design, phase9_3_validation, phase9_4_design, phase9_4_validation, negative_fixture_results


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 9.3 / 9.4 Blocked Design Hardening - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This package hardens Phase 9.3 status/cancel design and adds Phase 9.4 testnet reconciliation design while real submit remains blocked.",
            "",
            "## Result",
            "",
            f"- Phase 9.3 may begin: `{report.get('phase9_3_status_polling_may_begin')}`",
            f"- Phase 9.4 may begin: `{report.get('phase9_4_testnet_reconciliation_may_begin')}`",
            f"- Phase 10 may begin: `{report.get('phase10_signed_testnet_session_validation_may_begin')}`",
            f"- Real order id: `{report.get('real_order_id')}`",
            "",
            "## Still Disabled",
            "",
            "- `order_status_endpoint_called=false`",
            "- `cancel_endpoint_called=false`",
            "- `reconciliation_started=false`",
            "- `actual_order_submission_performed=false`",
            "- `phase10_signed_testnet_session_validation_may_begin=false`",
            "",
        ]
    )


def persist_phase9_3_9_4_blocked_design_hardening_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_3_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_3_9_4_blocked_design_hardening")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, phase9_3_design, phase9_3_validation, phase9_4_design, phase9_4_validation, negative_fixture_results = build_phase9_3_9_4_blocked_design_hardening_report(
        cfg=cfg,
        run_phase9_3_first=run_phase9_3_first,
    )
    handoff = _build_handoff_markdown(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_3_9_4_blocked_design_hardening_report.json", report)
        atomic_write_json(base / "phase9_3_status_cancel_HARDENED_BLOCKED_REVIEW_ONLY.json", phase9_3_design)
        atomic_write_json(base / "phase9_3_status_cancel_hardened_validation_report.json", phase9_3_validation)
        atomic_write_json(base / "phase9_4_testnet_reconciliation_DESIGN_BLOCKED_REVIEW_ONLY.json", phase9_4_design)
        atomic_write_json(base / "phase9_4_testnet_reconciliation_validation_report.json", phase9_4_validation)
        atomic_write_json(base / "phase9_3_9_4_blocked_design_hardening_negative_fixture_results.json", negative_fixture_results)
        (base / "PHASE9_3_9_4_BLOCKED_DESIGN_HARDENING_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_3_9_4_HARDENING_REGISTRY_NAME),
        {
            "phase9_3_9_4_blocked_design_hardening_id": report.get("phase9_3_9_4_blocked_design_hardening_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "phase9_3_status_cancel_hardening_recorded": report.get("phase9_3_status_cancel_hardening_recorded"),
            "phase9_4_testnet_reconciliation_design_recorded": report.get("phase9_4_testnet_reconciliation_design_recorded"),
            "phase9_3_status_polling_may_begin": False,
            "phase9_4_testnet_reconciliation_may_begin": False,
            "phase10_signed_testnet_session_validation_may_begin": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_3_9_4_HARDENING_REGISTRY_NAME,
        id_field="phase9_3_9_4_blocked_design_hardening_registry_record_id",
        hash_field="phase9_3_9_4_blocked_design_hardening_registry_record_sha256",
        id_prefix="phase9_3_9_4_blocked_design_hardening_registry_record",
    )
    atomic_write_json(latest / "phase9_3_9_4_blocked_design_hardening_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_3_9_4_blocked_design_hardening_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_3_9_4_HARDENING_VERSION",
    "STATUS_PHASE9_3_9_4_HARDENING_RECORDED_BLOCKED_REVIEW_ONLY",
    "STATUS_PHASE9_3_9_4_HARDENING_BLOCKED_REVIEW_ONLY",
    "build_phase9_3_9_4_blocked_design_hardening_report",
    "persist_phase9_3_9_4_blocked_design_hardening_report",
    "validate_phase9_3_status_cancel_hardened_design",
    "validate_phase9_4_testnet_reconciliation_design",
]
