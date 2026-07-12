from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from crypto_ai_system.config import load_config
from crypto_ai_system.features.research_feature_matrix import build_feature_store_manifest, persist_feature_store_outputs
from crypto_ai_system.research.research_bot import ResearchBot


def _price_frame(rows: int = 120) -> pd.DataFrame:
    ts = pd.date_range("2026-06-01 00:00:00+00:00", periods=rows, freq="h")
    close = [100_000 + i * 80 + (300 if i % 6 in {1, 2, 3} else -300) for i in range(rows)]
    return pd.DataFrame(
        {
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S+00:00"),
            "symbol": "BTC-PERP",
            "timeframe": "PT1H",
            "exchange": "extended",
            "exchange_market": "BTC-USD",
            "open": [c - 30 for c in close],
            "high": [c + 120 for c in close],
            "low": [c - 150 for c in close],
            "close": close,
            "volume": [1000 + i for i in range(rows)],
        }
    )


def _derivatives_frame(rows: int = 120) -> pd.DataFrame:
    ts = pd.date_range("2026-06-01 00:00:00+00:00", periods=rows, freq="h")
    return pd.DataFrame(
        {
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S+00:00"),
            "funding_rate": [0.0001] * rows,
            "open_interest": [1_000_000 + i * 2000 for i in range(rows)],
            "open_interest_base": [10_000 + i * 10 for i in range(rows)],
            "oi_change_pct": [0.01] * rows,
            "long_liquidation": [0.0] * rows,
            "short_liquidation": [0.0] * rows,
        }
    )


def _cfg(tmp_path: Path | None = None):
    cfg = load_config(".")
    cfg.settings.setdefault("entry_policy", {})["bullish_threshold"] = 0.30
    cfg.settings.setdefault("entry_policy", {})["bearish_threshold"] = -0.30
    cfg.settings.setdefault("price_data", {})["include_multi_timeframe_context"] = False
    if tmp_path is not None:
        cfg.settings.setdefault("storage", {})["features_dir"] = str(tmp_path / "features")
    return cfg


def test_step286_research_bot_signal_carries_feature_lineage_before_persistence(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    data_manifest = {
        "data_snapshot_id": "data_snapshot_step286",
        "data_snapshot_sha256": "d" * 64,
        "source_bundle_sha256": "b" * 64,
        "optional_data_health": {"binance_futures": {"collector_status": "ok"}},
        "missing_optional_source_count": 0,
        "stale_optional_source_count": 0,
        "live_candidate_eligible": True,
    }

    bot = ResearchBot(cfg)
    result = bot.analyze(
        _price_frame(),
        _derivatives_frame(),
        orderbook={
            "bid_price": 109_490,
            "ask_price": 109_510,
            "spread_bps": 2,
            "data_snapshot_manifest": data_manifest,
            "optional_data_health": data_manifest["optional_data_health"],
        },
        source="extended",
    )

    signal = result.research_signal
    snapshot = result.snapshot
    manifest = snapshot["feature_snapshot_manifest"]

    assert signal["data_snapshot_id"] == "data_snapshot_step286"
    assert signal["feature_snapshot_id"] == manifest["feature_snapshot_id"]
    assert signal["feature_matrix_sha256"] == manifest["feature_matrix_sha256"]
    assert signal["source_bundle_sha256"] == "b" * 64
    assert signal["feature_snapshot_id"]
    assert signal["feature_matrix_sha256"]
    assert signal["research_signal_id"] == signal["signal_id"]
    assert "None" not in signal["research_signal_id"]


def test_step286_feature_snapshot_id_is_stable_before_and_after_persistence(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    data_manifest = {
        "data_snapshot_id": "data_snapshot_step286_stable",
        "data_snapshot_sha256": "e" * 64,
        "source_bundle_sha256": "c" * 64,
        "optional_data_health": {},
        "missing_optional_source_count": 0,
        "stale_optional_source_count": 0,
        "live_candidate_eligible": True,
    }
    matrix = pd.DataFrame(
        {
            "timestamp": ["2026-06-30T00:00:00Z"],
            "close": [100.0],
            "missing_optional_data_neutral": [False],
        }
    )

    in_memory = build_feature_store_manifest(matrix, data_snapshot_manifest=data_manifest)
    written = persist_feature_store_outputs(cfg, research_feature_matrix_live=matrix, data_snapshot_manifest=data_manifest)
    persisted = json.loads(Path(written["research_feature_matrix_live_manifest_json"]).read_text(encoding="utf-8"))

    assert in_memory["feature_snapshot_id"] == persisted["feature_snapshot_id"]
    assert in_memory["feature_matrix_sha256"] == persisted["feature_matrix_sha256"]
    assert in_memory["data_snapshot_id"] == persisted["data_snapshot_id"]
    assert in_memory["source_bundle_sha256"] == persisted["source_bundle_sha256"]


def test_step286_latest_signal_lineage_fields_can_be_materialized(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    bot = ResearchBot(cfg)
    result = bot.analyze(
        _price_frame(),
        _derivatives_frame(),
        orderbook={"bid_price": 109_490, "ask_price": 109_510, "spread_bps": 2},
        source="extended",
    )

    signal = result.research_signal
    for key in ["data_snapshot_id", "feature_snapshot_id", "feature_matrix_sha256", "source_bundle_sha256"]:
        assert signal.get(key), key
        assert signal.get(key) is not None
