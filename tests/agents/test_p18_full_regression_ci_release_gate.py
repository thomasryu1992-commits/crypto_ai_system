from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.full_regression_ci_release_gate import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_HARDENED_REVIEW_ONLY,
    build_docker_compatibility_check,
    build_full_regression_ci_release_gate_report,
    build_launcher_compatibility_check,
    build_p18_command_plan,
    build_p18_negative_fixture_results,
    persist_full_regression_ci_release_gate,
)


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text("[project]\nname='tmp-crypto-ai-system'\nversion='0.286.0'\n", encoding="utf-8")
    (root / "Dockerfile").write_text(
        "# review-only container\nENTRYPOINT [\"python\", \"scripts/run_command.py\"]\n",
        encoding="utf-8",
    )
    (root / "docker-compose.yml").write_text(
        "services:\n  crypto_ai_system_self_test:\n    entrypoint: [\"python\", \"scripts/self_test.py\"]\n",
        encoding="utf-8",
    )
    (root / ".dockerignore").write_text(".env\nsecrets.json\n", encoding="utf-8")
    for rel in ["docker_smoke.py", "run_command.py", "self_test.py", "validate_package.py", "validate_agent_os_import_package.py"]:
        (root / "scripts" / rel).write_text("print('ok')\n", encoding="utf-8")
    (root / "agent_manifest.json").write_text(
        '{"agent_id":"crypto_ai_system","entrypoint":"python scripts/run_command.py","self_test":"python scripts/self_test.py","agent_os_import":{"launcher_import_manager_implemented_here":false,"telegram_router_implemented_here":false}}',
        encoding="utf-8",
    )
    (root / "agent_import_manifest.json").write_text(
        '{"agent_id":"crypto_ai_system","boundary":"crypto_ai_system_zip_only","expected_zip_top_level_dir":"crypto_ai_system"}',
        encoding="utf-8",
    )
    (root / "config" / "command_map.json").write_text(
        '{"daily":{},"scan":{},"signal":{},"source-health":{},"paper":{},"live":{"enabled":false}}',
        encoding="utf-8",
    )
    (root / "config" / "defaults.json").write_text(
        '{"execution_permission_granted":false,"stage_transition_allowed":false}',
        encoding="utf-8",
    )


