from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from crypto_ai_system.config import load_config
from crypto_ai_system.data.data_snapshot_manifest import (
    annotate_feature_frames_with_optional_health,
    build_data_snapshot_manifest,
    build_optional_data_health,
)
from crypto_ai_system.features.research_feature_matrix import (
    build_research_feature_matrix,
    persist_feature_store_outputs,
)
from crypto_ai_system.research.research_signal_builder import build_research_signal
from crypto_ai_system.trading.pre_order_risk_gate import evaluate_pre_order_risk_gate


def test_step270_data_snapshot_manifest_records_optional_health_and_hashes(tmp_path: Path) -> None:
    cfg = load_config(".")
    cfg.settings.setdefault("additional_data", {}).setdefault("health", {})["max_age_sec"] = 10_000
    raw_frames = {
        "binance_open_interest_hist": pd.DataFrame({
            "timestamp": ["2026-06-30T00:00:00Z"],
            "open_interest": [100.0],
            "source": ["binance_futures_public"],
        })
    }
    status = {
        "binance_futures": {"enabled": True, "ok": True, "source": "binance_futures_public", "frames": {"binance_open_interest_hist": 1}},
        "coinmetrics_exchange_flow": {"enabled": True, "ok": False, "source": "coinmetrics_community", "errors": {"api": "missing"}},
        "farside_etf_flow": {"enabled": False, "ok": True, "source": "farside_etf_flow", "reason": "manual_csv_disabled"},
        "defillama_stablecoins": {"enabled": True, "ok": False, "source": "defillama_stablecoins", "errors": {"api": "timeout"}},
    }
    source_file = tmp_path / "binance.csv"
    raw_frames["binance_open_interest_hist"].to_csv(source_file, index=False)

    health = build_optional_data_health(status, raw_frames, cfg, now_utc="2026-06-30T01:00:00Z")
    manifest = build_data_snapshot_manifest(
        raw_frames,
        status,
        cfg,
        source_files={"binance_open_interest_hist": str(source_file)},
        optional_data_health=health,
        created_at_utc="2026-06-30T01:00:00Z",
    )

    assert manifest["version"] == "step270_raw_data_snapshot_manifest_v1"
    assert manifest["data_snapshot_id"].startswith("data_snapshot_")
    assert manifest["data_snapshot_sha256"]
    assert manifest["source_bundle_sha256"]
    assert manifest["source_files"]["binance_open_interest_hist"]["sha256"]
    assert manifest["optional_data_health"]["binance_futures"]["collector_status"] == "ok"
    assert manifest["optional_data_health"]["binance_futures"]["source_age_sec"] == 3600.0
    assert manifest["optional_data_health"]["coinmetrics_exchange_flow"]["neutral_due_to_missing"] is True
    assert manifest["missing_optional_source_count"] >= 2
    assert manifest["live_candidate_eligible"] is False


def test_step270_optional_health_is_carried_into_feature_matrix() -> None:
    cfg = load_config(".")
    base = pd.DataFrame({
        "timestamp": ["2026-06-30T00:00:00Z"],
        "open": [100.0],
        "high": [101.0],
        "low": [99.0],
        "close": [100.0],
        "volume": [1.0],
    })
    feature = pd.DataFrame({
        "timestamp": ["2026-06-30T00:00:00Z"],
        "binance_derivatives_score": [0.1],
        "derivatives_signal": ["NEUTRAL"],
    })
    health = {
        "binance_futures": {
            "matrix_group": "extra_derivatives_features",
            "collector_status": "ok",
            "collector_error": None,
            "source_age_sec": 60.0,
            "stale": False,
            "neutral_due_to_missing": False,
            "last_success_utc": "2026-06-30T00:00:00Z",
            "live_candidate_eligible": True,
        }
    }
    frames = annotate_feature_frames_with_optional_health({"binance_derivatives_features": feature}, health)
    matrix = build_research_feature_matrix(base, frames, cfg, mode="live")
    row = matrix.iloc[-1].to_dict()

    assert row["extra_derivatives_features_collector_status"] == "ok"
    assert row["extra_derivatives_features_source_age_sec"] == 60.0
    assert row["extra_derivatives_features_neutral_due_to_missing"] is False
    assert row["extra_derivatives_features_live_candidate_eligible"] is True
    assert row["missing_optional_data_neutral"] is True  # other optional groups are still missing
    assert row["live_candidate_eligible"] is False


