from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from crypto_ai_system.config import load_config
from crypto_ai_system.registry.base_registry import registry_path
from crypto_ai_system.registry.market_thesis_registry import build_market_thesis_registry_record, persist_market_thesis_registry_record
from crypto_ai_system.research.market_thesis_note import build_market_thesis_note
from crypto_ai_system.research.research_bot import ResearchBot


def _cfg(tmp_path: Path | None = None):
    cfg = load_config(".")
    cfg.settings.setdefault("entry_policy", {})["bullish_threshold"] = 0.30
    cfg.settings.setdefault("entry_policy", {})["bearish_threshold"] = -0.30
    cfg.settings.setdefault("price_data", {})["include_multi_timeframe_context"] = False
    if tmp_path is not None:
        cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "registries")
        cfg.settings.setdefault("storage", {})["features_dir"] = str(tmp_path / "features")
    return cfg


def _snapshot() -> dict:
    return {
        "timestamp": "2026-06-30T00:00:00Z",
        "symbol": "BTC-PERP",
        "close": 108500.0,
        "score_total_score": 0.62,
        "score_structure": 0.32,
        "score_momentum": 0.41,
        "score_derivatives": 0.18,
        "exchange_flow_score": 0.27,
        "etf_flow_score": -0.12,
        "stablecoin_liquidity_score": 0.35,
        "binance_derivatives_score": 0.44,
        "market_condition": "BULLISH_TREND",
        "market_regime": "TRENDING",
        "mtf_bias": "BULLISH",
        "mtf_alignment_score": 0.55,
        "data_snapshot_id": "data_snapshot_step287",
        "data_snapshot_manifest_sha256": "d" * 64,
        "feature_snapshot_id": "feature_snapshot_step287",
        "feature_matrix_sha256": "f" * 64,
        "source_bundle_sha256": "b" * 64,
        "optional_data_health": {"binance_futures": {"collector_status": "ok"}},
        "missing_optional_source_count": 0,
        "stale_optional_source_count": 0,
        "live_candidate_eligible": False,
    }


def _condition() -> dict:
    return {
        "final_condition": "BULLISH_TREND",
        "volatility_state": "NORMAL",
        "derivatives_state": "SUPPORTIVE",
        "liquidity_state": "MIXED",
    }


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


def test_step287_market_thesis_note_preserves_lineage_and_review_only_safety(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    note = build_market_thesis_note(_snapshot(), _condition(), cfg)

    assert note["market_thesis_note_id"].startswith("market_thesis_note_")
    assert note["data_snapshot_id"] == "data_snapshot_step287"
    assert note["feature_snapshot_id"] == "feature_snapshot_step287"
    assert note["feature_matrix_sha256"] == "f" * 64
    assert note["source_bundle_sha256"] == "b" * 64
    assert note["long_arguments"]
    assert note["short_arguments"]
    assert note["neutral_arguments"]
    assert note["counterarguments"]
    assert note["invalidation_conditions"]
    assert "supporting_features" in note
    assert note["order_intent_created"] is False
    assert note["trade_approved"] is False
    assert note["runtime_settings_mutated"] is False
    assert note["score_weights_mutated"] is False


def test_step287_market_thesis_registry_appends_summary_record(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    note = build_market_thesis_note(_snapshot(), _condition(), cfg)
    record = build_market_thesis_registry_record(note)
    persisted = persist_market_thesis_registry_record(cfg, note)
    rows = [json.loads(line) for line in registry_path(cfg, "market_thesis_registry").read_text(encoding="utf-8").splitlines()]

    assert record["market_thesis_note_id"] == note["market_thesis_note_id"]
    assert persisted["market_thesis_note_id"] == note["market_thesis_note_id"]
    assert persisted["registry_name"] == "market_thesis_registry"
    assert len(rows) == 1
    assert rows[0]["market_thesis_note_sha256"] == note["market_thesis_note_sha256"]
    assert rows[0]["order_intent_created"] is False
    assert rows[0]["trade_approved"] is False


def test_step287_research_bot_creates_market_thesis_before_research_signal(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    data_manifest = {
        "data_snapshot_id": "data_snapshot_step287_bot",
        "data_snapshot_sha256": "d" * 64,
        "source_bundle_sha256": "b" * 64,
        "optional_data_health": {"binance_futures": {"collector_status": "ok"}},
        "missing_optional_source_count": 0,
        "stale_optional_source_count": 0,
        "live_candidate_eligible": False,
    }

    result = ResearchBot(cfg).analyze(
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

    note = result.market_thesis_note
    signal = result.research_signal

    assert note["market_thesis_note_id"] == result.snapshot["market_thesis_note_id"]
    assert signal["market_thesis_note_id"] == note["market_thesis_note_id"]
    assert signal["market_thesis_note_sha256"] == note["market_thesis_note_sha256"]
    assert note["data_snapshot_id"] == "data_snapshot_step287_bot"
    assert note["feature_snapshot_id"] == signal["feature_snapshot_id"]
    assert note["feature_matrix_sha256"] == signal["feature_matrix_sha256"]
    assert note["source_bundle_sha256"] == signal["source_bundle_sha256"]
    assert note["order_intent_created"] is False
    assert signal["entry_allowed"] in {True, False}
