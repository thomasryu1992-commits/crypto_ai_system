from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.repeated_clean_live_canary_sessions import (
    MIN_CLEAN_LIVE_CANARY_SESSION_COUNT,
    REQUIRED_LIVE_CANARY_SESSION_SCENARIOS,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALIDATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    LiveCanarySessionEvidence,
    build_p12_negative_fixture_results,
    build_repeated_clean_live_canary_sessions_report,
    build_required_live_canary_session_fixture_set,
    persist_repeated_clean_live_canary_sessions,
    validate_repeated_clean_live_canary_sessions,
    validate_single_live_canary_session_evidence,
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


def _write_p11_waiting(root: Path) -> None:
    atomic_write_json(
        root / "storage" / "latest" / "p11_live_canary_post_submit_evidence_review_report.json",
        {
            "status": "P11_LIVE_CANARY_POST_SUBMIT_EVIDENCE_REVIEW_WAITING_REVIEW_ONLY",
            "p11_live_canary_post_submit_evidence_review_sha256": "b" * 64,
            "external_live_canary_submit_evidence_present": False,
            "live_canary_post_submit_chain_complete": False,
            "live_canary_reconciliation_clean": False,
            "canary_outcome_review_completed": False,
            "post_submit_relock_confirmed": False,
            "secret_value_accessed": False,
            "secret_value_logged": False,
            "live_canary_execution_enabled": False,
            "live_scaled_readiness_allowed": False,
            "live_scaled_promotion_allowed": False,
            "live_scaled_execution_enabled": False,
        },
    )


def _p11_complete() -> dict:
    return {
        "status": "P11_LIVE_CANARY_POST_SUBMIT_EVIDENCE_REVIEW_OUTCOME_REVIEW_RECORDED_REVIEW_ONLY",
        "p11_live_canary_post_submit_evidence_review_sha256": "b" * 64,
        "external_live_canary_submit_evidence_present": True,
        "live_canary_post_submit_chain_complete": True,
        "live_canary_reconciliation_clean": True,
        "canary_outcome_review_completed": True,
        "post_submit_relock_confirmed": True,
        "actual_live_order_submitted": True,
        "live_order_endpoint_called": True,
        "order_status_endpoint_called": True,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "live_canary_execution_enabled": False,
        "live_scaled_readiness_allowed": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_execution_enabled": False,
    }


def test_p12_waits_review_only_without_repeated_live_canary_evidence(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p11_waiting(tmp_path)
    cfg = load_config(tmp_path)

    report = build_repeated_clean_live_canary_sessions_report(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["repeated_live_canary_session_evidence_present"] is False
    assert report["repeated_clean_live_canary_sessions_validated"] is False
    assert report["live_scaled_readiness_candidate_evidence_created"] is False
    assert report["live_scaled_readiness_allowed"] is False
    assert report["live_scaled_promotion_allowed"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["secret_value_accessed"] is False
    assert report["unsafe_truthy_execution_flags"] == []


def test_p12_validates_repeated_clean_live_canary_fixture_set_review_only(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    sessions = build_required_live_canary_session_fixture_set()

    report = build_repeated_clean_live_canary_sessions_report(cfg=cfg, p11_report=_p11_complete(), session_evidence=sessions)

    assert report["status"] == STATUS_VALIDATED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["repeated_clean_live_canary_sessions_validated"] is True
    assert report["clean_submitted_live_canary_session_count"] >= MIN_CLEAN_LIVE_CANARY_SESSION_COUNT
    assert report["reconciliation_mismatch_count"] == 0
    assert report["manual_override_count"] == 0
    assert report["incident_count"] == 0
    assert report["kill_switch_session_count"] == 1
    assert report["live_scaled_readiness_candidate_evidence_created"] is True
    assert report["live_scaled_readiness_allowed"] is False
    assert report["live_scaled_promotion_allowed"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["secret_value_accessed"] is False
    observed = set(report["repeated_clean_live_canary_sessions_validation"]["observed_live_canary_session_scenarios"])
    assert REQUIRED_LIVE_CANARY_SESSION_SCENARIOS.issubset(observed)


def test_p12_single_session_blocks_secret_mainnet_and_live_scaled_flags() -> None:
    validation = validate_single_live_canary_session_evidence(
        {
            **LiveCanarySessionEvidence(session_id="bad", scenario="live_long_filled").to_dict(),
            "secret_value_logged": True,
            "mainnet_key_scope_allowed": True,
            "live_scaled_execution_enabled": True,
            "reconciliation_mismatch_count": 1,
        }
    )

    assert validation["single_live_canary_session_evidence_valid"] is False
    assert "P12_SESSION_SECRET_VALUE_LOGGED" in validation["single_live_canary_session_block_reasons"]
    assert "P12_SESSION_MAINNET_KEY_SCOPE_ALLOWED" in validation["single_live_canary_session_block_reasons"]
    assert "P12_SESSION_LIVE_SCALED_EXECUTION_ENABLED" in validation["single_live_canary_session_block_reasons"]
    assert "P12_SESSION_RECONCILIATION_MISMATCH_COUNT_NONZERO" in validation["single_live_canary_session_block_reasons"]


def test_p12_repeated_validator_blocks_minimum_missing_scenario_and_duplicates() -> None:
    sessions = [s.to_dict() for s in build_required_live_canary_session_fixture_set()[:4]]
    sessions[0]["idempotency_key"] = "duplicate_key"
    sessions[1]["idempotency_key"] = "duplicate_key"

    validation = validate_repeated_clean_live_canary_sessions(sessions)

    assert validation["repeated_clean_live_canary_sessions_valid"] is False
    assert validation["blocked"] is True
    assert "P12_MIN_CLEAN_LIVE_CANARY_SESSION_COUNT_NOT_MET" in validation["block_reasons"]
    assert "P12_DUPLICATE_IDEMPOTENCY_KEY_DETECTED" in validation["block_reasons"]
    assert validation["missing_live_canary_session_scenarios"]


def test_p12_repeated_validator_blocks_slippage_latency_manual_override_and_incident() -> None:
    sessions = [s.to_dict() for s in build_required_live_canary_session_fixture_set()]
    sessions[0]["slippage_bps"] = 50.0
    sessions[1]["slippage_bps"] = 50.0
    sessions[2]["slippage_bps"] = 50.0
    sessions[1]["latency_ms"] = 20_000
    sessions[2]["manual_override_count"] = 1
    sessions[3]["incident_count"] = 1

    validation = validate_repeated_clean_live_canary_sessions(sessions)

    assert validation["repeated_clean_live_canary_sessions_valid"] is False
    assert "P12_MANUAL_OVERRIDE_COUNT_NONZERO" in validation["block_reasons"]
    assert "P12_INCIDENT_COUNT_NONZERO" in validation["block_reasons"]
    assert "P12_AVERAGE_LATENCY_ABOVE_THRESHOLD" in validation["block_reasons"]
    assert "P12_AVERAGE_SLIPPAGE_ABOVE_THRESHOLD" in validation["block_reasons"]


def test_p12_build_report_blocks_source_p11_secret_or_scaled_flags(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    p11 = {**_p11_complete(), "secret_value_logged": True, "live_scaled_execution_enabled": True}

    report = build_repeated_clean_live_canary_sessions_report(
        cfg=cfg,
        p11_report=p11,
        session_evidence=build_required_live_canary_session_fixture_set(),
    )

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["blocked"] is True
    assert "P12_SOURCE_P11_SECRET_VALUE_LOGGED" in report["block_reasons"]
    assert "P12_SOURCE_P11_LIVE_SCALED_EXECUTION_ENABLED" in report["block_reasons"]
    assert report["live_scaled_execution_enabled"] is False


def test_p12_negative_fixtures_all_block_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)

    results = build_p12_negative_fixture_results(cfg=cfg)

    assert results["all_negative_fixtures_blocked_fail_closed"] is True
    assert results["live_scaled_readiness_allowed"] is False
    assert results["live_scaled_promotion_allowed"] is False
    assert results["live_scaled_execution_enabled"] is False
    for item in results["fixture_results"].values():
        assert item["blocked_fail_closed"] is True
        assert item["repeated_clean_live_canary_sessions_validated"] is False


def test_p12_persist_writes_waiting_report_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p11_waiting(tmp_path)
    cfg = load_config(tmp_path)

    report = persist_repeated_clean_live_canary_sessions(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert (tmp_path / "storage" / "latest" / "p12_repeated_clean_live_canary_sessions_report.json").exists()
    assert (tmp_path / "storage" / "latest" / "p12_repeated_clean_live_canary_sessions_summary.json").exists()
    assert (tmp_path / "storage" / "latest" / "p12_repeated_clean_live_canary_sessions_negative_fixture_results.json").exists()
    assert (tmp_path / "storage" / "latest" / "p12_repeated_clean_live_canary_sessions_registry_record.json").exists()
    assert (tmp_path / "storage" / "p12_repeated_clean_live_canary_sessions" / "p12_repeated_clean_live_canary_sessions_report.json").exists()
    summary = read_json(tmp_path / "storage" / "latest" / "p12_repeated_clean_live_canary_sessions_summary.json")
    assert summary["repeated_live_canary_session_evidence_present"] is False
    assert summary["repeated_clean_live_canary_sessions_validated"] is False
    assert summary["live_scaled_readiness_allowed"] is False
    assert summary["live_scaled_promotion_allowed"] is False
    assert summary["live_scaled_execution_enabled"] is False
    assert summary["secret_value_accessed"] is False
