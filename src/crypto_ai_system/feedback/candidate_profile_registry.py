from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.feedback.performance_report_generator import (
    RECOMMEND_CREATE_CANDIDATE_PROFILE_DRAFT,
    STATUS_PERFORMANCE_REPORT_RECORDED,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

CANDIDATE_PROFILE_VERSION = "step298_candidate_profile_registry_v1"
CANDIDATE_PROFILE_REGISTRY_NAME = "candidate_profile_registry"

STATUS_DRAFT = "draft"
STATUS_REVIEW_ONLY = "review_only"
STATUS_PAPER_CANDIDATE = "paper_candidate"
STATUS_APPROVAL_PACKET_READY = "approval_packet_ready"
STATUS_REJECTED = "rejected"
STATUS_ARCHIVED = "archived"

CREATION_STATUS_CREATED_REVIEW_ONLY = "CANDIDATE_PROFILE_DRAFT_CREATED_REVIEW_ONLY"
CREATION_STATUS_BLOCKED_MISSING_PERFORMANCE_REPORT = "CANDIDATE_PROFILE_BLOCKED_MISSING_PERFORMANCE_REPORT"
CREATION_STATUS_BLOCKED_PERFORMANCE_REPORT_NOT_READY = "CANDIDATE_PROFILE_BLOCKED_PERFORMANCE_REPORT_NOT_READY"
CREATION_STATUS_BLOCKED_UNSAFE_SIDE_EFFECT = "CANDIDATE_PROFILE_BLOCKED_UNSAFE_SIDE_EFFECT"

LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False
APPROVAL_PACKET_CREATED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE = False
SETTINGS_WRITE_PREVIEW_CREATED_BY_THIS_MODULE = False


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except Exception:
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _latest_path(cfg: AppConfig, name: str) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def _unsafe_report_side_effect(report: Mapping[str, Any]) -> bool:
    return any(
        _bool(report.get(name))
        for name in [
            "live_trading_allowed_by_this_module",
            "runtime_settings_mutated",
            "score_weights_mutated",
            "auto_promotion_allowed",
            "approval_packet_created",
            "candidate_profile_applied",
            "settings_write_preview_created",
            "live_order_executed",
            "external_order_submission_performed",
            "adapter_called",
        ]
    )


def _direction_from_report(report: Mapping[str, Any]) -> str:
    summary = report.get("summary_by_direction")
    if isinstance(summary, Mapping) and summary:
        keys = sorted(_text(k).lower() for k in summary.keys() if _text(k) and _text(k).lower() not in {"unknown", "none"})
        if len(keys) == 1:
            value = keys[0]
            if value in {"long", "buy"}:
                return "long_only"
            if value in {"short", "sell"}:
                return "short_only"
        if len(keys) > 1:
            return "long_short"
    return "review_only"


def _target_timeframe_from_report(report: Mapping[str, Any]) -> str:
    for key in ["target_timeframe", "timeframe", "primary_timeframe"]:
        if _text(report.get(key)):
            return _text(report.get(key))
    return "unknown"


def _risk_complexity_score(report: Mapping[str, Any]) -> float:
    components = [
        _float(report.get("max_drawdown"), 0.0),
        _float(report.get("rejection_rate"), 0.0),
        _float(report.get("stale_data_rate"), 0.0),
        _float(report.get("api_error_rate"), 0.0),
        _float(report.get("signal_to_outcome_drift"), 0.0),
        _float(report.get("reconciliation_mismatch_count"), 0.0),
    ]
    return round(sum(max(0.0, value) for value in components), 8)


def _data_quality_score(report: Mapping[str, Any]) -> float:
    penalty = min(1.0, _float(report.get("stale_data_rate"), 0.0) + _float(report.get("api_error_rate"), 0.0))
    if _float(report.get("reconciliation_mismatch_count"), 0.0) > 0:
        penalty = 1.0
    return round(max(0.0, 1.0 - penalty), 8)


def _paper_priority_score(report: Mapping[str, Any]) -> float:
    expectancy = max(0.0, _float(report.get("expectancy"), 0.0))
    average_r = max(0.0, _float(report.get("average_R"), 0.0))
    win_loss_ratio = max(0.0, _float(report.get("win_loss_ratio"), 0.0))
    sample_bonus = min(1.0, _float(report.get("sample_size"), 0.0) / 20.0)
    risk_penalty = min(1.0, _risk_complexity_score(report))
    score = expectancy + (0.5 * average_r) + (0.25 * win_loss_ratio) + sample_bonus - risk_penalty
    return round(max(0.0, score), 8)


def _eligible_to_create_candidate(report: Mapping[str, Any]) -> tuple[bool, str, list[str]]:
    if not report:
        return False, CREATION_STATUS_BLOCKED_MISSING_PERFORMANCE_REPORT, ["MISSING_PERFORMANCE_REPORT"]
    if _unsafe_report_side_effect(report):
        return False, CREATION_STATUS_BLOCKED_UNSAFE_SIDE_EFFECT, ["UNSAFE_SIDE_EFFECT_FLAG_DETECTED"]
    blockers = list(report.get("blockers") or []) if isinstance(report.get("blockers"), list) else []
    failure_modes = list(report.get("failure_modes") or []) if isinstance(report.get("failure_modes"), list) else []
    if report.get("status") != STATUS_PERFORMANCE_REPORT_RECORDED:
        return False, CREATION_STATUS_BLOCKED_PERFORMANCE_REPORT_NOT_READY, ["PERFORMANCE_REPORT_STATUS_NOT_RECORDED", *blockers, *failure_modes]
    if report.get("recommendation") != RECOMMEND_CREATE_CANDIDATE_PROFILE_DRAFT:
        return False, CREATION_STATUS_BLOCKED_PERFORMANCE_REPORT_NOT_READY, ["PERFORMANCE_REPORT_RECOMMENDATION_NOT_CANDIDATE", *blockers, *failure_modes]
    if _float(report.get("expectancy"), 0.0) <= 0:
        return False, CREATION_STATUS_BLOCKED_PERFORMANCE_REPORT_NOT_READY, ["NON_POSITIVE_EXPECTANCY", *blockers, *failure_modes]
    if blockers or failure_modes:
        return False, CREATION_STATUS_BLOCKED_PERFORMANCE_REPORT_NOT_READY, [*blockers, *failure_modes]
    return True, CREATION_STATUS_CREATED_REVIEW_ONLY, []


@dataclass
class CandidateProfileDraft:
    candidate_profile_id: str
    candidate_profile_version: str
    creation_status: str
    source_report_id: str
    source_report_hash: str
    source_report_registry_record_id: str
    source_report_registry_record_sha256: str
    profile_version: str
    strategy_family: str
    target_timeframe: str
    allowed_direction: str
    expected_edge_reason: str
    data_quality_score: float
    paper_priority_score: float
    risk_complexity_score: float
    feature_matrix_sha256: str | None
    profile_candidate_hash: str
    live_ineligible_reason: str
    status: str
    performance_snapshot: dict[str, Any]
    review_only: bool = True
    paper_candidate: bool = False
    approval_packet_ready: bool = False
    candidate_profile_applied: bool = CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE
    approval_packet_created: bool = APPROVAL_PACKET_CREATED_BY_THIS_MODULE
    settings_write_preview_created: bool = SETTINGS_WRITE_PREVIEW_CREATED_BY_THIS_MODULE
    live_trading_allowed_by_this_module: bool = LIVE_TRADING_ALLOWED_BY_THIS_MODULE
    runtime_settings_mutated: bool = RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE
    score_weights_mutated: bool = SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE
    auto_promotion_allowed: bool = AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not payload.get("profile_candidate_hash"):
            payload["profile_candidate_hash"] = sha256_json({k: v for k, v in payload.items() if k != "profile_candidate_hash"})
        return payload


def build_candidate_profile_from_performance_report(report: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(report or {})
    allowed, creation_status, blockers = _eligible_to_create_candidate(payload)
    if not allowed:
        blocked = {
            "candidate_profile_version": CANDIDATE_PROFILE_VERSION,
            "creation_status": creation_status,
            "candidate_profile_created": False,
            "status": STATUS_REJECTED,
            "source_report_id": payload.get("performance_report_id"),
            "source_report_hash": payload.get("performance_report_sha256"),
            "source_report_registry_record_id": payload.get("performance_report_registry_record_id"),
            "source_report_registry_record_sha256": payload.get("performance_report_registry_record_sha256"),
            "blockers": sorted(dict.fromkeys(_text(item) for item in blockers if _text(item))),
            "live_ineligible_reason": "performance_report_not_ready_for_candidate_profile",
            "review_only": True,
            "paper_candidate": False,
            "approval_packet_ready": False,
            "candidate_profile_applied": False,
            "approval_packet_created": False,
            "settings_write_preview_created": False,
            "live_trading_allowed_by_this_module": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "auto_promotion_allowed": False,
            "created_at_utc": utc_now_canonical(),
        }
        blocked["candidate_profile_blocked_record_id"] = stable_id("candidate_profile_blocked", blocked, 24)
        blocked["candidate_profile_blocked_record_sha256"] = sha256_json(blocked)
        return blocked

    performance_snapshot = {
        "sample_size": payload.get("sample_size"),
        "expectancy": payload.get("expectancy"),
        "average_R": payload.get("average_R"),
        "win_loss_ratio": payload.get("win_loss_ratio"),
        "max_drawdown": payload.get("max_drawdown"),
        "rejection_rate": payload.get("rejection_rate"),
        "stale_data_rate": payload.get("stale_data_rate"),
        "signal_to_outcome_drift": payload.get("signal_to_outcome_drift"),
        "paper_live_gap": payload.get("paper_live_gap"),
        "api_error_rate": payload.get("api_error_rate"),
        "manual_override_count": payload.get("manual_override_count"),
        "source_outcome_count": payload.get("source_outcome_count"),
        "source_outcome_ids": payload.get("source_outcome_ids"),
        "source_outcome_hashes": payload.get("source_outcome_hashes"),
    }
    seed = {
        "version": CANDIDATE_PROFILE_VERSION,
        "source_report_id": payload.get("performance_report_id"),
        "source_report_hash": payload.get("performance_report_sha256"),
        "profile_id": payload.get("profile_id"),
        "research_signal_id": payload.get("research_signal_id"),
        "performance_snapshot": performance_snapshot,
        "created_at_utc": utc_now_canonical(),
    }
    profile_candidate_hash = sha256_json(seed)
    profile = CandidateProfileDraft(
        candidate_profile_id=stable_id("candidate_profile", {**seed, "profile_candidate_hash": profile_candidate_hash}, 24),
        candidate_profile_version=CANDIDATE_PROFILE_VERSION,
        creation_status=CREATION_STATUS_CREATED_REVIEW_ONLY,
        source_report_id=_text(payload.get("performance_report_id")),
        source_report_hash=_text(payload.get("performance_report_sha256")),
        source_report_registry_record_id=_text(payload.get("performance_report_registry_record_id")),
        source_report_registry_record_sha256=_text(payload.get("performance_report_registry_record_sha256")),
        profile_version=f"candidate_from_{_text(payload.get('performance_report_id')) or 'performance_report'}",
        strategy_family="research_signal_feedback_v1",
        target_timeframe=_target_timeframe_from_report(payload),
        allowed_direction=_direction_from_report(payload),
        expected_edge_reason=(
            f"positive_expectancy={_float(payload.get('expectancy'), 0.0):.8f}; "
            f"average_R={_float(payload.get('average_R'), 0.0):.8f}; "
            f"sample_size={int(_float(payload.get('sample_size'), 0.0))}"
        ),
        data_quality_score=_data_quality_score(payload),
        paper_priority_score=_paper_priority_score(payload),
        risk_complexity_score=_risk_complexity_score(payload),
        feature_matrix_sha256=payload.get("feature_matrix_sha256"),
        profile_candidate_hash=profile_candidate_hash,
        live_ineligible_reason="candidate_profile_requires_manual_approval_and_paper_validation",
        status=STATUS_REVIEW_ONLY,
        performance_snapshot=performance_snapshot,
        paper_candidate=False,
        approval_packet_ready=False,
        created_at_utc=seed["created_at_utc"],
    )
    result = profile.to_dict()
    result["candidate_profile_created"] = True
    result["blockers"] = []
    return result


def build_candidate_profile_registry_record(candidate_profile: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(candidate_profile or {})
    record = {
        "candidate_profile_registry_version": CANDIDATE_PROFILE_VERSION,
        "candidate_profile_id": payload.get("candidate_profile_id"),
        "candidate_profile_created": payload.get("candidate_profile_created", False),
        "creation_status": payload.get("creation_status"),
        "source_report_id": payload.get("source_report_id"),
        "source_report_hash": payload.get("source_report_hash"),
        "source_report_registry_record_id": payload.get("source_report_registry_record_id"),
        "source_report_registry_record_sha256": payload.get("source_report_registry_record_sha256"),
        "profile_version": payload.get("profile_version"),
        "strategy_family": payload.get("strategy_family"),
        "target_timeframe": payload.get("target_timeframe"),
        "allowed_direction": payload.get("allowed_direction"),
        "expected_edge_reason": payload.get("expected_edge_reason"),
        "data_quality_score": payload.get("data_quality_score"),
        "paper_priority_score": payload.get("paper_priority_score"),
        "risk_complexity_score": payload.get("risk_complexity_score"),
        "feature_matrix_sha256": payload.get("feature_matrix_sha256"),
        "profile_candidate_hash": payload.get("profile_candidate_hash"),
        "live_ineligible_reason": payload.get("live_ineligible_reason"),
        "status": payload.get("status"),
        "review_only": payload.get("review_only", True),
        "paper_candidate": payload.get("paper_candidate", False),
        "approval_packet_ready": payload.get("approval_packet_ready", False),
        "candidate_profile_applied": payload.get("candidate_profile_applied", False),
        "approval_packet_created": payload.get("approval_packet_created", False),
        "settings_write_preview_created": payload.get("settings_write_preview_created", False),
        "live_trading_allowed_by_this_module": payload.get("live_trading_allowed_by_this_module", False),
        "runtime_settings_mutated": payload.get("runtime_settings_mutated", False),
        "score_weights_mutated": payload.get("score_weights_mutated", False),
        "auto_promotion_allowed": payload.get("auto_promotion_allowed", False),
        "blockers": payload.get("blockers", []),
        "created_at_utc": payload.get("created_at_utc") or utc_now_canonical(),
    }
    if not record.get("candidate_profile_id"):
        record["candidate_profile_blocked_record_id"] = payload.get("candidate_profile_blocked_record_id") or stable_id("candidate_profile_blocked", record, 24)
    record["candidate_profile_registry_record_id"] = stable_id("candidate_profile_registry", record, 24)
    record["candidate_profile_registry_record_sha256"] = sha256_json(record)
    return record


def persist_candidate_profile(cfg: AppConfig, candidate_profile: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(candidate_profile or {})
    atomic_write_json(_latest_path(cfg, "candidate_profile.json"), payload)
    registry_record = build_candidate_profile_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, CANDIDATE_PROFILE_REGISTRY_NAME),
        registry_record,
        registry_name=CANDIDATE_PROFILE_REGISTRY_NAME,
        id_field="candidate_profile_registry_record_id",
        hash_field="candidate_profile_registry_record_sha256",
        id_prefix="candidate_profile_registry",
    )
    atomic_write_json(_latest_path(cfg, "candidate_profile_registry_record.json"), persisted)
    payload["candidate_profile_registry_record_id"] = persisted.get("candidate_profile_registry_record_id")
    payload["candidate_profile_registry_record_sha256"] = persisted.get("candidate_profile_registry_record_sha256")
    atomic_write_json(_latest_path(cfg, "candidate_profile.json"), payload)
    return persisted


def generate_and_persist_candidate_profile(
    performance_report: Mapping[str, Any],
    *,
    cfg: AppConfig | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    candidate = build_candidate_profile_from_performance_report(performance_report)
    registry_record = persist_candidate_profile(cfg, candidate)
    candidate["candidate_profile_registry_record_id"] = registry_record.get("candidate_profile_registry_record_id")
    candidate["candidate_profile_registry_record_sha256"] = registry_record.get("candidate_profile_registry_record_sha256")
    atomic_write_json(_latest_path(cfg, "candidate_profile.json"), candidate)
    return candidate


def run_candidate_profile_latest(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    path = _latest_path(cfg, "performance_report.json")
    if not path.exists():
        return generate_and_persist_candidate_profile({}, cfg=cfg)
    report = read_json(path, default={})
    if not isinstance(report, Mapping):
        report = {}
    return generate_and_persist_candidate_profile(report, cfg=cfg)
