from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.data.data_snapshot_manifest import build_data_snapshot_manifest
from crypto_ai_system.features.research_feature_matrix import build_research_feature_matrix
from crypto_ai_system.validation.paper_data_quality_gate import build_paper_data_quality_gate_report


def _cfg_with_price_age(max_age_sec: int = 3600):
    cfg = load_config(".")
    cfg.settings.setdefault("data", {}).setdefault("live_candidate", {})["max_price_age_sec"] = max_age_sec
    return cfg


def _price_frame(*, end: str = "2026-07-08T00:30:00Z") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": ["2026-07-08T00:00:00Z", end],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [10.0, 11.0],
        }
    )


def _all_optional_ok() -> dict[str, dict[str, object]]:
    return {
        "binance_futures": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False, "live_candidate_eligible": True},
        "coinmetrics_exchange_flow": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False, "live_candidate_eligible": True},
        "farside_etf_flow": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False, "live_candidate_eligible": True},
        "defillama_stablecoins": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False, "live_candidate_eligible": True},
    }


def test_phase_b_manifest_can_mark_fresh_real_price_and_optional_health_live_candidate_eligible() -> None:
    cfg = _cfg_with_price_age(3600)
    manifest = build_data_snapshot_manifest(
        {"btc_ohlcv_1h": _price_frame()},
        {"price": {"source": "approved_public_read_only_btc_price_csv", "ok": True}},
        cfg,
        optional_data_health=_all_optional_ok(),
        created_at_utc="2026-07-08T00:45:00Z",
    )

    assert manifest["data_quality_status"] == "valid"
    assert manifest["hard_required_sources_present"] is True
    assert manifest["price_source_stale"] is False
    assert manifest["price_source_age_sec"] == 900.0
    assert manifest["price_timestamp_start_utc"] == "2026-07-08T00:00:00Z"
    assert manifest["price_timestamp_end_utc"] == "2026-07-08T00:30:00Z"
    assert manifest["optional_data_health_summary"]["all_optional_sources_live_candidate_eligible"] is True
    assert manifest["live_candidate_block_reasons"] == []
    assert manifest["live_candidate_eligible"] is True


def test_phase_b_manifest_blocks_stale_price_for_live_candidate() -> None:
    cfg = _cfg_with_price_age(600)
    manifest = build_data_snapshot_manifest(
        {"btc_ohlcv_1h": _price_frame(end="2026-07-08T00:00:00Z")},
        {"price": {"source": "approved_public_read_only_btc_price_csv", "ok": True}},
        cfg,
        optional_data_health=_all_optional_ok(),
        created_at_utc="2026-07-08T01:00:01Z",
    )

    assert manifest["data_quality_status"] == "blocked_stale_price"
    assert manifest["price_source_stale"] is True
    assert manifest["live_candidate_eligible"] is False
    assert "STALE_PRICE_DATA_BLOCKS_LIVE_CANDIDATE" in manifest["live_candidate_block_reasons"]


def test_phase_b_manifest_blocks_mock_sample_fallback_synthetic_price_tokens() -> None:
    cfg = _cfg_with_price_age(3600)
    cases = [
        ("mock", "blocked_mock", "MOCK_PRICE_DATA_BLOCKS_LIVE_CANDIDATE"),
        ("sample", "blocked_sample", "SAMPLE_PRICE_DATA_BLOCKS_LIVE_CANDIDATE"),
        ("fallback", "blocked_fallback", "FALLBACK_PRICE_DATA_BLOCKS_LIVE_CANDIDATE"),
        ("synthetic", "blocked_synthetic", "SYNTHETIC_PRICE_DATA_BLOCKS_LIVE_CANDIDATE"),
    ]
    for token, expected_status, expected_reason in cases:
        manifest = build_data_snapshot_manifest(
            {"btc_ohlcv_1h": _price_frame()},
            {"price": {"source": f"{token}_price_source", "ok": True}},
            cfg,
            optional_data_health=_all_optional_ok(),
            created_at_utc="2026-07-08T00:45:00Z",
        )
        assert manifest["data_quality_status"] == expected_status
        assert manifest["live_candidate_eligible"] is False
        assert expected_reason in manifest["live_candidate_block_reasons"]


def test_phase_b_optional_missing_and_stale_are_explicitly_not_live_candidates() -> None:
    cfg = _cfg_with_price_age(3600)
    missing_health = _all_optional_ok()
    missing_health["farside_etf_flow"] = {
        "collector_status": "missing",
        "neutral_due_to_missing": True,
        "stale": False,
        "live_candidate_eligible": False,
    }
    missing_manifest = build_data_snapshot_manifest(
        {"btc_ohlcv_1h": _price_frame()},
        {"price": {"source": "approved_public_read_only_btc_price_csv", "ok": True}},
        cfg,
        optional_data_health=missing_health,
        created_at_utc="2026-07-08T00:45:00Z",
    )
    assert missing_manifest["data_quality_status"] == "valid_with_optional_missing"
    assert missing_manifest["optional_sources_missing"] == ["farside_etf_flow"]
    assert "OPTIONAL_DATA_MISSING_LIVE_CANDIDATE_BLOCKED" in missing_manifest["live_candidate_block_reasons"]
    assert missing_manifest["live_candidate_eligible"] is False

    stale_health = _all_optional_ok()
    stale_health["coinmetrics_exchange_flow"] = {
        "collector_status": "stale",
        "neutral_due_to_missing": False,
        "stale": True,
        "live_candidate_eligible": False,
    }
    stale_manifest = build_data_snapshot_manifest(
        {"btc_ohlcv_1h": _price_frame()},
        {"price": {"source": "approved_public_read_only_btc_price_csv", "ok": True}},
        cfg,
        optional_data_health=stale_health,
        created_at_utc="2026-07-08T00:45:00Z",
    )
    assert stale_manifest["data_quality_status"] == "valid_with_optional_stale"
    assert stale_manifest["stale_optional_sources"] == ["coinmetrics_exchange_flow"]
    assert "OPTIONAL_DATA_STALE_LIVE_CANDIDATE_BLOCKED" in stale_manifest["live_candidate_block_reasons"]
    assert stale_manifest["live_candidate_eligible"] is False


