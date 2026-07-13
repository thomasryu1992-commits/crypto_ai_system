from __future__ import annotations

from core.json_io import atomic_write_json
from crypto_ai_system.config import AppConfig
from crypto_ai_system.validation.phase9_2_real_public_metadata_probe_command import (
    _disabled_payload,
    build_phase9_2_real_public_metadata_probe_command_report,
    build_public_metadata_probe_command_template,
    run_public_metadata_probe,
    validate_public_metadata_probe_command_template,
)


def _dry_probe() -> dict:
    return {
        "status": "PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_RECORDED_NO_ORDER_SUBMIT_REVIEW_ONLY",
        "blocked": False,
        "fail_closed": False,
        "network_dry_probe_ready_for_operator_no_order_command": True,
        "public_metadata_network_probe_performed": False,
        "real_testnet_submit_may_begin": False,
        **_disabled_payload(),
    }


def _filled_validation() -> dict:
    return {
        "status": "PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_BLOCKED_FAIL_CLOSED",
        "blocked": True,
        "fail_closed": True,
        "real_testnet_submit_may_begin": False,
        **_disabled_payload(),
    }


def _template() -> dict:
    return build_public_metadata_probe_command_template(
        _dry_probe(),
        _filled_validation(),
        created_at_utc="2026-01-01T00:00:00Z",
    )


def test_public_metadata_probe_command_template_is_ready_but_no_submit():
    template = _template()
    validation = validate_public_metadata_probe_command_template(template)
    assert validation["blocked"] is False
    assert validation["public_metadata_network_probe_command_ready"] is True
    assert validation["real_testnet_submit_may_begin"] is False
    assert validation["order_endpoint_called"] is False
    assert validation["signature_created"] is False


def test_command_template_blocks_order_or_private_scope():
    template = _template()
    command = dict(template["public_metadata_probe_command"])
    command["allowed_endpoint_paths"] = ["/fapi/v1/order"]
    template["public_metadata_probe_command"] = command
    validation = validate_public_metadata_probe_command_template(template)
    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    assert any("ENDPOINT" in reason for reason in validation["block_reasons"])


def test_default_run_does_not_execute_network_or_submit():
    result = run_public_metadata_probe(_template(), execute_network=False, created_at_utc="2026-01-01T00:00:00Z")
    assert result["blocked"] is False
    assert result["public_metadata_network_probe_command_ready"] is True
    assert result["public_metadata_network_probe_performed"] is False
    assert result["real_testnet_submit_may_begin"] is False
    assert result["actual_order_submission_performed"] is False


def test_network_execution_with_fake_fetcher_creates_public_metadata_payload_only():
    def fake_fetcher(url: str, timeout: int):
        if url.endswith("/fapi/v1/time"):
            return 200, '{"serverTime": 1710000000000}'
        if url.endswith("/fapi/v1/exchangeInfo"):
            return 200, '{"symbols":[{"symbol":"BTCUSDT"}]}'
        raise AssertionError(url)

    result = run_public_metadata_probe(
        _template(),
        execute_network=True,
        fetcher=fake_fetcher,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert result["blocked"] is False
    assert result["public_metadata_network_probe_performed"] is True
    assert result["public_metadata_network_probe_result_validated"] is True
    assert result["real_testnet_submit_may_begin"] is False
    payload = result["operator_filled_result_payload"]
    op = payload["operator_supplied_result"]
    assert op["order_endpoint_called"] is False
    assert op["requires_signature"] is False
    assert op["api_secret_value_logged"] is False


def test_report_uses_sources_and_stays_no_submit(tmp_path):
    root = tmp_path
    latest = root / "storage" / "latest"
    latest.mkdir(parents=True)
    atomic_write_json(latest / "phase9_2_real_testnet_network_dry_probe_report.json", _dry_probe())
    atomic_write_json(latest / "phase9_2_public_metadata_probe_result_filled_validation_report.json", _filled_validation())
    cfg = AppConfig(root=root, settings={"storage": {"latest_dir": "storage/latest"}})
    report, template, validation, result = build_phase9_2_real_public_metadata_probe_command_report(
        cfg=cfg,
        execute_network=False,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert report["blocked"] is False
    assert report["command_template_created"] is True
    assert report["public_metadata_network_probe_command_ready"] is True
    assert report["public_metadata_network_probe_performed"] is False
    assert report["real_testnet_submit_may_begin"] is False
    assert template["no_order_submit"] is True
    assert validation["blocked"] is False
    assert result["network_execution_requested"] is False
