from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.quality.signal_qa import (
    BLOCK_FALLBACK_OR_SYNTHETIC,
    BLOCK_INVALID_LINEAGE,
    BLOCK_LEGACY_FALLBACK,
    BLOCK_MISSING_SIGNAL,
    BLOCK_STALE_DATA,
    PASS_PAPER_ONLY,
    PASS_REVIEW_ONLY,
    persist_signal_qa_report,
    validate_research_signal_quality,
)
from crypto_ai_system.registry.base_registry import registry_path
from crypto_ai_system.registry.research_signal_registry import build_research_signal_registry_record
from crypto_ai_system.research.raw_score_pipeline import run_raw_to_score_pipeline


def _cfg(tmp_path: Path | None = None):
    cfg = load_config(".")
    cfg.settings.setdefault("entry_policy", {})["bullish_threshold"] = 0.30
    cfg.settings.setdefault("entry_policy", {})["bearish_threshold"] = -0.30
    cfg.settings.setdefault("price_data", {})["include_multi_timeframe_context"] = False
    if tmp_path is not None:
        cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
        cfg.settings.setdefault("storage", {})["features_dir"] = str(tmp_path / "storage" / "features")
    return cfg


def _signal(**overrides) -> dict:
    signal = {
        "signal_id": "signal_step289",
        "research_signal_id": "signal_step289",
        "signal_version": "research_signal_lineage_step270_data_snapshot_health_chain",
        "version": "research_signal_v2_step259_weight_calibration_permission_distribution",
        "profile_id": "default_review_profile",
        "profile_version": "v1",
        "config_version": "step286_researchsignal_feature_lineage_fix",
        "data_snapshot_id": "data_snapshot_step289",
        "data_snapshot_manifest_sha256": "d" * 64,
        "feature_snapshot_id": "feature_snapshot_step289",
        "feature_matrix_sha256": "f" * 64,
        "source_bundle_sha256": "b" * 64,
        "market_thesis_note_id": "market_thesis_note_step289",
        "market_thesis_note_sha256": "m" * 64,
        "optional_data_health": {"binance_futures": {"collector_status": "ok", "stale": False}},
        "missing_optional_source_count": 0,
        "stale_optional_source_count": 0,
        "neutral_due_to_missing": False,
        "live_candidate_eligible": True,
        "entry_side": "LONG",
        "entry_allowed": True,
        "block_reasons": [],
        "trade_permission": {"allow_long": True, "allow_new_position": True, "risk_level": "normal"},
        "created_at_utc": "2026-06-30T00:00:00Z",
    }
    signal.update(overrides)
    return signal


