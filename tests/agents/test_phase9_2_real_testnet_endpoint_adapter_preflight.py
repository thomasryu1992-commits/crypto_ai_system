from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_real_testnet_endpoint_adapter_preflight import (
    STATUS_PREFLIGHT_RECORDED,
    build_negative_fixture_results,
    build_phase9_2_real_testnet_endpoint_adapter_preflight_report,
    build_preflight_template,
    persist_phase9_2_real_testnet_endpoint_adapter_preflight,
    validate_preflight_payload,
)


def _write_mock_flow_source() -> None:
    latest = Path("storage/latest")
    latest.mkdir(parents=True, exist_ok=True)
    payload = {
        "artifact_type": "phase9_2_mock_submit_evidence_flow_report",
        "status": "PHASE9_2_MOCK_SUBMIT_TO_EVIDENCE_FLOW_RECORDED_REVIEW_ONLY",
        "blocked": False,
        "fail_closed": False,
        "review_only": True,
        "mock_evidence_only": True,
        "mock_flow_ready_for_review_only_evidence_intake": True,
        "actual_order_submission_performed": False,
        "real_exchange_endpoint_call_performed": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
    }
    (latest / "phase9_2_mock_submit_evidence_flow_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def test_real_testnet_endpoint_adapter_preflight_builds_no_submit_packet() -> None:
    _write_mock_flow_source()
    cfg = load_config()
    report, template = build_phase9_2_real_testnet_endpoint_adapter_preflight_report(cfg=cfg)

    assert report["status"] == STATUS_PREFLIGHT_RECORDED
    assert report["blocked"] is False
    assert report["preflight_ready_for_manual_review_only"] is True
    assert report["real_testnet_submit_may_begin"] is False
    assert report["real_testnet_endpoint_adapter_attached"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert template["no_submit"] is True
    assert template["network_calls_allowed"] is False
    assert template["order_endpoint_calls_allowed"] is False
    assert template["adapter_interface"]["environment"] == "testnet"


def test_real_testnet_endpoint_adapter_preflight_blocks_missing_or_unsafe_source() -> None:
    latest = Path("storage/latest")
    latest.mkdir(parents=True, exist_ok=True)
    (latest / "phase9_2_mock_submit_evidence_flow_report.json").write_text(json.dumps({
        "mock_flow_ready_for_review_only_evidence_intake": True,
        "actual_order_submission_performed": True,
        "real_exchange_endpoint_call_performed": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
    }), encoding="utf-8")
    cfg = load_config()
    report, template = build_phase9_2_real_testnet_endpoint_adapter_preflight_report(cfg=cfg)

    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert template == {}
    assert any("actual_order_submission_performed" in reason for reason in report["block_reasons"])
    assert report["real_testnet_submit_may_begin"] is False


def test_real_testnet_endpoint_adapter_preflight_validator_blocks_runtime_or_secret_values() -> None:
    payload = build_preflight_template({}, created_at_utc="2026-01-01T00:00:00Z")
    payload["order_endpoint_calls_allowed"] = True
    payload["actual_order_submission_performed"] = True
    payload["api_secret"] = "SHOULD_NOT_BE_HERE"
    payload["adapter_interface"]["environment"] = "mainnet"

    validation = validate_preflight_payload(payload)

    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    assert "actual_order_submission_performed" in validation["unsafe_true_fields"]
    assert validation["secret_like_values_detected"] is True
    assert any("LIVE_OR_MAINNET" in reason for reason in validation["block_reasons"])


def test_real_testnet_endpoint_adapter_preflight_persists_outputs_and_negative_fixtures() -> None:
    _write_mock_flow_source()
    report = persist_phase9_2_real_testnet_endpoint_adapter_preflight()
    negative = build_negative_fixture_results()

    assert report["preflight_ready_for_manual_review_only"] is True
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert Path("storage/latest/phase9_2_real_testnet_endpoint_adapter_preflight_report.json").exists()
    assert Path("storage/latest/phase9_2_real_testnet_endpoint_adapter_PREFLIGHT_TEMPLATE_NO_SUBMIT_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_2_real_testnet_endpoint_adapter_preflight_validation_report.json").exists()
    assert Path("storage/latest/phase9_2_real_testnet_endpoint_adapter_preflight_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE9_2_REAL_TESTNET_ENDPOINT_ADAPTER_PREFLIGHT_HANDOFF_NO_SUBMIT_REVIEW_ONLY.md").exists()
    assert Path("storage/latest/phase9_2_real_testnet_endpoint_adapter_preflight_registry_record.json").exists()
