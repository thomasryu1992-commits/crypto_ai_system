from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.docker_launcher_evidence_intake import (
    build_docker_build_external_evidence_template,
    build_docker_run_external_evidence_template,
    build_launcher_import_external_evidence_template,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_VERSION = "p21_ci_filled_evidence_release_candidate_bundle_v1"
P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_REGISTRY_NAME = "p21_ci_filled_evidence_release_candidate_bundle_registry"

STATUS_WAITING_REVIEW_ONLY = "P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_WAITING_REVIEW_ONLY"
STATUS_VALID_REVIEW_ONLY = "P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_VALID_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_BLOCKED_FAIL_CLOSED"

_P19_SUMMARY_FILENAME = "p19_docker_launcher_evidence_intake_summary.json"
_P19_REPORT_FILENAME = "p19_docker_launcher_evidence_intake_report.json"
_P20_SUMMARY_FILENAME = "p20_external_evidence_template_export_pack_summary.json"
_P20_REPORT_FILENAME = "p20_external_evidence_template_export_pack_report.json"
_P20_MANIFEST_FILENAME = "p20_ci_artifact_export_manifest.json"
_DOCKER_BUILD_EXTERNAL_EVIDENCE_FILENAME = "p19_docker_build_evidence_external.json"
_DOCKER_RUN_EXTERNAL_EVIDENCE_FILENAME = "p19_docker_run_self_test_evidence_external.json"
_LAUNCHER_EXTERNAL_EVIDENCE_FILENAME = "p19_launcher_import_evidence_external.json"

_EXECUTION_FIELDS_FOR_P21 = {
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

_REQUIRED_FILLED_EVIDENCE = {
    "docker_build": _DOCKER_BUILD_EXTERNAL_EVIDENCE_FILENAME,
    "docker_run_self_test": _DOCKER_RUN_EXTERNAL_EVIDENCE_FILENAME,
    "launcher_import": _LAUNCHER_EXTERNAL_EVIDENCE_FILENAME,
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


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value.lower())


def _scan_truthy_execution_fields(payloads: Sequence[tuple[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                next_path = f"{path}.{key}"
                if key in _EXECUTION_FIELDS_FOR_P21 and _bool(value):
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


def _filled_evidence_missing(
    *,
    docker_build_evidence: Mapping[str, Any],
    docker_run_evidence: Mapping[str, Any],
    launcher_import_evidence: Mapping[str, Any],
) -> list[str]:
    missing: list[str] = []
    if not docker_build_evidence:
        missing.append(_DOCKER_BUILD_EXTERNAL_EVIDENCE_FILENAME)
    if not docker_run_evidence:
        missing.append(_DOCKER_RUN_EXTERNAL_EVIDENCE_FILENAME)
    if not launcher_import_evidence:
        missing.append(_LAUNCHER_EXTERNAL_EVIDENCE_FILENAME)
    return missing


def _evidence_file_hashes(
    *,
    docker_build_evidence: Mapping[str, Any],
    docker_run_evidence: Mapping[str, Any],
    launcher_import_evidence: Mapping[str, Any],
) -> dict[str, str | None]:
    return {
        "docker_build": sha256_json(docker_build_evidence) if docker_build_evidence else None,
        "docker_run_self_test": sha256_json(docker_run_evidence) if docker_run_evidence else None,
        "launcher_import": sha256_json(launcher_import_evidence) if launcher_import_evidence else None,
    }


def _validate_filled_evidence_against_p19(
    *,
    p19_report: Mapping[str, Any],
    docker_build_evidence: Mapping[str, Any],
    docker_run_evidence: Mapping[str, Any],
    launcher_import_evidence: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    hashes = _evidence_file_hashes(
        docker_build_evidence=docker_build_evidence,
        docker_run_evidence=docker_run_evidence,
        launcher_import_evidence=launcher_import_evidence,
    )
    expected = {
        "docker_build": p19_report.get("docker_build_evidence_sha256"),
        "docker_run_self_test": p19_report.get("docker_run_self_test_evidence_sha256"),
        "launcher_import": p19_report.get("launcher_import_evidence_sha256"),
    }
    for key, actual in hashes.items():
        if actual and expected.get(key) and actual != expected[key]:
            reasons.append(f"P21_{key.upper()}_EVIDENCE_HASH_MISMATCH")
    checks = {
        "docker_build": p19_report.get("docker_build_evidence_valid_review_only"),
        "docker_run_self_test": p19_report.get("docker_run_self_test_evidence_valid_review_only"),
        "launcher_import": p19_report.get("launcher_import_evidence_valid_review_only"),
    }
    for key, value in checks.items():
        if value is not True:
            reasons.append(f"P21_{key.upper()}_P19_CHECK_NOT_VALID")
    return reasons


def _validate_manifest_artifacts(
    *,
    p20_summary: Mapping[str, Any],
    p20_report: Mapping[str, Any],
    p20_manifest: Mapping[str, Any],
    p18_hash: str | None,
) -> list[str]:
    reasons: list[str] = []
    if not p20_manifest:
        return ["P21_P20_MANIFEST_MISSING"]
    if p20_manifest.get("artifact_pack_type") != "docker_launcher_external_evidence_template_export_pack":
        reasons.append("P21_P20_MANIFEST_TYPE_INVALID")
    if p20_manifest.get("source_p18_full_regression_ci_release_gate_sha256") != p18_hash:
        reasons.append("P21_P20_MANIFEST_P18_HASH_MISMATCH")
    if p20_summary.get("ci_artifact_export_manifest_sha256") and p20_manifest.get("p20_ci_artifact_export_manifest_sha256") != p20_summary.get("ci_artifact_export_manifest_sha256"):
        reasons.append("P21_P20_MANIFEST_HASH_MISMATCH")
    if p20_report.get("ci_artifact_export_manifest_sha256") and p20_manifest.get("p20_ci_artifact_export_manifest_sha256") != p20_report.get("ci_artifact_export_manifest_sha256"):
        reasons.append("P21_P20_REPORT_MANIFEST_HASH_MISMATCH")
    entries = p20_manifest.get("artifact_entries")
    if not isinstance(entries, list) or len(entries) != 3:
        reasons.append("P21_P20_MANIFEST_ARTIFACT_ENTRIES_INVALID")
    else:
        targets = {entry.get("target_external_evidence_filename") for entry in entries if isinstance(entry, Mapping)}
        if targets != set(_REQUIRED_FILLED_EVIDENCE.values()):
            reasons.append("P21_P20_MANIFEST_TARGET_FILES_INVALID")
        for entry in entries:
            if isinstance(entry, Mapping) and entry.get("must_be_filled_by_external_ci_or_operator") is not True:
                reasons.append("P21_P20_MANIFEST_EXTERNAL_FILL_NOT_REQUIRED")
            if isinstance(entry, Mapping) and entry.get("must_not_be_filled_by_this_module") is not True:
                reasons.append("P21_P20_MANIFEST_MODULE_FILL_ALLOWED")
    return reasons


def build_release_candidate_bundle_manifest(
    *,
    p18_hash: str | None,
    p19_hash: str | None,
    p20_hash: str | None,
    p20_manifest_hash: str | None,
    p21_report_hash: str | None = None,
    evidence_hashes: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "p21_ci_filled_evidence_release_candidate_bundle_version": P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_VERSION,
        "bundle_type": "release_candidate_bundle_review_only",
        "created_at_utc": utc_now_canonical(),
        "source_p18_full_regression_ci_release_gate_sha256": p18_hash,
        "source_p19_docker_launcher_evidence_intake_sha256": p19_hash,
        "source_p20_external_evidence_template_export_pack_sha256": p20_hash,
        "source_p20_ci_artifact_export_manifest_sha256": p20_manifest_hash,
        "source_p21_report_sha256": p21_report_hash,
        "filled_external_evidence_sha256s": dict(evidence_hashes or {}),
        "included_artifacts": [
            "p18_full_regression_ci_release_gate_summary.json",
            "p19_docker_launcher_evidence_intake_summary.json",
            "p19_docker_launcher_evidence_intake_report.json",
            "p20_external_evidence_template_export_pack_summary.json",
            "p20_external_evidence_template_export_pack_report.json",
            "p20_ci_artifact_export_manifest.json",
            "p19_docker_build_evidence_external.json",
            "p19_docker_run_self_test_evidence_external.json",
            "p19_launcher_import_evidence_external.json",
            "p21_ci_filled_evidence_release_candidate_bundle_report.json",
        ],
        "operator_handoff_instructions": {
            "review_only_bundle": True,
            "not_runtime_authority": True,
            "separate_runtime_enablement_required": True,
            "must_not_edit_execution_flags": True,
            "must_not_insert_secret_values": True,
            "next_gate": "P22 operator release candidate acceptance review",
        },
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
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    manifest["p21_release_candidate_bundle_manifest_sha256"] = sha256_json(manifest)
    return manifest


def build_ci_filled_evidence_release_candidate_bundle_report(
    *,
    root: Path,
    p19_summary: Mapping[str, Any] | None = None,
    p19_report: Mapping[str, Any] | None = None,
    p20_summary: Mapping[str, Any] | None = None,
    p20_report: Mapping[str, Any] | None = None,
    p20_manifest: Mapping[str, Any] | None = None,
    docker_build_evidence: Mapping[str, Any] | None = None,
    docker_run_evidence: Mapping[str, Any] | None = None,
    launcher_import_evidence: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    del root
    p19_summary = dict(p19_summary or {})
    p19_report = dict(p19_report or {})
    p20_summary = dict(p20_summary or {})
    p20_report = dict(p20_report or {})
    p20_manifest = dict(p20_manifest or {})
    docker_build_evidence = dict(docker_build_evidence or {})
    docker_run_evidence = dict(docker_run_evidence or {})
    launcher_import_evidence = dict(launcher_import_evidence or {})

    p18_hash = p19_report.get("source_p18_full_regression_ci_release_gate_sha256") or p20_report.get("source_p18_full_regression_ci_release_gate_sha256") or p20_manifest.get("source_p18_full_regression_ci_release_gate_sha256")
    p19_hash = p19_summary.get("p19_docker_launcher_evidence_intake_sha256") or p19_report.get("p19_docker_launcher_evidence_intake_sha256")
    p20_hash = p20_summary.get("p20_external_evidence_template_export_pack_sha256") or p20_report.get("p20_external_evidence_template_export_pack_sha256")
    p20_manifest_hash = p20_summary.get("ci_artifact_export_manifest_sha256") or p20_report.get("ci_artifact_export_manifest_sha256") or p20_manifest.get("p20_ci_artifact_export_manifest_sha256")

    evidence_hashes = _evidence_file_hashes(
        docker_build_evidence=docker_build_evidence,
        docker_run_evidence=docker_run_evidence,
        launcher_import_evidence=launcher_import_evidence,
    )
    bundle_manifest = build_release_candidate_bundle_manifest(
        p18_hash=str(p18_hash) if p18_hash else None,
        p19_hash=str(p19_hash) if p19_hash else None,
        p20_hash=str(p20_hash) if p20_hash else None,
        p20_manifest_hash=str(p20_manifest_hash) if p20_manifest_hash else None,
        evidence_hashes=evidence_hashes,
    )

    named_payloads: list[tuple[str, Mapping[str, Any]]] = [
        ("p19_summary", p19_summary),
        ("p19_report", p19_report),
        ("p20_summary", p20_summary),
        ("p20_report", p20_report),
        ("p20_manifest", p20_manifest),
        ("docker_build_evidence", docker_build_evidence),
        ("docker_run_evidence", docker_run_evidence),
        ("launcher_import_evidence", launcher_import_evidence),
        ("release_candidate_bundle_manifest", bundle_manifest),
    ]
    named_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(named_payloads)
    secret_hits = _scan_secret_value_patterns(named_payloads)

    disabled_state = default_execution_flag_state()
    disabled_state.update({field: False for field in _EXECUTION_FIELDS_FOR_P21})
    truthy_disabled = truthy_execution_flags(disabled_state)

    missing_external = _filled_evidence_missing(
        docker_build_evidence=docker_build_evidence,
        docker_run_evidence=docker_run_evidence,
        launcher_import_evidence=launcher_import_evidence,
    )

    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if not p19_summary:
        waiting_reasons.append("P21_SOURCE_P19_SUMMARY_MISSING")
    if p19_summary and p19_summary.get("status") == "P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_BLOCKED_FAIL_CLOSED":
        block_reasons.append("P21_SOURCE_P19_BLOCKED")
    if p19_summary and p19_summary.get("p19_docker_launcher_evidence_intake_valid_review_only") is not True:
        waiting_reasons.append("P21_SOURCE_P19_FILLED_EVIDENCE_NOT_VALID")
    if not p19_report:
        waiting_reasons.append("P21_SOURCE_P19_REPORT_MISSING")
    if p19_summary and p19_report and p19_summary.get("p19_docker_launcher_evidence_intake_sha256") != p19_report.get("p19_docker_launcher_evidence_intake_sha256"):
        block_reasons.append("P21_SOURCE_P19_SUMMARY_REPORT_HASH_MISMATCH")
    if not _is_sha256(p19_hash):
        waiting_reasons.append("P21_SOURCE_P19_HASH_MISSING_OR_INVALID")

    if not p20_summary:
        waiting_reasons.append("P21_SOURCE_P20_SUMMARY_MISSING")
    if p20_summary and p20_summary.get("status") == "P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_BLOCKED_FAIL_CLOSED":
        block_reasons.append("P21_SOURCE_P20_BLOCKED")
    if p20_summary and p20_summary.get("p20_templates_ready_for_external_ci_fill") is not True:
        block_reasons.append("P21_SOURCE_P20_TEMPLATES_NOT_READY")
    if not p20_report:
        waiting_reasons.append("P21_SOURCE_P20_REPORT_MISSING")
    if p20_summary and p20_report and p20_summary.get("p20_external_evidence_template_export_pack_sha256") != p20_report.get("p20_external_evidence_template_export_pack_sha256"):
        block_reasons.append("P21_SOURCE_P20_SUMMARY_REPORT_HASH_MISMATCH")
    if not _is_sha256(p20_hash):
        waiting_reasons.append("P21_SOURCE_P20_HASH_MISSING_OR_INVALID")

    if not _is_sha256(p18_hash):
        waiting_reasons.append("P21_SOURCE_P18_HASH_MISSING_OR_INVALID")
    if p19_report and p20_report and p19_report.get("source_p18_full_regression_ci_release_gate_sha256") != p20_report.get("source_p18_full_regression_ci_release_gate_sha256"):
        block_reasons.append("P21_P18_HASH_MISMATCH_BETWEEN_P19_AND_P20")
    if p20_summary and p20_report and p20_summary.get("ci_artifact_export_manifest_sha256") != p20_report.get("ci_artifact_export_manifest_sha256"):
        block_reasons.append("P21_P20_SUMMARY_REPORT_MANIFEST_HASH_MISMATCH")

    if missing_external:
        waiting_reasons.append("P21_FILLED_EXTERNAL_EVIDENCE_MISSING")
    if not missing_external and p19_report:
        block_reasons.extend(_validate_filled_evidence_against_p19(
            p19_report=p19_report,
            docker_build_evidence=docker_build_evidence,
            docker_run_evidence=docker_run_evidence,
            launcher_import_evidence=launcher_import_evidence,
        ))
    if _is_sha256(p18_hash):
        block_reasons.extend(_validate_manifest_artifacts(
            p20_summary=p20_summary,
            p20_report=p20_report,
            p20_manifest=p20_manifest,
            p18_hash=str(p18_hash),
        ))
    elif p20_manifest:
        block_reasons.append("P21_CANNOT_VALIDATE_P20_MANIFEST_WITHOUT_P18_HASH")

    if unsafe_hits:
        block_reasons.append("P21_UNSAFE_TRUTHY_FLAG_FOUND")
    if secret_hits:
        block_reasons.append("P21_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P21_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    valid = not blocked and not waiting_reasons
    status = STATUS_BLOCKED_FAIL_CLOSED if blocked else (STATUS_VALID_REVIEW_ONLY if valid else STATUS_WAITING_REVIEW_ONLY)

    report: dict[str, Any] = {
        "p21_ci_filled_evidence_release_candidate_bundle_version": P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": valid,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "source_p18_full_regression_ci_release_gate_sha256": p18_hash,
        "source_p19_docker_launcher_evidence_intake_sha256": p19_hash,
        "source_p20_external_evidence_template_export_pack_sha256": p20_hash,
        "source_p20_ci_artifact_export_manifest_sha256": p20_manifest_hash,
        "filled_external_evidence_files": list(_REQUIRED_FILLED_EVIDENCE.values()),
        "missing_filled_external_evidence_files": missing_external,
        "filled_external_evidence_sha256s": evidence_hashes,
        "release_candidate_bundle_manifest": bundle_manifest,
        "release_candidate_bundle_manifest_sha256": bundle_manifest["p21_release_candidate_bundle_manifest_sha256"],
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "p21_ci_filled_evidence_valid_review_only": valid,
        "p21_release_candidate_bundle_ready_review_only": valid,
        "release_candidate_bundle_exported_by_this_module": valid,
        "release_candidate_bundle_is_runtime_authority": False,
        "separate_operator_acceptance_required": True,
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
    report["p21_ci_filled_evidence_release_candidate_bundle_id"] = stable_id("p21_ci_filled_evidence_release_candidate_bundle", report, 24)
    report["p21_ci_filled_evidence_release_candidate_bundle_sha256"] = sha256_json(report)
    report["release_candidate_bundle_manifest"] = build_release_candidate_bundle_manifest(
        p18_hash=str(p18_hash) if p18_hash else None,
        p19_hash=str(p19_hash) if p19_hash else None,
        p20_hash=str(p20_hash) if p20_hash else None,
        p20_manifest_hash=str(p20_manifest_hash) if p20_manifest_hash else None,
        p21_report_hash=report["p21_ci_filled_evidence_release_candidate_bundle_sha256"],
        evidence_hashes=evidence_hashes,
    )
    report["release_candidate_bundle_manifest_sha256"] = report["release_candidate_bundle_manifest"]["p21_release_candidate_bundle_manifest_sha256"]
    return report


def _write_release_candidate_bundle_zip(target: Path, files: Mapping[str, Mapping[str, Any]]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, payload in files.items():
            archive.writestr(filename, json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")


def build_p21_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    p18_hash = "a" * 64
    p19_hash = "b" * 64
    p20_hash = "c" * 64
    docker_build = build_docker_build_external_evidence_template(p18_hash)
    docker_run = build_docker_run_external_evidence_template(p18_hash)
    launcher = build_launcher_import_external_evidence_template(p18_hash)
    p20_manifest = {
        "artifact_pack_type": "docker_launcher_external_evidence_template_export_pack",
        "source_p18_full_regression_ci_release_gate_sha256": p18_hash,
        "p20_ci_artifact_export_manifest_sha256": "d" * 64,
        "artifact_entries": [
            {"artifact_id": "docker_build", "target_external_evidence_filename": _DOCKER_BUILD_EXTERNAL_EVIDENCE_FILENAME, "must_be_filled_by_external_ci_or_operator": True, "must_not_be_filled_by_this_module": True},
            {"artifact_id": "docker_run_self_test", "target_external_evidence_filename": _DOCKER_RUN_EXTERNAL_EVIDENCE_FILENAME, "must_be_filled_by_external_ci_or_operator": True, "must_not_be_filled_by_this_module": True},
            {"artifact_id": "launcher_import", "target_external_evidence_filename": _LAUNCHER_EXTERNAL_EVIDENCE_FILENAME, "must_be_filled_by_external_ci_or_operator": True, "must_not_be_filled_by_this_module": True},
        ],
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    base_p19_report = {
        "status": "P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_VALID_REVIEW_ONLY",
        "p19_docker_launcher_evidence_intake_sha256": p19_hash,
        "p19_docker_launcher_evidence_intake_valid_review_only": True,
        "source_p18_full_regression_ci_release_gate_sha256": p18_hash,
        "docker_build_evidence_sha256": sha256_json(docker_build),
        "docker_run_self_test_evidence_sha256": sha256_json(docker_run),
        "launcher_import_evidence_sha256": sha256_json(launcher),
        "docker_build_evidence_valid_review_only": True,
        "docker_run_self_test_evidence_valid_review_only": True,
        "launcher_import_evidence_valid_review_only": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    base_p19_summary = {
        "status": "P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_VALID_REVIEW_ONLY",
        "p19_docker_launcher_evidence_intake_sha256": p19_hash,
        "p19_docker_launcher_evidence_intake_valid_review_only": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    base_p20_report = {
        "status": "P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_GENERATED_REVIEW_ONLY",
        "p20_external_evidence_template_export_pack_sha256": p20_hash,
        "p20_templates_ready_for_external_ci_fill": True,
        "source_p18_full_regression_ci_release_gate_sha256": p18_hash,
        "ci_artifact_export_manifest_sha256": "d" * 64,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    base_p20_summary = {
        "status": "P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_GENERATED_REVIEW_ONLY",
        "p20_external_evidence_template_export_pack_sha256": p20_hash,
        "p20_templates_ready_for_external_ci_fill": True,
        "ci_artifact_export_manifest_sha256": "d" * 64,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    base_kwargs = {
        "p19_summary": base_p19_summary,
        "p19_report": base_p19_report,
        "p20_summary": base_p20_summary,
        "p20_report": base_p20_report,
        "p20_manifest": p20_manifest,
        "docker_build_evidence": docker_build,
        "docker_run_evidence": docker_run,
        "launcher_import_evidence": launcher,
    }
    cases = {
        "missing_p20_summary": {**base_kwargs, "p20_summary": {}},
        "p20_blocked": {**base_kwargs, "p20_summary": {**base_p20_summary, "status": "P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_BLOCKED_FAIL_CLOSED"}},
        "missing_p19_summary": {**base_kwargs, "p19_summary": {}},
        "p19_not_valid": {**base_kwargs, "p19_summary": {**base_p19_summary, "p19_docker_launcher_evidence_intake_valid_review_only": False}},
        "missing_filled_evidence": {**base_kwargs, "docker_build_evidence": {}},
        "evidence_hash_mismatch": {**base_kwargs, "docker_run_evidence": {**docker_run, "run_log_sha256": "9" * 64}},
        "p18_hash_mismatch": {**base_kwargs, "p20_report": {**base_p20_report, "source_p18_full_regression_ci_release_gate_sha256": "e" * 64}},
        "secret_pattern_found": {**base_kwargs, "docker_build_evidence": {**docker_build, "stdout_excerpt": "BINANCE_API_SECRET=leaked"}},
        "endpoint_called": {**base_kwargs, "docker_run_evidence": {**docker_run, "order_endpoint_called": True}},
        "unsafe_runtime_flag": {**base_kwargs, "p19_summary": {**base_p19_summary, "live_scaled_execution_enabled": True}},
        "manifest_allows_module_fill": {**base_kwargs, "p20_manifest": {**p20_manifest, "artifact_entries": [{**entry, "must_not_be_filled_by_this_module": False} for entry in p20_manifest["artifact_entries"]]}},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_ci_filled_evidence_release_candidate_bundle_report(root=root, **kwargs)
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
        "p21_ci_filled_evidence_release_candidate_bundle_version": P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_VERSION,
        "status": "P21_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_ci_filled_evidence_release_candidate_bundle(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p21_ci_filled_evidence_release_candidate_bundle")
    p19_summary = _read_latest_json(cfg, _P19_SUMMARY_FILENAME)
    p19_report = _read_latest_json(cfg, _P19_REPORT_FILENAME)
    p20_summary = _read_latest_json(cfg, _P20_SUMMARY_FILENAME)
    p20_report = _read_latest_json(cfg, _P20_REPORT_FILENAME)
    p20_manifest = _read_latest_json(cfg, _P20_MANIFEST_FILENAME)
    docker_build_evidence = _read_latest_json(cfg, _DOCKER_BUILD_EXTERNAL_EVIDENCE_FILENAME)
    docker_run_evidence = _read_latest_json(cfg, _DOCKER_RUN_EXTERNAL_EVIDENCE_FILENAME)
    launcher_import_evidence = _read_latest_json(cfg, _LAUNCHER_EXTERNAL_EVIDENCE_FILENAME)

    report = build_ci_filled_evidence_release_candidate_bundle_report(
        root=cfg.root,
        p19_summary=p19_summary,
        p19_report=p19_report,
        p20_summary=p20_summary,
        p20_report=p20_report,
        p20_manifest=p20_manifest,
        docker_build_evidence=docker_build_evidence,
        docker_run_evidence=docker_run_evidence,
        launcher_import_evidence=launcher_import_evidence,
    )
    negative_results = build_p21_negative_fixture_results(root=cfg.root)

    atomic_write_json(latest / "p21_ci_filled_evidence_release_candidate_bundle_report.json", report)
    atomic_write_json(storage / "p21_ci_filled_evidence_release_candidate_bundle_report.json", report)
    atomic_write_json(latest / "p21_ci_filled_evidence_release_candidate_bundle_negative_fixture_results.json", negative_results)

    bundle_zip_path = latest / "p21_release_candidate_bundle_review_only.zip"
    bundle_files: dict[str, Mapping[str, Any]] = {
        "p21_release_candidate_bundle_manifest.json": report["release_candidate_bundle_manifest"],
        "p21_ci_filled_evidence_release_candidate_bundle_report.json": report,
    }
    for filename, payload in (
        (_P19_SUMMARY_FILENAME, p19_summary),
        (_P19_REPORT_FILENAME, p19_report),
        (_P20_SUMMARY_FILENAME, p20_summary),
        (_P20_REPORT_FILENAME, p20_report),
        (_P20_MANIFEST_FILENAME, p20_manifest),
        (_DOCKER_BUILD_EXTERNAL_EVIDENCE_FILENAME, docker_build_evidence),
        (_DOCKER_RUN_EXTERNAL_EVIDENCE_FILENAME, docker_run_evidence),
        (_LAUNCHER_EXTERNAL_EVIDENCE_FILENAME, launcher_import_evidence),
    ):
        if payload:
            bundle_files[filename] = payload
    if report["valid_review_only"]:
        _write_release_candidate_bundle_zip(bundle_zip_path, bundle_files)
        bundle_zip_content_sha256 = sha256_json({name: sha256_json(payload) for name, payload in bundle_files.items()})
        bundle_zip_path_value: str | None = "storage/latest/p21_release_candidate_bundle_review_only.zip"
    else:
        bundle_zip_content_sha256 = None
        bundle_zip_path_value = None

    summary = {
        "status": report["status"],
        "p21_ci_filled_evidence_release_candidate_bundle_sha256": report["p21_ci_filled_evidence_release_candidate_bundle_sha256"],
        "p21_ci_filled_evidence_valid_review_only": report["p21_ci_filled_evidence_valid_review_only"],
        "p21_release_candidate_bundle_ready_review_only": report["p21_release_candidate_bundle_ready_review_only"],
        "release_candidate_bundle_path": bundle_zip_path_value,
        "release_candidate_bundle_content_sha256": bundle_zip_content_sha256,
        "missing_filled_external_evidence_files": report["missing_filled_external_evidence_files"],
        "waiting_reasons": report["waiting_reasons"],
        "block_reasons": report["block_reasons"],
        "separate_operator_acceptance_required": True,
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
    summary["p21_ci_filled_evidence_release_candidate_bundle_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p21_ci_filled_evidence_release_candidate_bundle_summary.json", summary)

    registry_record = append_registry_record(
        registry_path(cfg, P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_REGISTRY_NAME),
        report,
        registry_name=P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_REGISTRY_NAME,
        id_field="p21_ci_filled_evidence_release_candidate_bundle_registry_id",
        hash_field="p21_ci_filled_evidence_release_candidate_bundle_registry_sha256",
        id_prefix="p21_ci_filled_evidence_release_candidate_bundle",
    )
    atomic_write_json(latest / "p21_ci_filled_evidence_release_candidate_bundle_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_ci_filled_evidence_release_candidate_bundle()
    print(result["status"])
    print(result["p21_ci_filled_evidence_release_candidate_bundle_sha256"])
