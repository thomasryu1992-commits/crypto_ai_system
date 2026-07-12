from __future__ import annotations

from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_runtime_activation_request_template_gate import (
    P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_EXACT_PHRASE,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_operator_runtime_activation_request_template,
    build_operator_runtime_activation_request_template_gate_report,
    build_p26_negative_fixture_results,
    persist_operator_runtime_activation_request_template_gate,
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


def _p25_summary() -> dict:
    return {
        "status": "P25_FINAL_RUNTIME_ENABLEMENT_BOUNDARY_REVIEW_PACKET_READY_REVIEW_ONLY",
        "p25_final_runtime_enablement_boundary_review_packet_report_sha256": "a" * 64,
        "p25_final_runtime_enablement_boundary_review_packet_valid_review_only": True,
        "p25_final_runtime_enablement_boundary_review_packet_ready_review_only": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p25_report() -> dict:
    return {
        "status": "P25_FINAL_RUNTIME_ENABLEMENT_BOUNDARY_REVIEW_PACKET_READY_REVIEW_ONLY",
        "p25_final_runtime_enablement_boundary_review_packet_valid_review_only": True,
        "final_review_packet_is_runtime_authority": False,
        "separate_operator_runtime_activation_required_after_this_packet": True,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p25_packet() -> dict:
    return {
        "packet_type": "final_runtime_enablement_boundary_review_packet_review_only",
        "p25_final_runtime_enablement_boundary_review_packet_sha256": "b" * 64,
        "packet_is_runtime_authority": False,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
    }


def test_p26_waits_when_p25_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_runtime_activation_request_template_gate_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert "P26_SOURCE_P25_SUMMARY_MISSING" in report["waiting_reasons"]
    assert "P26_SOURCE_P25_REPORT_MISSING" in report["waiting_reasons"]
    assert report["live_scaled_execution_enabled"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p26_generates_template_and_skeleton_when_p25_valid_review_only(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_runtime_activation_request_template_gate_report(
        root=tmp_path,
        p25_summary=_p25_summary(),
        p25_report=_p25_report(),
        p25_packet=_p25_packet(),
    )
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["p26_operator_runtime_activation_request_template_generated_review_only"] is True
    assert report["p26_final_activation_gate_skeleton_generated_review_only"] is True
    assert report["activation_request_template_is_runtime_authority"] is False
    assert report["final_activation_gate_skeleton_is_runtime_authority"] is False
    assert report["separate_filled_operator_activation_request_required_after_this_template"] is True
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["runtime_enablement_performed"] is False
    assert report["secret_value_accessed"] is False
    template = report["operator_runtime_activation_request_template"]
    assert template["exact_operator_runtime_activation_request_phrase"] == P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_EXACT_PHRASE
    assert template["request_is_runtime_authority"] is False
    skeleton = report["final_activation_gate_skeleton"]
    assert skeleton["activation_gate_is_runtime_authority"] is False
    assert skeleton["gate_controls"]["hot_path_preorder_risk_gate_required"] is True


def test_p26_persists_summary_template_skeleton_registry_and_negative_results(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    from core.json_io import atomic_write_json

    atomic_write_json(latest / "p25_final_runtime_enablement_boundary_review_packet_summary.json", _p25_summary())
    atomic_write_json(latest / "p25_final_runtime_enablement_boundary_review_packet_report.json", _p25_report())
    atomic_write_json(latest / "p25_final_runtime_enablement_boundary_review_packet.json", _p25_packet())
    report = persist_operator_runtime_activation_request_template_gate(load_config(tmp_path))
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert (latest / "p26_operator_runtime_activation_request_template_gate_report.json").exists()
    assert (latest / "p26_operator_runtime_activation_request_template_gate_summary.json").exists()
    assert (latest / "p26_operator_runtime_activation_request_TEMPLATE.json").exists()
    assert (latest / "p26_final_activation_gate_skeleton.json").exists()
    assert (latest / "p26_operator_runtime_activation_request_template_gate_negative_fixture_results.json").exists()
    assert (latest / "p26_operator_runtime_activation_request_template_gate_registry_record.json").exists()
    summary = read_json(latest / "p26_operator_runtime_activation_request_template_gate_summary.json")
    template = read_json(latest / "p26_operator_runtime_activation_request_TEMPLATE.json")
    skeleton = read_json(latest / "p26_final_activation_gate_skeleton.json")
    negative = read_json(latest / "p26_operator_runtime_activation_request_template_gate_negative_fixture_results.json")
    registry = read_json(latest / "p26_operator_runtime_activation_request_template_gate_registry_record.json")
    assert summary["p26_operator_runtime_activation_gate_ready_review_only"] is True
    assert template["request_executes_runtime"] is False
    assert skeleton["activation_gate_executes_runtime"] is False
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert registry["live_scaled_execution_enabled"] is False


def test_p26_blocks_runtime_authority_scheduler_endpoint_and_secret_pattern(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    authority = build_operator_runtime_activation_request_template_gate_report(
        root=tmp_path,
        p25_summary=_p25_summary(),
        p25_report={**_p25_report(), "final_review_packet_is_runtime_authority": True},
        p25_packet=_p25_packet(),
    )
    assert authority["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P26_SOURCE_P25_RUNTIME_AUTHORITY_CLAIMED" in authority["block_reasons"]

    scheduler = build_operator_runtime_activation_request_template_gate_report(
        root=tmp_path,
        p25_summary={**_p25_summary(), "runtime_scheduler_enabled": True},
        p25_report=_p25_report(),
        p25_packet=_p25_packet(),
    )
    assert scheduler["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P26_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND_IN_SOURCE" in scheduler["block_reasons"]

    endpoint = build_operator_runtime_activation_request_template_gate_report(
        root=tmp_path,
        p25_summary=_p25_summary(),
        p25_report={**_p25_report(), "order_endpoint_called": True},
        p25_packet=_p25_packet(),
    )
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P26_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND_IN_SOURCE" in endpoint["block_reasons"]

    secret = build_operator_runtime_activation_request_template_gate_report(
        root=tmp_path,
        p25_summary=_p25_summary(),
        p25_report={**_p25_report(), "diagnostic": "BINANCE_API_SECRET=leak"},
        p25_packet=_p25_packet(),
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P26_SECRET_VALUE_PATTERN_FOUND_IN_SOURCE" in secret["block_reasons"]


def test_p26_template_is_not_runtime_authority() -> None:
    template = build_operator_runtime_activation_request_template()
    assert template["request_is_runtime_authority"] is False
    assert template["request_executes_runtime"] is False
    assert template["live_scaled_execution_enabled"] is False
    assert template["runtime_scheduler_enabled"] is False
    assert template["secret_value_accessed"] is False
    assert template["acknowledgements"]["no_endpoint_call_allowed_by_this_template_acknowledged"] is True


def test_p26_negative_fixtures_fail_closed() -> None:
    results = build_p26_negative_fixture_results()
    assert results["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert results["live_scaled_execution_enabled"] is False
    assert results["runtime_scheduler_enabled"] is False
    assert results["secret_value_accessed"] is False
