from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.post_submit_evidence_intake import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_RECONCILED_SESSION_CLOSED_REVIEW_ONLY,
    STATUS_WAITING_FOR_EXTERNAL_SUBMIT_REVIEW_ONLY,
    CancelBoundaryEvidence,
    PostSubmitOrderIdIntakeEvidence,
    SignedTestnetReconciliationEvidence,
    SignedTestnetSessionCloseEvidence,
    StatusPollingEventEvidence,
    build_p7_negative_fixture_results,
    build_post_submit_evidence_intake_report,
    persist_post_submit_evidence_intake,
    validate_cancel_boundary_evidence,
    validate_post_submit_order_id_intake,
    validate_signed_testnet_reconciliation_evidence,
    validate_signed_testnet_session_close_evidence,
    validate_status_polling_evidence,
)


def _write_min_project(root: Path) -> None:
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text("[project]\nname='tmp-crypto-ai-system'\nversion='0.286.0'\n", encoding="utf-8")


def _write_p6_ready_waiting(root: Path, *, p6_hash: str = "6" * 64) -> None:
    latest = root / "storage" / "latest"
    atomic_write_json(
        latest / "p6_single_signed_testnet_submit_runtime_action_report.json",
        {
            "status": "P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_READY_DISABLED_NO_SUBMIT",
            "p6_single_signed_testnet_submit_runtime_action_sha256": p6_hash,
            "actual_order_submission_performed": False,
            "actual_testnet_order_submitted": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "real_exchange_order_id_present": False,
            "secret_value_accessed": False,
            "secret_value_logged": False,
            "testnet_order_submission_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
        },
    )


def _p6_submitted(*, p6_hash: str = "7" * 64) -> dict:
    return {
        "status": "P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_SUBMITTED_BY_EXTERNAL_RUNTIME",
        "p6_single_signed_testnet_submit_runtime_action_sha256": p6_hash,
        "actual_order_submission_performed": True,
        "actual_testnet_order_submitted": True,
        "external_order_submission_performed": True,
        "order_endpoint_called": True,
        "http_request_sent": True,
        "signature_created": True,
        "signed_request_created": True,
        "real_exchange_order_id_present": True,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "testnet_order_submission_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
    }


