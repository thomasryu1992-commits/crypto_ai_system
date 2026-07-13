from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_VERSION = "p22_operator_release_candidate_acceptance_review_v1"
P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_REGISTRY_NAME = "p22_operator_release_candidate_acceptance_review_registry"

STATUS_WAITING_REVIEW_ONLY = "P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_WAITING_REVIEW_ONLY"
STATUS_VALID_REVIEW_ONLY = "P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_VALID_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_BLOCKED_FAIL_CLOSED"

_P21_SUMMARY_FILENAME = "p21_ci_filled_evidence_release_candidate_bundle_summary.json"
_P21_REPORT_FILENAME = "p21_ci_filled_evidence_release_candidate_bundle_report.json"
_P22_ACCEPTANCE_INTAKE_FILENAME = "p22_operator_release_candidate_acceptance_intake.json"

P22_EXACT_ACCEPTANCE_PHRASE = "I ACCEPT THIS REVIEW-ONLY RELEASE CANDIDATE BUNDLE AND ACKNOWLEDGE IT IS NOT RUNTIME AUTHORITY"

_EXECUTION_FIELDS_FOR_P22 = {
    "limited_live_scaled_auto_trading_allowed",
    "live_scaled_runtime_enablement_allowed",
    "live_scaled_execution_enabled",
    "live_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "runtime_scheduler_enabled",
    "runtime_loop_started",
    "actual_live_order_submitted",
    "actual_testnet_order_submitted",
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
}

_SECRET_VALUE_PATTERNS = (
    "BINANCE_API_SECRET=",
    "BINANCE_API_KEY=",
    "PRIVATE_KEY=",
    "api_secret_value:",
    "api_key_value:",
    "secret_value:",
    "BEGIN PRIVATE KEY",
)


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


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value.lower())


