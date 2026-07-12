from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.registry.base_registry import load_registry_records
from crypto_ai_system.validation.paper_data_quality_gate import (
    STATUS_PAPER_DATA_QUALITY_BLOCKED_REVIEW_ONLY,
    STATUS_PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY,
    build_paper_data_quality_gate_report,
    persist_paper_data_quality_gate_report,
)


def _write_min_config(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  version: step286_researchsignal_feature_lineage_fix\n"
        "storage:\n  registry_dir: storage/registries\n"
        "safety:\n  live_trading_enabled: false\n  testnet_signed_order_enabled: false\n",
        encoding="utf-8",
    )


def _write_valid_data_evidence(root: Path) -> None:
    latest = root / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        latest / "data_health_report.json",
        {
            "status": "HEALTHY",
            "allow_trading": False,
            "source_type": "price_data_research",
            "data_quality": "valid",
            "is_synthetic": False,
            "is_fallback": False,
            "candle_count": 120,
            "latest_candle_time": "2026-07-01T09:00:00+00:00",
            "problems": [],
        },
    )
    optional = {
        "binance_futures": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False},
        "coinmetrics": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False},
        "farside_etf_flow": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False},
        "defillama_stablecoin": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False},
    }
    atomic_write_json(
        latest / "data_snapshot_manifest.json",
        {
            "data_snapshot_id": "data_snapshot_valid",
            "data_snapshot_sha256": "a" * 64,
            "source_bundle_sha256": "b" * 64,
            "hard_required_sources_present": True,
            "optional_data_health": optional,
        },
    )
    atomic_write_json(
        latest / "feature_store_manifest.json",
        {
            "data_snapshot_id": "data_snapshot_valid",
            "feature_snapshot_id": "feature_snapshot_valid",
            "feature_matrix_sha256": "c" * 64,
            "source_bundle_sha256": "b" * 64,
            "optional_data_health": optional,
        },
    )


def test_phase2_blocks_synthetic_fallback_evidence(tmp_path: Path) -> None:
    _write_min_config(tmp_path)
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        latest / "data_health_report.json",
        {
            "status": "UNHEALTHY",
            "allow_trading": False,
            "problems": ["fallback_data_source_blocks_trading", "synthetic_data_source_blocks_trading"],
            "source_type": "synthetic_fallback",
            "data_quality": "synthetic",
            "is_synthetic": True,
            "is_fallback": True,
            "candle_count": 120,
            "latest_candle_time": "2026-07-01T09:00:00+00:00",
        },
    )

    report = build_paper_data_quality_gate_report(project_root=tmp_path)

    assert report["status"] == STATUS_PAPER_DATA_QUALITY_BLOCKED_REVIEW_ONLY
    assert report["passed"] is False
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["paper_candidate_allowed"] is False
    assert report["live_candidate_eligible"] is False
    assert "FALLBACK_PRICE_DATA_BLOCKS_PAPER_CANDIDATE" in report["block_reasons"]
    assert "SYNTHETIC_PRICE_DATA_BLOCKS_PAPER_CANDIDATE" in report["block_reasons"]
    assert "INCOMPLETE_DATA_FEATURE_LINEAGE" in report["block_reasons"]


def test_phase2_valid_price_and_lineage_passes_review_only(tmp_path: Path) -> None:
    _write_min_config(tmp_path)
    _write_valid_data_evidence(tmp_path)

    report = build_paper_data_quality_gate_report(project_root=tmp_path)

    assert report["status"] == STATUS_PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY
    assert report["passed"] is True
    assert report["paper_candidate_allowed"] is True
    assert report["live_candidate_eligible"] is False
    assert report["runtime_permission_source"] is False
    assert report["order_submission_performed"] is False
    assert report["lineage_checks"]["lineage_complete"] is True
    assert report["missing_optional_sources"] == []


def test_phase2_missing_optional_requires_explicit_neutral(tmp_path: Path) -> None:
    _write_min_config(tmp_path)
    _write_valid_data_evidence(tmp_path)
    latest = tmp_path / "storage" / "latest"
    manifest = {
        "data_snapshot_id": "data_snapshot_valid",
        "data_snapshot_sha256": "a" * 64,
        "source_bundle_sha256": "b" * 64,
        "hard_required_sources_present": True,
        "optional_data_health": {
            "binance_futures": {"collector_status": "error", "stale": False},
            "coinmetrics": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False},
            "farside_etf_flow": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False},
            "defillama_stablecoin": {"collector_status": "ok", "neutral_due_to_missing": False, "stale": False},
        },
    }
    atomic_write_json(latest / "data_snapshot_manifest.json", manifest)
    feature = {
        "data_snapshot_id": "data_snapshot_valid",
        "feature_snapshot_id": "feature_snapshot_valid",
        "feature_matrix_sha256": "c" * 64,
        "source_bundle_sha256": "b" * 64,
        "optional_data_health": manifest["optional_data_health"],
    }
    atomic_write_json(latest / "feature_store_manifest.json", feature)

    report = build_paper_data_quality_gate_report(project_root=tmp_path)

    assert report["status"] == STATUS_PAPER_DATA_QUALITY_BLOCKED_REVIEW_ONLY
    assert "OPTIONAL_MISSING_WITHOUT_EXPLICIT_NEUTRAL:binance_futures" in report["block_reasons"]


def test_phase2_persists_latest_and_append_only_registry(tmp_path: Path) -> None:
    _write_min_config(tmp_path)
    _write_valid_data_evidence(tmp_path)
    cfg = load_config(tmp_path)

    report = persist_paper_data_quality_gate_report(cfg=cfg, project_root=tmp_path)

    assert report["status"] == STATUS_PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY
    latest_report = tmp_path / "storage" / "latest" / "paper_data_quality_gate_report.json"
    latest_registry_record = tmp_path / "storage" / "latest" / "paper_data_quality_gate_registry_record.json"
    registry = tmp_path / "storage" / "registries" / "paper_data_quality_gate_registry.jsonl"
    assert latest_report.exists()
    assert latest_registry_record.exists()
    assert registry.exists()
    records = load_registry_records(registry)
    assert records[-1]["paper_data_quality_gate_sha256"] == report["paper_data_quality_gate_sha256"]
