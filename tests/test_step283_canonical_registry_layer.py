from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_ai_system.config import load_config
from crypto_ai_system.registry.base_registry import RegistryIntegrityError, append_registry_record, load_registry_records, registry_path
from crypto_ai_system.registry.source_registry import build_source_registry_records, persist_source_registry_records


def _cfg(tmp_path: Path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "registries")
    return cfg


def _manifest() -> dict:
    return {
        "data_snapshot_id": "data_snapshot_step283",
        "data_snapshot_sha256": "a" * 64,
        "source_bundle_sha256": "b" * 64,
        "raw_frames": {
            "ohlcv_raw": {
                "rows": 3,
                "columns": ["timestamp", "close"],
                "frame_sha256": "c" * 64,
                "min_timestamp_utc": "2026-06-01T00:00:00Z",
                "max_timestamp_utc": "2026-06-01T02:00:00Z",
            }
        },
        "source_files": {},
        "source_status": {},
        "optional_data_health": {},
        "created_at_utc": "2026-06-30T00:00:00Z",
    }


def test_step283_append_only_registry_creates_and_loads_records(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    path = registry_path(cfg, "unit_registry")
    record = append_registry_record(
        path,
        {"value": 1, "created_at_utc": "2026-06-30T00:00:00Z"},
        registry_name="unit_registry",
        id_field="unit_id",
        hash_field="unit_sha256",
        id_prefix="unit",
    )

    rows = load_registry_records(path)
    assert len(rows) == 1
    assert rows[0]["unit_id"] == record["unit_id"]
    assert rows[0]["unit_sha256"] == record["unit_sha256"]
    assert rows[0]["registry_schema_version"] == "step283_canonical_registry_v1"


def test_step283_damaged_registry_fails_closed(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    path = registry_path(cfg, "damaged_registry")
    path.write_text("{not valid json}\n", encoding="utf-8")

    with pytest.raises(RegistryIntegrityError):
        append_registry_record(path, {"value": 1}, registry_name="damaged_registry")


def test_step283_source_registry_records_cover_required_price_and_optional_health(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    manifest = _manifest()
    manifest["optional_data_health"] = {
        "binance_futures": {
            "source": "binance_futures_public",
            "matrix_group": "extra_derivatives_features",
            "collector_status": "missing",
            "neutral_due_to_missing": True,
            "stale": False,
        }
    }

    records = build_source_registry_records(manifest)
    persisted = persist_source_registry_records(cfg, manifest)
    source_registry_path = registry_path(cfg, "source_registry")
    lines = [json.loads(line) for line in source_registry_path.read_text(encoding="utf-8").splitlines()]

    assert len(records) >= 2
    assert len(persisted) == len(records)
    assert len(lines) == len(records)
    assert any(r["required_or_optional"] == "required" and r["data_group"] == "price_structure" for r in records)
    assert any(r["neutral_due_to_missing"] is True and r["required_or_optional"] == "optional" for r in records)
