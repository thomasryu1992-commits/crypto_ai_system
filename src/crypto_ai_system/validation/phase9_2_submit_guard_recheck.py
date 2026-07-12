from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_operator_supplied_approval_fixture import (
    STATUS_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY,
    persist_phase9_1_operator_supplied_approval_fixture_report,
)
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS

PHASE9_2_RECHECK_VERSION = "phase9_2_submit_guard_recheck_after_operator_fixture_v1"
PHASE9_2_RECHECK_REGISTRY_NAME = "phase9_2_submit_guard_recheck_after_operator_fixture_registry"
STATUS_RECHECK_READY_REVIEW_ONLY = "PHASE9_2_SUBMIT_GUARD_RECHECK_READY_REVIEW_ONLY"
STATUS_RECHECK_BLOCKED_REVIEW_ONLY = "PHASE9_2_SUBMIT_GUARD_RECHECK_BLOCKED_REVIEW_ONLY"

REQUIRED_RECHECK_SOURCE_FILES = {
    "phase9_1_operator_fixture_report": "phase9_1_operator_supplied_approval_fixture_report.json",
    "phase9_1_operator_fixture": "phase9_1_operator_supplied_approval_FIXTURE_REVIEW_ONLY.json",
    "phase9_1_operator_fixture_validation": "phase9_1_operator_supplied_approval_fixture_validation_report.json",
    "phase8_3_hot_path_gate": "hot_path_preorder_risk_gate_review_only.json",
    "phase8_3_hot_path_guard": "hot_path_preorder_risk_gate_guard_report.json",
}

UNSAFE_TRUTHY_FIELDS = list(FALSE_FLAGS) + [
    "phase9_2_order_submission_authorized",
    "phase9_order_submission_authorized",
    "order_submission_authorized",
]

CLEARED_BY_FIXTURE_RECHECK = [
    "PHASE9_2_OPERATOR_DECISION_NOT_EXPLICIT_APPROVAL",
    "PHASE9_2_OPERATOR_SIGNATURE_MISSING",
    "PHASE9_2_TESTNET_KEY_FINGERPRINT_MISSING_OR_PLACEHOLDER",
    "PHASE9_2_KILL_SWITCH_NOT_CONFIRMED_FOR_SUBMIT",
    "PHASE9_2_PHASE9_1_ACTUAL_APPROVAL_INCOMPLETE",
]

