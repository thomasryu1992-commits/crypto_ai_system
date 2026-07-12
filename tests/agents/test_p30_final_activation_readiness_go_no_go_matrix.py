from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.final_activation_readiness_go_no_go_matrix import (
    OPERATOR_DECISION_GO_REVIEW_ONLY,
    OPERATOR_DECISION_NO_GO,
    OPERATOR_DECISION_WAITING,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY,
    build_final_activation_readiness_go_no_go_matrix_report,
    build_p30_negative_fixture_results,
    persist_final_activation_readiness_go_no_go_matrix,
)


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )


def _valid_phase_summaries() -> dict[str, dict]:
    return {
        f"P{idx}": {
            "status": f"P{idx}_VALID_REVIEW_ONLY",
            "phase": f"P{idx}",
            "limited_live_scaled_auto_trading_allowed": False,
            "live_scaled_execution_enabled": False,
            "runtime_scheduler_enabled": False,
            "live_order_submission_allowed": False,
            "order_endpoint_called": False,
            "secret_value_accessed": False,
        }
        for idx in range(30)
    }


def test_p30_generates_waiting_matrix_when_phase_summaries_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_final_activation_readiness_go_no_go_matrix_report(root=tmp_path)
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["operator_final_activation_decision"] == OPERATOR_DECISION_WAITING
    assert report["required_phase_count"] == 30
    assert report["present_phase_count"] == 0
    assert report["waiting_phase_count"] == 30
    assert report["final_activation_execution_allowed_by_this_matrix"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p30_generates_go_review_only_when_all_phase_summaries_valid(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_final_activation_readiness_go_no_go_matrix_report(root=tmp_path, phase_summaries=_valid_phase_summaries())
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["operator_final_activation_decision"] == OPERATOR_DECISION_GO_REVIEW_ONLY
    assert report["final_activation_go_review_only"] is True
    assert report["final_activation_go_runtime_authority"] is False
    assert report["final_activation_execution_allowed_by_this_matrix"] is False
    assert report["go_review_only_phase_count"] == 30
    assert report["waiting_phase_count"] == 0
    assert report["no_go_phase_count"] == 0
    assert len(report["go_no_go_matrix"]) == 30
    assert report["live_order_submission_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False


def test_p30_blocks_unsafe_flags_endpoint_and_secret_patterns(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    valid = _valid_phase_summaries()
    unsafe = {**valid, "P15": {**valid["P15"], "live_scaled_execution_enabled": True}}
    unsafe_report = build_final_activation_readiness_go_no_go_matrix_report(root=tmp_path, phase_summaries=unsafe)
    assert unsafe_report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert unsafe_report["operator_final_activation_decision"] == OPERATOR_DECISION_NO_GO
    assert "P30_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND" in unsafe_report["block_reasons"]

    endpoint = {**valid, "P29": {**valid["P29"], "order_endpoint_called": True}}
    endpoint_report = build_final_activation_readiness_go_no_go_matrix_report(root=tmp_path, phase_summaries=endpoint)
    assert endpoint_report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P30_ENDPOINT_CALL_EVIDENCE_FOUND" in endpoint_report["block_reasons"]

    secret = {**valid, "P22": {**valid["P22"], "operator_note": "BINANCE_API_SECRET=leaked"}}
    secret_report = build_final_activation_readiness_go_no_go_matrix_report(root=tmp_path, phase_summaries=secret)
    assert secret_report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P30_SECRET_VALUE_PATTERN_FOUND" in secret_report["block_reasons"]


def test_p30_records_waiting_and_blocked_phase_rows(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    valid = _valid_phase_summaries()
    waiting = {**valid, "P29": {**valid["P29"], "status": "P29_WAITING_REVIEW_ONLY"}}
    waiting_report = build_final_activation_readiness_go_no_go_matrix_report(root=tmp_path, phase_summaries=waiting)
    assert waiting_report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert waiting_report["operator_final_activation_decision"] == OPERATOR_DECISION_WAITING
    assert waiting_report["waiting_phases"] == ["P29"]

    blocked = {**valid, "P21": {**valid["P21"], "status": "P21_BLOCKED_FAIL_CLOSED"}}
    blocked_report = build_final_activation_readiness_go_no_go_matrix_report(root=tmp_path, phase_summaries=blocked)
    assert blocked_report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert blocked_report["operator_final_activation_decision"] == OPERATOR_DECISION_NO_GO
    assert "P21" in blocked_report["no_go_phases"]


def test_p30_persists_report_summary_matrix_registry_and_negative_results(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    filename_by_phase = {
        0: "p0_baseline_hygiene_completion_summary.json",
        1: "p1_live_candidate_data_foundation_summary.json",
        2: "p2_paper_operation_validation_summary.json",
        3: "p3_candidate_manual_approval_chain_summary.json",
        4: "p4_signed_testnet_one_order_runtime_package_summary.json",
        5: "p5_action_time_submit_approval_boundary_summary.json",
        6: "p6_single_signed_testnet_submit_runtime_action_summary.json",
        7: "p7_post_submit_evidence_intake_summary.json",
        8: "p8_repeated_clean_signed_testnet_sessions_summary.json",
        9: "p9_live_read_only_canary_preparation_summary.json",
        10: "p10_live_canary_one_order_execution_boundary_summary.json",
        11: "p11_live_canary_post_submit_evidence_review_summary.json",
        12: "p12_repeated_clean_live_canary_sessions_summary.json",
        13: "p13_live_scaled_readiness_review_summary.json",
        14: "p14_live_scaled_approval_intake_validation_summary.json",
        15: "p15_limited_live_scaled_runtime_enablement_boundary_summary.json",
        16: "p16_limited_live_scaled_loop_dry_run_harness_summary.json",
        17: "p17_runtime_release_gate_operator_handoff_summary.json",
        18: "p18_full_regression_ci_release_gate_summary.json",
        19: "p19_docker_launcher_evidence_intake_summary.json",
        20: "p20_external_evidence_template_export_pack_summary.json",
        21: "p21_ci_filled_evidence_release_candidate_bundle_summary.json",
        22: "p22_operator_release_candidate_acceptance_review_summary.json",
        23: "p23_operator_accepted_release_candidate_handoff_summary.json",
        24: "p24_runtime_enablement_request_intake_validator_summary.json",
        25: "p25_final_runtime_enablement_boundary_review_packet_summary.json",
        26: "p26_operator_runtime_activation_request_template_gate_summary.json",
        27: "p27_operator_runtime_activation_request_intake_validator_summary.json",
        28: "p28_final_operator_runtime_activation_gate_review_summary.json",
        29: "p29_final_runtime_activation_dry_run_evidence_bundle_summary.json",
    }
    for idx, filename in filename_by_phase.items():
        atomic_write_json(latest / filename, _valid_phase_summaries()[f"P{idx}"])
    report = persist_final_activation_readiness_go_no_go_matrix(load_config(tmp_path))
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert (latest / "p30_final_activation_readiness_go_no_go_matrix_report.json").exists()
    assert (latest / "p30_final_activation_readiness_go_no_go_matrix_summary.json").exists()
    assert (latest / "p30_final_activation_readiness_go_no_go_matrix.json").exists()
    assert (latest / "p30_final_activation_readiness_go_no_go_matrix_negative_fixture_results.json").exists()
    assert (latest / "p30_final_activation_readiness_go_no_go_matrix_registry_record.json").exists()
    summary = read_json(latest / "p30_final_activation_readiness_go_no_go_matrix_summary.json")
    matrix = read_json(latest / "p30_final_activation_readiness_go_no_go_matrix.json")
    negative = read_json(latest / "p30_final_activation_readiness_go_no_go_matrix_negative_fixture_results.json")
    assert summary["operator_decision_matrix_generated_review_only"] is True
    assert summary["final_activation_execution_allowed_by_this_matrix"] is False
    assert len(matrix) == 30
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True


def test_p30_negative_fixture_results_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    negative = build_p30_negative_fixture_results(root=tmp_path)
    assert negative["status"] == "P30_NEGATIVE_FIXTURES_RECORDED"
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_results"]["unsafe_live_scaled_enabled"]["blocked"] is True
    assert negative["fixture_results"]["endpoint_call_evidence_found"]["blocked"] is True
    assert negative["fixture_results"]["secret_pattern_found"]["blocked"] is True
