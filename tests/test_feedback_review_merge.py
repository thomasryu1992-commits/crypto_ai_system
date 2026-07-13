from __future__ import annotations

from crypto_ai_system.feedback.review import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_feedback_review_report,
)


def _component(component_id: str, hash_field: str, *, blocked: bool = False) -> dict:
    return {
        component_id: f"{component_id}_value",
        hash_field: "a" * 64,
        "status": "RECORDED_REVIEW_ONLY" if not blocked else "BLOCKED_REVIEW_ONLY",
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "approval_packet_created": False,
        "auto_promotion_allowed": False,
        "testnet_order_submission_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "external_order_submission_performed": False,
    }


def _valid_outputs() -> dict:
    return {
        "sample_accumulation": _component(
            "phase4_1_paper_outcome_sample_accumulation_id",
            "phase4_1_report_sha256",
        ),
        "outcome_candidate_feedback": _component(
            "phase4_outcome_candidate_feedback_id",
            "phase4_outcome_candidate_feedback_sha256",
        ),
        "signal_drift_readiness": _component(
            "phase4_2_signal_drift_candidate_readiness_id",
            "phase4_2_report_sha256",
        ),
        "signal_score_replay": _component(
            "phase4_3_research_signal_score_bucket_replay_id",
            "phase4_3_report_sha256",
        ),
        "candidate_review_packet": _component(
            "phase4_4_candidate_profile_review_packet_id",
            "phase4_4_report_sha256",
        ),
    }


def test_feedback_review_records_all_components_without_runtime_authority() -> None:
    report = build_feedback_review_report(
        legacy_outputs=_valid_outputs(),
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["component_count"] == 5
    assert report["runtime_permission_source"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["candidate_profile_applied"] is False
    assert report["approval_packet_created"] is False
    assert report["auto_promotion_allowed"] is False
    assert report["signed_testnet_promotion_allowed"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["live_trading_allowed_by_this_module"] is False
    assert report["external_order_submission_performed"] is False
    assert len(report["feedback_review_sha256"]) == 64


def test_feedback_review_fails_closed_when_component_is_blocked() -> None:
    outputs = _valid_outputs()
    outputs["signal_drift_readiness"]["blocked"] = True
    outputs["signal_drift_readiness"]["fail_closed"] = True

    report = build_feedback_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert "FEEDBACK_COMPONENT_BLOCKED:signal_drift_readiness" in report["blockers"]
    assert report["testnet_order_submission_allowed"] is False


def test_feedback_review_fails_closed_on_unsafe_legacy_flag() -> None:
    outputs = _valid_outputs()
    outputs["candidate_review_packet"]["auto_promotion_allowed"] = True

    report = build_feedback_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["blocked"] is True
    assert "FEEDBACK_COMPONENT_UNSAFE_FLAG:candidate_review_packet" in report["blockers"]
    assert report["auto_promotion_allowed"] is False


def test_feedback_review_fails_closed_when_component_is_missing() -> None:
    outputs = _valid_outputs()
    outputs.pop("signal_score_replay")

    report = build_feedback_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["blocked"] is True
    assert "FEEDBACK_COMPONENT_MISSING:signal_score_replay" in report["blockers"]
