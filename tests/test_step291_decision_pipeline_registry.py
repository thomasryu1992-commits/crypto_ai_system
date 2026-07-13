from __future__ import annotations

import json
from pathlib import Path
from dataclasses import replace

from crypto_ai_system.config import load_config
from crypto_ai_system.registry.base_registry import registry_path
from crypto_ai_system.registry.decision_pipeline_registry import (
    DECISION_PIPELINE_REGISTRY_VERSION,
    FULL_CANONICAL_ID_CHAIN,
    build_decision_pipeline_registry_record,
    persist_decision_pipeline_registry_record,
)
from crypto_ai_system.research.raw_score_pipeline import run_raw_to_score_pipeline


def _cfg(tmp_path: Path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["features_dir"] = str(tmp_path / "storage" / "features")
    return cfg


def _signal() -> dict:
    return {
        "research_signal_id": "signal_step291",
        "signal_id": "signal_step291",
        "signal_version": "research_signal_v2_step291",
        "profile_id": "profile_step291",
        "profile_version": "v1",
        "config_version": "step286_researchsignal_feature_lineage_fix",
        "data_snapshot_id": "data_snapshot_step291",
        "feature_snapshot_id": "feature_snapshot_step291",
        "feature_matrix_sha256": "f" * 64,
        "source_bundle_sha256": "b" * 64,
        "entry_side": "LONG",
        "entry_allowed": True,
        "permission_result": "allow_long",
        "trade_permission": {"allow_long": True, "allow_new_position": True, "risk_level": "normal"},
        "live_candidate_eligible": False,
        "created_at_utc": "2026-06-30T00:00:00Z",
    }


def _qa() -> dict:
    return {
        "signal_qa_report_id": "qa_step291",
        "research_signal_id": "signal_step291",
        "signal_qa_result": "PASS_PAPER_ONLY",
        "allowed_for_decision": True,
    }


def _blocker() -> dict:
    return {
        "legacy_signal_fallback_blocker_id": "legacy_blocker_step291",
        "research_signal_id": "signal_step291",
        "legacy_signal_fallback_blocker_result": "PASS_RESEARCH_SIGNAL_QA",
        "allowed_for_decision": True,
        "allowed_for_paper": True,
    }


def _decision() -> dict:
    return {
        "decision_id": "decision_step291",
        "research_signal_id": "signal_step291",
        "profile_id": "profile_step291",
        "data_snapshot_id": "data_snapshot_step291",
        "feature_snapshot_id": "feature_snapshot_step291",
        "side": "LONG",
        "allow_long": True,
        "allow_short": False,
        "allow_new_position": True,
        "signal_permission_authoritative": True,
        "risk_level": "normal",
        "created_at_utc": "2026-06-30T00:00:00Z",
    }


def test_step291_decision_pipeline_record_preserves_chain_and_missing_future_ids() -> None:
    record = build_decision_pipeline_registry_record(
        decision=_decision(),
        research_signal=_signal(),
        signal_qa_report=_qa(),
        legacy_blocker=_blocker(),
    )

    assert record["decision_pipeline_registry_version"] == DECISION_PIPELINE_REGISTRY_VERSION
    assert record["data_snapshot_id"] == "data_snapshot_step291"
    assert record["feature_snapshot_id"] == "feature_snapshot_step291"
    assert record["research_signal_id"] == "signal_step291"
    assert record["profile_id"] == "profile_step291"
    assert record["decision_id"] == "decision_step291"
    assert record["decision_stage"] == "review_only"
    assert record["current_stage_id_chain_complete"] is True
    assert record["full_canonical_id_chain_complete"] is False
    assert "approval_packet_id" in record["missing_canonical_id_fields"]
    assert "order_intent_id" in record["missing_canonical_id_fields"]
    assert record["trade_approved"] is False
    assert record["runtime_settings_mutated"] is False
    assert record["score_weights_mutated"] is False
    assert record["external_order_submission_performed"] is False
    assert list(record["canonical_id_chain"].keys()) == list(FULL_CANONICAL_ID_CHAIN)


def test_step291_decision_pipeline_registry_appends_jsonl(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    persisted = persist_decision_pipeline_registry_record(
        cfg,
        decision=_decision(),
        research_signal=_signal(),
        signal_qa_report=_qa(),
        legacy_blocker=_blocker(),
    )
    rows = [json.loads(line) for line in registry_path(cfg, "decision_pipeline_registry").read_text(encoding="utf-8").splitlines()]

    assert persisted["registry_name"] == "decision_pipeline_registry"
    assert len(rows) == 1
    assert rows[0]["decision_id"] == "decision_step291"
    assert rows[0]["decision_pipeline_registry_record_sha256"]
    assert rows[0]["current_stage_id_chain_complete"] is True


def test_step291_record_marks_current_stage_incomplete_when_feature_snapshot_missing() -> None:
    decision = _decision()
    signal = _signal()
    decision["feature_snapshot_id"] = ""
    signal["feature_snapshot_id"] = ""

    record = build_decision_pipeline_registry_record(
        decision=decision,
        research_signal=signal,
        signal_qa_report=_qa(),
        legacy_blocker=_blocker(),
    )

    assert record["current_stage_id_chain_complete"] is False
    assert "feature_snapshot_id" in record["missing_current_stage_id_fields"]


def test_step291_research_decision_engine_writes_latest_registry_record(tmp_path: Path, monkeypatch) -> None:
    import crypto_ai_system.research.decision_engine as decision_engine

    cfg = _cfg(tmp_path)
    research_path = tmp_path / "research_result.json"
    signal_path = tmp_path / "research_signal.json"
    qa_path = tmp_path / "signal_qa.json"
    decision_path = tmp_path / "decision.json"
    latest_registry_path = tmp_path / "decision_pipeline_registry_record.json"
    research_path.write_text(
        json.dumps({"research_signal_id": "signal_step291", "scenario": "Constructive", "signal_timing": "Early", "scores": {"final_score": 62}}),
        encoding="utf-8",
    )
    signal_path.write_text(json.dumps(_signal()), encoding="utf-8")
    qa_path.write_text(json.dumps(_qa()), encoding="utf-8")

    monkeypatch.setattr(decision_engine, "USE_RESEARCH_SIGNAL_GATE", True)
    monkeypatch.setattr(decision_engine, "RESEARCH_RESULT_PATH", research_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_SIGNAL_PATH", signal_path)
    monkeypatch.setattr(decision_engine, "SIGNAL_QA_REPORT_PATH", qa_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_DECISION_PATH", decision_path)
    monkeypatch.setattr(decision_engine, "DECISION_PIPELINE_REGISTRY_RECORD_PATH", latest_registry_path)
    monkeypatch.setattr(decision_engine, "load_config", lambda _root: cfg)

    decision = decision_engine.run_research_decision()
    latest = json.loads(latest_registry_path.read_text(encoding="utf-8"))

    assert decision["signal_permission_authoritative"] is True
    assert decision["decision_pipeline_current_stage_id_chain_complete"] is True
    assert latest["decision_id"] == decision["decision_id"]
    assert latest["research_signal_id"] == "signal_step291"
    assert latest["full_canonical_id_chain_complete"] is False
    assert (tmp_path / "storage" / "registries" / "decision_pipeline_registry.jsonl").exists()


def test_step291_raw_pipeline_plus_decision_can_append_decision_registry(tmp_path: Path, monkeypatch) -> None:
    import crypto_ai_system.research.decision_engine as decision_engine

    cfg = replace(_cfg(tmp_path), root=tmp_path)
    cfg.settings.setdefault("data", {})["use_mock_data"] = True
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["features_dir"] = str(tmp_path / "storage" / "features")
    payload = run_raw_to_score_pipeline(cfg)

    research_path = tmp_path / "storage" / "latest" / "research_cycle_result.json"
    signal_path = tmp_path / "storage" / "latest" / "research_signal.json"
    qa_path = tmp_path / "storage" / "latest" / "signal_qa_report.json"
    decision_path = tmp_path / "storage" / "latest" / "research_decision_result.json"
    latest_registry_path = tmp_path / "storage" / "latest" / "decision_pipeline_registry_record.json"
    research_path.write_text(json.dumps({
        "research_signal_id": payload["research_signal"]["research_signal_id"],
        "scenario": "Constructive",
        "signal_timing": "Early",
        "scores": {"final_score": 62},
    }), encoding="utf-8")

    monkeypatch.setattr(decision_engine, "USE_RESEARCH_SIGNAL_GATE", True)
    monkeypatch.setattr(decision_engine, "RESEARCH_RESULT_PATH", research_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_SIGNAL_PATH", signal_path)
    monkeypatch.setattr(decision_engine, "SIGNAL_QA_REPORT_PATH", qa_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_DECISION_PATH", decision_path)
    monkeypatch.setattr(decision_engine, "DECISION_PIPELINE_REGISTRY_RECORD_PATH", latest_registry_path)
    monkeypatch.setattr(decision_engine, "load_config", lambda _root: cfg)

    decision = decision_engine.run_research_decision()
    registry_file = tmp_path / "storage" / "registries" / "decision_pipeline_registry.jsonl"
    latest = json.loads(latest_registry_path.read_text(encoding="utf-8"))

    assert registry_file.exists()
    assert latest["decision_id"] == decision["decision_id"]
    assert latest["data_snapshot_id"] == payload["research_signal"]["data_snapshot_id"]
    assert latest["feature_snapshot_id"] == payload["research_signal"]["feature_snapshot_id"]
    assert latest["research_signal_id"] == payload["research_signal"]["research_signal_id"]
    assert latest["current_stage_id_chain_complete"] is True
    assert "approval_packet_id" in latest["missing_canonical_id_fields"]
