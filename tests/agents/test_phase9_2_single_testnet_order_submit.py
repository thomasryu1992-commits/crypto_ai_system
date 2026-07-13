from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import (
    persist_phase9_1_single_signed_testnet_enablement_intake_report,
)
from crypto_ai_system.validation.phase9_2_single_testnet_order_submit import (
    STATUS_RECORDED_BLOCKED_REVIEW_ONLY,
    build_phase9_2_single_testnet_order_submit_report,
    persist_phase9_2_single_testnet_order_submit_report,
    validate_phase9_2_single_testnet_order_submit_attempt,
)
from tests.agents.test_phase9_1_single_signed_testnet_enablement_intake import _write_ready_phase8_4_sources


def _write_ready_phase9_1_sources() -> None:
    _write_ready_phase8_4_sources()
    cfg = load_config()
    persist_phase9_1_single_signed_testnet_enablement_intake_report(cfg=cfg, run_phase8_4_first=False)


def test_phase9_2_records_blocked_submit_attempt_without_order_submission() -> None:
    _write_ready_phase9_1_sources()
    cfg = load_config()
    report, submit_attempt, guard_report, negative_fixture_results = build_phase9_2_single_testnet_order_submit_report(
        cfg=cfg,
        run_phase9_1_first=False,
    )

    assert report["status"] == STATUS_RECORDED_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["phase9_2_single_testnet_order_submit_attempt_recorded"] is True
    assert report["phase9_2_single_testnet_order_submit_blocked_fail_closed"] is True
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["phase9_3_status_polling_may_begin"] is False
    assert "PHASE9_2_PHASE9_1_ACTUAL_APPROVAL_INCOMPLETE" in report["block_reasons"]
    assert "PHASE9_2_OPERATOR_SIGNATURE_MISSING" in report["block_reasons"]
    assert submit_attempt["submit_attempt_type"] == "phase9_2_single_testnet_order_submit_blocked_review_only"
    assert submit_attempt["idempotency_key_preview"]
    assert submit_attempt["dry_order_payload_preview"]["no_order_endpoint_called"] is True
    assert guard_report["guard_blocked_fail_closed"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    for payload in (report, submit_attempt, guard_report):
        assert payload["testnet_order_submission_allowed"] is False
        assert payload["place_order_enabled"] is False
        assert payload["cancel_order_enabled"] is False
        assert payload["signed_order_executor_enabled"] is False
        assert payload["order_endpoint_called"] is False
        assert payload["http_request_sent"] is False
        assert payload["signature_created"] is False
        assert payload["actual_order_submission_performed"] is False


def test_phase9_2_persist_writes_blocked_review_only_artifacts() -> None:
    _write_ready_phase9_1_sources()
    report = persist_phase9_2_single_testnet_order_submit_report(run_phase9_1_first=False)

    assert report["status"] == STATUS_RECORDED_BLOCKED_REVIEW_ONLY
    assert Path("storage/latest/phase9_2_single_testnet_order_submit_report.json").exists()
    assert Path("storage/latest/single_testnet_order_submit_BLOCKED_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/single_testnet_order_submit_guard_report.json").exists()
    assert Path("storage/latest/phase9_2_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE9_2_SINGLE_TESTNET_ORDER_SUBMIT_HANDOFF_BLOCKED_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/single_testnet_order_submit_BLOCKED_REVIEW_ONLY.json").exists()
    assert Path("storage/phase9_2_single_testnet_order_submit/PHASE9_2_SINGLE_TESTNET_ORDER_SUBMIT_HANDOFF_BLOCKED_REVIEW_ONLY.md").exists()


def test_phase9_2_validator_blocks_endpoint_signature_and_over_scope() -> None:
    _write_ready_phase9_1_sources()
    cfg = load_config()
    _report, submit_attempt, _guard_report, _fixtures = build_phase9_2_single_testnet_order_submit_report(
        cfg=cfg,
        run_phase9_1_first=False,
    )
    submit_attempt["testnet_order_submission_allowed"] = True
    submit_attempt["order_endpoint_called"] = True
    submit_attempt["http_request_sent"] = True
    submit_attempt["signature_created"] = True
    submit_attempt["order_count_requested"] = 2
    submit_attempt["small_max_notional"] = "1000.0"

    result = validate_phase9_2_single_testnet_order_submit_attempt(submit_attempt)

    assert result["phase9_2_single_testnet_order_submit_attempt_valid"] is False
    assert result["phase9_2_single_testnet_order_submit_blocked_fail_closed"] is True
    blockers = result["phase9_2_submit_attempt_blockers"]
    assert "testnet_order_submission_allowed" in result["unsafe_truthy_fields"]
    assert "order_endpoint_called" in result["unsafe_truthy_fields"]
    assert "http_request_sent" in result["unsafe_truthy_fields"]
    assert "signature_created" in result["unsafe_truthy_fields"]
    assert "PHASE9_2_ORDER_COUNT_REQUESTED_NOT_ONE" in blockers
    assert "PHASE9_2_SMALL_MAX_NOTIONAL_INVALID_OR_TOO_HIGH" in blockers


def test_phase9_2_stays_blocked_even_if_phase9_1_file_is_manually_forced_unsafe() -> None:
    _write_ready_phase9_1_sources()
    intake_path = Path("storage/latest/single_signed_testnet_enablement_intake_REVIEW_ONLY.json")
    intake = json.load(open(intake_path, encoding="utf-8"))
    intake["operator_decision"] = "approve_single_signed_testnet_order"
    intake["operator_signature"] = "operator_signature_fixture"
    intake["actual_operator_approval_recorded"] = True
    intake["kill_switch_confirmed_for_actual_approval"] = True
    intake["testnet_key_fingerprint_sha256"] = "a" * 64
    intake["phase9_2_single_testnet_order_submit_may_begin"] = True
    intake["testnet_order_submission_allowed"] = True
    intake_path.write_text(json.dumps(intake, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _submit_attempt, _guard_report, _fixtures = build_phase9_2_single_testnet_order_submit_report(
        cfg=cfg,
        run_phase9_1_first=False,
    )

    assert report["status"] == STATUS_RECORDED_BLOCKED_REVIEW_ONLY
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert any(item.startswith("UNSAFE_PHASE9_2_SOURCE_FLAGS:phase9_1_intake") for item in report["block_reasons"])
