from __future__ import annotations

from pathlib import Path

import pandas as pd

from crypto_ai_system.config import load_config
from crypto_ai_system.registry.base_registry import load_registry_records
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from crypto_ai_system.validation.phase4_outcome_candidate_feedback import (
    STATUS_PHASE4_BLOCKED_REVIEW_ONLY,
    persist_phase4_outcome_candidate_feedback_report,
)
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  version: step286_researchsignal_feature_lineage_fix\n"
        "storage:\n  registry_dir: storage/registries\n"
        "price_data:\n  enabled: true\n  directory: data/price_data/BINANCE_BTCUSDT_P\n  primary_timeframe: 1h\n  files:\n    1h: btcusdtp_1h.csv\n"
        "data:\n  canonical_symbol: BTC-PERP\n  timeframe: PT1H\n  limit: 120\n"
        "research:\n  score_weights:\n    price_direction: 1.0\n    derivatives_positioning: 0.0\n    exchange_flow: 0.0\n    etf_flow: 0.0\n    stablecoin_liquidity: 0.0\n"
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


def test_phase4_records_blocked_review_only_candidate_feedback_when_sample_is_insufficient(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_bearish_price_csv(tmp_path)
    cfg = load_config(tmp_path)

    persist_valid_price_lineage_artifacts(cfg=cfg, project_root=tmp_path)
    persist_paper_data_quality_gate_report(cfg=cfg, project_root=tmp_path)
    persist_paper_strategy_validation_report(cfg=cfg, project_root=tmp_path)
    report = persist_phase4_outcome_candidate_feedback_report(cfg=cfg)

    assert report["status"] == STATUS_PHASE4_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["outcome_status"] == "OUTCOME_REVIEW_ONLY_OPEN_POSITION"
    assert report["performance_report_status"] == "PERFORMANCE_REPORT_REVIEW_ONLY_INSUFFICIENT_SAMPLE"
    assert report["candidate_profile_created"] is False
    assert report["candidate_profile_status"] == "rejected"
    assert "PERFORMANCE_REPORT_NOT_READY_FOR_CANDIDATE_PROFILE" in report["blockers"]
    assert "CANDIDATE_PROFILE_NOT_CREATED" in report["blockers"]
    assert report["next_action"] == "repeat_in_paper"
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["candidate_profile_applied"] is False
    assert report["settings_write_preview_applied"] is False
    assert report["auto_promotion_allowed"] is False
    assert report["external_order_submission_performed"] is False
    assert report["live_candidate_eligible"] is False

    latest = tmp_path / "storage" / "latest"
    for name in [
        "phase4_outcome_candidate_feedback_report.json",
        "phase4_outcome_candidate_feedback_registry_record.json",
        "performance_report.json",
        "candidate_profile.json",
        "settings_write_preview_guard_manifest.json",
    ]:
        assert (latest / name).exists(), name


def test_phase4_persists_append_only_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_bearish_price_csv(tmp_path)
    cfg = load_config(tmp_path)

    persist_valid_price_lineage_artifacts(cfg=cfg, project_root=tmp_path)
    persist_paper_data_quality_gate_report(cfg=cfg, project_root=tmp_path)
    persist_paper_strategy_validation_report(cfg=cfg, project_root=tmp_path)
    report = persist_phase4_outcome_candidate_feedback_report(cfg=cfg)

    registry = tmp_path / "storage" / "registries" / "phase4_outcome_candidate_feedback_registry.jsonl"
    assert registry.exists()
    records = load_registry_records(registry)
    assert records[-1]["phase4_outcome_candidate_feedback_sha256"] == report["phase4_outcome_candidate_feedback_sha256"]
    assert records[-1]["runtime_settings_mutated"] is False
    assert records[-1]["score_weights_mutated"] is False
    assert records[-1]["external_order_submission_performed"] is False


def test_phase4_current_project_records_review_only_feedback_without_live_unlock() -> None:
    persist_valid_price_lineage_artifacts()
    persist_paper_data_quality_gate_report()
    persist_paper_strategy_validation_report()
    report = persist_phase4_outcome_candidate_feedback_report()

    assert report["status"] in {
        "PHASE4_OUTCOME_CANDIDATE_BLOCKED_REVIEW_ONLY",
        "PHASE4_OUTCOME_CANDIDATE_RECORDED_REVIEW_ONLY",
    }
    assert report["review_only"] is True
    assert report["live_candidate_eligible"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["auto_promotion_allowed"] is False
    assert report["external_order_submission_performed"] is False
    assert report["signed_testnet_promotion_allowed"] is False
    assert report["testnet_order_submission_allowed_by_this_module"] is False
