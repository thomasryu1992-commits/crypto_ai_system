from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.runtime_release_gate_operator_handoff import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY,
    build_latest_status_matrix,
    build_p17_negative_fixture_results,
    build_runtime_release_gate_operator_handoff_report,
    persist_runtime_release_gate_operator_handoff,
)

_REQUIRED_FILES = [
    "p0_baseline_hygiene_completion_summary.json",
    "p1_live_candidate_data_foundation_summary.json",
    "p2_paper_operation_validation_summary.json",
    "p3_candidate_manual_approval_chain_summary.json",
    "p4_signed_testnet_one_order_runtime_package_summary.json",
    "p5_action_time_submit_approval_boundary_summary.json",
    "p6_single_signed_testnet_submit_runtime_action_summary.json",
    "p7_post_submit_evidence_intake_summary.json",
    "p8_repeated_clean_signed_testnet_sessions_summary.json",
    "p9_live_read_only_canary_preparation_summary.json",
    "p10_live_canary_one_order_execution_boundary_summary.json",
    "p11_live_canary_post_submit_evidence_review_summary.json",
    "p12_repeated_clean_live_canary_sessions_summary.json",
    "p13_live_scaled_readiness_review_summary.json",
    "p14_live_scaled_approval_intake_validation_summary.json",
    "p15_limited_live_scaled_runtime_enablement_boundary_summary.json",
    "p16_limited_live_scaled_loop_dry_run_harness_summary.json",
]


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text("[project]\nname='tmp-crypto-ai-system'\nversion='0.286.0'\n", encoding="utf-8")


def _valid_payloads() -> dict[str, dict]:
    payloads: dict[str, dict] = {}
    for idx, filename in enumerate(_REQUIRED_FILES):
        phase = f"P{idx}"
        payloads[filename] = {
            "status": f"{phase}_REVIEW_ONLY_FIXTURE",
            "review_only": True,
            "waiting": filename.startswith("p16_") or filename.startswith("p15_"),
            "blocked": False,
            "live_scaled_execution_enabled": False,
            "live_order_submission_allowed": False,
            "runtime_scheduler_enabled": False,
            "actual_live_order_submitted": False,
            "live_order_endpoint_called": False,
            "http_request_sent": False,
            "secret_value_accessed": False,
            "secret_value_logged": False,
        }
    return payloads


def test_p17_builds_status_matrix_for_all_required_artifacts() -> None:
    matrix = build_latest_status_matrix(latest_payloads=_valid_payloads())

    assert len(matrix) == len(_REQUIRED_FILES)
    assert matrix[0]["phase_id"] == "P0"
    assert matrix[-1]["phase_id"] == "P16"
    assert all(row["artifact_present"] for row in matrix)
    assert any(row["waiting"] for row in matrix)
    assert all(row["live_scaled_execution_enabled"] is False for row in matrix)


def test_p17_generates_review_only_operator_handoff_report() -> None:
    report = build_runtime_release_gate_operator_handoff_report(latest_payloads=_valid_payloads())

    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["p17_runtime_release_gate_operator_handoff_valid_review_only"] is True
    assert report["p17_operator_handoff_pack_created"] is True
    assert report["present_phase_artifact_count"] == len(_REQUIRED_FILES)
    assert report["missing_required_phase_artifacts"] == []
    assert report["unsafe_truthy_execution_flag_hits"] == []
    assert report["endpoint_call_evidence_hits"] == []
    assert report["secret_value_scan_hits"] == []
    assert report["operator_release_decision"]["live_scaled_runtime_ready"] is False
    assert report["limited_live_scaled_auto_trading_allowed"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False
    assert report["one_command_release_gate_command"] == "PYTHONPATH=src:. python scripts/run_release_gate.py"


def test_p17_persists_latest_report_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    for filename, payload in _valid_payloads().items():
        atomic_write_json(latest / filename, payload)
    cfg = load_config(tmp_path)

    report = persist_runtime_release_gate_operator_handoff(cfg=cfg)

    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    saved = read_json(latest / "p17_runtime_release_gate_operator_handoff_report.json")
    summary = read_json(latest / "p17_runtime_release_gate_operator_handoff_summary.json")
    registry = read_json(latest / "p17_runtime_release_gate_operator_handoff_registry_record.json")
    negative = read_json(latest / "p17_runtime_release_gate_operator_handoff_negative_fixture_results.json")
    assert saved["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert summary["p17_operator_handoff_pack_created"] is True
    assert summary["limited_live_scaled_auto_trading_allowed"] is False
    assert registry["live_scaled_execution_enabled"] is False
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True


def test_p17_blocks_missing_artifact_unsafe_endpoint_secret_scheduler_and_runtime_flags() -> None:
    payloads = _valid_payloads()
    payloads.pop("p16_limited_live_scaled_loop_dry_run_harness_summary.json")
    report = build_runtime_release_gate_operator_handoff_report(latest_payloads=payloads)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P17_REQUIRED_PHASE_ARTIFACT_MISSING" in report["block_reasons"]

    payloads = _valid_payloads()
    payloads["p16_limited_live_scaled_loop_dry_run_harness_summary.json"]["live_scaled_execution_enabled"] = True
    report = build_runtime_release_gate_operator_handoff_report(latest_payloads=payloads)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P17_UNSAFE_TRUTHY_FLAG_FOUND" in report["block_reasons"]

    payloads = _valid_payloads()
    payloads["p15_limited_live_scaled_runtime_enablement_boundary_summary.json"]["http_request_sent"] = True
    report = build_runtime_release_gate_operator_handoff_report(latest_payloads=payloads)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P17_ENDPOINT_CALL_EVIDENCE_FOUND" in report["block_reasons"]

    payloads = _valid_payloads()
    payloads["p14_live_scaled_approval_intake_validation_summary.json"]["operator_note"] = "sk-thisIsAFakeSecretPatternForScannerOnly123456"
    report = build_runtime_release_gate_operator_handoff_report(latest_payloads=payloads)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P17_SECRET_VALUE_PATTERN_FOUND" in report["block_reasons"]

    payloads = _valid_payloads()
    payloads["p16_limited_live_scaled_loop_dry_run_harness_summary.json"]["runtime_scheduler_enabled"] = True
    report = build_runtime_release_gate_operator_handoff_report(latest_payloads=payloads)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P17_UNSAFE_TRUTHY_FLAG_FOUND" in report["block_reasons"]


def test_p17_negative_fixture_results_all_block_fail_closed() -> None:
    results = build_p17_negative_fixture_results()

    assert results["all_negative_fixtures_blocked_fail_closed"] is True
    assert set(results["fixture_results"]) == {
        "missing_required_artifact",
        "unsafe_live_scaled_enabled",
        "endpoint_call_evidence_found",
        "secret_pattern_found",
        "runtime_scheduler_enabled",
    }
    for result in results["fixture_results"].values():
        assert result["blocked"] is True
        assert result["limited_live_scaled_auto_trading_allowed"] is False
        assert result["live_scaled_execution_enabled"] is False
        assert result["live_order_submission_allowed"] is False
        assert result["secret_value_accessed"] is False