def test_step289_signal_qa_passes_paper_only_when_lineage_is_complete() -> None:
    signal = _signal()
    record = build_research_signal_registry_record(signal)
    report = validate_research_signal_quality(signal, registry_record=record)

    assert report["signal_qa_result"] == PASS_PAPER_ONLY
    assert report["allowed_for_decision"] is True
    assert report["allowed_for_paper"] is True
    assert report["allowed_for_signed_testnet"] is False
    assert report["order_intent_created"] is False
    assert report["trade_approved"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False


def test_step289_signal_qa_marks_optional_missing_as_review_only_when_explicitly_neutral() -> None:
    signal = _signal(
        missing_optional_source_count=2,
        neutral_due_to_missing=True,
        live_candidate_eligible=False,
        optional_data_health={
            "binance_futures": {"collector_status": "missing", "stale": False},
            "farside_etf_flow": {"collector_status": "disabled", "stale": False},
        },
    )
    record = build_research_signal_registry_record(signal)
    report = validate_research_signal_quality(signal, registry_record=record)

    assert report["signal_qa_result"] == PASS_REVIEW_ONLY
    assert report["missing_optional_source_count"] == 2
    assert report["neutral_due_to_missing"] is True
    assert report["allowed_for_decision"] is True
    assert report["allowed_for_paper"] is False


def test_step289_signal_qa_blocks_hidden_optional_missing() -> None:
    signal = _signal(missing_optional_source_count=1, neutral_due_to_missing=False, live_candidate_eligible=False)
    record = build_research_signal_registry_record(signal)
    record["neutral_due_to_missing"] = False
    report = validate_research_signal_quality(signal, registry_record=record)

    assert report["signal_qa_result"] == BLOCK_INVALID_LINEAGE
    assert BLOCK_INVALID_LINEAGE in report["block_reasons"]
    assert report["allowed_for_decision"] is False


def test_step289_signal_qa_blocks_missing_signal() -> None:
    report = validate_research_signal_quality({})

    assert report["signal_qa_result"] == BLOCK_MISSING_SIGNAL
    assert BLOCK_MISSING_SIGNAL in report["block_reasons"]
    assert report["allowed_for_decision"] is False


def test_step289_signal_qa_blocks_lineage_mismatch() -> None:
    signal = _signal()
    record = build_research_signal_registry_record(signal)
    record["feature_matrix_sha256"] = "0" * 64
    report = validate_research_signal_quality(signal, registry_record=record)

    assert report["signal_qa_result"] == BLOCK_INVALID_LINEAGE
    assert report["lineage_mismatches"] == ["feature_matrix_sha256"]


def test_step289_signal_qa_blocks_stale_and_fallback_or_synthetic_data() -> None:
    stale_report = validate_research_signal_quality(_signal(stale_optional_source_count=1), registry_record=build_research_signal_registry_record(_signal()))
    fallback_report = validate_research_signal_quality(_signal(fallback_flag=True), registry_record=build_research_signal_registry_record(_signal()))

    assert stale_report["signal_qa_result"] == BLOCK_STALE_DATA
    assert BLOCK_STALE_DATA in stale_report["block_reasons"]
    assert fallback_report["signal_qa_result"] == BLOCK_FALLBACK_OR_SYNTHETIC
    assert BLOCK_FALLBACK_OR_SYNTHETIC in fallback_report["block_reasons"]


def test_step289_signal_qa_blocks_legacy_fallback() -> None:
    report = validate_research_signal_quality(_signal(legacy_fallback_used=True), registry_record=build_research_signal_registry_record(_signal()))

    assert report["signal_qa_result"] == BLOCK_LEGACY_FALLBACK
    assert BLOCK_LEGACY_FALLBACK in report["block_reasons"]


def test_step289_signal_qa_report_appends_to_registry(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    signal = _signal()
    record = build_research_signal_registry_record(signal)
    report = validate_research_signal_quality(signal, registry_record=record, cfg=cfg)
    persisted = persist_signal_qa_report(cfg, report)
    rows = [json.loads(line) for line in registry_path(cfg, "signal_qa_registry").read_text(encoding="utf-8").splitlines()]

    assert persisted["registry_name"] == "signal_qa_registry"
    assert rows[-1]["signal_qa_result"] == PASS_PAPER_ONLY
    assert rows[-1]["signal_qa_report_sha256"]


def test_step289_raw_pipeline_writes_latest_signal_qa_report_and_registry(tmp_path: Path) -> None:
    cfg = replace(_cfg(tmp_path), root=tmp_path)
    cfg.settings.setdefault("data", {})["use_mock_data"] = True
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["features_dir"] = str(tmp_path / "storage" / "features")

    payload = run_raw_to_score_pipeline(cfg)
    latest_report = tmp_path / "storage" / "latest" / "signal_qa_report.json"
    latest_record = tmp_path / "storage" / "latest" / "signal_qa_registry_record.json"
    registry_file = tmp_path / "storage" / "registries" / "signal_qa_registry.jsonl"

    assert latest_report.exists()
    assert latest_record.exists()
    assert registry_file.exists()
    report = json.loads(latest_report.read_text(encoding="utf-8"))
    assert payload["signal_qa_report"]["research_signal_id"] == payload["research_signal"]["research_signal_id"]
    assert report["research_signal_id"] == payload["research_signal"]["research_signal_id"]
    assert report["signal_qa_result"] in {PASS_REVIEW_ONLY, PASS_PAPER_ONLY}
    assert report["order_intent_created"] is False
    assert report["trade_approved"] is False


def test_step289_research_decision_blocks_matching_signal_when_signal_qa_blocks(tmp_path, monkeypatch):
    import crypto_ai_system.research.decision_engine as decision_engine

    research_path = tmp_path / "research_result.json"
    signal_path = tmp_path / "research_signal.json"
    qa_path = tmp_path / "signal_qa_report.json"
    decision_path = tmp_path / "research_decision.json"

    research_path.write_text(json.dumps({"research_signal_id": "blocked_signal", "scenario": "Constructive", "signal_timing": "Early", "scores": {"final_score": 62}}), encoding="utf-8")
    signal_path.write_text(json.dumps({"research_signal_id": "blocked_signal", "profile_id": "profile_a", "trade_permission": {"allow_long": True, "allow_new_position": True, "risk_level": "normal"}}), encoding="utf-8")
    qa_path.write_text(json.dumps({"research_signal_id": "blocked_signal", "signal_qa_result": BLOCK_INVALID_LINEAGE, "signal_qa_report_id": "qa_block"}), encoding="utf-8")

    monkeypatch.setattr(decision_engine, "RESEARCH_RESULT_PATH", research_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_SIGNAL_PATH", signal_path)
    monkeypatch.setattr(decision_engine, "SIGNAL_QA_REPORT_PATH", qa_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_DECISION_PATH", decision_path)

    decision = decision_engine.run_research_decision()
    assert decision["signal_qa_blocks_decision"] is True
    assert decision["signal_permission_authoritative"] is False
    assert decision["allow_long"] is False
    assert decision["allow_new_position"] is False
    assert decision["risk_level"] == "blocked"
