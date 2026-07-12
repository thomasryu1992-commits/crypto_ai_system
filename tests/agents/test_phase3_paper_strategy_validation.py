from __future__ import annotations

from pathlib import Path

import pandas as pd

from crypto_ai_system.config import load_config
from crypto_ai_system.registry.base_registry import load_registry_records
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import (
    STATUS_PAPER_STRATEGY_VALIDATION_RECORDED_REVIEW_ONLY,
    persist_paper_strategy_validation_report,
)
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  version: step286_researchsignal_feature_lineage_fix\n"
        "storage:\n  registry_dir: storage/registries\n"
        "price_data:\n  enabled: true\n  directory: data/price_data/BINANCE_BTCUSDT_P\n  primary_timeframe: 1h\n  files:\n    1h: btcusdtp_1h.csv\n"
        "data:\n  canonical_symbol: BTC-PERP\n  timeframe: PT1H\n  limit: 120\n"
        "trading:\n  use_research_signal_gate: true\n"
        "safety:\n  live_trading_enabled: false\n  testnet_signed_order_enabled: false\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[project]\nname='tmp-crypto-ai-system'\nversion='0.286.0'\n",
        encoding="utf-8",
    )


def _write_bearish_price_csv(root: Path) -> None:
    price_dir = root / "data" / "price_data" / "BINANCE_BTCUSDT_P"
    price_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    base = pd.Timestamp("2026-07-01T00:00:00Z")
    price = 100_000.0
    for i in range(120):
        ts = int((base + pd.Timedelta(hours=i)).timestamp())
        price -= 15.0
        rows.append(
            {
                "time": ts,
                "open": price + 8,
                "high": price + 30,
                "low": price - 30,
                "close": price,
                "Volume": 1000 + i,
                "RSI": max(25, 55 - i * 0.1),
                "CVD": -i * 2.5,
            }
        )
    pd.DataFrame(rows).to_csv(price_dir / "btcusdtp_1h.csv", index=False)


def test_phase3_builds_full_paper_validation_chain_without_live_side_effects(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_bearish_price_csv(tmp_path)
    cfg = load_config(tmp_path)

    persist_valid_price_lineage_artifacts(cfg=cfg, project_root=tmp_path)
    persist_paper_data_quality_gate_report(cfg=cfg, project_root=tmp_path)
    report = persist_paper_strategy_validation_report(cfg=cfg, project_root=tmp_path)

    assert report["status"] == STATUS_PAPER_STRATEGY_VALIDATION_RECORDED_REVIEW_ONLY
    assert report["passed"] is True
    assert report["paper_data_quality_gate_status"] == "PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY"
    assert report["pre_order_risk_gate_status"] == "PASS_PAPER"
    assert report["pre_order_risk_gate_approved"] is True
    assert report["paper_execution_status"] == "PAPER_PENDING_RECONCILIATION"
    assert report["reconciliation_status"] == "RECONCILED"
    assert report["paper_stage_chain_complete"] is True
    assert report["external_order_submission_performed"] is False
    assert report["live_order_executed"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["auto_promotion_allowed"] is False

    latest = tmp_path / "storage" / "latest"
    for name in [
        "paper_strategy_validation_report.json",
        "research_signal.json",
        "signal_qa_report.json",
        "paper_trade_decision.json",
        "pre_order_risk_gate_report.json",
        "paper_order_intent.json",
        "paper_execution_record.json",
        "paper_reconciliation_record.json",
        "outcome_analytics_record.json",
    ]:
        assert (latest / name).exists(), name


def test_phase3_persists_append_only_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_bearish_price_csv(tmp_path)
    cfg = load_config(tmp_path)

    persist_valid_price_lineage_artifacts(cfg=cfg, project_root=tmp_path)
    persist_paper_data_quality_gate_report(cfg=cfg, project_root=tmp_path)
    report = persist_paper_strategy_validation_report(cfg=cfg, project_root=tmp_path)

    registry = tmp_path / "storage" / "registries" / "paper_strategy_validation_registry.jsonl"
    assert registry.exists()
    records = load_registry_records(registry)
    assert records[-1]["paper_strategy_validation_sha256"] == report["paper_strategy_validation_sha256"]
    assert records[-1]["paper_stage_chain_complete"] is True
    assert records[-1]["external_order_submission_performed"] is False


def test_phase3_current_project_runs_review_only_chain() -> None:
    report = persist_paper_strategy_validation_report()

    assert report["status"] == STATUS_PAPER_STRATEGY_VALIDATION_RECORDED_REVIEW_ONLY
    assert report["passed"] is True
    assert report["paper_stage_chain_complete"] is True
    assert report["live_candidate_eligible"] is False
    assert report["signed_testnet_unlock_authority"] is False
    assert report["live_execution_unlock_authority"] is False
    assert report["external_order_submission_performed"] is False
    assert report["live_order_executed"] is False
