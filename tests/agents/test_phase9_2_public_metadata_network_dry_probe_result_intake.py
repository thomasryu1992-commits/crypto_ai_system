from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_public_metadata_network_dry_probe_result_intake import (
    STATUS_RECORDED,
    build_negative_fixture_results,
    build_phase9_2_public_metadata_network_dry_probe_result_intake_report,
    build_public_metadata_probe_result_template,
    persist_phase9_2_public_metadata_network_dry_probe_result_intake,
    validate_public_metadata_probe_result_payload,
)


def _write_dry_probe_source() -> None:
    latest = Path("storage/latest")
    latest.mkdir(parents=True, exist_ok=True)
    payload = {
        "artifact_type": "phase9_2_real_testnet_network_dry_probe_report",
        "status": "PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_RECORDED_NO_ORDER_SUBMIT_REVIEW_ONLY",
        "blocked": False,
        "fail_closed": False,
        "review_only": True,
        "no_order_submit": True,
        "network_dry_probe_ready_for_operator_no_order_command": True,
        "public_metadata_network_probe_performed": False,
        "real_testnet_submit_may_begin": False,
        "actual_order_submission_performed": False,
        "real_exchange_endpoint_call_performed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "private_account_endpoint_called": False,
        "balance_endpoint_called": False,
        "position_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
    }
    (latest / "phase9_2_real_testnet_network_dry_probe_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def test_public_metadata_result_intake_builds_no_order_template() -> None:
    _write_dry_probe_source()
    cfg = load_config()
    report, template = build_phase9_2_public_metadata_network_dry_probe_result_intake_report(cfg=cfg)

    assert report["status"] == STATUS_RECORDED
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["public_metadata_network_probe_result_intake_ready"] is True
    assert report["public_metadata_network_probe_result_validated"] is False
    assert report["real_testnet_submit_may_begin"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert template["no_order_submit"] is True
    assert template["operator_supplied_result_placeholder"]["environment"] == "testnet"
    assert template["operator_supplied_result_placeholder"]["order_submit_attempted"] is False


def test_public_metadata_result_intake_blocks_unsafe_dry_probe_source() -> None:
    latest = Path("storage/latest")
    latest.mkdir(parents=True, exist_ok=True)
    (latest / "phase9_2_real_testnet_network_dry_probe_report.json").write_text(json.dumps({
        "network_dry_probe_ready_for_operator_no_order_command": True,
        "public_metadata_network_probe_performed": False,
        "real_testnet_submit_may_begin": False,
        "actual_order_submission_performed": False,
        "real_exchange_endpoint_call_performed": False,
        "order_endpoint_called": True,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "private_account_endpoint_called": False,
        "balance_endpoint_called": False,
        "position_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
    }), encoding="utf-8")
    cfg = load_config()
    report, template = build_phase9_2_public_metadata_network_dry_probe_result_intake_report(cfg=cfg)

    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert template == {}
    assert any("order_endpoint_called" in reason for reason in report["block_reasons"])
    assert report["real_testnet_submit_may_begin"] is False


def test_public_metadata_result_validator_blocks_order_private_or_secret_results() -> None:
    payload = build_public_metadata_probe_result_template({}, created_at_utc="2026-01-01T00:00:00Z")
    payload["operator_supplied_result"] = {
        **payload["operator_supplied_result_placeholder"],
        "environment": "mainnet",
        "order_submit_attempted": True,
        "order_endpoint_called": True,
        "private_account_endpoint_called": True,
        "requires_signature": True,
        "api_secret_value_logged": True,
    }
    payload["api_secret"] = "SHOULD_NOT_BE_HERE"

    validation = validate_public_metadata_probe_result_payload(payload)

    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    assert validation["secret_like_values_detected"] is True
    assert any("LIVE_OR_MAINNET" in reason for reason in validation["block_reasons"])
    assert any("UNSAFE_RESULT_FIELD:order_endpoint_called" in reason for reason in validation["block_reasons"])


def test_public_metadata_result_validator_blocks_missing_symbol_rules() -> None:
    payload = build_public_metadata_probe_result_template({}, created_at_utc="2026-01-01T00:00:00Z")
    result = {**payload["operator_supplied_result_placeholder"]}
    result["symbol_info_result"] = {
        "reachable": True,
        "http_status_code": 200,
        "latency_ms": 10,
        "symbol_present": True,
        "min_notional_present": False,
        "price_tick_present": True,
        "quantity_step_present": True,
    }
    payload["operator_supplied_result"] = result
    validation = validate_public_metadata_probe_result_payload(payload)

    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    assert any("min_notional_present" in reason for reason in validation["block_reasons"])


def test_public_metadata_result_intake_persists_outputs_and_negative_fixtures() -> None:
    _write_dry_probe_source()
    report = persist_phase9_2_public_metadata_network_dry_probe_result_intake()
    negative = build_negative_fixture_results()

    assert report["public_metadata_network_probe_result_intake_ready"] is True
    assert report["public_metadata_network_probe_result_validated"] is False
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert Path("storage/latest/phase9_2_public_metadata_network_dry_probe_result_intake_report.json").exists()
    assert Path("storage/latest/phase9_2_public_metadata_network_dry_probe_RESULT_TEMPLATE_NO_ORDER_SUBMIT_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_2_public_metadata_network_dry_probe_result_intake_validation_report.json").exists()
    assert Path("storage/latest/phase9_2_public_metadata_network_dry_probe_result_intake_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_HANDOFF_NO_ORDER_SUBMIT_REVIEW_ONLY.md").exists()
    assert Path("storage/latest/phase9_2_public_metadata_network_dry_probe_result_intake_registry_record.json").exists()