def _scan_truthy_execution_fields(payloads: Sequence[tuple[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                next_path = f"{path}.{key}"
                if key in _EXECUTION_FIELDS_FOR_P22 and _bool(value):
                    hits.append({"path": next_path, "field": str(key), "value": True})
                walk(value, next_path)
        elif isinstance(payload, list):
            for idx, item in enumerate(payload):
                walk(item, f"{path}[{idx}]")

    for source, payload in payloads:
        before = len(hits)
        walk(payload)
        for hit in hits[before:]:
            hit["source"] = source
    return hits


def _scan_secret_value_patterns(payloads: Sequence[tuple[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, source: str, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                walk(value, source, f"{path}.{key}")
        elif isinstance(payload, list):
            for idx, item in enumerate(payload):
                walk(item, source, f"{path}[{idx}]")
        elif isinstance(payload, str):
            for pattern in _SECRET_VALUE_PATTERNS:
                if pattern.lower() in payload.lower():
                    hits.append({"source": source, "path": path, "pattern": pattern})

    for source, payload in payloads:
        walk(payload, source)
    return hits


def build_operator_release_candidate_acceptance_intake_template(
    *,
    p21_release_candidate_bundle_sha256: str | None = None,
    release_candidate_bundle_content_sha256: str | None = None,
) -> dict[str, Any]:
    template = {
        "acceptance_type": "operator_release_candidate_acceptance_review_only",
        "stage": "release_candidate_acceptance",
        "operator_id": "OPERATOR_ID_REQUIRED",
        "ticket_or_signature": "TICKET_OR_SIGNATURE_REQUIRED",
        "accepted_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
        "exact_acceptance_phrase": P22_EXACT_ACCEPTANCE_PHRASE,
        "source_p21_ci_filled_evidence_release_candidate_bundle_sha256": p21_release_candidate_bundle_sha256 or "P21_REPORT_SHA256_REQUIRED",
        "release_candidate_bundle_content_sha256": release_candidate_bundle_content_sha256 or "P21_BUNDLE_CONTENT_SHA256_REQUIRED",
        "review_only_release_candidate_accepted": True,
        "release_candidate_bundle_is_runtime_authority_acknowledged": False,
        "no_runtime_authority_acknowledged": True,
        "separate_runtime_enablement_required_acknowledged": True,
        "no_execution_flags_modified_acknowledged": True,
        "no_order_submission_allowed_acknowledged": True,
        "no_scheduler_enablement_allowed_acknowledged": True,
        "no_secret_values_inserted_acknowledged": True,
        "manual_operator_submission": True,
        "auto_generated_intake": False,
        "runtime_enablement_requested": False,
        "order_submission_requested": False,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "actual_live_order_submitted": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
    }
    template["p22_operator_acceptance_intake_template_sha256"] = sha256_json(template)
    return template


def _validate_acceptance_intake(
    *,
    p21_summary: Mapping[str, Any],
    p21_report: Mapping[str, Any],
    acceptance_intake: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    waiting: list[str] = []
    blocked: list[str] = []
    if not acceptance_intake:
        waiting.append("P22_OPERATOR_ACCEPTANCE_INTAKE_MISSING")
        return waiting, blocked
    if acceptance_intake.get("acceptance_type") != "operator_release_candidate_acceptance_review_only":
        blocked.append("P22_ACCEPTANCE_TYPE_INVALID")
    if acceptance_intake.get("stage") != "release_candidate_acceptance":
        blocked.append("P22_ACCEPTANCE_STAGE_INVALID")
    if not str(acceptance_intake.get("operator_id", "")).strip() or str(acceptance_intake.get("operator_id", "")).startswith("OPERATOR"):
        blocked.append("P22_OPERATOR_ID_MISSING")
    if not str(acceptance_intake.get("ticket_or_signature", "")).strip() or str(acceptance_intake.get("ticket_or_signature", "")).startswith("TICKET"):
        blocked.append("P22_TICKET_OR_SIGNATURE_MISSING")
    if acceptance_intake.get("exact_acceptance_phrase") != P22_EXACT_ACCEPTANCE_PHRASE:
        blocked.append("P22_EXACT_ACCEPTANCE_PHRASE_MISSING_OR_INVALID")
    p21_hash = p21_summary.get("p21_ci_filled_evidence_release_candidate_bundle_sha256") or p21_report.get("p21_ci_filled_evidence_release_candidate_bundle_sha256")
    if not _is_sha256(p21_hash):
        waiting.append("P22_SOURCE_P21_HASH_MISSING_OR_INVALID")
    elif acceptance_intake.get("source_p21_ci_filled_evidence_release_candidate_bundle_sha256") != p21_hash:
        blocked.append("P22_P21_HASH_MISMATCH")
    bundle_hash = p21_summary.get("release_candidate_bundle_content_sha256")
    if not _is_sha256(bundle_hash):
        waiting.append("P22_P21_RELEASE_CANDIDATE_BUNDLE_HASH_MISSING_OR_INVALID")
    elif acceptance_intake.get("release_candidate_bundle_content_sha256") != bundle_hash:
        blocked.append("P22_BUNDLE_CONTENT_HASH_MISMATCH")
    required_true = [
        "review_only_release_candidate_accepted",
        "no_runtime_authority_acknowledged",
        "separate_runtime_enablement_required_acknowledged",
        "no_execution_flags_modified_acknowledged",
        "no_order_submission_allowed_acknowledged",
        "no_scheduler_enablement_allowed_acknowledged",
        "no_secret_values_inserted_acknowledged",
        "manual_operator_submission",
    ]
    for field in required_true:
        if acceptance_intake.get(field) is not True:
            blocked.append(f"P22_{field.upper()}_REQUIRED")
    required_false = [
        "release_candidate_bundle_is_runtime_authority_acknowledged",
        "auto_generated_intake",
        "runtime_enablement_requested",
        "order_submission_requested",
        "limited_live_scaled_auto_trading_allowed",
        "live_scaled_execution_enabled",
        "live_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "runtime_scheduler_enabled",
        "runtime_loop_started",
        "actual_live_order_submitted",
        "secret_value_accessed",
        "secret_value_logged",
    ]
    for field in required_false:
        if acceptance_intake.get(field) is not False:
            blocked.append(f"P22_{field.upper()}_MUST_BE_FALSE")
    return waiting, blocked


def build_operator_release_candidate_acceptance_review_report(
    *,
    root: Path,
    p21_summary: Mapping[str, Any] | None = None,
    p21_report: Mapping[str, Any] | None = None,
    acceptance_intake: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    del root
    p21_summary = dict(p21_summary or {})
    p21_report = dict(p21_report or {})
    acceptance_intake = dict(acceptance_intake or {})
    p21_hash = p21_summary.get("p21_ci_filled_evidence_release_candidate_bundle_sha256") or p21_report.get("p21_ci_filled_evidence_release_candidate_bundle_sha256")
    bundle_hash = p21_summary.get("release_candidate_bundle_content_sha256")
    template = build_operator_release_candidate_acceptance_intake_template(
        p21_release_candidate_bundle_sha256=str(p21_hash) if p21_hash else None,
        release_candidate_bundle_content_sha256=str(bundle_hash) if bundle_hash else None,
    )

    named_payloads: list[tuple[str, Mapping[str, Any]]] = [
        ("p21_summary", p21_summary),
        ("p21_report", p21_report),
        ("acceptance_intake", acceptance_intake),
        ("acceptance_template", template),
    ]
    named_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(named_payloads)
    secret_hits = _scan_secret_value_patterns(named_payloads)
    disabled_state = default_execution_flag_state()
    disabled_state.update({field: False for field in _EXECUTION_FIELDS_FOR_P22})
    truthy_disabled = truthy_execution_flags(disabled_state)

    waiting_reasons: list[str] = []
    block_reasons: list[str] = []
    if not p21_summary:
        waiting_reasons.append("P22_SOURCE_P21_SUMMARY_MISSING")
    if p21_summary and p21_summary.get("status") == "P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_BLOCKED_FAIL_CLOSED":
        block_reasons.append("P22_SOURCE_P21_BLOCKED")
    if p21_summary and p21_summary.get("p21_release_candidate_bundle_ready_review_only") is not True:
        waiting_reasons.append("P22_SOURCE_P21_RELEASE_CANDIDATE_BUNDLE_NOT_READY")
    if p21_summary and p21_summary.get("separate_operator_acceptance_required") is not True:
        block_reasons.append("P22_SOURCE_P21_OPERATOR_ACCEPTANCE_NOT_REQUIRED_INVALID")
    if p21_summary and p21_summary.get("release_candidate_bundle_path") is None:
        waiting_reasons.append("P22_SOURCE_P21_RELEASE_CANDIDATE_BUNDLE_PATH_MISSING")
    if not p21_report:
        waiting_reasons.append("P22_SOURCE_P21_REPORT_MISSING")
    if p21_report and p21_report.get("p21_release_candidate_bundle_ready_review_only") is not True:
        waiting_reasons.append("P22_SOURCE_P21_REPORT_NOT_VALID_FOR_ACCEPTANCE")
    if p21_summary and p21_report and p21_summary.get("p21_ci_filled_evidence_release_candidate_bundle_sha256") != p21_report.get("p21_ci_filled_evidence_release_candidate_bundle_sha256"):
        block_reasons.append("P22_SOURCE_P21_SUMMARY_REPORT_HASH_MISMATCH")
    intake_waiting, intake_blocked = _validate_acceptance_intake(
        p21_summary=p21_summary,
        p21_report=p21_report,
        acceptance_intake=acceptance_intake,
    )
    waiting_reasons.extend(intake_waiting)
    block_reasons.extend(intake_blocked)
    if unsafe_hits:
        block_reasons.append("P22_UNSAFE_TRUTHY_FLAG_FOUND")
    if secret_hits:
        block_reasons.append("P22_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P22_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    valid = not blocked and not waiting_reasons
    status = STATUS_BLOCKED_FAIL_CLOSED if blocked else (STATUS_VALID_REVIEW_ONLY if valid else STATUS_WAITING_REVIEW_ONLY)
    acceptance_hash = sha256_json(acceptance_intake) if acceptance_intake else None
    report: dict[str, Any] = {
        "p22_operator_release_candidate_acceptance_review_version": P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": valid,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "source_p21_ci_filled_evidence_release_candidate_bundle_sha256": p21_hash,
        "source_p21_release_candidate_bundle_content_sha256": bundle_hash,
        "operator_acceptance_intake_sha256": acceptance_hash,
        "operator_acceptance_template": template,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "p22_operator_release_candidate_acceptance_valid_review_only": valid,
        "release_candidate_accepted_review_only": valid,
        "operator_acceptance_is_runtime_authority": False,
        "release_candidate_bundle_is_runtime_authority": False,
        "separate_runtime_enablement_required": True,
        "separate_live_scaled_runtime_enablement_boundary_required": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "actual_live_order_submitted": False,
        "actual_testnet_order_submitted": False,
        "live_order_endpoint_called": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    report["p22_operator_release_candidate_acceptance_review_id"] = stable_id("p22_operator_release_candidate_acceptance_review", report, 24)
    report["p22_operator_release_candidate_acceptance_review_sha256"] = sha256_json(report)
    return report


def build_p22_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    p21_hash = "a" * 64
    bundle_hash = "b" * 64
    p21_summary = {
        "status": "P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_VALID_REVIEW_ONLY",
        "p21_ci_filled_evidence_release_candidate_bundle_sha256": p21_hash,
        "p21_release_candidate_bundle_ready_review_only": True,
        "release_candidate_bundle_path": "storage/latest/p21_release_candidate_bundle_review_only.zip",
        "release_candidate_bundle_content_sha256": bundle_hash,
        "separate_operator_acceptance_required": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p21_report = {
        "status": "P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_VALID_REVIEW_ONLY",
        "p21_ci_filled_evidence_release_candidate_bundle_sha256": p21_hash,
        "p21_release_candidate_bundle_ready_review_only": True,
        "release_candidate_bundle_is_runtime_authority": False,
        "separate_operator_acceptance_required": True,
        "separate_runtime_enablement_required": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    intake = build_operator_release_candidate_acceptance_intake_template(
        p21_release_candidate_bundle_sha256=p21_hash,
        release_candidate_bundle_content_sha256=bundle_hash,
    )
    intake.update({"operator_id": "operator-thomas", "ticket_or_signature": "OPS-12345-signed"})
    base = {"p21_summary": p21_summary, "p21_report": p21_report, "acceptance_intake": intake}
    cases = {
        "p21_not_ready": {**base, "p21_summary": {**p21_summary, "p21_release_candidate_bundle_ready_review_only": False}},
        "missing_acceptance_intake": {**base, "acceptance_intake": {}},
        "missing_operator_identity": {**base, "acceptance_intake": {**intake, "operator_id": ""}},
        "missing_ticket_signature": {**base, "acceptance_intake": {**intake, "ticket_or_signature": ""}},
        "missing_exact_phrase": {**base, "acceptance_intake": {**intake, "exact_acceptance_phrase": "approve"}},
        "p21_hash_mismatch": {**base, "acceptance_intake": {**intake, "source_p21_ci_filled_evidence_release_candidate_bundle_sha256": "c" * 64}},
        "bundle_hash_mismatch": {**base, "acceptance_intake": {**intake, "release_candidate_bundle_content_sha256": "d" * 64}},
        "runtime_authority_claimed": {**base, "acceptance_intake": {**intake, "release_candidate_bundle_is_runtime_authority_acknowledged": True}},
        "runtime_enablement_requested": {**base, "acceptance_intake": {**intake, "runtime_enablement_requested": True}},
        "order_submission_requested": {**base, "acceptance_intake": {**intake, "order_submission_requested": True}},
        "auto_generated_intake": {**base, "acceptance_intake": {**intake, "auto_generated_intake": True}},
        "missing_no_runtime_ack": {**base, "acceptance_intake": {**intake, "no_runtime_authority_acknowledged": False}},
        "unsafe_runtime_flag": {**base, "acceptance_intake": {**intake, "live_scaled_execution_enabled": True}},
        "secret_pattern_found": {**base, "acceptance_intake": {**intake, "operator_note": "BINANCE_API_SECRET=leaked"}},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_operator_release_candidate_acceptance_review_report(root=root, **kwargs)
        blocked_or_waiting = report["blocked"] or report["waiting"]
        results[name] = {
            "blocked_or_waiting": blocked_or_waiting,
            "blocked": report["blocked"],
            "waiting": report["waiting"],
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "waiting_reasons": report["waiting_reasons"],
            "limited_live_scaled_auto_trading_allowed": report["limited_live_scaled_auto_trading_allowed"],
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
            "live_order_submission_allowed": report["live_order_submission_allowed"],
            "runtime_scheduler_enabled": report["runtime_scheduler_enabled"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    return {
        "p22_operator_release_candidate_acceptance_review_version": P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_VERSION,
        "status": "P22_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_operator_release_candidate_acceptance_review(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p22_operator_release_candidate_acceptance_review")
    p21_summary = _read_latest_json(cfg, _P21_SUMMARY_FILENAME)
    p21_report = _read_latest_json(cfg, _P21_REPORT_FILENAME)
    acceptance_intake = _read_latest_json(cfg, _P22_ACCEPTANCE_INTAKE_FILENAME)
    report = build_operator_release_candidate_acceptance_review_report(
        root=cfg.root,
        p21_summary=p21_summary,
        p21_report=p21_report,
        acceptance_intake=acceptance_intake,
    )
    negative_results = build_p22_negative_fixture_results(root=cfg.root)
    atomic_write_json(latest / "p22_operator_release_candidate_acceptance_review_report.json", report)
    atomic_write_json(storage / "p22_operator_release_candidate_acceptance_review_report.json", report)
    atomic_write_json(latest / "p22_operator_release_candidate_acceptance_intake_TEMPLATE.json", report["operator_acceptance_template"])
    atomic_write_json(latest / "p22_operator_release_candidate_acceptance_review_negative_fixture_results.json", negative_results)
    summary = {
        "status": report["status"],
        "p22_operator_release_candidate_acceptance_review_sha256": report["p22_operator_release_candidate_acceptance_review_sha256"],
        "p22_operator_release_candidate_acceptance_valid_review_only": report["p22_operator_release_candidate_acceptance_valid_review_only"],
        "release_candidate_accepted_review_only": report["release_candidate_accepted_review_only"],
        "operator_acceptance_intake_sha256": report["operator_acceptance_intake_sha256"],
        "source_p21_ci_filled_evidence_release_candidate_bundle_sha256": report["source_p21_ci_filled_evidence_release_candidate_bundle_sha256"],
        "waiting_reasons": report["waiting_reasons"],
        "block_reasons": report["block_reasons"],
        "separate_runtime_enablement_required": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "actual_live_order_submitted": False,
        "actual_testnet_order_submitted": False,
        "live_order_endpoint_called": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    summary["p22_operator_release_candidate_acceptance_review_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p22_operator_release_candidate_acceptance_review_summary.json", summary)
    registry_record = append_registry_record(
        registry_path(cfg, P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_REGISTRY_NAME),
        report,
        registry_name=P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_REGISTRY_NAME,
        id_field="p22_operator_release_candidate_acceptance_review_registry_id",
        hash_field="p22_operator_release_candidate_acceptance_review_registry_sha256",
        id_prefix="p22_operator_release_candidate_acceptance_review",
    )
    atomic_write_json(latest / "p22_operator_release_candidate_acceptance_review_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_operator_release_candidate_acceptance_review()
    print(result["status"])
    print(result["p22_operator_release_candidate_acceptance_review_sha256"])
