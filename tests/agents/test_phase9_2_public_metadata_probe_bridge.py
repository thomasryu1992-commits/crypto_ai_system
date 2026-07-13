from __future__ import annotations

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig
from crypto_ai_system.validation.phase9_2_public_metadata_probe_bridge import (
    bridge_public_metadata_probe_result,
    build_negative_fixture_results,
    persist_phase9_2_public_metadata_probe_bridge,
)
from crypto_ai_system.validation.phase9_2_public_metadata_network_dry_probe_result_intake import (
    build_public_metadata_probe_result_template,
)
from crypto_ai_system.validation.phase9_2_real_public_metadata_probe_command import _disabled_payload


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


def _cfg_with_sources(tmp_path) -> AppConfig:
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True)
    atomic_write_json(latest / "phase9_2_real_testnet_network_dry_probe_report.json", _dry_probe())
    atomic_write_json(latest / "phase9_2_public_metadata_probe_result_filled_validation_report.json", _filled_validation())
    template = build_public_metadata_probe_result_template(
        {
            "status": "PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_RECORDED_NO_ORDER_SUBMIT_REVIEW_ONLY",
            "blocked": False,
            "fail_closed": False,
            "public_metadata_network_probe_result_intake_ready": True,
            "real_testnet_submit_may_begin": False,
            **_disabled_payload(),
        },
        created_at_utc="2026-01-01T00:00:00Z",
    )
    atomic_write_json(latest / "phase9_2_public_metadata_network_dry_probe_RESULT_TEMPLATE_NO_ORDER_SUBMIT_REVIEW_ONLY.json", template)
    return AppConfig(root=tmp_path, settings={"storage": {"latest_dir": "storage/latest"}})


def test_bridge_default_is_ready_and_does_not_execute_network(tmp_path):
    cfg = _cfg_with_sources(tmp_path)
    report, command_result, operator_payload, validation = bridge_public_metadata_probe_result(
        cfg=cfg,
        execute_network=False,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert report["blocked"] is False
    assert report["status"].endswith("NO_ORDER_SUBMIT_REVIEW_ONLY")
    assert report["network_execution_requested"] is False
    assert report["operator_filled_result_payload_created"] is False
    assert report["real_testnet_submit_may_begin"] is False
    assert report["actual_order_submission_performed"] is False
    assert operator_payload is None
    assert validation is None
    assert command_result["public_metadata_network_probe_performed"] is False


def test_bridge_with_fake_public_fetcher_validates_payload_but_still_blocks_submit(tmp_path):
    cfg = _cfg_with_sources(tmp_path)

    def fake_fetcher(url: str, timeout: int):
        assert "/order" not in url
        assert "/account" not in url
        if url.endswith("/fapi/v1/time"):
            return 200, '{"serverTime": 1710000000000}'
        if url.endswith("/fapi/v1/exchangeInfo"):
            return 200, '{"symbols":[{"symbol":"BTCUSDT","filters":[]}]}'
        raise AssertionError(url)

    report, command_result, operator_payload, validation = bridge_public_metadata_probe_result(
        cfg=cfg,
        execute_network=True,
        fetcher=fake_fetcher,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert report["blocked"] is False
    assert report["operator_filled_result_payload_created"] is True
    assert report["operator_filled_public_metadata_probe_result_validated"] is True
    assert report["real_testnet_metadata_conditions_ready_for_submit_review_only"] is True
    assert report["real_testnet_submit_may_begin"] is False
    assert report["order_endpoint_called"] is False
    assert report["signature_created"] is False
    assert operator_payload is not None
    assert operator_payload["operator_supplied_result"]["order_endpoint_called"] is False
    assert validation is not None
    assert validation["operator_filled_public_metadata_probe_result_validated"] is True
    assert command_result["real_testnet_submit_may_begin"] is False


def test_persist_default_does_not_overwrite_filled_result_when_no_network(tmp_path):
    cfg = _cfg_with_sources(tmp_path)
    latest = tmp_path / "storage" / "latest"
    existing = {"sample_only": True, "synthetic": True, "real_testnet_submit_may_begin": False}
    atomic_write_json(latest / "phase9_2_public_metadata_network_dry_probe_RESULT_FILLED_REVIEW_ONLY.json", existing)
    report = persist_phase9_2_public_metadata_probe_bridge(cfg=cfg, execute_network=False)
    assert report["operator_filled_result_written"] is False
    after = read_json(latest / "phase9_2_public_metadata_network_dry_probe_RESULT_FILLED_REVIEW_ONLY.json", default={})
    assert after == existing
    assert report["real_testnet_submit_may_begin"] is False


def test_negative_bridge_fixtures_fail_closed():
    negative = build_negative_fixture_results()
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert negative["real_testnet_submit_may_begin"] is False