def test_p7_waits_review_only_when_no_external_submit(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p6_ready_waiting(tmp_path, p6_hash="1" * 64)
    cfg = load_config(tmp_path)

    report = build_post_submit_evidence_intake_report(cfg=cfg)

    assert report["status"] == STATUS_WAITING_FOR_EXTERNAL_SUBMIT_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["external_submit_evidence_present"] is False
    assert report["post_submit_chain_complete"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["order_status_endpoint_called"] is False
    assert report["cancel_endpoint_called"] is False
    assert report["secret_value_accessed"] is False
    assert report["unsafe_truthy_execution_flags"] == []


def test_p7_accepts_complete_external_submitted_chain_review_only(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    p6 = _p6_submitted(p6_hash="2" * 64)

    report = build_post_submit_evidence_intake_report(
        cfg=cfg,
        p6_report=p6,
        order_id_intake=PostSubmitOrderIdIntakeEvidence(source_p6_submit_runtime_action_sha256="2" * 64),
        status_polling_events=[StatusPollingEventEvidence()],
        cancel_boundary=CancelBoundaryEvidence(),
        reconciliation_evidence=SignedTestnetReconciliationEvidence(),
        session_close_evidence=SignedTestnetSessionCloseEvidence(),
    )

    assert report["status"] == STATUS_RECONCILED_SESSION_CLOSED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["external_submit_evidence_present"] is True
    assert report["post_submit_chain_complete"] is True
    assert report["actual_testnet_order_submitted"] is True
    assert report["order_endpoint_called"] is True
    assert report["order_status_endpoint_called"] is True
    assert report["cancel_endpoint_called"] is False
    assert report["signed_testnet_promotion_allowed"] is False
    assert report["live_canary_preparation_allowed"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p7_order_id_intake_blocks_missing_order_id_secret_leak_and_mainnet_scope() -> None:
    invalid = validate_post_submit_order_id_intake(
        {
            **PostSubmitOrderIdIntakeEvidence(source_p6_submit_runtime_action_sha256="3" * 64).to_dict(),
            "exchange_order_id": "",
            "secret_value_included": True,
            "environment": "mainnet",
            "mainnet_key_scope_allowed": True,
        },
        expected_p6_sha256="3" * 64,
    )
    assert invalid["post_submit_order_id_intake_valid"] is False
    assert "P7_EXCHANGE_ORDER_ID_MISSING" in invalid["post_submit_order_id_intake_block_reasons"]
    assert "P7_SECRET_VALUE_INCLUDED_IN_ORDER_ID_INTAKE" in invalid["post_submit_order_id_intake_block_reasons"]
    assert "P7_ORDER_ID_INTAKE_ENVIRONMENT_NOT_TESTNET" in invalid["post_submit_order_id_intake_block_reasons"]
    assert "P7_MAINNET_KEY_SCOPE_NOT_ALLOWED" in invalid["post_submit_order_id_intake_block_reasons"]


def test_p7_status_polling_requires_endpoint_hashes_and_no_secret_leak() -> None:
    invalid = validate_status_polling_evidence(
        [
            {
                **StatusPollingEventEvidence().to_dict(),
                "response_hash": "",
                "order_status_endpoint_called": False,
                "secret_value_logged": True,
            }
        ],
        exchange_order_id="testnet_order_12345",
    )
    assert invalid["status_polling_evidence_valid"] is False
    assert "P7_STATUS_EVENT_0_RESPONSE_HASH_MISSING" in invalid["status_polling_block_reasons"]
    assert "P7_STATUS_EVENT_0_ORDER_STATUS_ENDPOINT_CALL_MISSING" in invalid["status_polling_block_reasons"]
    assert "P7_STATUS_EVENT_0_SECRET_VALUE_LOGGED" in invalid["status_polling_block_reasons"]


def test_p7_cancel_boundary_requires_decision_for_open_status() -> None:
    invalid = validate_cancel_boundary_evidence(
        CancelBoundaryEvidence(
            final_status_before_cancel_decision="NEW",
            cancel_required=False,
            cancel_requested=False,
            cancel_block_reason=None,
        ),
        exchange_order_id="testnet_order_12345",
        final_status="NEW",
    )
    assert invalid["cancel_boundary_evidence_valid"] is False
    assert "P7_CANCEL_REQUIRED_FOR_OPEN_STATUS_NOT_MARKED" in invalid["cancel_boundary_block_reasons"]
    assert "P7_CANCEL_REQUIRED_WITHOUT_REQUEST_OR_BLOCK_REASON" in invalid["cancel_boundary_block_reasons"]


def test_p7_reconciliation_and_session_close_block_mismatch_and_promotion() -> None:
    recon = validate_signed_testnet_reconciliation_evidence(
        SignedTestnetReconciliationEvidence(reconciliation_mismatch_count=1),
        exchange_order_id="testnet_order_12345",
        final_status="FILLED",
    )
    assert recon["signed_testnet_reconciliation_evidence_valid"] is False
    assert "P7_RECONCILIATION_MISMATCH_COUNT_NONZERO" in recon["signed_testnet_reconciliation_block_reasons"]

    close = validate_signed_testnet_session_close_evidence(
        SignedTestnetSessionCloseEvidence(signed_testnet_promotion_allowed=True),
        exchange_order_id="testnet_order_12345",
        reconciliation_id="reconciliation_signed_testnet_1",
        final_status="FILLED",
    )
    assert close["signed_testnet_session_close_evidence_valid"] is False
    assert "P7_SIGNED_TESTNET_PROMOTION_NOT_ALLOWED" in close["signed_testnet_session_close_block_reasons"]


def test_p7_blocks_incomplete_external_submitted_chain(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    report = build_post_submit_evidence_intake_report(
        cfg=cfg,
        p6_report=_p6_submitted(p6_hash="4" * 64),
        order_id_intake=PostSubmitOrderIdIntakeEvidence(source_p6_submit_runtime_action_sha256="4" * 64),
        status_polling_events=[],
        cancel_boundary=CancelBoundaryEvidence(),
        reconciliation_evidence=SignedTestnetReconciliationEvidence(),
        session_close_evidence=SignedTestnetSessionCloseEvidence(),
    )
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P7_STATUS_POLLING_EVENTS_MISSING" in report["block_reasons"]
    assert report["post_submit_chain_complete"] is False


def test_p7_persist_writes_waiting_report_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p6_ready_waiting(tmp_path, p6_hash="5" * 64)
    cfg = load_config(tmp_path)

    report = persist_post_submit_evidence_intake(cfg=cfg)
    latest = tmp_path / "storage" / "latest"
    summary = read_json(latest / "p7_post_submit_evidence_intake_summary.json", default={})
    negative = read_json(latest / "p7_post_submit_evidence_intake_negative_fixture_results.json", default={})

    assert report["status"] == STATUS_WAITING_FOR_EXTERNAL_SUBMIT_REVIEW_ONLY
    assert (latest / "p7_post_submit_evidence_intake_report.json").exists()
    assert (latest / "p7_post_submit_evidence_intake_registry_record.json").exists()
    assert summary["status"] == STATUS_WAITING_FOR_EXTERNAL_SUBMIT_REVIEW_ONLY
    assert summary["actual_order_submission_performed"] is False
    assert summary["order_endpoint_called"] is False
    assert summary["secret_value_accessed"] is False
    assert summary["negative_fixtures_all_blocked"] is True
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True


def test_p7_negative_fixture_builder_blocks_all_cases(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    payload = build_p7_negative_fixture_results(cfg=cfg)

    assert payload["all_negative_fixtures_blocked_fail_closed"] is True
    assert payload["actual_order_submission_performed"] is False
    assert payload["order_endpoint_called"] is False
    assert payload["secret_value_accessed"] is False
    assert set(payload["fixture_results"]) >= {
        "missing_exchange_order_id",
        "p6_hash_mismatch",
        "status_endpoint_secret_leak",
        "cancel_required_without_decision",
        "reconciliation_mismatch",
        "session_close_promotion_enabled",
        "mainnet_scope_in_order_intake",
    }


def test_p7_order_id_intake_requires_real_evidence_origin_hashes_and_secret_reference() -> None:
    from crypto_ai_system.execution.post_submit_evidence_intake import PostSubmitOrderIdIntakeEvidence, validate_post_submit_order_id_intake

    invalid = validate_post_submit_order_id_intake(
        {
            **PostSubmitOrderIdIntakeEvidence(source_p6_submit_runtime_action_sha256="7" * 64).to_dict(),
            "exchange_order_id": "mock_order_123",
            "request_hash": "not-a-hash",
            "secret_reference_id": "",
            "evidence_origin": "fixture",
            "mock_or_fixture_evidence": True,
        },
        expected_p6_sha256="7" * 64,
    )

    assert invalid["post_submit_order_id_intake_valid"] is False
    assert "P7_EXCHANGE_ORDER_ID_LOOKS_MOCK_OR_FIXTURE" in invalid["post_submit_order_id_intake_block_reasons"]
    assert "P7_REQUEST_HASH_NOT_SHA256_HEX" in invalid["post_submit_order_id_intake_block_reasons"]
    assert "P7_SECRET_REFERENCE_ID_MISSING" in invalid["post_submit_order_id_intake_block_reasons"]
    assert "P7_EVIDENCE_ORIGIN_NOT_REAL_SIGNED_TESTNET_EXTERNAL_RUNTIME" in invalid["post_submit_order_id_intake_block_reasons"]
