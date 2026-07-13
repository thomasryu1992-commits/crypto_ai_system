from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

FEEDBACK_REVIEW_VERSION = "lean_feedback_review_v1"
STATUS_RECORDED_REVIEW_ONLY = "FEEDBACK_REVIEW_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "FEEDBACK_REVIEW_BLOCKED_REVIEW_ONLY"

# This layer is a review-only aggregator. It is never runtime authority.
RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE = False
APPROVAL_PACKET_CREATED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False
SIGNED_TESTNET_PROMOTION_ALLOWED_BY_THIS_MODULE = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE = False

_COMPONENT_SPECS: tuple[tuple[str, str, str], ...] = (
    (
        "sample_accumulation",
        "phase4_1_paper_outcome_sample_accumulation_id",
        "phase4_1_report_sha256",
    ),
    (
        "outcome_candidate_feedback",
        "phase4_outcome_candidate_feedback_id",
        "phase4_outcome_candidate_feedback_sha256",
    ),
    (
        "signal_drift_readiness",
        "phase4_2_signal_drift_candidate_readiness_id",
        "phase4_2_report_sha256",
    ),
    (
        "signal_score_replay",
        "phase4_3_research_signal_score_bucket_replay_id",
        "phase4_3_report_sha256",
    ),
    (
        "candidate_review_packet",
        "phase4_4_candidate_profile_review_packet_id",
        "phase4_4_report_sha256",
    ),
)

_UNSAFE_FLAGS: tuple[str, ...] = (
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "approval_packet_created",
    "approval_intake_submitted",
    "auto_promotion_allowed",
    "signed_testnet_promotion_allowed",
    "signed_testnet_unlock_allowed",
    "testnet_order_submission_allowed",
    "testnet_order_submission_allowed_by_this_module",
    "live_candidate_eligible",
    "live_trading_allowed_by_this_module",
    "live_order_executed",
    "external_order_submission_performed",
)


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _storage_dir(cfg: AppConfig) -> Path:
    path = cfg.root / "storage" / "feedback_review"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _component_projection(
    name: str,
    payload: Mapping[str, Any] | None,
    id_field: str,
    hash_field: str,
) -> dict[str, Any]:
    source = dict(payload or {})
    unsafe_flags = sorted(flag for flag in _UNSAFE_FLAGS if _bool(source.get(flag)))
    blockers = source.get("blockers")
    if not isinstance(blockers, list):
        blockers = source.get("block_reasons")
    if not isinstance(blockers, list):
        blockers = source.get("readiness_blockers")
    if not isinstance(blockers, list):
        blockers = []

    return {
        "component": name,
        "source_id": source.get(id_field),
        "source_sha256": source.get(hash_field),
        "status": source.get("status"),
        "blocked": source.get("blocked") is True,
        "fail_closed": source.get("fail_closed") is True,
        "review_only": source.get("review_only") is True,
        "source_blockers": [str(item) for item in blockers],
        "unsafe_true_flags": unsafe_flags,
    }