REMAINING_REAL_SUBMIT_BLOCKERS = [
    "PHASE9_2_OPERATOR_APPROVAL_IS_FIXTURE_ONLY_NOT_RUNTIME_AUTHORITY",
    "PHASE9_2_FRESH_PREORDER_RISK_GATE_REFRESH_REQUIRED_IMMEDIATELY_BEFORE_REAL_SUBMIT",
    "PHASE9_2_ORDER_ENDPOINT_CALLS_DISABLED_BY_DESIGN",
    "PHASE9_2_SIGNATURE_CREATION_DISABLED_BY_DESIGN",
    "PHASE9_2_HTTP_TRANSMISSION_DISABLED_BY_DESIGN",
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
    return sorted(dict.fromkeys(fields))


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase9_2_submit_guard_recheck_report_sha256",
        "phase9_2_submit_guard_recheck_artifact_sha256",
        "phase9_1_operator_supplied_approval_fixture_report_sha256",
        "phase9_1_operator_supplied_approval_fixture_sha256",
        "phase9_1_operator_supplied_approval_fixture_validation_report_sha256",
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
        "status": data.get("status") or data.get("artifact_type") or data.get("gate_type") or data.get("guard_type"),
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
    if name == "phase9_1_operator_fixture_report":
        return (
            data.get("status") == STATUS_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY
            and data.get("phase9_1_operator_supplied_approval_fixture_validated") is True
            and data.get("phase9_2_submit_guard_recheck_may_begin") is True
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "phase9_1_operator_fixture":
        return (
            data.get("artifact_type") == "phase9_1_operator_supplied_approval_fixture_review_only"
            and data.get("operator_decision") == "approve_single_signed_testnet_order"
            and data.get("operator_supplied_fixture_only") is True
            and data.get("fixture_not_actual_runtime_approval") is True
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "phase9_1_operator_fixture_validation":
        return (
            data.get("artifact_type") == "phase9_1_operator_supplied_approval_fixture_validation_report"
            and data.get("fixture_valid_review_only") is True
            and data.get("fixture_values_complete_review_only") is True
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "phase8_3_hot_path_gate":
        return (
            data.get("gate_type") == "phase8_3_hot_path_preorder_risk_gate_review_only"
            and data.get("no_order_endpoint_calls") is True
            and data.get("pre_submit_order_allowed") is False
        )
    if name == "phase8_3_hot_path_guard":
        return data.get("guard_passed") is True
    return True


def _flag_false_payload() -> dict[str, bool]:
    return {field: False for field in FALSE_FLAGS}


def build_phase9_2_submit_guard_recheck_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_operator_fixture_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_operator_fixture_first:
        persist_phase9_1_operator_supplied_approval_fixture_report(cfg=cfg, run_phase9_1_hardening_first=True)

    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_RECHECK_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_2_RECHECK_REQUIRED_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_2_RECHECK_REQUIRED_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_2_RECHECK_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items())
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers

    fixture = sources.get("phase9_1_operator_fixture", {})
    gate = sources.get("phase8_3_hot_path_gate", {})
    canonical_id_chain = dict(gate.get("canonical_id_chain") or {})
    idempotency_key_preview = stable_id(
        "phase9_2_recheck_idempotency_key_preview",
        {
            "approval_fixture_hash": _artifact_hash(fixture),
            "hot_path_gate_hash": _artifact_hash(gate),
            "created_at_utc": created,
        },
        24,
    )

    recheck = {
        "artifact_type": "phase9_2_single_testnet_order_submit_guard_recheck_review_only",
        "phase9_2_recheck_version": PHASE9_2_RECHECK_VERSION,
        "review_only": True,
        "fixture_only": True,
        "source_evidence_hash_summary": source_summary,
        "canonical_id_chain": canonical_id_chain,
        "phase9_1_operator_supplied_approval_fixture_validated": ready,
        "phase9_2_pre_submit_conditions_ready_for_review_only": ready,
        "cleared_previous_phase9_2_blockers_by_fixture": CLEARED_BY_FIXTURE_RECHECK if ready else [],
        "remaining_real_submit_blockers": REMAINING_REAL_SUBMIT_BLOCKERS,
        "idempotency_key_preview": idempotency_key_preview,
        "idempotency_key_is_preview_only": True,
        "dry_order_payload_preview": {
            "symbol": "BTCUSDT",
            "side": "UNSET_REVIEW_ONLY_FIXTURE",
            "order_type": "UNSET_REVIEW_ONLY_FIXTURE",
            "notional_cap": str(fixture.get("small_max_notional") or "5.0"),
            "client_order_id_preview": idempotency_key_preview,
            "complete_id_chain_required": True,
            "no_signature_created": True,
            "no_http_request_sent": True,
            "no_order_endpoint_called": True,
        },
        "phase9_2_order_submission_authorized": False,
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "phase9_3_status_polling_may_begin": False,
        "order_submission_performed": False,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        **_flag_false_payload(),
        "created_at_utc": created,
    }
    recheck["phase9_2_submit_guard_recheck_artifact_sha256"] = sha256_json(recheck)

    negative_fixture_results = _build_negative_fixture_results(recheck)
    status = STATUS_RECHECK_READY_REVIEW_ONLY if ready and negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] else STATUS_RECHECK_BLOCKED_REVIEW_ONLY
    report = {
        "phase9_2_submit_guard_recheck_id": stable_id(
            "phase9_2_submit_guard_recheck_after_operator_fixture",
            {"source_summary": source_summary, "recheck_hash": sha256_json(recheck), "blockers": blockers, "created_at_utc": created},
            24,
        ),
        "phase9_2_recheck_version": PHASE9_2_RECHECK_VERSION,
        "status": status,
        "blocked": status != STATUS_RECHECK_READY_REVIEW_ONLY,
        "fail_closed": status != STATUS_RECHECK_READY_REVIEW_ONLY,
        "review_only": True,
        "fixture_only": True,
        "phase9_2_submit_guard_recheck_ready": status == STATUS_RECHECK_READY_REVIEW_ONLY,
        "phase9_2_pre_submit_conditions_ready_for_review_only": status == STATUS_RECHECK_READY_REVIEW_ONLY,
        "phase9_2_order_submission_authorized": False,
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "phase9_3_status_polling_may_begin": False,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe,
        "cleared_previous_phase9_2_blockers_by_fixture": CLEARED_BY_FIXTURE_RECHECK if status == STATUS_RECHECK_READY_REVIEW_ONLY else [],
        "remaining_real_submit_blockers": REMAINING_REAL_SUBMIT_BLOCKERS,
        "block_reasons": blockers,
        "negative_fixture_results": negative_fixture_results,
        "recommended_next_action": "collect_real_operator_approval_outside_fixture_and_run_phase9_2_real_submit_guard_with_order_endpoint_controls_still_disabled_until_explicit_action",
        **_flag_false_payload(),
        "created_at_utc": created,
    }
    report["phase9_2_submit_guard_recheck_report_sha256"] = sha256_json(report)
    return report, recheck, negative_fixture_results


def _build_negative_fixture_results(recheck: Mapping[str, Any]) -> dict[str, Any]:
    cases: dict[str, dict[str, Any]] = {
        "unsafe_submit_permission_true": {"testnet_order_submission_allowed": True},
        "order_endpoint_called_true": {"order_endpoint_called": True},
        "http_request_sent_true": {"http_request_sent": True},
        "signature_created_true": {"signature_created": True},
        "order_submission_authorized_true": {"phase9_2_order_submission_authorized": True},
    }
    results: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(recheck)
        payload.update(patch)
        unsafe = _unsafe_fields(payload)
        blocked = bool(unsafe)
        results[name] = {
            "fixture_name": name,
            "blocked": blocked,
            "fail_closed": blocked,
            "block_reasons": ["UNSAFE_PHASE9_2_RECHECK_FLAGS:" + ",".join(unsafe)] if unsafe else [],
        }
    all_blocked = all(item["blocked"] and item["fail_closed"] for item in results.values())
    return {
        "artifact_type": "phase9_2_submit_guard_recheck_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 9.2 Submit Guard Recheck After Operator Fixture - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact rechecks the Phase 9.2 submit guard using a review-only operator approval fixture. It does not authorize or perform a signed testnet order submission.",
            "",
            "## Result",
            "",
            f"- Recheck ready: `{report.get('phase9_2_submit_guard_recheck_ready')}`",
            f"- Pre-submit conditions ready for review only: `{report.get('phase9_2_pre_submit_conditions_ready_for_review_only')}`",
            f"- Order submission authorized: `{report.get('phase9_2_order_submission_authorized')}`",
            f"- Phase 9.3 status polling may begin: `{report.get('phase9_3_status_polling_may_begin')}`",
            "",
            "## Still Disabled",
            "",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `actual_order_submission_performed=false`",
            "- `order_endpoint_called=false`",
            "- `http_request_sent=false`",
            "- `signature_created=false`",
            "",
        ]
    )


def persist_phase9_2_submit_guard_recheck_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_operator_fixture_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_single_testnet_order_submit")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, recheck, negative_fixture_results = build_phase9_2_submit_guard_recheck_report(
        cfg=cfg,
        run_operator_fixture_first=run_operator_fixture_first,
    )
    handoff = _build_handoff_markdown(report)
    atomic_write_json(latest / "phase9_2_submit_guard_recheck_after_operator_fixture_report.json", report)
    atomic_write_json(latest / "single_testnet_order_submit_guard_recheck_REVIEW_ONLY.json", recheck)
    atomic_write_json(latest / "phase9_2_submit_guard_recheck_negative_fixture_results.json", negative_fixture_results)
    (latest / "PHASE9_2_SUBMIT_GUARD_RECHECK_AFTER_OPERATOR_FIXTURE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(phase_dir / "phase9_2_submit_guard_recheck_after_operator_fixture_report.json", report)
    atomic_write_json(phase_dir / "single_testnet_order_submit_guard_recheck_REVIEW_ONLY.json", recheck)
    atomic_write_json(phase_dir / "phase9_2_submit_guard_recheck_negative_fixture_results.json", negative_fixture_results)
    (phase_dir / "PHASE9_2_SUBMIT_GUARD_RECHECK_AFTER_OPERATOR_FIXTURE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(signed_testnet_dir / "phase9_2_submit_guard_recheck_after_operator_fixture_report.json", report)
    atomic_write_json(signed_testnet_dir / "single_testnet_order_submit_guard_recheck_REVIEW_ONLY.json", recheck)
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_RECHECK_REGISTRY_NAME),
        {
            "phase9_2_submit_guard_recheck_id": report.get("phase9_2_submit_guard_recheck_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "fixture_only": True,
            "phase9_2_submit_guard_recheck_ready": report.get("phase9_2_submit_guard_recheck_ready"),
            "phase9_2_order_submission_authorized": False,
            "phase9_3_status_polling_may_begin": False,
            "actual_order_submission_performed": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_2_RECHECK_REGISTRY_NAME,
        id_field="phase9_2_submit_guard_recheck_registry_record_id",
        hash_field="phase9_2_submit_guard_recheck_registry_record_sha256",
        id_prefix="phase9_2_submit_guard_recheck_registry_record",
    )
    atomic_write_json(latest / "phase9_2_submit_guard_recheck_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_submit_guard_recheck_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_RECHECK_VERSION",
    "STATUS_RECHECK_READY_REVIEW_ONLY",
    "STATUS_RECHECK_BLOCKED_REVIEW_ONLY",
    "build_phase9_2_submit_guard_recheck_report",
    "persist_phase9_2_submit_guard_recheck_report",
]