def _p17_summary() -> dict:
    return {
        "status": "P17_RUNTIME_RELEASE_GATE_OPERATOR_HANDOFF_GENERATED_REVIEW_ONLY",
        "p17_runtime_release_gate_operator_handoff_summary_sha256": "0" * 64,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p17_report() -> dict:
    return {
        "status": "P17_RUNTIME_RELEASE_GATE_OPERATOR_HANDOFF_GENERATED_REVIEW_ONLY",
        "p17_runtime_release_gate_operator_handoff_sha256": "1" * 64,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def test_p18_command_plan_contains_full_ci_release_gate_commands() -> None:
    plan = build_p18_command_plan()
    command_ids = {item["command_id"] for item in plan}

    assert {
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
    }.issubset(command_ids)
    assert all(item["order_endpoint_risk"] is False for item in plan)


def test_p18_generates_review_only_ci_release_gate_report(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_full_regression_ci_release_gate_report(
        root=tmp_path,
        p17_summary=_p17_summary(),
        p17_report=_p17_report(),
    )

    assert report["status"] == STATUS_HARDENED_REVIEW_ONLY
    assert report["p18_ci_release_gate_hardened_review_only"] is True
    assert report["p18_full_regression_command_suite_defined"] is True
    assert report["docker_compatibility_check"]["docker_compatibility_valid_review_only"] is True
    assert report["launcher_compatibility_check"]["launcher_compatibility_valid_review_only"] is True
    assert report["one_command_ci_release_gate_command"] == "PYTHONPATH=src:. python scripts/run_ci_release_gate.py"
    assert report["limited_live_scaled_auto_trading_allowed"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p18_static_docker_and_launcher_checks_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    docker_check = build_docker_compatibility_check(tmp_path)
    launcher_check = build_launcher_compatibility_check(tmp_path)
    assert docker_check["docker_compatibility_valid_review_only"] is True
    assert docker_check["actual_docker_build_performed_by_this_module"] is False
    assert launcher_check["launcher_compatibility_valid_review_only"] is True
    assert launcher_check["telegram_router_mutated_by_this_module"] is False

    (tmp_path / "Dockerfile").write_text("FROM python:3.11\n", encoding="utf-8")
    assert build_docker_compatibility_check(tmp_path)["docker_compatibility_valid_review_only"] is False

    (tmp_path / "agent_manifest.json").write_text('{"agent_id":"wrong"}', encoding="utf-8")
    assert build_launcher_compatibility_check(tmp_path)["launcher_compatibility_valid_review_only"] is False


def test_p18_persists_latest_report_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    atomic_write_json(latest / "p17_runtime_release_gate_operator_handoff_summary.json", _p17_summary())
    atomic_write_json(latest / "p17_runtime_release_gate_operator_handoff_report.json", _p17_report())
    cfg = load_config(tmp_path)

    report = persist_full_regression_ci_release_gate(cfg=cfg)

    assert report["status"] == STATUS_HARDENED_REVIEW_ONLY
    saved = read_json(latest / "p18_full_regression_ci_release_gate_report.json")
    summary = read_json(latest / "p18_full_regression_ci_release_gate_summary.json")
    registry = read_json(latest / "p18_full_regression_ci_release_gate_registry_record.json")
    negative = read_json(latest / "p18_full_regression_ci_release_gate_negative_fixture_results.json")
    assert saved["status"] == STATUS_HARDENED_REVIEW_ONLY
    assert summary["p18_ci_release_gate_hardened_review_only"] is True
    assert summary["docker_compatibility_valid_review_only"] is True
    assert summary["launcher_compatibility_valid_review_only"] is True
    assert registry["live_scaled_execution_enabled"] is False
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True


def test_p18_blocks_missing_p17_blocked_p17_bad_docker_bad_launcher_missing_command_and_unsafe_flags(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_full_regression_ci_release_gate_report(root=tmp_path, p17_summary={}, p17_report=_p17_report())
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P18_SOURCE_P17_SUMMARY_MISSING" in report["block_reasons"]

    report = build_full_regression_ci_release_gate_report(root=tmp_path, p17_summary={**_p17_summary(), "status": "P17_RUNTIME_RELEASE_GATE_OPERATOR_HANDOFF_BLOCKED_FAIL_CLOSED"}, p17_report=_p17_report())
    assert "P18_SOURCE_P17_RELEASE_GATE_BLOCKED" in report["block_reasons"]

    report = build_full_regression_ci_release_gate_report(root=tmp_path, p17_summary=_p17_summary(), p17_report=_p17_report(), docker_check={"docker_compatibility_valid_review_only": False})
    assert "P18_DOCKER_COMPATIBILITY_CHECK_FAILED" in report["block_reasons"]

    report = build_full_regression_ci_release_gate_report(root=tmp_path, p17_summary=_p17_summary(), p17_report=_p17_report(), launcher_check={"launcher_compatibility_valid_review_only": False})
    assert "P18_LAUNCHER_COMPATIBILITY_CHECK_FAILED" in report["block_reasons"]

    plan = [item for item in build_p18_command_plan() if item["command_id"] != "docker_build"]
    report = build_full_regression_ci_release_gate_report(root=tmp_path, p17_summary=_p17_summary(), p17_report=_p17_report(), command_plan=plan)
    assert "P18_REQUIRED_CI_COMMAND_MISSING" in report["block_reasons"]

    report = build_full_regression_ci_release_gate_report(root=tmp_path, p17_summary={**_p17_summary(), "live_scaled_execution_enabled": True}, p17_report=_p17_report())
    assert "P18_UNSAFE_TRUTHY_FLAG_FOUND" in report["block_reasons"]


def test_p18_negative_fixture_results_all_block_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    results = build_p18_negative_fixture_results(root=tmp_path)

    assert results["all_negative_fixtures_blocked_fail_closed"] is True
    assert set(results["fixture_results"]) == {
        "missing_p17_summary",
        "p17_blocked",
        "docker_compatibility_failed",
        "launcher_compatibility_failed",
        "missing_ci_command",
        "unsafe_runtime_flag",
    }
    for result in results["fixture_results"].values():
        assert result["blocked"] is True
        assert result["limited_live_scaled_auto_trading_allowed"] is False
        assert result["live_scaled_execution_enabled"] is False
        assert result["live_order_submission_allowed"] is False
        assert result["runtime_scheduler_enabled"] is False
        assert result["secret_value_accessed"] is False
