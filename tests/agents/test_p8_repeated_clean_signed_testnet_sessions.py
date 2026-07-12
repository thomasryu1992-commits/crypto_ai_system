from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.repeated_clean_signed_testnet_sessions import (
    MIN_CLEAN_SESSION_COUNT,
    REQUIRED_SESSION_SCENARIOS,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALIDATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    SignedTestnetSessionEvidence,
    build_p8_negative_fixture_results,
    build_repeated_clean_signed_testnet_sessions_report,
    build_required_session_fixture_set,
    persist_repeated_clean_signed_testnet_sessions,
    validate_repeated_clean_signed_testnet_sessions,
    validate_single_signed_testnet_session_evidence,
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


def _write_p7_waiting(root: Path) -> None:
    atomic_write_json(
        root / "storage" / "latest" / "p7_post_submit_evidence_intake_report.json",
        {
            "status": "P7_POST_SUBMIT_EVIDENCE_INTAKE_WAITING_FOR_EXTERNAL_SUBMIT_REVIEW_ONLY",
            "p7_post_submit_evidence_intake_sha256": "7" * 64,
            "post_submit_chain_complete": False,
            "signed_testnet_session_closed_clean_review_only": False,
            "actual_testnet_order_submitted": False,
            "secret_value_accessed": False,
            "secret_value_logged": False,
            "signed_testnet_promotion_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
        },
    )


def _p7_complete() -> dict:
    return {
        "status": "P7_POST_SUBMIT_EVIDENCE_INTAKE_RECONCILED_SESSION_CLOSED_REVIEW_ONLY",
        "p7_post_submit_evidence_intake_sha256": "7" * 64,
        "post_submit_chain_complete": True,
        "signed_testnet_session_closed_clean_review_only": True,
        "actual_testnet_order_submitted": True,
        "order_endpoint_called": True,
        "order_status_endpoint_called": True,
        "cancel_endpoint_called": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
    }


def test_p8_waits_review_only_without_repeated_session_evidence(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p7_waiting(tmp_path)
    cfg = load_config(tmp_path)

    report = build_repeated_clean_signed_testnet_sessions_report(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["repeated_session_evidence_present"] is False
    assert report["repeated_clean_signed_testnet_sessions_validated"] is False
    assert report["live_canary_preparation_candidate_evidence_created"] is False
    assert report["live_canary_preparation_allowed"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["secret_value_accessed"] is False
    assert report["unsafe_truthy_execution_flags"] == []


def test_p8_validates_required_repeated_session_fixture_set_review_only(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    sessions = build_required_session_fixture_set()

    report = build_repeated_clean_signed_testnet_sessions_report(cfg=cfg, p7_report=_p7_complete(), session_evidence=sessions)

    assert report["status"] == STATUS_VALIDATED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["repeated_clean_signed_testnet_sessions_validated"] is True
    assert report["clean_submitted_session_count"] >= MIN_CLEAN_SESSION_COUNT
    assert report["reconciliation_mismatch_count"] == 0
    assert report["kill_switch_session_count"] == 1
    assert report["live_canary_preparation_candidate_evidence_created"] is True
    assert report["live_canary_preparation_allowed"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_scaled_execution_enabled"] is False
    observed = set(report["repeated_clean_signed_testnet_sessions_validation"]["observed_session_scenarios"])
    assert REQUIRED_SESSION_SCENARIOS.issubset(observed)


def test_p8_single_session_blocks_secret_leak_mainnet_scope_and_mismatch() -> None:
    validation = validate_single_signed_testnet_session_evidence(
        {
            **SignedTestnetSessionEvidence(session_id="bad", scenario="long_filled").to_dict(),
            "secret_value_logged": True,
            "mainnet_key_scope_allowed": True,
            "reconciliation_mismatch_count": 1,
        }
    )

    assert validation["single_session_evidence_valid"] is False
    assert "P8_SESSION_SECRET_VALUE_LOGGED" in validation["single_session_block_reasons"]
    assert "P8_SESSION_MAINNET_KEY_SCOPE_ALLOWED" in validation["single_session_block_reasons"]
    assert "P8_SESSION_RECONCILIATION_MISMATCH_COUNT_NONZERO" in validation["single_session_block_reasons"]


def test_p8_repeated_validator_blocks_missing_minimum_and_scenarios() -> None:
    sessions = build_required_session_fixture_set()[:4]
    validation = validate_repeated_clean_signed_testnet_sessions(sessions)

    assert validation["repeated_clean_signed_testnet_sessions_valid"] is False
    assert validation["blocked"] is True
    assert "P8_MIN_CLEAN_SIGNED_TESTNET_SESSION_COUNT_NOT_MET" in validation["block_reasons"]
    assert validation["missing_session_scenarios"]


def test_p8_repeated_validator_blocks_duplicate_idempotency_and_missing_kill_switch() -> None:
    sessions = [s.to_dict() for s in build_required_session_fixture_set() if s.scenario != "kill_switch_blocked"]
    sessions[0]["idempotency_key"] = "duplicate_key"
    sessions[1]["idempotency_key"] = "duplicate_key"

    validation = validate_repeated_clean_signed_testnet_sessions(sessions)

    assert validation["repeated_clean_signed_testnet_sessions_valid"] is False
    assert "P8_DUPLICATE_IDEMPOTENCY_KEY_DETECTED" in validation["block_reasons"]
    assert "P8_REQUIRED_SCENARIO_MISSING:kill_switch_blocked" in validation["block_reasons"]
    assert "P8_KILL_SWITCH_BLOCK_SESSION_MISSING" in validation["block_reasons"]


def test_p8_build_report_blocks_source_p7_secret_leak_or_live_flags(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    p7 = {**_p7_complete(), "secret_value_logged": True, "live_canary_execution_enabled": True}

    report = build_repeated_clean_signed_testnet_sessions_report(
        cfg=cfg,
        p7_report=p7,
        session_evidence=build_required_session_fixture_set(),
    )

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["blocked"] is True
    assert "P8_SOURCE_P7_SECRET_LEAK_FLAG_TRUE" in report["block_reasons"]
    assert "P8_SOURCE_P7_LIVE_EXECUTION_FLAG_TRUE" in report["block_reasons"]


def test_p8_negative_fixtures_all_block_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)

    results = build_p8_negative_fixture_results(cfg=cfg)

    assert results["all_negative_fixtures_blocked_fail_closed"] is True
    assert results["live_canary_preparation_allowed"] is False
    assert results["live_canary_execution_enabled"] is False
    assert results["live_scaled_execution_enabled"] is False
    for item in results["fixture_results"].values():
        assert item["blocked_fail_closed"] is True
        assert item["repeated_clean_signed_testnet_sessions_validated"] is False


def test_p8_persist_writes_waiting_report_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p7_waiting(tmp_path)
    cfg = load_config(tmp_path)

    report = persist_repeated_clean_signed_testnet_sessions(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert (tmp_path / "storage" / "latest" / "p8_repeated_clean_signed_testnet_sessions_report.json").exists()
    assert (tmp_path / "storage" / "latest" / "p8_repeated_clean_signed_testnet_sessions_summary.json").exists()
    assert (tmp_path / "storage" / "latest" / "p8_repeated_clean_signed_testnet_sessions_negative_fixture_results.json").exists()
    assert (tmp_path / "storage" / "latest" / "p8_repeated_clean_signed_testnet_sessions_registry_record.json").exists()
    assert (tmp_path / "storage" / "p8_repeated_clean_signed_testnet_sessions" / "p8_repeated_clean_signed_testnet_sessions_report.json").exists()


def test_p8_session_blocks_fixture_or_unvalidated_real_evidence_marker() -> None:
    bad = {
        **SignedTestnetSessionEvidence(session_id="p8_bad_real_marker", scenario="long_filled").to_dict(),
        "fixture_evidence": True,
        "evidence_origin": "fixture",
        "p7_real_evidence_validated": False,
    }

    validation = validate_single_signed_testnet_session_evidence(bad)

    assert validation["single_session_evidence_valid"] is False
    assert "P8_SESSION_FIXTURE_EVIDENCE_NOT_ALLOWED_AS_REAL_SESSION" in validation["single_session_block_reasons"]
    assert "P8_SESSION_EVIDENCE_ORIGIN_NOT_REAL_SIGNED_TESTNET_EXTERNAL_RUNTIME" in validation["single_session_block_reasons"]
    assert "P8_SESSION_P7_REAL_EVIDENCE_NOT_VALIDATED" in validation["single_session_block_reasons"]