def build_feedback_review_report(
    *,
    legacy_outputs: Mapping[str, Mapping[str, Any]],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = created_at_utc or utc_now_canonical()
    components: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []

    for name, id_field, hash_field in _COMPONENT_SPECS:
        source = legacy_outputs.get(name)
        projection = _component_projection(name, source, id_field, hash_field)
        components[name] = projection

        if not source:
            blockers.append(f"FEEDBACK_COMPONENT_MISSING:{name}")
            continue
        if projection["blocked"] or projection["fail_closed"]:
            blockers.append(f"FEEDBACK_COMPONENT_BLOCKED:{name}")
        if projection["unsafe_true_flags"]:
            blockers.append(f"FEEDBACK_COMPONENT_UNSAFE_FLAG:{name}")
        if not projection["source_id"]:
            blockers.append(f"FEEDBACK_COMPONENT_ID_MISSING:{name}")
        if not projection["status"]:
            blockers.append(f"FEEDBACK_COMPONENT_STATUS_MISSING:{name}")

    blockers = sorted(set(blockers))
    blocked = bool(blockers)
    status = STATUS_BLOCKED_REVIEW_ONLY if blocked else STATUS_RECORDED_REVIEW_ONLY

    seed = {
        "version": FEEDBACK_REVIEW_VERSION,
        "component_ids": {
            name: projection.get("source_id")
            for name, projection in components.items()
        },
        "status": status,
        "created_at_utc": created,
    }

    candidate_review = components.get("candidate_review_packet", {})
    report: dict[str, Any] = {
        "feedback_review_id": stable_id("feedback_review", seed, 24),
        "feedback_review_version": FEEDBACK_REVIEW_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "paper_only": True,
        "component_count": len(components),
        "components": components,
        "blockers": blockers,
        "candidate_review_packet_recorded": (
            not candidate_review.get("blocked")
            and bool(candidate_review.get("source_id"))
        ),
        "next_action": (
            "resolve_feedback_review_blockers"
            if blocked
            else "manual_governance_review_required"
        ),
        "runtime_permission_source": False,
        "live_candidate_eligible": False,
        "runtime_settings_mutated": RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE,
        "score_weights_mutated": SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE,
        "candidate_profile_applied": CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE,
        "approval_packet_created": APPROVAL_PACKET_CREATED_BY_THIS_MODULE,
        "auto_promotion_allowed": AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE,
        "signed_testnet_promotion_allowed": SIGNED_TESTNET_PROMOTION_ALLOWED_BY_THIS_MODULE,
        "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE,
        "created_at_utc": created,
    }
    report["feedback_review_sha256"] = sha256_json(report)
    return report


def _load_phase4_feedback_if_current(cfg: AppConfig) -> dict[str, Any]:
    path = _latest_dir(cfg) / "phase4_outcome_candidate_feedback_report.json"
    payload = read_json(path, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def run_feedback_review_chain(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    sample_size: int = 50,
    horizon_bars: int = 12,
    min_closed_sample_size: int = 10,
    min_subset_sample_size: int = 10,
    drift_threshold: float = 0.0,
    max_drift_rate: float = 0.25,
    min_expectancy: float = 0.0,
    max_drawdown_limit: float = 6.0,
    phase4_1_runner: Callable[..., Mapping[str, Any]] | None = None,
    phase4_runner: Callable[..., Mapping[str, Any]] | None = None,
    phase4_2_runner: Callable[..., Mapping[str, Any]] | None = None,
    phase4_3_runner: Callable[..., Mapping[str, Any]] | None = None,
    phase4_4_runner: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the legacy Phase 4 chain through one canonical feedback entry point.

    Existing Phase 4 artifacts remain available during the compatibility period.
    The returned ``legacy_outputs`` map preserves old callers without allowing
    any Phase 4 artifact to become runtime permission.
    """

    cfg = cfg or load_config(project_root)

    if phase4_1_runner is None:
        from crypto_ai_system.feedback.paper_sample_accumulation import (
            persist_phase4_1_paper_outcome_sample_accumulation_report,
        )
        phase4_1_runner = persist_phase4_1_paper_outcome_sample_accumulation_report

    if phase4_runner is None:
        from crypto_ai_system.feedback.outcome_candidate_feedback import (
            persist_phase4_outcome_candidate_feedback_report,
        )
        phase4_runner = persist_phase4_outcome_candidate_feedback_report

    if phase4_2_runner is None:
        from crypto_ai_system.feedback.signal_drift_readiness import (
            persist_phase4_2_signal_drift_candidate_readiness_report,
        )
        phase4_2_runner = persist_phase4_2_signal_drift_candidate_readiness_report

    if phase4_3_runner is None:
        from crypto_ai_system.feedback.signal_score_replay import (
            persist_phase4_3_research_signal_score_bucket_replay_report,
        )
        phase4_3_runner = persist_phase4_3_research_signal_score_bucket_replay_report

    if phase4_4_runner is None:
        from crypto_ai_system.feedback.candidate_review import (
            persist_phase4_4_candidate_profile_review_packet_report,
        )
        phase4_4_runner = persist_phase4_4_candidate_profile_review_packet_report

    phase4_1 = dict(
        phase4_1_runner(
            cfg=cfg,
            sample_size=sample_size,
            horizon_bars=horizon_bars,
            min_closed_sample_size=min_closed_sample_size,
        )
    )

    # Phase 4.1 already refreshes the base Phase 4 feedback artifact on its
    # successful sample path. Reuse it to remove one duplicate execution.
    phase4 = _load_phase4_feedback_if_current(cfg)
    if not phase4 or phase4_1.get("paper_sample_accumulated") is not True:
        phase4 = dict(phase4_runner(cfg=cfg))

    phase4_2 = dict(
        phase4_2_runner(
            cfg=cfg,
            min_closed_sample_size=max(min_closed_sample_size, 30),
            min_subset_sample_size=min_subset_sample_size,
            drift_threshold=drift_threshold,
            max_drift_rate=max_drift_rate,
            min_expectancy=min_expectancy,
            max_drawdown_limit=max_drawdown_limit,
        )
    )
    phase4_3 = dict(
        phase4_3_runner(
            cfg=cfg,
            min_closed_sample_size=max(min_closed_sample_size, 30),
            min_subset_sample_size=min_subset_sample_size,
            max_alignment_drift_rate=max_drift_rate,
            min_expectancy=min_expectancy,
            max_drawdown_limit=max_drawdown_limit,
        )
    )
    phase4_4 = dict(phase4_4_runner(cfg=cfg))

    legacy_outputs = {
        "sample_accumulation": phase4_1,
        "outcome_candidate_feedback": phase4,
        "signal_drift_readiness": phase4_2,
        "signal_score_replay": phase4_3,
        "candidate_review_packet": phase4_4,
    }
    report = build_feedback_review_report(legacy_outputs=legacy_outputs)

    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg)
    atomic_write_json(latest / "feedback_review_report.json", report)
    atomic_write_json(storage / "feedback_review_report.json", report)

    return {
        "report": report,
        "legacy_outputs": legacy_outputs,
    }


def run_feedback_review_latest(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    return run_feedback_review_chain(cfg=cfg, project_root=project_root)["report"]


__all__ = [
    "FEEDBACK_REVIEW_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_feedback_review_report",
    "run_feedback_review_chain",
    "run_feedback_review_latest",
]