def test_step270_feature_store_manifest_references_data_snapshot(tmp_path: Path) -> None:
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["features_dir"] = str(tmp_path / "features")
    data_manifest = {
        "data_snapshot_id": "data_snapshot_test",
        "data_snapshot_sha256": "abc123",
        "source_bundle_sha256": "bundle123",
        "optional_data_health": {"binance_futures": {"collector_status": "ok"}},
        "missing_optional_source_count": 0,
        "stale_optional_source_count": 0,
        "live_candidate_eligible": True,
    }
    data_manifest_path = tmp_path / "data_snapshot_manifest.json"
    data_manifest_path.write_text(json.dumps(data_manifest, sort_keys=True), encoding="utf-8")
    matrix = pd.DataFrame({"timestamp": ["2026-06-30T00:00:00Z"], "close": [100.0], "missing_optional_data_neutral": [False]})

    written = persist_feature_store_outputs(
        cfg,
        research_feature_matrix_live=matrix,
        data_snapshot_manifest=data_manifest,
        data_snapshot_manifest_path=data_manifest_path,
    )
    manifest = json.loads(Path(written["research_feature_matrix_live_manifest_json"]).read_text(encoding="utf-8"))

    assert manifest["version"] == "step270_feature_store_manifest_with_data_snapshot_v1"
    assert manifest["data_snapshot_id"] == "data_snapshot_test"
    assert manifest["data_snapshot_manifest_sha256"] == "abc123"
    assert manifest["source_bundle_sha256"] == "bundle123"
    assert manifest["optional_data_health"]["binance_futures"]["collector_status"] == "ok"
    assert any(src.get("artifact_role") == "data_snapshot_manifest" for src in manifest["source_files"])


def test_step270_research_signal_carries_data_snapshot_health() -> None:
    cfg = load_config(".")
    snapshot = {
        "timestamp": "2026-06-30T00:00:00Z",
        "symbol": "BTC-PERP",
        "score_total_score": 0.8,
        "market_condition": "BULLISH_TREND",
        "data_source": "extended",
        "data_snapshot_id": "data_snapshot_test",
        "feature_snapshot_id": "feature_snapshot_test",
        "feature_matrix_sha256": "feature_hash",
        "source_bundle_sha256": "bundle_hash",
        "data_snapshot_manifest_sha256": "data_manifest_hash",
        "optional_data_health": {"binance_futures": {"collector_status": "ok"}},
        "missing_optional_data_neutral": False,
        "stale_optional_data": False,
        "live_candidate_eligible": True,
    }
    signal = build_research_signal(snapshot, {"final_condition": "BULLISH_TREND"}, cfg, source="extended")

    assert signal["signal_version"] == "research_signal_lineage_step270_data_snapshot_health_chain"
    assert signal["data_snapshot_id"] == "data_snapshot_test"
    assert signal["data_snapshot_manifest_sha256"] == "data_manifest_hash"
    assert signal["optional_data_health"]["binance_futures"]["collector_status"] == "ok"
    assert signal["trade_permission"]["live_candidate_eligible"] is True


def test_step270_pre_order_gate_blocks_missing_optional_data_for_live_candidate() -> None:
    result = evaluate_pre_order_risk_gate(
        decision={"decision_id": "decision_1", "side": "LONG"},
        research_signal={
            "research_signal_id": "signal_1",
            "profile_id": "profile_1",
            "trade_permission": {"allow_long": True, "allow_short": False, "allow_new_position": True, "risk_level": "normal"},
            "missing_optional_data_neutral": True,
            "stale_optional_data": False,
            "live_candidate_eligible": False,
        },
        profile={"profile_id": "profile_1", "approved": True},
        runtime_state={"open_positions": 0, "daily_pnl_r": 0, "consecutive_losses": 0, "api_error_rate": 0, "manual_kill_switch": False},
        market_state={"spread_bps": 1, "slippage_bps": 1},
        gate_config={"stage": "live_canary"},
    )

    assert result.approved is False
    assert result.risk_level == "blocked"
    assert "OPTIONAL_DATA_MISSING_LIVE_CANDIDATE_BLOCKED" in result.block_reasons
    assert "OPTIONAL_DATA_HEALTH_LIVE_CANDIDATE_BLOCKED" in result.block_reasons
