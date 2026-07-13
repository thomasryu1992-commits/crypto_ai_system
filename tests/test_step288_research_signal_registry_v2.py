from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from crypto_ai_system.config import load_config
from crypto_ai_system.registry.base_registry import registry_path
from crypto_ai_system.registry.research_signal_registry import build_research_signal_registry_record, persist_research_signal_registry_record
from crypto_ai_system.research.raw_score_pipeline import run_raw_to_score_pipeline
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


def _signal() -> dict:
    return {
        "signal_id": "signal_step288",
        "research_signal_id": "signal_step288",
        "signal_version": "research_signal_lineage_step270_data_snapshot_health_chain",
        "version": "research_signal_v2_step259_weight_calibration_permission_distribution",
        "profile_id": "default_review_profile",
        "profile_version": "v1",
        "config_version": "step286_researchsignal_feature_lineage_fix",
        "data_snapshot_id": "data_snapshot_step288",
        "data_snapshot_manifest_sha256": "d" * 64,
        "feature_snapshot_id": "feature_snapshot_step288",
        "feature_matrix_sha256": "f" * 64,
        "source_bundle_sha256": "b" * 64,
        "market_thesis_note_id": "market_thesis_note_step288",
        "market_thesis_note_sha256": "m" * 64,
        "optional_data_health": {"binance_futures": {"collector_status": "ok"}},
        "missing_optional_source_count": 0,
        "stale_optional_source_count": 0,
        "live_candidate_eligible": False,
        "entry_side": "LONG",
        "entry_allowed": True,
        "entry_confidence": 0.62,
        "block_reasons": [],
        "score_components": {
            "price": 0.73,
            "derivatives": 0.15,
            "exchange_flow": 0.22,
            "etf_flow": -0.1,
            "stablecoin_liquidity": 0.31,
        },
        "trade_permission": {"risk_level": "normal", "block_reasons": [], "allow_long": True},
        "data_source": "extended",
        "data_source_role": "primary_price",
        "data_quality_status": "valid_with_optional_missing",
        "created_at_utc": "2026-06-30T00:00:00Z",
    }


def test_step288_research_signal_registry_record_preserves_required_lineage() -> None:
    record = build_research_signal_registry_record(_signal())

    assert record["research_signal_id"] == "signal_step288"
    assert record["data_snapshot_id"] == "data_snapshot_step288"
    assert record["feature_snapshot_id"] == "feature_snapshot_step288"
    assert record["feature_matrix_sha256"] == "f" * 64
    assert record["source_bundle_sha256"] == "b" * 64
    assert record["market_thesis_note_id"] == "market_thesis_note_step288"
    assert record["permission_result"] == "allow_long"
    assert record["price_direction_score"] == 0.73
    assert record["derivatives_positioning_score"] == 0.15
    assert record["exchange_flow_score"] == 0.22
    assert record["etf_flow_score"] == -0.1
    assert record["stablecoin_liquidity_score"] == 0.31
    assert record["order_intent_created"] is False
    assert record["trade_approved"] is False
    assert record["runtime_settings_mutated"] is False
    assert record["score_weights_mutated"] is False


def test_step288_research_signal_registry_appends_canonical_jsonl(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    persisted = persist_research_signal_registry_record(cfg, _signal())
    rows = [json.loads(line) for line in registry_path(cfg, "research_signal_registry").read_text(encoding="utf-8").splitlines()]

    assert persisted["registry_name"] == "research_signal_registry"
    assert persisted["registry_schema_version"].startswith("step283")
    assert len(rows) == 1
    assert rows[0]["research_signal_id"] == "signal_step288"
    assert rows[0]["research_signal_registry_record_sha256"]
    assert rows[0]["neutral_due_to_missing"] is False


def test_step288_research_bot_signal_can_be_persisted_to_registry(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    data_manifest = {
        "data_snapshot_id": "data_snapshot_step288_bot",
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
    persisted = persist_research_signal_registry_record(cfg, result.research_signal)

    assert persisted["research_signal_id"] == result.research_signal["research_signal_id"]
    assert persisted["data_snapshot_id"] == "data_snapshot_step288_bot"
    assert persisted["feature_snapshot_id"] == result.research_signal["feature_snapshot_id"]
    assert persisted["feature_matrix_sha256"] == result.research_signal["feature_matrix_sha256"]
    assert persisted["source_bundle_sha256"] == "b" * 64
    assert persisted["market_thesis_note_id"] == result.market_thesis_note["market_thesis_note_id"]
    assert persisted["permission_result"] in {
        "allow_long",
        "allow_short",
        "reduce_long",
        "reduce_short",
        "block_long",
        "block_short",
        "neutral",
        "review_only",
    }


def test_step288_raw_pipeline_writes_latest_and_registry_record(tmp_path: Path) -> None:
    cfg = replace(_cfg(tmp_path), root=tmp_path)
    cfg.settings.setdefault("data", {})["use_mock_data"] = True
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["features_dir"] = str(tmp_path / "storage" / "features")

    payload = run_raw_to_score_pipeline(cfg)
    latest_record = tmp_path / "storage" / "latest" / "research_signal_registry_record.json"
    registry_file = tmp_path / "storage" / "registries" / "research_signal_registry.jsonl"

    assert payload["research_signal_registry"]["research_signal_id"] == payload["research_signal"]["research_signal_id"]
    assert latest_record.exists()
    assert registry_file.exists()
    row = json.loads(registry_file.read_text(encoding="utf-8").splitlines()[-1])
    assert row["research_signal_id"] == payload["research_signal"]["research_signal_id"]
    assert row["data_snapshot_id"] == payload["research_signal"]["data_snapshot_id"]
    assert row["feature_snapshot_id"] == payload["research_signal"]["feature_snapshot_id"]
    assert row["feature_matrix_sha256"] == payload["research_signal"]["feature_matrix_sha256"]
    assert row["source_bundle_sha256"] == payload["research_signal"]["source_bundle_sha256"]
    assert row["order_intent_created"] is False
    assert row["trade_approved"] is False
