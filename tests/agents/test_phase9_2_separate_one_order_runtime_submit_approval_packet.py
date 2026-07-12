from __future__ import annotations

from core.json_io import atomic_write_json
from crypto_ai_system.config import AppConfig
from crypto_ai_system.validation.phase9_2_separate_one_order_runtime_submit_approval_packet import (
    FILLED_APPROVAL_FILENAME,
    APPROVAL_TEXT_KO,
    build_approval_template,
    build_negative_fixture_results,
    build_phase9_2_separate_one_order_runtime_submit_approval_packet,
    persist_phase9_2_separate_one_order_runtime_submit_approval_packet,
)


def _cfg(tmp_path, metadata_ready: bool = True, with_filled: bool = False) -> AppConfig:
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True)
    atomic_write_json(latest / "phase9_2_public_metadata_probe_bridge_report.json", {
        "real_testnet_metadata_conditions_ready_for_submit_review_only": metadata_ready,
        "real_testnet_submit_may_begin": False,
        "order_endpoint_called": False,
        "signature_created": False,
    })
    atomic_write_json(latest / "phase9_2_public_metadata_probe_result_filled_validation_report.json", {
        "operator_filled_public_metadata_probe_result_validated": metadata_ready,
        "real_testnet_metadata_conditions_ready_for_submit_review_only": metadata_ready,
        "real_testnet_submit_may_begin": False,
    })
    atomic_write_json(latest / "phase9_2_final_pre_submit_checklist_report.json", {
        "ready_for_separate_one_order_runtime_approval_review_only": metadata_ready,
        "real_testnet_submit_may_begin": False,
    })
    if with_filled:
        filled = build_approval_template(created_at_utc="2026-01-01T00:00:00Z")
        filled.update({
            "operator_approval_text": APPROVAL_TEXT_KO + " 범위는 testnet 단일 주문 1개로 제한합니다. 심볼은 BTCUSDT testnet only입니다. 최대 주문 금액은 10 USDT입니다. live/mainnet 주문은 승인하지 않습니다. testnet order endpoint가 1회 호출될 수 있음을 이해합니다.",
            "operator_name_or_handle": "operator_fixture",
            "approved_at_utc": "2026-01-01T00:00:00Z",
        })
        atomic_write_json(latest / FILLED_APPROVAL_FILENAME, filled)
    return AppConfig(root=tmp_path, settings={"storage": {"latest_dir": "storage/latest"}})


def test_packet_awaits_filled_approval_when_missing(tmp_path):
    cfg = _cfg(tmp_path, metadata_ready=True, with_filled=False)
    report = build_phase9_2_separate_one_order_runtime_submit_approval_packet(cfg=cfg, created_at_utc="2026-01-01T00:00:00Z")
    assert report["operator_filled_approval_present"] is False
    assert report["operator_filled_approval_validated"] is False
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["real_testnet_submit_may_begin"] is False
    assert any("FILLED_APPROVAL_PACKET_MISSING" in reason for reason in report["block_reasons"])


def test_packet_validates_operator_approval_but_never_unlocks_submit(tmp_path):
    cfg = _cfg(tmp_path, metadata_ready=True, with_filled=True)
    report = build_phase9_2_separate_one_order_runtime_submit_approval_packet(cfg=cfg, created_at_utc="2026-01-01T00:00:00Z")
    assert report["operator_filled_approval_present"] is True
    assert report["operator_filled_approval_validated"] is True
    assert report["ready_for_one_order_runtime_submit_operator_review_only"] is True
    assert report["real_testnet_submit_may_begin"] is False
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["order_endpoint_called"] is False
    assert report["signature_created"] is False
    assert report["actual_order_submission_performed"] is False


def test_packet_blocks_valid_approval_if_metadata_not_ready(tmp_path):
    cfg = _cfg(tmp_path, metadata_ready=False, with_filled=True)
    report = build_phase9_2_separate_one_order_runtime_submit_approval_packet(cfg=cfg, created_at_utc="2026-01-01T00:00:00Z")
    assert report["operator_filled_approval_validated"] is False
    assert report["ready_for_one_order_runtime_submit_operator_review_only"] is False
    assert report["real_testnet_submit_may_begin"] is False
    assert any("METADATA" in reason for reason in report["block_reasons"])


def test_persist_writes_packet_and_template(tmp_path):
    cfg = _cfg(tmp_path, metadata_ready=True, with_filled=False)
    report = persist_phase9_2_separate_one_order_runtime_submit_approval_packet(cfg=cfg, created_at_utc="2026-01-01T00:00:00Z")
    latest = tmp_path / "storage" / "latest"
    assert (latest / "phase9_2_separate_one_order_runtime_submit_approval_packet_report.json").exists()
    assert (latest / "phase9_2_separate_one_order_runtime_submit_APPROVAL_TEMPLATE_REVIEW_ONLY.json").exists()
    assert report["real_testnet_submit_may_begin"] is False


def test_negative_approval_packet_fixtures_fail_closed():
    negative = build_negative_fixture_results()
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert negative["real_testnet_submit_may_begin"] is False
