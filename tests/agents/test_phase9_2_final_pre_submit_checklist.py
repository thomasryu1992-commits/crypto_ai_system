from __future__ import annotations

from core.json_io import atomic_write_json
from crypto_ai_system.config import AppConfig
from crypto_ai_system.validation.phase9_2_final_pre_submit_checklist import (
    REQUIRED_REPORTS,
    build_negative_fixture_results,
    build_phase9_2_final_pre_submit_checklist,
    persist_phase9_2_final_pre_submit_checklist,
)


def _base_report(**overrides):
    payload = {
        "status": "OK_REVIEW_ONLY",
        "blocked": False,
        "fail_closed": False,
        "review_only": True,
        "no_order_submit": True,
        "real_testnet_submit_may_begin": False,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "private_account_endpoint_called": False,
        "balance_endpoint_called": False,
        "position_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
    }
    payload.update(overrides)
    return payload


def _cfg(tmp_path, metadata_ready: bool = False) -> AppConfig:
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True)
    for _key, filename in REQUIRED_REPORTS.items():
        atomic_write_json(latest / filename, _base_report())
    atomic_write_json(
        latest / "phase9_2_public_metadata_probe_bridge_report.json",
        _base_report(real_testnet_metadata_conditions_ready_for_submit_review_only=metadata_ready),
    )
    atomic_write_json(
        latest / "phase9_2_public_metadata_probe_result_filled_validation_report.json",
        _base_report(real_testnet_metadata_conditions_ready_for_submit_review_only=metadata_ready),
    )
    return AppConfig(root=tmp_path, settings={"storage": {"latest_dir": "storage/latest"}})


def test_checklist_blocks_when_public_metadata_not_validated(tmp_path):
    cfg = _cfg(tmp_path, metadata_ready=False)
    report = build_phase9_2_final_pre_submit_checklist(cfg=cfg, created_at_utc="2026-01-01T00:00:00Z")
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["real_testnet_metadata_conditions_ready_for_submit_review_only"] is False
    assert report["ready_for_separate_one_order_runtime_approval_review_only"] is False
    assert report["real_testnet_submit_may_begin"] is False
    assert report["actual_order_submission_performed"] is False
    assert any("PUBLIC_METADATA" in reason for reason in report["block_reasons"])


def test_checklist_can_be_ready_for_separate_approval_but_never_submit(tmp_path):
    cfg = _cfg(tmp_path, metadata_ready=True)
    report = build_phase9_2_final_pre_submit_checklist(cfg=cfg, created_at_utc="2026-01-01T00:00:00Z")
    assert report["ready_for_separate_one_order_runtime_approval_review_only"] is True
    assert report["real_testnet_metadata_conditions_ready_for_submit_review_only"] is True
    assert report["real_testnet_submit_may_begin"] is False
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["order_endpoint_called"] is False
    assert report["signature_created"] is False
    assert report["blocked"] is True
    assert any("SEPARATE_EXPLICIT_ONE_ORDER" in reason for reason in report["block_reasons"])


def test_persist_writes_checklist(tmp_path):
    cfg = _cfg(tmp_path, metadata_ready=False)
    report = persist_phase9_2_final_pre_submit_checklist(cfg=cfg, created_at_utc="2026-01-01T00:00:00Z")
    assert (tmp_path / "storage" / "latest" / "phase9_2_final_pre_submit_checklist_report.json").exists()
    assert (tmp_path / "storage" / "latest" / "PHASE9_2_FINAL_PRE_SUBMIT_CHECKLIST_HANDOFF_NO_ORDER_SUBMIT_REVIEW_ONLY.md").exists()
    assert report["real_testnet_submit_may_begin"] is False


def test_negative_checklist_fixtures_fail_closed():
    negative = build_negative_fixture_results()
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert negative["real_testnet_submit_may_begin"] is False
