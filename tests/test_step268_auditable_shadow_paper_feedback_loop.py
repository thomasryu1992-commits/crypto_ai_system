from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from crypto_ai_system.config import load_config
from crypto_ai_system.features.research_feature_matrix import (
    build_feature_store_manifest,
    build_research_feature_matrix,
    feature_matrix_sha256,
)
from crypto_ai_system.feedback.paper_lifecycle_outcome_store import (
    _build_outcome_record,
    execute_paper_lifecycle_outcome_store,
)
from crypto_ai_system.research.research_signal_builder import build_research_signal
from crypto_ai_system.research.research_signal_profile_approval import (
    build_step261_manual_approval_packet,
    validate_step261_approval_packet,
)
from crypto_ai_system.research.research_signal_profile_settings_write_preview import (
    build_step267_disabled_settings_write_preview_packet,
    validate_step267_disabled_settings_write_preview_packet,
)
from crypto_ai_system.trading.pre_order_risk_gate import evaluate_pre_order_risk_gate
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp
from scripts.report_step259_researchsignal_weight_calibration import _synthetic_calibration_matrix
from scripts.report_step266_researchsignal_profile_final_apply_approval_validator import build_report as build_step266_report


def test_step268_feature_manifest_hash_reproducible_and_flags(tmp_path: Path) -> None:
    base = pd.DataFrame(
        {
            "timestamp": ["2026-06-30T00:00:00Z", "2026-06-30T01:00:00Z"],
            "close": [100.0, 101.0],
            "fallback_used": [False, True],
            "synthetic_used": [False, False],
            "sample_used": [False, True],
        }
    )
    matrix = build_research_feature_matrix(base, {}, mode="backtest")
    manifest1 = build_feature_store_manifest(matrix)
    manifest2 = build_feature_store_manifest(matrix)

    assert feature_matrix_sha256(matrix) == manifest1["feature_matrix_sha256"]
    assert manifest1["feature_matrix_sha256"] == manifest2["feature_matrix_sha256"]
    assert manifest1["feature_snapshot_id"] == manifest2["feature_snapshot_id"]
    assert manifest1["fallback_used"] is True
    assert manifest1["sample_used"] is True
    assert is_canonical_utc_timestamp(manifest1["created_at_utc"])
    assert matrix["timestamp"].str.contains("T").all()
    assert matrix["missing_optional_data_neutral"].any()
    assert matrix["live_candidate_eligible"].eq(False).any()


def test_step268_research_signal_carries_feature_lineage() -> None:
    cfg = load_config(".")
    snapshot = {
        "timestamp": "2026-06-30T00:00:00Z",
        "canonical_symbol": "BTC-PERP",
        "timeframe": "PT1H",
        "exchange_market": "BTC-USD",
        "data_source": "extended",
        "data_quality_status": "OK",
        "data_freshness_sec": 60,
        "close": 100.0,
        "score_total_score": 0.8,
        "market_condition": "BULLISH_TREND",
        "score_bias": "BULLISH",
        "profile_id": "profile_a",
        "profile_version": "v1",
        "config_version": "step268",
        "data_snapshot_id": "data_1",
        "feature_snapshot_id": "feature_1",
        "feature_matrix_sha256": "a" * 64,
        "source_bundle_sha256": "b" * 64,
    }
    signal = build_research_signal(snapshot, {"final_condition": "BULLISH_TREND"}, cfg)

    assert signal["research_signal_id"] == signal["signal_id"]
    assert signal["profile_id"] == "profile_a"
    assert signal["data_snapshot_id"] == "data_1"
    assert signal["feature_snapshot_id"] == "feature_1"
    assert signal["feature_matrix_sha256"] == "a" * 64
    assert signal["source_bundle_sha256"] == "b" * 64
    assert is_canonical_utc_timestamp(signal["created_at_utc"])


@pytest.mark.parametrize(
    "value,valid",
    [
        ("2026-06-30T12:00:00Z", True),
        ("2026-06-30 12:00:00", False),
        ("2026-06-30T12:00:00+09:00", False),
        ("2026-06-30T12:00:00.123Z", False),
    ],
)
def test_step268_canonical_utc_timestamp_validator(value: str, valid: bool) -> None:
    assert is_canonical_utc_timestamp(value) is valid


def test_step268_approval_packet_missing_source_report_fails_closed(tmp_path: Path) -> None:
    cfg = load_config(".")
    missing_report = tmp_path / "missing_step260_report.json"
    review = {
        "version": "step260_report",
        "matrix_source": "feature_store",
        "matrix_source_type": "stored_feature_store_matrix",
        "rows_evaluated": 10,
        "candidate_review": {
            "production_candidate_profile": "baseline_step258",
            "selection_reason": "test",
            "profile_reviews": [{"profile_name": "baseline_step258", "status": "candidate", "review_score": 1.0}],
        },
        "comparison": {
            "results": [
                {
                    "profile_name": "baseline_step258",
                    "weights": {"price": 1.0},
                    "permission_distribution": {},
                }
            ]
        },
    }
    packet = build_step261_manual_approval_packet(review, cfg, source_step_report_path=missing_report)
    validation = validate_step261_approval_packet(packet)

    assert validation["valid"] is False
    assert "source_report_not_missing_when_declared" in validation["failed_checks"]
    assert packet["source"]["source_step_report_exists"] is False


