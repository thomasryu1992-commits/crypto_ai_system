from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P18_FULL_REGRESSION_CI_RELEASE_GATE_VERSION = "p18_full_regression_ci_release_gate_v1"
P18_FULL_REGRESSION_CI_RELEASE_GATE_REGISTRY_NAME = "p18_full_regression_ci_release_gate_registry"

STATUS_HARDENED_REVIEW_ONLY = "P18_FULL_REGRESSION_CI_RELEASE_GATE_HARDENED_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P18_FULL_REGRESSION_CI_RELEASE_GATE_BLOCKED_FAIL_CLOSED"

_P17_SUMMARY_FILENAME = "p17_runtime_release_gate_operator_handoff_summary.json"
_P17_REPORT_FILENAME = "p17_runtime_release_gate_operator_handoff_report.json"

_EXECUTION_FIELDS_FOR_P18 = {
    "limited_live_scaled_auto_trading_allowed",
    "live_scaled_runtime_enablement_allowed",
    "live_scaled_execution_enabled",
    "live_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "runtime_scheduler_enabled",
    "runtime_loop_started",
    "actual_live_order_submitted",
    "live_order_endpoint_called",
    "order_endpoint_called",
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

_REQUIRED_DOCKER_FILES = ("Dockerfile", "docker-compose.yml", ".dockerignore", "scripts/docker_smoke.py")
_REQUIRED_LAUNCHER_FILES = (
    "agent_manifest.json",
    "agent_import_manifest.json",
    "scripts/run_command.py",
    "scripts/self_test.py",
    "scripts/validate_package.py",
    "scripts/validate_agent_os_import_package.py",
    "config/command_map.json",
    "config/defaults.json",
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


def _read_json_file(path: Path) -> dict[str, Any]:
    payload = read_json(path, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


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
                if key in _EXECUTION_FIELDS_FOR_P18 and _bool(value):
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


def build_p18_command_plan() -> list[dict[str, Any]]:
    return [
        {
            "command_id": "compileall",
            "category": "python_static",
            "command": "PYTHONPATH=src:. python -m compileall -q src config tests scripts",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
        },
        {
            "command_id": "focused_smoke_tests",
            "category": "pytest_smoke",
            "command": "PYTHONPATH=src:. pytest -q tests/agents/test_p17_runtime_release_gate_operator_handoff.py tests/agents/test_p16_limited_live_scaled_loop_dry_run_harness.py tests/agents/test_p15_limited_live_scaled_runtime_enablement_boundary.py tests/agents/test_p14_live_scaled_approval_intake_validation.py tests/agents/test_p13_live_scaled_readiness_review.py",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
        },
        {
            "command_id": "release_gate",
            "category": "release_gate",
            "command": "PYTHONPATH=src:. python scripts/run_release_gate.py",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
        },
        {
            "command_id": "status_consistency_checker",
            "category": "status_consistency",
            "command": "PYTHONPATH=src:. python scripts/status_consistency_checker.py .",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
        },
        {
            "command_id": "agent_lint",
            "category": "agent_library",
            "command": "PYTHONPATH=src:. python scripts/lint_agents.py",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
        },
        {
            "command_id": "agent_contracts",
            "category": "agent_library",
            "command": "PYTHONPATH=src:. python scripts/validate_agent_contracts.py",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
        },
        {
            "command_id": "agent_outputs",
            "category": "agent_library",
            "command": "PYTHONPATH=src:. python scripts/validate_agent_outputs.py",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
        },
        {
            "command_id": "agent_evals",
            "category": "agent_library",
            "command": "PYTHONPATH=src:. python scripts/run_agent_evals.py",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
        },
        {
            "command_id": "validate_package",
            "category": "launcher_package",
            "command": "PYTHONPATH=src:. python scripts/validate_package.py",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
        },
        {
            "command_id": "self_test",
            "category": "launcher_package",
            "command": "PYTHONPATH=src:. python scripts/self_test.py",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
        },
        {
            "command_id": "launcher_import_validation",
            "category": "launcher_package",
            "command": "PYTHONPATH=src:. python scripts/validate_agent_os_import_package.py",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
        },
        {
            "command_id": "docker_smoke_static",
            "category": "docker_static",
            "command": "PYTHONPATH=src:. python scripts/docker_smoke.py",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
        },
        {
            "command_id": "docker_build",
            "category": "docker_build",
            "command": "docker compose build crypto_ai_system_self_test",
            "required_in_ci": True,
            "network_required": True,
            "order_endpoint_risk": False,
            "external_runtime_required": True,
        },
        {
            "command_id": "docker_run_self_test",
            "category": "docker_runtime_smoke",
            "command": "docker compose run --rm crypto_ai_system_self_test",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
            "external_runtime_required": True,
        },
        {
            "command_id": "zip_integrity",
            "category": "artifact_packaging",
            "command": "python -m zipfile -t <release_zip>",
            "required_in_ci": True,
            "network_required": False,
            "order_endpoint_risk": False,
        },
    ]


def build_docker_compatibility_check(root: Path) -> dict[str, Any]:
    missing = [rel for rel in _REQUIRED_DOCKER_FILES if not (root / rel).exists()]
    dockerfile_text = (root / "Dockerfile").read_text(encoding="utf-8") if (root / "Dockerfile").exists() else ""
    compose_text = (root / "docker-compose.yml").read_text(encoding="utf-8") if (root / "docker-compose.yml").exists() else ""
    dockerignore_text = (root / ".dockerignore").read_text(encoding="utf-8") if (root / ".dockerignore").exists() else ""
    checks = {
        "required_docker_files_present": not missing,
        "dockerfile_review_only_comment_present": "review-only" in dockerfile_text.lower(),
        "dockerfile_entrypoint_run_command": 'ENTRYPOINT ["python", "scripts/run_command.py"]' in dockerfile_text,
        "compose_self_test_service_present": "crypto_ai_system_self_test" in compose_text and "scripts/self_test.py" in compose_text,
        "compose_no_env_file": "env_file:" not in compose_text.lower(),
        "compose_no_secret_value_names": "BINANCE_API_SECRET" not in compose_text and "PRIVATE_KEY" not in compose_text,
        "dockerignore_blocks_env_and_secret_files": ".env" in dockerignore_text and "secrets.json" in dockerignore_text,
        "docker_smoke_script_present": (root / "scripts/docker_smoke.py").exists(),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "docker_compatibility_valid_review_only": not failed,
        "checks": checks,
        "failed_checks": failed,
        "missing_files": missing,
        "docker_build_command": "docker compose build crypto_ai_system_self_test",
        "docker_run_self_test_command": "docker compose run --rm crypto_ai_system_self_test",
        "actual_docker_build_performed_by_this_module": False,
        "actual_docker_run_performed_by_this_module": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def build_launcher_compatibility_check(root: Path) -> dict[str, Any]:
    missing = [rel for rel in _REQUIRED_LAUNCHER_FILES if not (root / rel).exists()]
    manifest = _read_json_file(root / "agent_manifest.json")
    import_manifest = _read_json_file(root / "agent_import_manifest.json")
    command_map = _read_json_file(root / "config/command_map.json")
    defaults = _read_json_file(root / "config/defaults.json")
    checks = {
        "required_launcher_files_present": not missing,
        "manifest_agent_id_crypto_ai_system": manifest.get("agent_id") == "crypto_ai_system",
        "manifest_entrypoint_run_command": manifest.get("entrypoint") == "python scripts/run_command.py",
        "manifest_self_test_present": manifest.get("self_test") == "python scripts/self_test.py",
        "import_manifest_boundary_zip_only": import_manifest.get("boundary") == "crypto_ai_system_zip_only",
        "import_manifest_expected_top_level": import_manifest.get("expected_zip_top_level_dir") == "crypto_ai_system",
        "launcher_owned_responsibilities_not_implemented_here": manifest.get("agent_os_import", {}).get("launcher_import_manager_implemented_here") is False and manifest.get("agent_os_import", {}).get("telegram_router_implemented_here") is False,
        "required_commands_present": {"daily", "scan", "signal", "source-health", "paper"}.issubset(set(command_map)),
        "live_command_disabled": command_map.get("live", {}).get("enabled") is False,
        "safe_defaults_no_execution_permission": defaults.get("execution_permission_granted") is False and defaults.get("stage_transition_allowed") is False,
        "validate_import_script_present": (root / "scripts/validate_agent_os_import_package.py").exists(),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "launcher_compatibility_valid_review_only": not failed,
        "checks": checks,
        "failed_checks": failed,
        "missing_files": missing,
        "launcher_import_validation_command": "PYTHONPATH=src:. python scripts/validate_agent_os_import_package.py",
        "launcher_import_simulation_performed_by_this_module": False,
        "telegram_router_mutated_by_this_module": False,
        "agent_registry_mutated_by_this_module": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def build_full_regression_ci_release_gate_report(
    *,
    root: Path,
    p17_summary: Mapping[str, Any] | None = None,
    p17_report: Mapping[str, Any] | None = None,
    docker_check: Mapping[str, Any] | None = None,
    launcher_check: Mapping[str, Any] | None = None,
    command_plan: Sequence[Mapping[str, Any]] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    p17_summary = dict(p17_summary or {})
    p17_report = dict(p17_report or {})
    docker_check = dict(docker_check or build_docker_compatibility_check(root))
    launcher_check = dict(launcher_check or build_launcher_compatibility_check(root))
    command_plan = [dict(item) for item in (command_plan or build_p18_command_plan())]

    command_ids = {item.get("command_id") for item in command_plan}
    required_command_ids = {
        "compileall",
        "focused_smoke_tests",
        "release_gate",
        "status_consistency_checker",
        "agent_lint",
        "agent_contracts",
        "agent_outputs",
        "agent_evals",
        "validate_package",
        "self_test",
        "launcher_import_validation",
        "docker_smoke_static",
        "docker_build",
        "docker_run_self_test",
        "zip_integrity",
    }
    missing_command_ids = sorted(required_command_ids - command_ids)
    named_payloads = [("p17_summary", p17_summary), ("p17_report", p17_report)]
    named_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(named_payloads)

    disabled_state = default_execution_flag_state()
    disabled_state.update({field: False for field in _EXECUTION_FIELDS_FOR_P18})
    truthy_disabled = truthy_execution_flags(disabled_state)

    block_reasons: list[str] = []
    if not p17_summary:
        block_reasons.append("P18_SOURCE_P17_SUMMARY_MISSING")
    if p17_summary and p17_summary.get("status") == "P17_RUNTIME_RELEASE_GATE_OPERATOR_HANDOFF_BLOCKED_FAIL_CLOSED":
        block_reasons.append("P18_SOURCE_P17_RELEASE_GATE_BLOCKED")
    if not p17_report:
        block_reasons.append("P18_SOURCE_P17_REPORT_MISSING")
    if missing_command_ids:
        block_reasons.append("P18_REQUIRED_CI_COMMAND_MISSING")
    if not docker_check.get("docker_compatibility_valid_review_only"):
        block_reasons.append("P18_DOCKER_COMPATIBILITY_CHECK_FAILED")
    if not launcher_check.get("launcher_compatibility_valid_review_only"):
        block_reasons.append("P18_LAUNCHER_COMPATIBILITY_CHECK_FAILED")
    if unsafe_hits:
        block_reasons.append("P18_UNSAFE_TRUTHY_FLAG_FOUND")
    if truthy_disabled:
        block_reasons.append("P18_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    status = STATUS_BLOCKED_FAIL_CLOSED if blocked else STATUS_HARDENED_REVIEW_ONLY
    report: dict[str, Any] = {
        "p18_full_regression_ci_release_gate_version": P18_FULL_REGRESSION_CI_RELEASE_GATE_VERSION,
        "status": status,
        "blocked": blocked,
        "block_reasons": sorted(set(block_reasons)),
        "created_at_utc": utc_now_canonical(),
        "source_p17_summary_sha256": p17_summary.get("p17_runtime_release_gate_operator_handoff_summary_sha256"),
        "source_p17_report_sha256": p17_report.get("p17_runtime_release_gate_operator_handoff_sha256"),
        "p18_ci_release_gate_hardened_review_only": not blocked,
        "p18_full_regression_command_suite_defined": not missing_command_ids,
        "required_ci_command_count": len(required_command_ids),
        "configured_ci_command_count": len(command_ids),
        "missing_ci_command_ids": missing_command_ids,
        "ci_command_plan": command_plan,
        "docker_compatibility_check": docker_check,
        "launcher_compatibility_check": launcher_check,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "one_command_ci_release_gate_command": "PYTHONPATH=src:. python scripts/run_ci_release_gate.py",
        "legacy_p17_release_gate_command": "PYTHONPATH=src:. python scripts/run_release_gate.py",
        "ci_operator_handoff": {
            "run_before_packaging": "PYTHONPATH=src:. python scripts/run_ci_release_gate.py",
            "run_zip_integrity_after_packaging": "python -m zipfile -t <release_zip>",
            "docker_build_required_in_ci": True,
            "docker_build_performed_by_this_module": False,
            "launcher_import_performed_by_this_module": False,
            "review_only_result_required": STATUS_HARDENED_REVIEW_ONLY,
            "must_not_enable_runtime_from_this_gate": True,
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
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    report["p18_full_regression_ci_release_gate_id"] = stable_id("p18_full_regression_ci_release_gate", report, 24)
    report["p18_full_regression_ci_release_gate_sha256"] = sha256_json(report)
    return report


def build_p18_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    base_p17_summary = {
        "status": "P17_RUNTIME_RELEASE_GATE_OPERATOR_HANDOFF_GENERATED_REVIEW_ONLY",
        "p17_runtime_release_gate_operator_handoff_summary_sha256": "0" * 64,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    base_p17_report = {
        "status": "P17_RUNTIME_RELEASE_GATE_OPERATOR_HANDOFF_GENERATED_REVIEW_ONLY",
        "p17_runtime_release_gate_operator_handoff_sha256": "1" * 64,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    base_docker = {"docker_compatibility_valid_review_only": True, "failed_checks": [], "actual_docker_build_performed_by_this_module": False, "actual_docker_run_performed_by_this_module": False}
    base_launcher = {"launcher_compatibility_valid_review_only": True, "failed_checks": [], "launcher_import_simulation_performed_by_this_module": False, "telegram_router_mutated_by_this_module": False}
    base_plan = build_p18_command_plan()
    cases = {
        "missing_p17_summary": {"p17_summary": {}, "p17_report": base_p17_report, "docker_check": base_docker, "launcher_check": base_launcher, "command_plan": base_plan},
        "p17_blocked": {"p17_summary": {**base_p17_summary, "status": "P17_RUNTIME_RELEASE_GATE_OPERATOR_HANDOFF_BLOCKED_FAIL_CLOSED"}, "p17_report": base_p17_report, "docker_check": base_docker, "launcher_check": base_launcher, "command_plan": base_plan},
        "docker_compatibility_failed": {"p17_summary": base_p17_summary, "p17_report": base_p17_report, "docker_check": {**base_docker, "docker_compatibility_valid_review_only": False, "failed_checks": ["dockerfile_entrypoint_run_command"]}, "launcher_check": base_launcher, "command_plan": base_plan},
        "launcher_compatibility_failed": {"p17_summary": base_p17_summary, "p17_report": base_p17_report, "docker_check": base_docker, "launcher_check": {**base_launcher, "launcher_compatibility_valid_review_only": False, "failed_checks": ["manifest_agent_id_crypto_ai_system"]}, "command_plan": base_plan},
        "missing_ci_command": {"p17_summary": base_p17_summary, "p17_report": base_p17_report, "docker_check": base_docker, "launcher_check": base_launcher, "command_plan": [item for item in base_plan if item["command_id"] != "docker_build"]},
        "unsafe_runtime_flag": {"p17_summary": {**base_p17_summary, "live_scaled_execution_enabled": True}, "p17_report": base_p17_report, "docker_check": base_docker, "launcher_check": base_launcher, "command_plan": base_plan},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_full_regression_ci_release_gate_report(root=root, **kwargs)
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
        "p18_full_regression_ci_release_gate_version": P18_FULL_REGRESSION_CI_RELEASE_GATE_VERSION,
        "status": "P18_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_full_regression_ci_release_gate(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    p17_summary = _read_latest_json(cfg, _P17_SUMMARY_FILENAME)
    p17_report = _read_latest_json(cfg, _P17_REPORT_FILENAME)
    report = build_full_regression_ci_release_gate_report(
        root=cfg.root,
        p17_summary=p17_summary,
        p17_report=p17_report,
    )
    negative_results = build_p18_negative_fixture_results(root=cfg.root)
    storage = _storage_dir(cfg, "storage/p18_full_regression_ci_release_gate")

    atomic_write_json(latest / "p18_full_regression_ci_release_gate_report.json", report)
    atomic_write_json(storage / "p18_full_regression_ci_release_gate_report.json", report)
    atomic_write_json(latest / "p18_full_regression_ci_release_gate_negative_fixture_results.json", negative_results)

    summary = {
        "status": report["status"],
        "p18_full_regression_ci_release_gate_sha256": report["p18_full_regression_ci_release_gate_sha256"],
        "p18_ci_release_gate_hardened_review_only": report["p18_ci_release_gate_hardened_review_only"],
        "p18_full_regression_command_suite_defined": report["p18_full_regression_command_suite_defined"],
        "required_ci_command_count": report["required_ci_command_count"],
        "configured_ci_command_count": report["configured_ci_command_count"],
        "missing_ci_command_ids": report["missing_ci_command_ids"],
        "docker_compatibility_valid_review_only": report["docker_compatibility_check"].get("docker_compatibility_valid_review_only"),
        "launcher_compatibility_valid_review_only": report["launcher_compatibility_check"].get("launcher_compatibility_valid_review_only"),
        "one_command_ci_release_gate_command": report["one_command_ci_release_gate_command"],
        "docker_build_command": report["docker_compatibility_check"].get("docker_build_command"),
        "docker_run_self_test_command": report["docker_compatibility_check"].get("docker_run_self_test_command"),
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
    summary["p18_full_regression_ci_release_gate_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p18_full_regression_ci_release_gate_summary.json", summary)

    registry_record = append_registry_record(
        registry_path(cfg, P18_FULL_REGRESSION_CI_RELEASE_GATE_REGISTRY_NAME),
        report,
        registry_name=P18_FULL_REGRESSION_CI_RELEASE_GATE_REGISTRY_NAME,
        id_field="p18_full_regression_ci_release_gate_registry_id",
        hash_field="p18_full_regression_ci_release_gate_registry_sha256",
        id_prefix="p18_ci_gate",
    )
    atomic_write_json(latest / "p18_full_regression_ci_release_gate_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_full_regression_ci_release_gate()
    print(result["status"])
    print(result["p18_full_regression_ci_release_gate_sha256"])
