from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.registry.base_registry import load_registry_records
from crypto_ai_system.validation.paper_data_quality_gate import STATUS_PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY, build_paper_data_quality_gate_report
from crypto_ai_system.validation.valid_price_lineage_artifacts import (
    STATUS_VALID_PRICE_LINEAGE_RECORDED,
    persist_valid_price_lineage_artifacts,
)


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  version: step286_researchsignal_feature_lineage_fix\n"
        "storage:\n  registry_dir: storage/registries\n"
        "price_data:\n  enabled: true\n  directory: data/price_data/BINANCE_BTCUSDT_P\n  primary_timeframe: 1h\n  files:\n    1h: btcusdtp_1h.csv\n"
        "data:\n  canonical_symbol: BTC-PERP\n  timeframe: PT1H\n  limit: 500\n"
        "safety:\n  live_trading_enabled: false\n  testnet_signed_order_enabled: false\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[project]\nname='tmp-crypto-ai-system'\nversion='0.286.0'\n",
        encoding="utf-8",
    )


def _write_price_csv(root: Path) -> None:
    price_dir = root / "data" / "price_data" / "BINANCE_BTCUSDT_P"
    price_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    base = pd.Timestamp("2026-07-01T00:00:00Z")
    for i in range(80):
        ts = int((base + pd.Timedelta(hours=i)).timestamp())
        close = 100_000 + i * 10
        rows.append({
            "time": ts,
            "open": close - 5,
            "high": close + 20,
            "low": close - 20,
            "close": close,
            "Volume": 100 + i,
            "RSI": 50 + (i % 10),
            "CVD": i * 1.5,
        })
    pd.DataFrame(rows).to_csv(price_dir / "btcusdtp_1h.csv", index=False)


def test_phase2_1_generates_valid_price_lineage_and_gate_passes(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_price_csv(tmp_path)
    cfg = load_config(tmp_path)

    report = persist_valid_price_lineage_artifacts(cfg=cfg, project_root=tmp_path)

    assert report["status"] == STATUS_VALID_PRICE_LINEAGE_RECORDED
    assert report["passed"] is True
    assert report["paper_candidate_source"] is True
    assert report["live_candidate_eligible"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["order_submission_performed"] is False
    assert (tmp_path / "storage" / "latest" / "data_snapshot_manifest.json").exists()
    assert (tmp_path / "storage" / "latest" / "feature_store_manifest.json").exists()
    assert (tmp_path / "storage" / "latest" / "data_health_report.json").exists()

    gate = build_paper_data_quality_gate_report(project_root=tmp_path)
    assert gate["status"] == STATUS_PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY
    assert gate["passed"] is True
    assert gate["paper_candidate_allowed"] is True
    assert gate["live_candidate_eligible"] is False
    assert gate["lineage_checks"]["lineage_complete"] is True


def test_phase2_1_persists_append_only_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_price_csv(tmp_path)
    cfg = load_config(tmp_path)

    report = persist_valid_price_lineage_artifacts(cfg=cfg, project_root=tmp_path)

    latest_report = tmp_path / "storage" / "latest" / "valid_price_lineage_artifacts_report.json"
    latest_registry = tmp_path / "storage" / "latest" / "valid_price_lineage_artifacts_registry_record.json"
    registry = tmp_path / "storage" / "registries" / "valid_price_lineage_artifacts_registry.jsonl"
    assert latest_report.exists()
    assert latest_registry.exists()
    assert registry.exists()
    records = load_registry_records(registry)
    assert records[-1]["valid_price_lineage_artifacts_sha256"] == report["valid_price_lineage_artifacts_sha256"]


def test_phase2_1_current_project_uses_local_csv_without_live_unlock() -> None:
    report = persist_valid_price_lineage_artifacts()

    assert report["status"] == STATUS_VALID_PRICE_LINEAGE_RECORDED
    assert report["passed"] is True
    assert report["source_type"] == "local_valid_price_csv"
    assert report["paper_strategy_validation_input_ready"] is True
    assert report["live_candidate_eligible"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["order_submission_performed"] is False
    assert report["auto_promotion_allowed"] is False