def test_step268_settings_preview_missing_target_settings_file_fails_closed(tmp_path: Path) -> None:
    cfg = load_config(".")
    matrix_path = tmp_path / "matrix.csv"
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)
    step266_report = build_step266_report(
        Path(".").resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        upstream_approval_decision="APPROVE_FOR_REVIEW_ONLY_STAGING",
        upstream_approver="thomas",
        upstream_approval_rationale="Review-only staging approved.",
        upstream_approval_timestamp_utc="2026-06-30T00:00:00Z",
        upstream_review_decision="READY",
        upstream_reviewer="thomas",
        upstream_review_rationale="Disabled pre-apply review ready.",
        upstream_review_timestamp_utc="2026-06-30T00:00:00Z",
        final_approval_decision="APPROVE_DRY_RUN",
        final_approver="thomas",
        final_rationale="Approve disabled dry-run only.",
        final_timestamp_utc="2026-06-30T00:00:00Z",
    )

    packet = build_step267_disabled_settings_write_preview_packet(
        step266_report,
        cfg,
        settings_path=tmp_path / "missing_settings.yaml",
    )
    validation = validate_step267_disabled_settings_write_preview_packet(packet)

    assert packet["preview"]["ready_for_disabled_settings_write_preview"] is False
    assert packet["settings_yaml_diff_artifact"]["settings_file_exists"] is False
    assert "TARGET_SETTINGS_FILE_MISSING_FAIL_CLOSED" in packet["preview"]["blocked_reasons"]
    assert validation["valid"] is True
    assert packet["settings_write_preview_export"]["settings_write_enabled"] is False


def test_step268_signal_engine_missing_research_signal_blocks_legacy_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import crypto_ai_system.trading.signal_engine as signal_engine

    monkeypatch.setattr(signal_engine, "USE_RESEARCH_SIGNAL_GATE", True)
    monkeypatch.setattr(signal_engine, "LEGACY_SIGNAL_FALLBACK_REVIEW_ONLY_COMPAT", False)
    monkeypatch.setattr(signal_engine, "RESEARCH_SIGNAL_PATH", tmp_path / "missing_research_signal.json")

    payload = signal_engine.generate_trading_signal()

    assert payload["allow_new_position"] is False
    assert payload["risk_level"] == "blocked"
    assert payload["legacy_fallback_used"] is False
    assert payload["reasons"] == ["RESEARCH_SIGNAL_MISSING_FAIL_CLOSED"]


def test_step268_pre_order_risk_gate_blocks_unapproved_stale_and_fallback() -> None:
    result = evaluate_pre_order_risk_gate(
        decision={"decision_id": "dec_1", "side": "LONG"},
        research_signal={
            "research_signal_id": "rs_1",
            "profile_id": "profile_a",
            "stale": True,
            "fallback_used": True,
            "trade_permission": {"allow_new_position": True, "allow_long": True, "allow_short": False, "risk_level": "normal"},
        },
        profile={"profile_id": "profile_a", "approved": False},
        runtime_state={"manual_kill_switch": True},
        market_state={"spread_bps": 2.0},
    )

    assert result.approved is False
    assert result.risk_level == "blocked"
    assert result.allow_new_position is False
    assert "APPROVED_PROFILE_GATE_BLOCKED" in result.block_reasons
    assert "DATA_FRESHNESS_GATE_BLOCKED" in result.block_reasons
    assert "FALLBACK_DATA_GATE_BLOCKED" in result.block_reasons
    assert "MANUAL_KILL_SWITCH_GATE_BLOCKED" in result.block_reasons


def test_step268_outcome_source_missing_requires_explicit_regeneration(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Step268 outcome store fails closed"):
        execute_paper_lifecycle_outcome_store(tmp_path)


def test_step268_outcome_record_standardizes_order_id_chain() -> None:
    record = _build_outcome_record(
        {
            "dry_run_order_intent_id": "oi_1",
            "idempotency_key": "idem_1",
            "simulated_order_id": "exec_1",
            "observation_id": "obs_1",
            "registry_id": "reg_1",
            "comparison_group": "group_1",
            "side": "LONG",
            "quantity": 1.0,
            "entry_price": 100.0,
            "final_lifecycle_status": "SIMULATED_CLOSED",
            "lifecycle_event_count": 4,
            "simulated_close_r": 1.5,
            "simulated_close_reason": "SIMULATED_TAKE_PROFIT",
            "decision_id": "dec_1",
            "risk_gate_id": "rg_1",
            "research_signal_id": "rs_1",
            "profile_id": "profile_a",
        }
    )

    assert record.decision_id == "dec_1"
    assert record.risk_gate_id == "rg_1"
    assert record.order_intent_id == "oi_1"
    assert record.execution_id == "exec_1"
    assert record.reconciliation_id.startswith("rec_")
    assert record.outcome_id.startswith("out_")
    assert record.feedback_cycle_id.startswith("fbc_")
    assert record.research_signal_id == "rs_1"
    assert record.paper_live_gap == "not_applicable"
