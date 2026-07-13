from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.feedback.candidate_profile_registry import (
    CANDIDATE_PROFILE_REGISTRY_NAME,
    CANDIDATE_PROFILE_VERSION,
    CREATION_STATUS_BLOCKED_PERFORMANCE_REPORT_NOT_READY,
    CREATION_STATUS_BLOCKED_UNSAFE_SIDE_EFFECT,
    CREATION_STATUS_CREATED_REVIEW_ONLY,
    STATUS_REJECTED,
    STATUS_REVIEW_ONLY,
    build_candidate_profile_from_performance_report,
    build_candidate_profile_registry_record,
    generate_and_persist_candidate_profile,
    run_candidate_profile_latest,
)
from crypto_ai_system.feedback.performance_report_generator import (
    RECOMMEND_CREATE_CANDIDATE_PROFILE_DRAFT,
    RECOMMEND_REPEAT_IN_PAPER,
    STATUS_PERFORMANCE_REPORT_RECORDED,
    STATUS_PERFORMANCE_REPORT_REVIEW_ONLY_INSUFFICIENT_SAMPLE,
)
from crypto_ai_system.registry.base_registry import registry_path


def _cfg(tmp_path: Path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    return cfg


def _report(**overrides):
    payload = {
        "performance_report_id": "performance_report_step298",
        "performance_report_sha256": "report_hash_step298",
        "performance_report_registry_record_id": "performance_report_registry_step298",
        "performance_report_registry_record_sha256": "report_registry_hash_step298",
        "status": STATUS_PERFORMANCE_REPORT_RECORDED,
        "recommendation": RECOMMEND_CREATE_CANDIDATE_PROFILE_DRAFT,
        "profile_id": "profile_step298",
        "research_signal_id": "signal_step298",
        "sample_size": 5,
        "source_outcome_count": 5,
        "expectancy": 0.75,
        "average_R": 0.8,
        "win_loss_ratio": 2.0,
        "max_drawdown": 0.2,
        "rejection_rate": 0.0,
        "stale_data_rate": 0.0,
        "signal_to_outcome_drift": 0.0,
        "paper_live_gap": "not_applicable",
        "api_error_rate": 0.0,
        "manual_override_count": 0,
        "source_outcome_ids": ["outcome_a", "outcome_b", "outcome_c"],
        "source_outcome_hashes": ["hash_a", "hash_b", "hash_c"],
        "summary_by_direction": {"LONG": {"closed_count": 5}},
        "failure_modes": [],
        "blockers": [],
        "live_candidate_eligible": True,
        "candidate_profile_created": False,
        "approval_packet_created": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
    }
    payload.update(overrides)
    return payload


def test_step298_builds_review_only_candidate_profile_from_ready_performance_report() -> None:
    candidate = build_candidate_profile_from_performance_report(_report())

    assert candidate["candidate_profile_version"] == CANDIDATE_PROFILE_VERSION
    assert candidate["creation_status"] == CREATION_STATUS_CREATED_REVIEW_ONLY
    assert candidate["candidate_profile_created"] is True
    assert candidate["status"] == STATUS_REVIEW_ONLY
    assert candidate["source_report_id"] == "performance_report_step298"
    assert candidate["source_report_hash"] == "report_hash_step298"
    assert candidate["strategy_family"] == "research_signal_feedback_v1"
    assert candidate["allowed_direction"] == "long_only"
    assert candidate["expected_edge_reason"]
    assert candidate["data_quality_score"] == 1.0
    assert candidate["paper_priority_score"] > 0
    assert candidate["risk_complexity_score"] == 0.2
    assert candidate["live_ineligible_reason"] == "candidate_profile_requires_manual_approval_and_paper_validation"
    assert candidate["review_only"] is True
    assert candidate["paper_candidate"] is False
    assert candidate["approval_packet_ready"] is False
    assert candidate["candidate_profile_applied"] is False
    assert candidate["approval_packet_created"] is False
    assert candidate["settings_write_preview_created"] is False
    assert candidate["runtime_settings_mutated"] is False
    assert candidate["score_weights_mutated"] is False
    assert candidate["auto_promotion_allowed"] is False
    assert candidate["live_trading_allowed_by_this_module"] is False
    assert candidate["profile_candidate_hash"]


def test_step298_blocks_insufficient_performance_report_without_creating_candidate() -> None:
    candidate = build_candidate_profile_from_performance_report(
        _report(
            status=STATUS_PERFORMANCE_REPORT_REVIEW_ONLY_INSUFFICIENT_SAMPLE,
            recommendation=RECOMMEND_REPEAT_IN_PAPER,
            blockers=["INSUFFICIENT_CLOSED_OUTCOME_SAMPLE"],
            failure_modes=["INSUFFICIENT_CLOSED_OUTCOME_SAMPLE"],
            live_candidate_eligible=False,
        )
    )

    assert candidate["creation_status"] == CREATION_STATUS_BLOCKED_PERFORMANCE_REPORT_NOT_READY
    assert candidate["candidate_profile_created"] is False
    assert candidate["status"] == STATUS_REJECTED
    assert "INSUFFICIENT_CLOSED_OUTCOME_SAMPLE" in candidate["blockers"]
    assert candidate["runtime_settings_mutated"] is False
    assert candidate["score_weights_mutated"] is False
    assert candidate["auto_promotion_allowed"] is False


def test_step298_blocks_unsafe_side_effect_report() -> None:
    candidate = build_candidate_profile_from_performance_report(_report(runtime_settings_mutated=True))

    assert candidate["creation_status"] == CREATION_STATUS_BLOCKED_UNSAFE_SIDE_EFFECT
    assert candidate["candidate_profile_created"] is False
    assert "UNSAFE_SIDE_EFFECT_FLAG_DETECTED" in candidate["blockers"]


def test_step298_registry_record_preserves_source_report_hash_and_review_only_flags() -> None:
    candidate = build_candidate_profile_from_performance_report(_report())
    record = build_candidate_profile_registry_record(candidate)

    assert record["candidate_profile_registry_version"] == CANDIDATE_PROFILE_VERSION
    assert record["candidate_profile_id"] == candidate["candidate_profile_id"]
    assert record["source_report_id"] == "performance_report_step298"
    assert record["source_report_hash"] == "report_hash_step298"
    assert record["profile_candidate_hash"] == candidate["profile_candidate_hash"]
    assert record["status"] == STATUS_REVIEW_ONLY
    assert record["candidate_profile_applied"] is False
    assert record["approval_packet_created"] is False
    assert record["runtime_settings_mutated"] is False
    assert record["score_weights_mutated"] is False
    assert record["auto_promotion_allowed"] is False
    assert record["candidate_profile_registry_record_sha256"]


def test_step298_persists_latest_candidate_profile_and_append_only_registry(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    candidate = generate_and_persist_candidate_profile(_report(), cfg=cfg)
    registry = registry_path(cfg, CANDIDATE_PROFILE_REGISTRY_NAME)
    rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]

    assert (tmp_path / "storage" / "latest" / "candidate_profile.json").exists()
    assert (tmp_path / "storage" / "latest" / "candidate_profile_registry_record.json").exists()
    assert len(rows) == 1
    assert rows[0]["registry_name"] == CANDIDATE_PROFILE_REGISTRY_NAME
    assert candidate["candidate_profile_registry_record_id"] == rows[0]["candidate_profile_registry_record_id"]
    assert candidate["candidate_profile_created"] is True


def test_step298_run_latest_reads_performance_report(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    latest_dir = tmp_path / "storage" / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    (latest_dir / "performance_report.json").write_text(json.dumps(_report()), encoding="utf-8")

    candidate = run_candidate_profile_latest(cfg=cfg)

    assert candidate["creation_status"] == CREATION_STATUS_CREATED_REVIEW_ONLY
    assert candidate["candidate_profile_created"] is True
    assert (tmp_path / "storage" / "registries" / "candidate_profile_registry.jsonl").exists()
