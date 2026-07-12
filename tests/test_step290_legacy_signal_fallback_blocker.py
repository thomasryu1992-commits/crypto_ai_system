from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.quality.legacy_signal_fallback_blocker import (
    BLOCK_LEGACY_FALLBACK,
    BLOCK_MISSING_SIGNAL,
    BLOCK_SIGNAL_QA_NOT_MATCHING_SIGNAL,
    BLOCK_SIGNAL_QA_UNAVAILABLE,
    PASS_RESEARCH_SIGNAL_QA,
    build_legacy_signal_fallback_block_report,
)
from crypto_ai_system.research.raw_score_pipeline import run_raw_to_score_pipeline
from crypto_ai_system.config import load_config


def _signal(**overrides) -> dict:
    signal = {
        "research_signal_id": "signal_step290",
        "signal_id": "signal_step290",
        "signal_version": "research_signal_v2_step290",
        "profile_id": "default_review_profile",
        "profile_version": "v1",
        "config_version": "step286_researchsignal_feature_lineage_fix",
        "data_snapshot_id": "data_snapshot_step290",
        "feature_snapshot_id": "feature_snapshot_step290",
        "feature_matrix_sha256": "f" * 64,
        "source_bundle_sha256": "b" * 64,
        "entry_side": "LONG",
        "entry_allowed": True,
        "trade_permission": {"allow_long": True, "allow_new_position": True, "risk_level": "normal"},
    }
    signal.update(overrides)
    return signal


def _qa(signal_id: str = "signal_step290", result: str = "PASS_PAPER_ONLY") -> dict:
    return {
        "signal_qa_report_id": "qa_step290",
        "research_signal_id": signal_id,
        "signal_qa_result": result,
        "allowed_for_decision": True,
    }


def test_step290_blocker_passes_only_with_matching_research_signal_and_signal_qa() -> None:
    report = build_legacy_signal_fallback_block_report(
        research_signal=_signal(),
        signal_qa_report=_qa(),
        use_research_signal_gate=True,
        consumer="unit_test",
    )

    assert report["legacy_signal_fallback_blocker_result"] == PASS_RESEARCH_SIGNAL_QA
    assert report["allowed_for_decision"] is True
    assert report["allowed_for_paper"] is True
    assert report["allowed_for_signed_testnet"] is False
    assert report["order_intent_created"] is False
    assert report["trade_approved"] is False


def test_step290_blocker_blocks_missing_signal_and_missing_signal_qa() -> None:
    report = build_legacy_signal_fallback_block_report(
        research_signal={},
        signal_qa_report={},
        use_research_signal_gate=True,
        consumer="unit_test",
    )

    assert report["legacy_signal_fallback_blocker_result"] in {BLOCK_MISSING_SIGNAL, BLOCK_SIGNAL_QA_UNAVAILABLE}
    assert BLOCK_MISSING_SIGNAL in report["block_reasons"]
    assert BLOCK_SIGNAL_QA_UNAVAILABLE in report["block_reasons"]
    assert report["allowed_for_decision"] is False


def test_step290_blocker_blocks_legacy_fallback_signal_even_with_matching_qa() -> None:
    report = build_legacy_signal_fallback_block_report(
        research_signal=_signal(legacy_fallback_used=True, signal_source="legacy_fallback"),
        signal_qa_report=_qa(),
        use_research_signal_gate=True,
        consumer="unit_test",
    )

    assert report["legacy_signal_fallback_blocker_result"] == BLOCK_LEGACY_FALLBACK
    assert BLOCK_LEGACY_FALLBACK in report["block_reasons"]
    assert report["allowed_for_decision"] is False


def test_step290_blocker_blocks_signal_qa_lineage_mismatch() -> None:
    report = build_legacy_signal_fallback_block_report(
        research_signal=_signal(),
        signal_qa_report=_qa(signal_id="other_signal"),
        use_research_signal_gate=True,
        consumer="unit_test",
    )

    assert BLOCK_SIGNAL_QA_NOT_MATCHING_SIGNAL in report["block_reasons"]
    assert report["signal_qa_relevant"] is False
    assert report["allowed_for_decision"] is False


