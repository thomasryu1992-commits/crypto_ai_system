from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from crypto_ai_system.config import load_config
from crypto_ai_system.data.data_snapshot_manifest import build_data_snapshot_manifest, persist_data_snapshot_registries
from crypto_ai_system.registry.base_registry import registry_path
from crypto_ai_system.registry.data_snapshot_registry import build_data_snapshot_registry_record, determine_data_quality_status


def _cfg(tmp_path: Path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "registries")
    return cfg


def _price_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": ["2026-06-01T00:00:00Z", "2026-06-01T01:00:00Z"],
            "close": [100.0, 101.0],
        }
    )


def test_step285_data_snapshot_manifest_adds_hardened_quality_fields(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    manifest = build_data_snapshot_manifest(
        {"ohlcv_raw": _price_frame()},
        {"binance_futures": {"enabled": False, "ok": False}},
        cfg,
        optional_data_health={
            "binance_futures": {
                "neutral_due_to_missing": True,
                "stale": False,
                "live_candidate_eligible": False,
                "collector_status": "disabled",
            }
        },
        created_at_utc="2026-06-30T00:00:00Z",
    )

    assert manifest["hard_required_sources_present"] is True
    assert manifest["optional_sources_missing"] == ["binance_futures"]
    assert manifest["missing_optional_source_count"] == 1
    assert manifest["data_quality_status"] == "valid_with_optional_missing"
    assert manifest["live_candidate_eligible"] is False
    assert manifest["data_snapshot_sha256"]


def test_step285_data_snapshot_registry_record_has_required_fields_and_status(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    manifest = build_data_snapshot_manifest({"ohlcv_raw": _price_frame()}, {}, cfg, created_at_utc="2026-06-30T00:00:00Z")
    outputs = persist_data_snapshot_registries(cfg, manifest)
    data_registry_path = registry_path(cfg, "data_snapshot_registry")
    source_registry_path = registry_path(cfg, "source_registry")

    rows = [json.loads(line) for line in data_registry_path.read_text(encoding="utf-8").splitlines()]
    source_rows = [json.loads(line) for line in source_registry_path.read_text(encoding="utf-8").splitlines()]
    record = rows[-1]

    assert outputs["data_snapshot_registry_record"]["data_snapshot_id"] == manifest["data_snapshot_id"]
    assert record["source_bundle_sha256"] == manifest["source_bundle_sha256"]
    assert record["hard_required_sources_present"] is True
    assert record["data_quality_status"] in {"valid", "valid_with_optional_missing"}
    assert record["source_ids"]
    assert len(source_rows) >= 1


def test_step285_data_quality_status_blocks_missing_price_and_flags_fallback() -> None:
    missing_price = {"raw_frames": {}, "source_status": {}, "optional_data_health": {}}
    fallback = {
        "raw_frames": {"ohlcv_raw": {"rows": 1}},
        "source_status": {"price": {"source": "fallback_price_data"}},
        "optional_data_health": {},
    }

    assert determine_data_quality_status(missing_price) == "blocked_missing_price"
    assert determine_data_quality_status(fallback) == "blocked_fallback"
    assert build_data_snapshot_registry_record(fallback)["fallback_flag"] is True
