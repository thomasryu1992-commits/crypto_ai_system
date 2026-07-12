from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_VERSION = "p19_docker_launcher_evidence_intake_v1"
P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_REGISTRY_NAME = "p19_docker_launcher_evidence_intake_registry"

STATUS_WAITING_REVIEW_ONLY = "P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_WAITING_REVIEW_ONLY"
STATUS_VALID_REVIEW_ONLY = "P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_VALID_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_BLOCKED_FAIL_CLOSED"

_P18_SUMMARY_FILENAME = "p18_full_regression_ci_release_gate_summary.json"
_P18_REPORT_FILENAME = "p18_full_regression_ci_release_gate_report.json"
_DOCKER_BUILD_EXTERNAL_EVIDENCE_FILENAME = "p19_docker_build_evidence_external.json"
_DOCKER_RUN_EXTERNAL_EVIDENCE_FILENAME = "p19_docker_run_self_test_evidence_external.json"
_LAUNCHER_EXTERNAL_EVIDENCE_FILENAME = "p19_launcher_import_evidence_external.json"

_EXECUTION_FIELDS_FOR_P19 = {
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

_REQUIRED_EXTERNAL_EVIDENCE_FILENAMES = (
    _DOCKER_BUILD_EXTERNAL_EVIDENCE_FILENAME,
    _DOCKER_RUN_EXTERNAL_EVIDENCE_FILENAME,
    _LAUNCHER_EXTERNAL_EVIDENCE_FILENAME,
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
                if key in _EXECUTION_FIELDS_FOR_P19 and _bool(value):
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


def build_docker_build_external_evidence_template(p18_hash: str) -> dict[str, Any]:
    return {
        "evidence_type": "docker_compose_build_external_evidence",
        "command_id": "docker_build",
        "command": "docker compose build crypto_ai_system_self_test",
        "source_p18_full_regression_ci_release_gate_sha256": p18_hash,
        "exit_code": 0,
        "completed": True,
        "image_name": "crypto_ai_system_self_test",
        "image_digest_sha256": "0" * 64,
        "stdout_sha256": "1" * 64,
        "stderr_sha256": "2" * 64,
        "build_log_secret_scan_passed": True,
        "docker_daemon_execution_performed_external": True,
        "performed_by_this_module": False,
        "actual_docker_build_performed_by_this_module": False,
        "actual_docker_run_performed_by_this_module": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
    }


def build_docker_run_external_evidence_template(p18_hash: str) -> dict[str, Any]:
    return {
        "evidence_type": "docker_compose_run_self_test_external_evidence",
        "command_id": "docker_run_self_test",
        "command": "docker compose run --rm crypto_ai_system_self_test",
        "source_p18_full_regression_ci_release_gate_sha256": p18_hash,
        "exit_code": 0,
        "completed": True,
        "container_exit_code": 0,
        "self_test_passed": True,
        "run_log_sha256": "3" * 64,
        "stdout_sha256": "4" * 64,
        "stderr_sha256": "5" * 64,
        "run_log_secret_scan_passed": True,
        "run_command_publish_blocked": True,
        "live_command_disabled": True,
        "docker_daemon_execution_performed_external": True,
        "performed_by_this_module": False,
        "actual_docker_build_performed_by_this_module": False,
        "actual_docker_run_performed_by_this_module": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
    }


def build_launcher_import_external_evidence_template(p18_hash: str) -> dict[str, Any]:
    return {
        "evidence_type": "launcher_import_simulation_external_evidence",
        "command_id": "launcher_import_validation",
        "command": "PYTHONPATH=src:. python scripts/validate_agent_os_import_package.py",
        "source_p18_full_regression_ci_release_gate_sha256": p18_hash,
        "exit_code": 0,
        "completed": True,
        "agent_id": "crypto_ai_system",
        "zip_top_level_dir": "crypto_ai_system",
        "manifest_imported": True,
        "command_map_imported": True,
        "run_command_publish_blocked": True,
        "live_command_enabled": False,
        "telegram_router_mutated_by_this_module": False,
        "agent_registry_mutated_by_this_module": False,
        "launcher_import_manager_mutated_by_this_module": False,
        "launcher_import_simulation_performed_external": True,
        "performed_by_this_module": False,
        "order_endpoint_called": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
    }


def _validate_docker_build_evidence(evidence: Mapping[str, Any], p18_hash: str) -> list[str]:
    reasons: list[str] = []
    if not evidence:
        return ["P19_DOCKER_BUILD_EVIDENCE_MISSING"]
    if evidence.get("evidence_type") != "docker_compose_build_external_evidence":
        reasons.append("P19_DOCKER_BUILD_EVIDENCE_TYPE_INVALID")
    if evidence.get("command_id") != "docker_build":
        reasons.append("P19_DOCKER_BUILD_COMMAND_ID_INVALID")
    if evidence.get("command") != "docker compose build crypto_ai_system_self_test":
        reasons.append("P19_DOCKER_BUILD_COMMAND_INVALID")
    if evidence.get("source_p18_full_regression_ci_release_gate_sha256") != p18_hash:
        reasons.append("P19_DOCKER_BUILD_P18_HASH_MISMATCH")
    if evidence.get("exit_code") != 0 or evidence.get("completed") is not True:
        reasons.append("P19_DOCKER_BUILD_NOT_SUCCESSFUL")
    if not _is_sha256(evidence.get("image_digest_sha256")):
        reasons.append("P19_DOCKER_BUILD_IMAGE_DIGEST_MISSING")
    if not _is_sha256(evidence.get("stdout_sha256")) or not _is_sha256(evidence.get("stderr_sha256")):
        reasons.append("P19_DOCKER_BUILD_LOG_HASH_MISSING")
    if evidence.get("build_log_secret_scan_passed") is not True:
        reasons.append("P19_DOCKER_BUILD_SECRET_SCAN_FAILED")
    if evidence.get("docker_daemon_execution_performed_external") is not True:
        reasons.append("P19_DOCKER_BUILD_NOT_MARKED_EXTERNAL")
    if evidence.get("performed_by_this_module") is not False:
        reasons.append("P19_DOCKER_BUILD_PERFORMED_BY_GATE")
    return reasons


def _validate_docker_run_evidence(evidence: Mapping[str, Any], p18_hash: str) -> list[str]:
    reasons: list[str] = []
    if not evidence:
        return ["P19_DOCKER_RUN_EVIDENCE_MISSING"]
    if evidence.get("evidence_type") != "docker_compose_run_self_test_external_evidence":
        reasons.append("P19_DOCKER_RUN_EVIDENCE_TYPE_INVALID")
    if evidence.get("command_id") != "docker_run_self_test":
        reasons.append("P19_DOCKER_RUN_COMMAND_ID_INVALID")
    if evidence.get("command") != "docker compose run --rm crypto_ai_system_self_test":
        reasons.append("P19_DOCKER_RUN_COMMAND_INVALID")
    if evidence.get("source_p18_full_regression_ci_release_gate_sha256") != p18_hash:
        reasons.append("P19_DOCKER_RUN_P18_HASH_MISMATCH")
    if evidence.get("exit_code") != 0 or evidence.get("container_exit_code") != 0 or evidence.get("completed") is not True:
        reasons.append("P19_DOCKER_RUN_NOT_SUCCESSFUL")
    if evidence.get("self_test_passed") is not True:
        reasons.append("P19_DOCKER_RUN_SELF_TEST_FAILED")
    if not _is_sha256(evidence.get("run_log_sha256")):
        reasons.append("P19_DOCKER_RUN_LOG_HASH_MISSING")
    if evidence.get("run_log_secret_scan_passed") is not True:
        reasons.append("P19_DOCKER_RUN_SECRET_SCAN_FAILED")
    if evidence.get("run_command_publish_blocked") is not True or evidence.get("live_command_disabled") is not True:
        reasons.append("P19_DOCKER_RUN_COMMAND_SAFETY_CHECK_FAILED")
    if evidence.get("docker_daemon_execution_performed_external") is not True:
        reasons.append("P19_DOCKER_RUN_NOT_MARKED_EXTERNAL")
    if evidence.get("performed_by_this_module") is not False:
        reasons.append("P19_DOCKER_RUN_PERFORMED_BY_GATE")
    return reasons


def _validate_launcher_import_evidence(evidence: Mapping[str, Any], p18_hash: str) -> list[str]:
    reasons: list[str] = []
    if not evidence:
        return ["P19_LAUNCHER_IMPORT_EVIDENCE_MISSING"]
    if evidence.get("evidence_type") != "launcher_import_simulation_external_evidence":
        reasons.append("P19_LAUNCHER_IMPORT_EVIDENCE_TYPE_INVALID")
    if evidence.get("command_id") != "launcher_import_validation":
        reasons.append("P19_LAUNCHER_IMPORT_COMMAND_ID_INVALID")
    if evidence.get("source_p18_full_regression_ci_release_gate_sha256") != p18_hash:
        reasons.append("P19_LAUNCHER_IMPORT_P18_HASH_MISMATCH")
    if evidence.get("exit_code") != 0 or evidence.get("completed") is not True:
        reasons.append("P19_LAUNCHER_IMPORT_NOT_SUCCESSFUL")
    if evidence.get("agent_id") != "crypto_ai_system" or evidence.get("zip_top_level_dir") != "crypto_ai_system":
        reasons.append("P19_LAUNCHER_IMPORT_AGENT_ID_OR_TOP_LEVEL_INVALID")
    if evidence.get("manifest_imported") is not True or evidence.get("command_map_imported") is not True:
        reasons.append("P19_LAUNCHER_IMPORT_MANIFEST_OR_COMMAND_MAP_FAILED")
    if evidence.get("run_command_publish_blocked") is not True or evidence.get("live_command_enabled") is not False:
        reasons.append("P19_LAUNCHER_IMPORT_COMMAND_SAFETY_CHECK_FAILED")
    if evidence.get("telegram_router_mutated_by_this_module") is not False or evidence.get("agent_registry_mutated_by_this_module") is not False:
        reasons.append("P19_LAUNCHER_IMPORT_MUTATION_DETECTED")
    if evidence.get("launcher_import_simulation_performed_external") is not True:
        reasons.append("P19_LAUNCHER_IMPORT_NOT_MARKED_EXTERNAL")
    if evidence.get("performed_by_this_module") is not False:
        reasons.append("P19_LAUNCHER_IMPORT_PERFORMED_BY_GATE")
    return reasons


def build_docker_launcher_evidence_intake_report(
    *,
    root: Path,
    p18_summary: Mapping[str, Any] | None = None,
    p18_report: Mapping[str, Any] | None = None,
    docker_build_evidence: Mapping[str, Any] | None = None,
    docker_run_evidence: Mapping[str, Any] | None = None,
    launcher_import_evidence: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    del root
    p18_summary = dict(p18_summary or {})
    p18_report = dict(p18_report or {})
    docker_build_evidence = dict(docker_build_evidence or {})
    docker_run_evidence = dict(docker_run_evidence or {})
    launcher_import_evidence = dict(launcher_import_evidence or {})

    p18_hash = p18_summary.get("p18_full_regression_ci_release_gate_sha256") or p18_report.get("p18_full_regression_ci_release_gate_sha256")
    named_payloads = [
        ("p18_summary", p18_summary),
        ("p18_report", p18_report),
        ("docker_build_evidence", docker_build_evidence),
        ("docker_run_evidence", docker_run_evidence),
        ("launcher_import_evidence", launcher_import_evidence),
    ]
    named_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(named_payloads)
    secret_hits = _scan_secret_value_patterns(named_payloads)

    disabled_state = default_execution_flag_state()
    disabled_state.update({field: False for field in _EXECUTION_FIELDS_FOR_P19})
    truthy_disabled = truthy_execution_flags(disabled_state)

    missing_external = []
    if not docker_build_evidence:
        missing_external.append(_DOCKER_BUILD_EXTERNAL_EVIDENCE_FILENAME)
    if not docker_run_evidence:
        missing_external.append(_DOCKER_RUN_EXTERNAL_EVIDENCE_FILENAME)
    if not launcher_import_evidence:
        missing_external.append(_LAUNCHER_EXTERNAL_EVIDENCE_FILENAME)

    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if not p18_summary:
        block_reasons.append("P19_SOURCE_P18_SUMMARY_MISSING")
    if p18_summary and p18_summary.get("status") == "P18_FULL_REGRESSION_CI_RELEASE_GATE_BLOCKED_FAIL_CLOSED":
        block_reasons.append("P19_SOURCE_P18_RELEASE_GATE_BLOCKED")
    if not p18_report:
        block_reasons.append("P19_SOURCE_P18_REPORT_MISSING")
    if p18_summary and p18_summary.get("p18_ci_release_gate_hardened_review_only") is not True:
        block_reasons.append("P19_SOURCE_P18_NOT_HARDENED")
    if not _is_sha256(p18_hash):
        block_reasons.append("P19_SOURCE_P18_HASH_MISSING_OR_INVALID")
    if missing_external:
        waiting_reasons.append("P19_EXTERNAL_DOCKER_OR_LAUNCHER_EVIDENCE_MISSING")
    if not missing_external and _is_sha256(p18_hash):
        block_reasons.extend(_validate_docker_build_evidence(docker_build_evidence, str(p18_hash)))
        block_reasons.extend(_validate_docker_run_evidence(docker_run_evidence, str(p18_hash)))
        block_reasons.extend(_validate_launcher_import_evidence(launcher_import_evidence, str(p18_hash)))
    if unsafe_hits:
        block_reasons.append("P19_UNSAFE_TRUTHY_FLAG_FOUND")
    if secret_hits:
        block_reasons.append("P19_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P19_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    valid = not blocked and not waiting_reasons
    status = STATUS_BLOCKED_FAIL_CLOSED if blocked else (STATUS_VALID_REVIEW_ONLY if valid else STATUS_WAITING_REVIEW_ONLY)

    docker_build_checks = {
        "present": bool(docker_build_evidence),
        "valid_review_only": bool(docker_build_evidence) and not _validate_docker_build_evidence(docker_build_evidence, str(p18_hash or "")),
        "performed_external": docker_build_evidence.get("docker_daemon_execution_performed_external") is True,
        "performed_by_this_module": docker_build_evidence.get("performed_by_this_module") is True,
    }
    docker_run_checks = {
        "present": bool(docker_run_evidence),
        "valid_review_only": bool(docker_run_evidence) and not _validate_docker_run_evidence(docker_run_evidence, str(p18_hash or "")),
        "performed_external": docker_run_evidence.get("docker_daemon_execution_performed_external") is True,
        "performed_by_this_module": docker_run_evidence.get("performed_by_this_module") is True,
    }
    launcher_checks = {
        "present": bool(launcher_import_evidence),
        "valid_review_only": bool(launcher_import_evidence) and not _validate_launcher_import_evidence(launcher_import_evidence, str(p18_hash or "")),
        "performed_external": launcher_import_evidence.get("launcher_import_simulation_performed_external") is True,
        "performed_by_this_module": launcher_import_evidence.get("performed_by_this_module") is True,
    }

    report: dict[str, Any] = {
        "p19_docker_launcher_evidence_intake_version": P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": valid,
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "created_at_utc": utc_now_canonical(),
        "source_p18_summary_sha256": p18_summary.get("p18_full_regression_ci_release_gate_summary_sha256"),
        "source_p18_report_sha256": p18_report.get("p18_full_regression_ci_release_gate_sha256"),
        "source_p18_full_regression_ci_release_gate_sha256": p18_hash,
        "required_external_evidence_files": list(_REQUIRED_EXTERNAL_EVIDENCE_FILENAMES),
        "missing_external_evidence_files": missing_external,
        "docker_build_evidence_check": docker_build_checks,
        "docker_run_self_test_evidence_check": docker_run_checks,
        "launcher_import_evidence_check": launcher_checks,
        "docker_build_evidence_sha256": sha256_json(docker_build_evidence) if docker_build_evidence else None,
        "docker_run_self_test_evidence_sha256": sha256_json(docker_run_evidence) if docker_run_evidence else None,
        "launcher_import_evidence_sha256": sha256_json(launcher_import_evidence) if launcher_import_evidence else None,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "operator_evidence_intake_instructions": {
            "docker_build_evidence_file": f"storage/latest/{_DOCKER_BUILD_EXTERNAL_EVIDENCE_FILENAME}",
            "docker_run_evidence_file": f"storage/latest/{_DOCKER_RUN_EXTERNAL_EVIDENCE_FILENAME}",
            "launcher_import_evidence_file": f"storage/latest/{_LAUNCHER_EXTERNAL_EVIDENCE_FILENAME}",
            "regenerate_gate": "PYTHONPATH=src:. python scripts/run_docker_launcher_evidence_gate.py",
            "must_not_include_secret_values": True,
            "must_not_claim_order_endpoint_calls": True,
        },
        "p19_docker_launcher_evidence_intake_valid_review_only": valid,
        "docker_build_evidence_valid_review_only": docker_build_checks["valid_review_only"],
        "docker_run_self_test_evidence_valid_review_only": docker_run_checks["valid_review_only"],
        "launcher_import_evidence_valid_review_only": launcher_checks["valid_review_only"],
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
    report["p19_docker_launcher_evidence_intake_id"] = stable_id("p19_docker_launcher_evidence_intake", report, 24)
    report["p19_docker_launcher_evidence_intake_sha256"] = sha256_json(report)
    return report


def build_p19_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    p18_hash = "a" * 64
    base_p18_summary = {
        "status": "P18_FULL_REGRESSION_CI_RELEASE_GATE_HARDENED_REVIEW_ONLY",
        "p18_full_regression_ci_release_gate_sha256": p18_hash,
        "p18_full_regression_ci_release_gate_summary_sha256": "b" * 64,
        "p18_ci_release_gate_hardened_review_only": True,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    base_p18_report = {
        "status": "P18_FULL_REGRESSION_CI_RELEASE_GATE_HARDENED_REVIEW_ONLY",
        "p18_full_regression_ci_release_gate_sha256": p18_hash,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    docker_build = build_docker_build_external_evidence_template(p18_hash)
    docker_run = build_docker_run_external_evidence_template(p18_hash)
    launcher = build_launcher_import_external_evidence_template(p18_hash)
    cases = {
        "missing_p18_summary": {"p18_summary": {}, "p18_report": base_p18_report, "docker_build_evidence": docker_build, "docker_run_evidence": docker_run, "launcher_import_evidence": launcher},
        "p18_blocked": {"p18_summary": {**base_p18_summary, "status": "P18_FULL_REGRESSION_CI_RELEASE_GATE_BLOCKED_FAIL_CLOSED"}, "p18_report": base_p18_report, "docker_build_evidence": docker_build, "docker_run_evidence": docker_run, "launcher_import_evidence": launcher},
        "docker_build_failed": {"p18_summary": base_p18_summary, "p18_report": base_p18_report, "docker_build_evidence": {**docker_build, "exit_code": 1}, "docker_run_evidence": docker_run, "launcher_import_evidence": launcher},
        "docker_run_failed": {"p18_summary": base_p18_summary, "p18_report": base_p18_report, "docker_build_evidence": docker_build, "docker_run_evidence": {**docker_run, "self_test_passed": False}, "launcher_import_evidence": launcher},
        "launcher_import_failed": {"p18_summary": base_p18_summary, "p18_report": base_p18_report, "docker_build_evidence": docker_build, "docker_run_evidence": docker_run, "launcher_import_evidence": {**launcher, "manifest_imported": False}},
        "p18_hash_mismatch": {"p18_summary": base_p18_summary, "p18_report": base_p18_report, "docker_build_evidence": {**docker_build, "source_p18_full_regression_ci_release_gate_sha256": "c" * 64}, "docker_run_evidence": docker_run, "launcher_import_evidence": launcher},
        "secret_pattern_found": {"p18_summary": base_p18_summary, "p18_report": base_p18_report, "docker_build_evidence": {**docker_build, "stdout_excerpt": "BINANCE_API_SECRET=leaked"}, "docker_run_evidence": docker_run, "launcher_import_evidence": launcher},
        "endpoint_called_in_evidence": {"p18_summary": base_p18_summary, "p18_report": base_p18_report, "docker_build_evidence": docker_build, "docker_run_evidence": {**docker_run, "order_endpoint_called": True}, "launcher_import_evidence": launcher},
        "launcher_mutated_router": {"p18_summary": base_p18_summary, "p18_report": base_p18_report, "docker_build_evidence": docker_build, "docker_run_evidence": docker_run, "launcher_import_evidence": {**launcher, "telegram_router_mutated_by_this_module": True}},
        "unsafe_runtime_flag": {"p18_summary": {**base_p18_summary, "live_scaled_execution_enabled": True}, "p18_report": base_p18_report, "docker_build_evidence": docker_build, "docker_run_evidence": docker_run, "launcher_import_evidence": launcher},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_docker_launcher_evidence_intake_report(root=root, **kwargs)
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
        "p19_docker_launcher_evidence_intake_version": P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_VERSION,
        "status": "P19_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_docker_launcher_evidence_intake(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    p18_summary = _read_latest_json(cfg, _P18_SUMMARY_FILENAME)
    p18_report = _read_latest_json(cfg, _P18_REPORT_FILENAME)
    docker_build_evidence = _read_latest_json(cfg, _DOCKER_BUILD_EXTERNAL_EVIDENCE_FILENAME)
    docker_run_evidence = _read_latest_json(cfg, _DOCKER_RUN_EXTERNAL_EVIDENCE_FILENAME)
    launcher_import_evidence = _read_latest_json(cfg, _LAUNCHER_EXTERNAL_EVIDENCE_FILENAME)
    report = build_docker_launcher_evidence_intake_report(
        root=cfg.root,
        p18_summary=p18_summary,
        p18_report=p18_report,
        docker_build_evidence=docker_build_evidence,
        docker_run_evidence=docker_run_evidence,
        launcher_import_evidence=launcher_import_evidence,
    )
    negative_results = build_p19_negative_fixture_results(root=cfg.root)
    storage = _storage_dir(cfg, "storage/p19_docker_launcher_evidence_intake")

    atomic_write_json(latest / "p19_docker_launcher_evidence_intake_report.json", report)
    atomic_write_json(storage / "p19_docker_launcher_evidence_intake_report.json", report)
    atomic_write_json(latest / "p19_docker_launcher_evidence_intake_negative_fixture_results.json", negative_results)

    summary = {
        "status": report["status"],
        "p19_docker_launcher_evidence_intake_sha256": report["p19_docker_launcher_evidence_intake_sha256"],
        "p19_docker_launcher_evidence_intake_valid_review_only": report["p19_docker_launcher_evidence_intake_valid_review_only"],
        "docker_build_evidence_valid_review_only": report["docker_build_evidence_valid_review_only"],
        "docker_run_self_test_evidence_valid_review_only": report["docker_run_self_test_evidence_valid_review_only"],
        "launcher_import_evidence_valid_review_only": report["launcher_import_evidence_valid_review_only"],
        "missing_external_evidence_files": report["missing_external_evidence_files"],
        "operator_evidence_intake_instructions": report["operator_evidence_intake_instructions"],
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
    summary["p19_docker_launcher_evidence_intake_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p19_docker_launcher_evidence_intake_summary.json", summary)

    registry_record = append_registry_record(
        registry_path(cfg, P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_REGISTRY_NAME),
        report,
        registry_name=P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_REGISTRY_NAME,
        id_field="p19_docker_launcher_evidence_intake_registry_id",
        hash_field="p19_docker_launcher_evidence_intake_registry_sha256",
        id_prefix="p19_docker_launcher",
    )
    atomic_write_json(latest / "p19_docker_launcher_evidence_intake_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_docker_launcher_evidence_intake()
    print(result["status"])
    print(result["p19_docker_launcher_evidence_intake_sha256"])