def test_step290_decision_engine_blocks_legacy_research_result_when_gate_enabled(tmp_path: Path, monkeypatch) -> None:
    import crypto_ai_system.research.decision_engine as decision_engine

    research_path = tmp_path / "research_result.json"
    signal_path = tmp_path / "missing_research_signal.json"
    qa_path = tmp_path / "missing_signal_qa.json"
    decision_path = tmp_path / "decision.json"
    research_path.write_text(
        json.dumps({"scenario": "Constructive", "signal_timing": "Early", "scores": {"final_score": 62}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(decision_engine, "USE_RESEARCH_SIGNAL_GATE", True)
    monkeypatch.setattr(decision_engine, "RESEARCH_RESULT_PATH", research_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_SIGNAL_PATH", signal_path)
    monkeypatch.setattr(decision_engine, "SIGNAL_QA_REPORT_PATH", qa_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_DECISION_PATH", decision_path)

    decision = decision_engine.run_research_decision()
    assert decision["allow_long"] is False
    assert decision["allow_new_position"] is False
    assert decision["risk_level"] == "blocked"
    assert decision["signal_permission_authoritative"] is False
    assert decision["legacy_signal_fallback_blocker_blocks_decision"] is True


def test_step290_decision_engine_uses_matching_signal_only_after_signal_qa_pass(tmp_path: Path, monkeypatch) -> None:
    import crypto_ai_system.research.decision_engine as decision_engine

    research_path = tmp_path / "research_result.json"
    signal_path = tmp_path / "research_signal.json"
    qa_path = tmp_path / "signal_qa.json"
    decision_path = tmp_path / "decision.json"
    research_path.write_text(
        json.dumps({"research_signal_id": "signal_step290", "scenario": "Constructive", "signal_timing": "Early", "scores": {"final_score": 62}}),
        encoding="utf-8",
    )
    signal_path.write_text(json.dumps(_signal()), encoding="utf-8")
    qa_path.write_text(json.dumps(_qa()), encoding="utf-8")

    monkeypatch.setattr(decision_engine, "USE_RESEARCH_SIGNAL_GATE", True)
    monkeypatch.setattr(decision_engine, "RESEARCH_RESULT_PATH", research_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_SIGNAL_PATH", signal_path)
    monkeypatch.setattr(decision_engine, "SIGNAL_QA_REPORT_PATH", qa_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_DECISION_PATH", decision_path)

    decision = decision_engine.run_research_decision()
    assert decision["allow_long"] is True
    assert decision["allow_new_position"] is True
    assert decision["risk_level"] == "normal"
    assert decision["signal_permission_authoritative"] is True
    assert decision["legacy_signal_fallback_blocker_result"] == PASS_RESEARCH_SIGNAL_QA


def test_step290_signal_engine_blocks_compat_legacy_fallback_when_gate_enabled(tmp_path: Path, monkeypatch) -> None:
    import crypto_ai_system.trading.signal_engine as signal_engine

    research_path = tmp_path / "research_result.json"
    snapshot_path = tmp_path / "market_snapshot.json"
    signal_path = tmp_path / "missing_research_signal.json"
    qa_path = tmp_path / "missing_signal_qa.json"
    research_path.write_text(json.dumps({"scenario": "Constructive", "signal_timing": "Early"}), encoding="utf-8")
    snapshot_path.write_text(json.dumps({"trend_bias": "bullish"}), encoding="utf-8")

    monkeypatch.setattr(signal_engine, "USE_RESEARCH_SIGNAL_GATE", True)
    monkeypatch.setattr(signal_engine, "LEGACY_SIGNAL_FALLBACK_REVIEW_ONLY_COMPAT", True)
    monkeypatch.setattr(signal_engine, "RESEARCH_RESULT_PATH", research_path)
    monkeypatch.setattr(signal_engine, "MARKET_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(signal_engine, "RESEARCH_SIGNAL_PATH", signal_path)
    monkeypatch.setattr(signal_engine, "SIGNAL_QA_REPORT_PATH", qa_path)

    payload = signal_engine.generate_trading_signal()
    assert payload["allow_new_position"] is False
    assert payload["signal"] == "NONE"
    assert payload["risk_level"] == "blocked"
    assert payload["legacy_fallback_used"] is False
    assert payload["legacy_signal_fallback_compat_requested"] is True


def test_step290_raw_pipeline_writes_legacy_fallback_blocker_evidence(tmp_path: Path) -> None:
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["features_dir"] = str(tmp_path / "storage" / "features")
    result = run_raw_to_score_pipeline(cfg)

    report = result["legacy_signal_fallback_blocker_report"]
    assert report["legacy_signal_fallback_blocker_version"] == "step290_legacy_signal_fallback_blocker_v1"
    assert report["research_signal_gate_enabled"] is True
    assert report["allowed_for_signed_testnet"] is False
    assert report["allowed_for_live"] is False
