from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.validation.phase9_2_public_metadata_probe_result_filled_validation import (
    _disabled_payload,
    build_operator_filled_result_skeleton,
    build_phase9_2_public_metadata_probe_result_filled_validation_report,
    validate_operator_filled_probe_result,
)
from crypto_ai_system.validation.phase9_2_public_metadata_network_dry_probe_result_intake import build_public_metadata_probe_result_template


def _hex(ch: str = "a") -> str:
    return ch * 64


def _template() -> dict:
    source = {
        "status": "PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_RECORDED_NO_ORDER_SUBMIT_REVIEW_ONLY",
        "blocked": False,
        "fail_closed": False,
        "network_dry_probe_ready_for_operator_no_order_command": True,
        "public_metadata_network_probe_performed": False,
        **_disabled_payload(),
    }
    return build_public_metadata_probe_result_template(source, created_at_utc="2026-01-01T00:00:00Z")


def _valid_payload() -> dict:
    template = _template()
    payload = build_operator_filled_result_skeleton(template, created_at_utc="2026-01-01T00:00:00Z")
    result = dict(payload["operator_supplied_result"])
    result["exchange_time_result"] = {**result["exchange_time_result"], "latency_ms": 12, "redacted_response_sha256": _hex("a")}
    result["exchange_info_result"] = {**result["exchange_info_result"], "latency_ms": 20, "redacted_response_sha256": _hex("b")}
    result["symbol_info_result"] = {**result["symbol_info_result"], "latency_ms": 18, "redacted_response_sha256": _hex("c")}
    result["source_probe_command_id"] = "PUBLIC-METADATA-PROBE-001"
    payload["operator_supplied_result"] = result
    return payload


def test_valid_operator_filled_probe_result_sets_metadata_ready_but_not_submit():
    template = _template()
    payload = _valid_payload()
    validation = validate_operator_filled_probe_result(payload, source_template=template)
    assert validation["blocked"] is False
    assert validation["operator_filled_public_metadata_probe_result_validated"] is True
    assert validation["real_testnet_metadata_conditions_ready_for_submit_review_only"] is True
    assert validation["real_testnet_submit_may_begin"] is False
    assert validation["actual_order_submission_performed"] is False
    assert validation["order_endpoint_called"] is False
    assert validation["signature_created"] is False


def test_blocks_order_or_private_endpoint_fields():
    payload = _valid_payload()
    payload["operator_supplied_result"]["order_endpoint_called"] = True
    validation = validate_operator_filled_probe_result(payload, source_template=_template())
    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    assert any("ORDER" in reason or "UNSAFE" in reason for reason in validation["block_reasons"])


def test_blocks_bad_redacted_hash():
    payload = _valid_payload()
    payload["operator_supplied_result"]["exchange_info_result"]["redacted_response_sha256"] = "not-a-hash"
    validation = validate_operator_filled_probe_result(payload, source_template=_template())
    assert validation["blocked"] is True
    assert any("64_HEX" in reason for reason in validation["block_reasons"])


def test_report_awaits_filled_file_without_blocking_when_sources_ready(tmp_path, monkeypatch):
    root = tmp_path
    latest = root / "storage" / "latest"
    latest.mkdir(parents=True)
    source_intake = {
        "status": "PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_RECORDED_NO_ORDER_SUBMIT_REVIEW_ONLY",
        "blocked": False,
        "fail_closed": False,
        "public_metadata_network_probe_result_intake_ready": True,
        "real_testnet_submit_may_begin": False,
    }
    atomic_write_json(latest / "phase9_2_public_metadata_network_dry_probe_result_intake_report.json", source_intake)
    atomic_write_json(latest / "phase9_2_public_metadata_network_dry_probe_RESULT_TEMPLATE_NO_ORDER_SUBMIT_REVIEW_ONLY.json", _template())

    from crypto_ai_system.config import AppConfig
    cfg = AppConfig(root=root, settings={"storage": {"latest_dir": "storage/latest"}})
    report, skeleton, validation = build_phase9_2_public_metadata_probe_result_filled_validation_report(cfg=cfg, created_at_utc="2026-01-01T00:00:00Z")
    assert report["blocked"] is False
    assert report["waiting_for_operator_filled_result"] is True
    assert report["operator_filled_public_metadata_probe_result_validated"] is False
    assert report["real_testnet_submit_may_begin"] is False
    assert skeleton["no_order_submit"] is True


def test_blocks_sample_or_synthetic_operator_filled_probe_result():
    payload = _valid_payload()
    payload["sample_only"] = True
    payload["synthetic"] = True
    payload["operator_supplied_result"]["source_probe_command_id"] = "SAMPLE-PUBLIC-METADATA-PROBE"
    validation = validate_operator_filled_probe_result(payload, source_template=_template())
    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    assert validation["operator_filled_public_metadata_probe_result_validated"] is False
    assert validation["real_testnet_metadata_conditions_ready_for_submit_review_only"] is False
    assert validation["real_testnet_submit_may_begin"] is False
    assert any("SAMPLE_SYNTHETIC" in reason for reason in validation["block_reasons"])
