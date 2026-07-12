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

P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_VERSION = "p20_external_evidence_template_export_pack_v1"
P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_REGISTRY_NAME = "p20_external_evidence_template_export_pack_registry"

STATUS_GENERATED_REVIEW_ONLY = "P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_GENERATED_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_BLOCKED_FAIL_CLOSED"

_P18_SUMMARY_FILENAME = "p18_full_regression_ci_release_gate_summary.json"
_P19_SUMMARY_FILENAME = "p19_docker_launcher_evidence_intake_summary.json"
_P19_REPORT_FILENAME = "p19_docker_launcher_evidence_intake_report.json"

_TEMPLATE_FILENAMES = {
    "docker_build": "p19_docker_build_evidence_external_TEMPLATE.json",
    "docker_run_self_test": "p19_docker_run_self_test_evidence_external_TEMPLATE.json",
    "launcher_import": "p19_launcher_import_evidence_external_TEMPLATE.json",
}
_TARGET_EXTERNAL_FILENAMES = {
    "docker_build": "p19_docker_build_evidence_external.json",
    "docker_run_self_test": "p19_docker_run_self_test_evidence_external.json",
    "launcher_import": "p19_launcher_import_evidence_external.json",
}

_EXECUTION_FIELDS_FOR_P20 = {
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


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value.lower())


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _scan_truthy_execution_fields(payloads: Sequence[tuple[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                next_path = f"{path}.{key}"
                if key in _EXECUTION_FIELDS_FOR_P20 and _bool(value):
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


def _template_is_safe(template: Mapping[str, Any], *, expected_type: str, expected_p18_hash: str) -> list[str]:
    reasons: list[str] = []
    if template.get("evidence_type") != expected_type:
        reasons.append("P20_TEMPLATE_EVIDENCE_TYPE_INVALID")
    if template.get("source_p18_full_regression_ci_release_gate_sha256") != expected_p18_hash:
        reasons.append("P20_TEMPLATE_P18_HASH_MISMATCH")
    if template.get("performed_by_this_module") is not False:
        reasons.append("P20_TEMPLATE_MARKS_PERFORMED_BY_THIS_MODULE")
    if template.get("order_endpoint_called") is not False:
        reasons.append("P20_TEMPLATE_ORDER_ENDPOINT_CALL_ENABLED")
    if template.get("http_request_sent") is not False:
        reasons.append("P20_TEMPLATE_HTTP_REQUEST_SENT_ENABLED")
    if template.get("secret_value_accessed") is not False:
        reasons.append("P20_TEMPLATE_SECRET_VALUE_ACCESSED")
    if template.get("secret_value_logged") is not False:
        reasons.append("P20_TEMPLATE_SECRET_VALUE_LOGGED")
    return reasons


def build_p20_external_evidence_templates(p18_hash: str) -> dict[str, dict[str, Any]]:
    templates = {
        "docker_build": build_docker_build_external_evidence_template(p18_hash),
        "docker_run_self_test": build_docker_run_external_evidence_template(p18_hash),
        "launcher_import": build_launcher_import_external_evidence_template(p18_hash),
    }
    # Normalize safety fields across all external templates so the template pack
    # itself can never be interpreted as runtime execution evidence.
    for template in templates.values():
        template.setdefault("http_request_sent", False)
        template.setdefault("order_endpoint_called", False)
        template.setdefault("secret_value_accessed", False)
        template.setdefault("secret_value_logged", False)
        template.setdefault("performed_by_this_module", False)
        template.setdefault("live_scaled_execution_enabled", False)
        template.setdefault("live_order_submission_allowed", False)
        template.setdefault("runtime_scheduler_enabled", False)
    return templates


def build_ci_artifact_export_manifest(*, p18_hash: str, p19_hash: str | None, templates: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    artifact_entries: list[dict[str, Any]] = []
    for key in ("docker_build", "docker_run_self_test", "launcher_import"):
        template = dict(templates[key])
        artifact_entries.append(
            {
                "artifact_id": key,
                "template_filename": _TEMPLATE_FILENAMES[key],
                "target_external_evidence_filename": _TARGET_EXTERNAL_FILENAMES[key],
                "template_sha256": sha256_json(template),
                "copy_target": f"storage/latest/{_TARGET_EXTERNAL_FILENAMES[key]}",
                "must_be_filled_by_external_ci_or_operator": True,
                "must_not_be_filled_by_this_module": True,
            }
        )
    manifest: dict[str, Any] = {
        "p20_external_evidence_template_export_pack_version": P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_VERSION,
        "artifact_pack_type": "docker_launcher_external_evidence_template_export_pack",
        "source_p18_full_regression_ci_release_gate_sha256": p18_hash,
        "source_p19_docker_launcher_evidence_intake_sha256": p19_hash,
        "created_at_utc": utc_now_canonical(),
        "artifact_entries": artifact_entries,
        "external_ci_commands": [
            {
                "command_id": "docker_build",
                "command": "docker compose build crypto_ai_system_self_test",
                "template_filename": _TEMPLATE_FILENAMES["docker_build"],
                "target_external_evidence_filename": _TARGET_EXTERNAL_FILENAMES["docker_build"],
            },
            {
                "command_id": "docker_run_self_test",
                "command": "docker compose run --rm crypto_ai_system_self_test",
                "template_filename": _TEMPLATE_FILENAMES["docker_run_self_test"],
                "target_external_evidence_filename": _TARGET_EXTERNAL_FILENAMES["docker_run_self_test"],
            },
            {
                "command_id": "launcher_import_validation",
                "command": "PYTHONPATH=src:. python scripts/validate_agent_os_import_package.py",
                "template_filename": _TEMPLATE_FILENAMES["launcher_import"],
                "target_external_evidence_filename": _TARGET_EXTERNAL_FILENAMES["launcher_import"],
            },
        ],
        "operator_instructions": {
            "copy_filled_files_to": "storage/latest/",
            "run_after_fill": "PYTHONPATH=src:. python scripts/run_docker_launcher_evidence_gate.py",
            "must_not_include_secret_values": True,
            "must_not_claim_runtime_enablement": True,
            "must_not_claim_order_endpoint_calls_from_template_generation": True,
            "external_evidence_only": True,
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
    manifest["p20_ci_artifact_export_manifest_sha256"] = sha256_json(manifest)
    return manifest


def build_external_evidence_template_export_pack_report(
    *,
    root: Path,
    p18_summary: Mapping[str, Any] | None = None,
    p19_summary: Mapping[str, Any] | None = None,
    p19_report: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    del root
    p18_summary = dict(p18_summary or {})
    p19_summary = dict(p19_summary or {})
    p19_report = dict(p19_report or {})
    p18_hash = p18_summary.get("p18_full_regression_ci_release_gate_sha256")
    p19_hash = p19_summary.get("p19_docker_launcher_evidence_intake_sha256") or p19_report.get("p19_docker_launcher_evidence_intake_sha256")
    templates = build_p20_external_evidence_templates(str(p18_hash or "0" * 64))
    manifest = build_ci_artifact_export_manifest(p18_hash=str(p18_hash or "0" * 64), p19_hash=p19_hash, templates=templates)

    named_payloads: list[tuple[str, Mapping[str, Any]]] = [
        ("p18_summary", p18_summary),
        ("p19_summary", p19_summary),
        ("p19_report", p19_report),
        ("docker_build_template", templates["docker_build"]),
        ("docker_run_template", templates["docker_run_self_test"]),
        ("launcher_import_template", templates["launcher_import"]),
        ("ci_artifact_export_manifest", manifest),
    ]
    named_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(named_payloads)
    secret_hits = _scan_secret_value_patterns(named_payloads)

    disabled_state = default_execution_flag_state()
    disabled_state.update({field: False for field in _EXECUTION_FIELDS_FOR_P20})
    truthy_disabled = truthy_execution_flags(disabled_state)

    block_reasons: list[str] = []
    if not p18_summary:
        block_reasons.append("P20_SOURCE_P18_SUMMARY_MISSING")
    if p18_summary and p18_summary.get("status") == "P18_FULL_REGRESSION_CI_RELEASE_GATE_BLOCKED_FAIL_CLOSED":
        block_reasons.append("P20_SOURCE_P18_RELEASE_GATE_BLOCKED")
    if p18_summary and p18_summary.get("p18_ci_release_gate_hardened_review_only") is not True:
        block_reasons.append("P20_SOURCE_P18_NOT_HARDENED")
    if not _is_sha256(p18_hash):
        block_reasons.append("P20_SOURCE_P18_HASH_MISSING_OR_INVALID")
    if not p19_summary:
        block_reasons.append("P20_SOURCE_P19_SUMMARY_MISSING")
    if p19_summary and p19_summary.get("status") == "P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_BLOCKED_FAIL_CLOSED":
        block_reasons.append("P20_SOURCE_P19_INTAKE_BLOCKED")
    if p19_summary and p19_summary.get("p19_docker_launcher_evidence_intake_sha256") != p19_hash:
        block_reasons.append("P20_SOURCE_P19_HASH_MISMATCH")

    if _is_sha256(p18_hash):
        expected_hash = str(p18_hash)
        block_reasons.extend(_template_is_safe(templates["docker_build"], expected_type="docker_compose_build_external_evidence", expected_p18_hash=expected_hash))
        block_reasons.extend(_template_is_safe(templates["docker_run_self_test"], expected_type="docker_compose_run_self_test_external_evidence", expected_p18_hash=expected_hash))
        block_reasons.extend(_template_is_safe(templates["launcher_import"], expected_type="launcher_import_simulation_external_evidence", expected_p18_hash=expected_hash))
    if unsafe_hits:
        block_reasons.append("P20_UNSAFE_TRUTHY_FLAG_FOUND")
    if secret_hits:
        block_reasons.append("P20_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P20_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    status = STATUS_BLOCKED_FAIL_CLOSED if blocked else STATUS_GENERATED_REVIEW_ONLY
    report: dict[str, Any] = {
        "p20_external_evidence_template_export_pack_version": P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_VERSION,
        "status": status,
        "blocked": blocked,
        "valid_review_only": not blocked,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "source_p18_full_regression_ci_release_gate_sha256": p18_hash,
        "source_p19_docker_launcher_evidence_intake_sha256": p19_hash,
        "source_p19_status": p19_summary.get("status") or p19_report.get("status"),
        "template_count": len(templates),
        "target_external_evidence_files": list(_TARGET_EXTERNAL_FILENAMES.values()),
        "template_files": list(_TEMPLATE_FILENAMES.values()),
        "template_sha256s": {key: sha256_json(value) for key, value in templates.items()},
        "ci_artifact_export_manifest": manifest,
        "ci_artifact_export_manifest_sha256": manifest["p20_ci_artifact_export_manifest_sha256"],
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "external_execution_performed_by_this_module": False,
        "docker_daemon_execution_performed_by_this_module": False,
        "launcher_import_mutated_by_this_module": False,
        "p20_external_evidence_template_export_pack_generated_review_only": not blocked,
        "p20_ci_artifact_export_manifest_valid_review_only": not blocked,
        "p20_templates_ready_for_external_ci_fill": not blocked,
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
    report["p20_external_evidence_template_export_pack_id"] = stable_id("p20_external_evidence_template_export_pack", report, 24)
    report["p20_external_evidence_template_export_pack_sha256"] = sha256_json(report)
    return report


def _write_export_pack_zip(target: Path, files: Mapping[str, Mapping[str, Any]]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, payload in files.items():
            archive.writestr(filename, json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")


def build_p20_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    p18_hash = "a" * 64
    base_p18 = {
        "status": "P18_FULL_REGRESSION_CI_RELEASE_GATE_HARDENED_REVIEW_ONLY",
        "p18_full_regression_ci_release_gate_sha256": p18_hash,
        "p18_full_regression_ci_release_gate_summary_sha256": "b" * 64,
        "p18_ci_release_gate_hardened_review_only": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    base_p19 = {
        "status": "P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_WAITING_REVIEW_ONLY",
        "p19_docker_launcher_evidence_intake_sha256": "c" * 64,
        "p19_docker_launcher_evidence_intake_valid_review_only": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    cases = {
        "missing_p18_summary": {"p18_summary": {}, "p19_summary": base_p19},
        "p18_blocked": {"p18_summary": {**base_p18, "status": "P18_FULL_REGRESSION_CI_RELEASE_GATE_BLOCKED_FAIL_CLOSED"}, "p19_summary": base_p19},
        "missing_p19_summary": {"p18_summary": base_p18, "p19_summary": {}},
        "p19_blocked": {"p18_summary": base_p18, "p19_summary": {**base_p19, "status": "P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_BLOCKED_FAIL_CLOSED"}},
        "invalid_p18_hash": {"p18_summary": {**base_p18, "p18_full_regression_ci_release_gate_sha256": "not-a-hash"}, "p19_summary": base_p19},
        "unsafe_runtime_flag": {"p18_summary": {**base_p18, "live_scaled_execution_enabled": True}, "p19_summary": base_p19},
        "secret_pattern_found": {"p18_summary": base_p18, "p19_summary": base_p19, "extra_payloads_for_scan": [("unsafe_extra", {"note": "BINANCE_API_SECRET=leaked"})]},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_external_evidence_template_export_pack_report(root=root, **kwargs)
        results[name] = {
            "blocked": report["blocked"],
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "limited_live_scaled_auto_trading_allowed": report["limited_live_scaled_auto_trading_allowed"],
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
            "live_order_submission_allowed": report["live_order_submission_allowed"],
            "runtime_scheduler_enabled": report["runtime_scheduler_enabled"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    return {
        "p20_external_evidence_template_export_pack_version": P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_VERSION,
        "status": "P20_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_external_evidence_template_export_pack(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p20_external_evidence_template_export_pack")
    p18_summary = _read_latest_json(cfg, _P18_SUMMARY_FILENAME)
    p19_summary = _read_latest_json(cfg, _P19_SUMMARY_FILENAME)
    p19_report = _read_latest_json(cfg, _P19_REPORT_FILENAME)
    report = build_external_evidence_template_export_pack_report(
        root=cfg.root,
        p18_summary=p18_summary,
        p19_summary=p19_summary,
        p19_report=p19_report,
    )
    p18_hash = str(report.get("source_p18_full_regression_ci_release_gate_sha256") or "0" * 64)
    templates = build_p20_external_evidence_templates(p18_hash)
    manifest = report["ci_artifact_export_manifest"]
    negative_results = build_p20_negative_fixture_results(root=cfg.root)

    for key, payload in templates.items():
        atomic_write_json(storage / _TEMPLATE_FILENAMES[key], payload)
        atomic_write_json(latest / _TEMPLATE_FILENAMES[key], payload)
    atomic_write_json(storage / "p20_ci_artifact_export_manifest.json", manifest)
    atomic_write_json(latest / "p20_ci_artifact_export_manifest.json", manifest)
    atomic_write_json(latest / "p20_external_evidence_template_export_pack_report.json", report)
    atomic_write_json(storage / "p20_external_evidence_template_export_pack_report.json", report)
    atomic_write_json(latest / "p20_external_evidence_template_export_pack_negative_fixture_results.json", negative_results)

    zip_files = {**{_TEMPLATE_FILENAMES[key]: value for key, value in templates.items()}, "p20_ci_artifact_export_manifest.json": manifest, "p20_external_evidence_template_export_pack_report.json": report}
    export_zip = latest / "p20_ci_artifact_export_pack_review_only.zip"
    _write_export_pack_zip(export_zip, zip_files)
    zip_sha = sha256_json({name: sha256_json(payload) for name, payload in zip_files.items()})

    summary = {
        "status": report["status"],
        "p20_external_evidence_template_export_pack_sha256": report["p20_external_evidence_template_export_pack_sha256"],
        "p20_external_evidence_template_export_pack_generated_review_only": report["p20_external_evidence_template_export_pack_generated_review_only"],
        "p20_templates_ready_for_external_ci_fill": report["p20_templates_ready_for_external_ci_fill"],
        "template_files": report["template_files"],
        "target_external_evidence_files": report["target_external_evidence_files"],
        "ci_artifact_export_manifest_sha256": report["ci_artifact_export_manifest_sha256"],
        "export_pack_zip_path": "storage/latest/p20_ci_artifact_export_pack_review_only.zip",
        "export_pack_zip_content_sha256": zip_sha,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "actual_live_order_submitted": False,
        "live_order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    summary["p20_external_evidence_template_export_pack_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p20_external_evidence_template_export_pack_summary.json", summary)

    registry_record = append_registry_record(
        registry_path(cfg, P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_REGISTRY_NAME),
        report,
        registry_name=P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_REGISTRY_NAME,
        id_field="p20_external_evidence_template_export_pack_registry_id",
        hash_field="p20_external_evidence_template_export_pack_registry_sha256",
        id_prefix="p20_external_evidence_template_export_pack",
    )
    atomic_write_json(latest / "p20_external_evidence_template_export_pack_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_external_evidence_template_export_pack()
    print(result["status"])
    print(result["p20_external_evidence_template_export_pack_sha256"])