def test_phase_b_backtest_matrix_does_not_accept_future_optional_snapshot() -> None:
    cfg = load_config(".")
    base = pd.DataFrame(
        {
            "timestamp": ["2026-07-08T00:00:00Z", "2026-07-08T01:00:00Z", "2026-07-08T02:00:00Z"],
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [10.0, 11.0, 12.0],
        }
    )
    future_optional = pd.DataFrame(
        {
            "timestamp": ["2026-07-08T03:00:00Z"],
            "binance_derivatives_score": [0.9],
            "derivatives_signal": ["BULLISH"],
        }
    )

    backtest = build_research_feature_matrix(
        base,
        {"binance_derivatives_features": future_optional},
        cfg,
        mode="backtest",
    )
    live = build_research_feature_matrix(
        base,
        {"binance_derivatives_features": future_optional},
        cfg,
        mode="live",
    )

    assert backtest["binance_derivatives_score"].tolist() == [0.0, 0.0, 0.0]
    assert backtest["missing_optional_data_neutral"].all()
    assert live.iloc[-1]["binance_derivatives_score"] == 0.9
    assert live.iloc[-1]["feature_matrix_mode"] == "live"


def test_phase_b_paper_quality_gate_records_live_candidate_data_foundation_without_runtime_permission(tmp_path: Path) -> None:
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "settings.yaml").write_text(
        "project:\n  version: step286_researchsignal_feature_lineage_fix\n"
        "storage:\n  registry_dir: storage/registries\n"
        "safety:\n  live_trading_enabled: false\n  testnet_signed_order_enabled: false\n",
        encoding="utf-8",
    )
    optional = {
        "binance_futures": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False, "live_candidate_eligible": True},
        "coinmetrics": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False, "live_candidate_eligible": True},
        "farside_etf_flow": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False, "live_candidate_eligible": True},
        "defillama_stablecoin": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False, "live_candidate_eligible": True},
    }
    atomic_write_json(
        latest / "data_health_report.json",
        {
            "status": "HEALTHY",
            "allow_trading": False,
            "source_type": "approved_public_read_only_btc_price_csv",
            "data_quality": "valid",
            "is_synthetic": False,
            "is_fallback": False,
            "candle_count": 120,
            "latest_candle_time": "2026-07-08T00:30:00Z",
            "problems": [],
        },
    )
    atomic_write_json(
        latest / "data_snapshot_manifest.json",
        {
            "data_snapshot_id": "data_snapshot_live_foundation",
            "data_snapshot_sha256": "a" * 64,
            "source_bundle_sha256": "b" * 64,
            "hard_required_sources_present": True,
            "data_quality_status": "valid",
            "price_timestamp_start_utc": "2026-07-08T00:00:00Z",
            "price_timestamp_end_utc": "2026-07-08T00:30:00Z",
            "price_source_stale": False,
            "optional_data_health": optional,
            "live_candidate_eligibility_checks": {
                "hard_required_price_present": True,
                "price_timestamp_range_present": True,
                "price_source_fresh": True,
                "no_fallback_price": True,
                "no_synthetic_price": True,
                "no_sample_price": True,
                "no_mock_price": True,
                "optional_missing_count_zero": True,
                "optional_stale_count_zero": True,
                "all_optional_sources_live_candidate_eligible": True,
            },
            "live_candidate_eligible": True,
        },
    )
    atomic_write_json(
        latest / "feature_store_manifest.json",
        {
            "data_snapshot_id": "data_snapshot_live_foundation",
            "feature_snapshot_id": "feature_snapshot_live_foundation",
            "feature_matrix_sha256": "c" * 64,
            "source_bundle_sha256": "b" * 64,
            "optional_data_health": optional,
            "live_candidate_eligible": True,
            "fallback_used": False,
            "synthetic_used": False,
            "sample_used": False,
        },
    )

    report = build_paper_data_quality_gate_report(project_root=tmp_path)

    assert report["passed"] is True
    assert report["paper_candidate_allowed"] is True
    assert report["live_candidate_data_foundation_eligible"] is True
    assert report["live_candidate_data_foundation"]["eligible"] is True
    assert report["live_candidate_eligible"] is False
    assert report["runtime_permission_source"] is False
    assert report["order_submission_performed"] is False
