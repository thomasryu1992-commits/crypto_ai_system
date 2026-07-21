from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.json_io import atomic_write_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.feedback.outcome_analytics_v2 import OUTCOME_FEEDBACK_REGISTRY_NAME, summarize_outcomes
from crypto_ai_system.registry.base_registry import append_registry_record, load_registry_records, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PERFORMANCE_REPORT_VERSION = "step297_performance_report_generator_v1"
PERFORMANCE_REPORT_REGISTRY_NAME = "performance_report_registry"

STATUS_PERFORMANCE_REPORT_RECORDED = "PERFORMANCE_REPORT_RECORDED"
STATUS_PERFORMANCE_REPORT_REVIEW_ONLY_INSUFFICIENT_SAMPLE = "PERFORMANCE_REPORT_REVIEW_ONLY_INSUFFICIENT_SAMPLE"
STATUS_PERFORMANCE_REPORT_BLOCKED_NO_OUTCOMES = "PERFORMANCE_REPORT_BLOCKED_NO_OUTCOMES"
STATUS_PERFORMANCE_REPORT_BLOCKED_UNSAFE_SIDE_EFFECT = "PERFORMANCE_REPORT_BLOCKED_UNSAFE_SIDE_EFFECT"

RECOMMEND_REPEAT_IN_PAPER = "repeat_in_paper"
RECOMMEND_EXPAND_TEST_COVERAGE = "expand_test_coverage"
RECOMMEND_CREATE_CANDIDATE_PROFILE_DRAFT = "create_candidate_profile_draft"
RECOMMEND_DROP_CANDIDATE_PROFILE = "drop_candidate_profile"
RECOMMEND_ARCHIVE = "archive"

LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_CREATED_BY_THIS_MODULE = False
APPROVAL_PACKET_CREATED_BY_THIS_MODULE = False


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


def _registry_rows(cfg: AppConfig) -> list[dict[str, Any]]:
    path = registry_path(cfg, OUTCOME_FEEDBACK_REGISTRY_NAME)
    return load_registry_records(path)


def _unsafe_side_effect(row: Mapping[str, Any]) -> bool:
    return any(
        _bool(row.get(name))
        for name in [
            "live_trading_allowed_by_this_module",
            "runtime_settings_mutated",
            "score_weights_mutated",
            "auto_promotion_allowed",
            "live_order_executed",
            "external_order_submission_performed",
            "adapter_called",
        ]
    )


def _filter_outcomes(
    rows: Iterable[Mapping[str, Any]],
    *,
    profile_id: str | None = None,
    research_signal_id: str | None = None,
    include_blocked: bool = True,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        if profile_id and _text(payload.get("profile_id")) != profile_id:
            continue
        if research_signal_id and _text(payload.get("research_signal_id")) != research_signal_id:
            continue
        if not include_blocked and str(payload.get("status", "")).startswith("OUTCOME_BLOCKED"):
            continue
        filtered.append(payload)
    return filtered


def _group_key(row: Mapping[str, Any], key: str) -> str:
    value = _text(row.get(key))
    return value or "unknown"


def _summaries_by(rows: list[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault(_group_key(row, key), []).append(row)
    return {name: summarize_outcomes(values) for name, values in sorted(groups.items())}


def _closed_count_by_signal(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("outcome_closed") is not True:
            continue
        key = _group_key(row, "research_signal_id")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _low_sample_signal_ids(rows: list[Mapping[str, Any]], min_signal_sample_size: int) -> set[str]:
    counts = _closed_count_by_signal(rows)
    return {signal_id for signal_id, count in counts.items() if count < min_signal_sample_size}


def _r_distribution(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    closed = [r for r in rows if r.get("outcome_closed") is True]
    values = [_float(r.get("result_R"), 0.0) for r in closed]
    return {
        "lt_minus_1R": sum(1 for value in values if value < -1.0),
        "minus_1R_to_0R": sum(1 for value in values if -1.0 <= value < 0.0),
        "zero_R": sum(1 for value in values if value == 0.0),
        "zero_to_1R": sum(1 for value in values if 0.0 < value < 1.0),
        "one_to_2R": sum(1 for value in values if 1.0 <= value < 2.0),
        "gte_2R": sum(1 for value in values if value >= 2.0),
    }


def _failure_modes(rows: list[Mapping[str, Any]], summary: Mapping[str, Any]) -> list[str]:
    modes: list[str] = []
    if not rows:
        return ["NO_OUTCOME_RECORDS"]
    if any(_unsafe_side_effect(row) for row in rows):
        modes.append("UNSAFE_SIDE_EFFECT_FLAG_DETECTED")
    mismatch_count = int(_float(summary.get("reconciliation_mismatch_count"), 0.0))
    if mismatch_count:
        modes.append("RECONCILIATION_MISMATCH_PRESENT")
    if _float(summary.get("rejection_rate"), 0.0) > 0:
        modes.append("ORDER_REJECTION_PRESENT")
    if _float(summary.get("stale_data_rate"), 0.0) > 0:
        modes.append("STALE_DATA_OBSERVED")
    if _float(summary.get("api_error_rate"), 0.0) > 0:
        modes.append("API_ERROR_OBSERVED")
    if _float(summary.get("signal_to_outcome_drift"), 0.0) > 0:
        modes.append("SIGNAL_TO_OUTCOME_DRIFT_OBSERVED")
    if _float(summary.get("expectancy"), 0.0) < 0:
        modes.append("NEGATIVE_EXPECTANCY")
    if int(_float(summary.get("closed_count"), 0.0)) == 0:
        modes.append("NO_CLOSED_OUTCOMES")
    return modes


def _status_and_recommendation(rows: list[Mapping[str, Any]], summary: Mapping[str, Any], *, min_sample_size: int) -> tuple[str, str, list[str]]:
    blockers: list[str] = []
    if not rows:
        return STATUS_PERFORMANCE_REPORT_BLOCKED_NO_OUTCOMES, RECOMMEND_EXPAND_TEST_COVERAGE, ["NO_OUTCOME_RECORDS"]
    if any(_unsafe_side_effect(row) for row in rows):
        return STATUS_PERFORMANCE_REPORT_BLOCKED_UNSAFE_SIDE_EFFECT, RECOMMEND_EXPAND_TEST_COVERAGE, ["UNSAFE_SIDE_EFFECT_FLAG_DETECTED"]

    closed_count = int(_float(summary.get("closed_count"), 0.0))
    mismatch_count = int(_float(summary.get("reconciliation_mismatch_count"), 0.0))
    if mismatch_count:
        blockers.append("RECONCILIATION_MISMATCH_PRESENT")
    if closed_count < min_sample_size:
        blockers.append("INSUFFICIENT_CLOSED_OUTCOME_SAMPLE")
        return STATUS_PERFORMANCE_REPORT_REVIEW_ONLY_INSUFFICIENT_SAMPLE, RECOMMEND_REPEAT_IN_PAPER, blockers

    expectancy = _float(summary.get("expectancy"), 0.0)
    if expectancy < 0:
        return STATUS_PERFORMANCE_REPORT_RECORDED, RECOMMEND_DROP_CANDIDATE_PROFILE, blockers
    if expectancy == 0:
        return STATUS_PERFORMANCE_REPORT_RECORDED, RECOMMEND_REPEAT_IN_PAPER, blockers
    return STATUS_PERFORMANCE_REPORT_RECORDED, RECOMMEND_CREATE_CANDIDATE_PROFILE_DRAFT, blockers


@dataclass
class PerformanceReport:
    performance_report_id: str
    performance_report_version: str
    status: str
    recommendation: str
    source_registry_name: str
    source_outcome_count: int
    sample_size: int
    closed_count: int
    profile_id: str
    research_signal_id: str
    time_range: dict[str, Any]
    expectancy: float
    win_loss_ratio: float
    average_R: float
    max_drawdown: float
    r_distribution: dict[str, int]
    min_signal_sample_size: int
    excluded_low_sample_signal_ids: list[str]
    excluded_low_sample_outcome_count: int
    average_slippage: float
    average_latency_ms: float
    rejection_rate: float
    stale_data_rate: float
    signal_to_outcome_drift: float
    paper_live_gap: str | float
    api_error_rate: float
    manual_override_count: int
    reconciliation_mismatch_count: int
    summary_by_profile: dict[str, dict[str, Any]]
    summary_by_signal: dict[str, dict[str, Any]]
    summary_by_regime: dict[str, dict[str, Any]]
    summary_by_direction: dict[str, dict[str, Any]]
    failure_modes: list[str]
    blockers: list[str]
    source_outcome_ids: list[str]
    source_outcome_hashes: list[str]
    live_candidate_eligible: bool
    candidate_profile_created: bool = CANDIDATE_PROFILE_CREATED_BY_THIS_MODULE
    approval_packet_created: bool = APPROVAL_PACKET_CREATED_BY_THIS_MODULE
    live_trading_allowed_by_this_module: bool = LIVE_TRADING_ALLOWED_BY_THIS_MODULE
    runtime_settings_mutated: bool = RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE
    score_weights_mutated: bool = SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE
    auto_promotion_allowed: bool = AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE
    created_at_utc: str = field(default_factory=utc_now_canonical)
    performance_report_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not payload.get("performance_report_sha256"):
            payload["performance_report_sha256"] = sha256_json({k: v for k, v in payload.items() if k != "performance_report_sha256"})
        return payload


def build_performance_report(
    outcomes: Iterable[Mapping[str, Any]],
    *,
    profile_id: str | None = None,
    research_signal_id: str | None = None,
    min_sample_size: int = 3,
    min_signal_sample_size: int = 3,
) -> dict[str, Any]:
    rows = _filter_outcomes(outcomes, profile_id=profile_id, research_signal_id=research_signal_id)
    # Signals that haven't closed enough trades yet are excluded from the
    # aggregate stats that drive live-candidate eligibility, so a single
    # one-off trade can't swing the decision. summary_by_signal below still
    # reports every signal, unfiltered, for visibility. This only applies when
    # blending multiple signals into one "mixed" report — a report already
    # scoped to a single research_signal_id is gated by min_sample_size alone,
    # not this per-signal threshold, or it would always exclude itself.
    distinct_signal_ids = {_group_key(row, "research_signal_id") for row in rows}
    if research_signal_id is not None or len(distinct_signal_ids) <= 1:
        low_sample_signal_ids: set[str] = set()
    else:
        low_sample_signal_ids = _low_sample_signal_ids(rows, min_signal_sample_size)
    eligible_rows = [row for row in rows if _group_key(row, "research_signal_id") not in low_sample_signal_ids]
    excluded_rows = [row for row in rows if _group_key(row, "research_signal_id") in low_sample_signal_ids]
    summary = summarize_outcomes(eligible_rows)
    status, recommendation, blockers = _status_and_recommendation(eligible_rows, summary, min_sample_size=min_sample_size)
    failure_modes = sorted(dict.fromkeys([*blockers, *_failure_modes(eligible_rows, summary)]))
    source_ids = [_text(row.get("outcome_id")) for row in rows if _text(row.get("outcome_id"))]
    source_hashes = [_text(row.get("outcome_record_sha256")) for row in rows if _text(row.get("outcome_record_sha256"))]
    created_values = sorted(_text(row.get("created_at_utc")) for row in rows if _text(row.get("created_at_utc")))
    profile_values = sorted({_text(row.get("profile_id")) for row in rows if _text(row.get("profile_id"))})
    signal_values = sorted({_text(row.get("research_signal_id")) for row in rows if _text(row.get("research_signal_id"))})
    paper_live_values = [row.get("paper_live_gap") for row in eligible_rows if row.get("paper_live_gap") not in {None, "", "not_applicable"}]
    if paper_live_values:
        paper_live_gap: str | float = round(sum(_float(v, 0.0) for v in paper_live_values) / len(paper_live_values), 8)
    else:
        paper_live_gap = "not_applicable"

    report_seed = {
        "version": PERFORMANCE_REPORT_VERSION,
        "profile_id": profile_id or (profile_values[0] if len(profile_values) == 1 else "mixed" if profile_values else "unknown"),
        "research_signal_id": research_signal_id or (signal_values[0] if len(signal_values) == 1 else "mixed" if signal_values else "unknown"),
        "source_outcome_ids": source_ids,
        "created_at_utc": utc_now_canonical(),
    }
    performance_report_id = stable_id("performance_report", report_seed, 24)
    live_candidate_eligible = (
        status == STATUS_PERFORMANCE_REPORT_RECORDED
        and recommendation == RECOMMEND_CREATE_CANDIDATE_PROFILE_DRAFT
        and not failure_modes
        and len(eligible_rows) >= min_sample_size
    )

    report = PerformanceReport(
        performance_report_id=performance_report_id,
        performance_report_version=PERFORMANCE_REPORT_VERSION,
        status=status,
        recommendation=recommendation,
        source_registry_name=OUTCOME_FEEDBACK_REGISTRY_NAME,
        source_outcome_count=len(rows),
        sample_size=int(summary.get("closed_count", 0) or 0),
        closed_count=int(summary.get("closed_count", 0) or 0),
        profile_id=report_seed["profile_id"],
        research_signal_id=report_seed["research_signal_id"],
        time_range={
            "created_at_start_utc": created_values[0] if created_values else None,
            "created_at_end_utc": created_values[-1] if created_values else None,
        },
        expectancy=_float(summary.get("expectancy"), 0.0),
        win_loss_ratio=_float(summary.get("win_loss_ratio"), 0.0),
        average_R=_float(summary.get("average_R"), 0.0),
        max_drawdown=_float(summary.get("max_drawdown"), 0.0),
        r_distribution=_r_distribution(eligible_rows),
        min_signal_sample_size=min_signal_sample_size,
        excluded_low_sample_signal_ids=sorted(low_sample_signal_ids),
        excluded_low_sample_outcome_count=len(excluded_rows),
        average_slippage=_float(summary.get("average_slippage"), 0.0),
        average_latency_ms=_float(summary.get("average_latency_ms"), 0.0),
        rejection_rate=_float(summary.get("rejection_rate"), 0.0),
        stale_data_rate=_float(summary.get("stale_data_rate"), 0.0),
        signal_to_outcome_drift=_float(summary.get("signal_to_outcome_drift"), 0.0),
        paper_live_gap=paper_live_gap,
        api_error_rate=_float(summary.get("api_error_rate"), 0.0),
        manual_override_count=int(summary.get("manual_override_count", 0) or 0),
        reconciliation_mismatch_count=int(summary.get("reconciliation_mismatch_count", 0) or 0),
        summary_by_profile=_summaries_by(rows, "profile_id"),
        summary_by_signal={
            signal_id: {**row_summary, "sufficient_sample": signal_id not in low_sample_signal_ids}
            for signal_id, row_summary in _summaries_by(rows, "research_signal_id").items()
        },
        summary_by_regime=_summaries_by(rows, "regime"),
        summary_by_direction=_summaries_by(rows, "direction"),
        failure_modes=failure_modes,
        blockers=blockers,
        source_outcome_ids=source_ids,
        source_outcome_hashes=source_hashes,
        live_candidate_eligible=live_candidate_eligible,
        created_at_utc=report_seed["created_at_utc"],
    )
    payload = report.to_dict()
    return payload


def build_performance_report_registry_record(report: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(report or {})
    record = {
        "performance_report_registry_version": PERFORMANCE_REPORT_VERSION,
        "performance_report_id": payload.get("performance_report_id"),
        "performance_report_sha256": payload.get("performance_report_sha256"),
        "status": payload.get("status"),
        "recommendation": payload.get("recommendation"),
        "profile_id": payload.get("profile_id"),
        "research_signal_id": payload.get("research_signal_id"),
        "source_registry_name": payload.get("source_registry_name"),
        "source_outcome_count": payload.get("source_outcome_count"),
        "sample_size": payload.get("sample_size"),
        "closed_count": payload.get("closed_count"),
        "expectancy": payload.get("expectancy"),
        "win_loss_ratio": payload.get("win_loss_ratio"),
        "average_R": payload.get("average_R"),
        "max_drawdown": payload.get("max_drawdown"),
        "r_distribution": payload.get("r_distribution"),
        "min_signal_sample_size": payload.get("min_signal_sample_size"),
        "excluded_low_sample_signal_ids": payload.get("excluded_low_sample_signal_ids"),
        "excluded_low_sample_outcome_count": payload.get("excluded_low_sample_outcome_count"),
        "reconciliation_mismatch_count": payload.get("reconciliation_mismatch_count"),
        "failure_modes": payload.get("failure_modes"),
        "blockers": payload.get("blockers"),
        "live_candidate_eligible": payload.get("live_candidate_eligible"),
        "candidate_profile_created": payload.get("candidate_profile_created"),
        "approval_packet_created": payload.get("approval_packet_created"),
        "live_trading_allowed_by_this_module": payload.get("live_trading_allowed_by_this_module"),
        "runtime_settings_mutated": payload.get("runtime_settings_mutated"),
        "score_weights_mutated": payload.get("score_weights_mutated"),
        "auto_promotion_allowed": payload.get("auto_promotion_allowed"),
        "source_outcome_ids": payload.get("source_outcome_ids"),
        "source_outcome_hashes": payload.get("source_outcome_hashes"),
        "created_at_utc": payload.get("created_at_utc") or utc_now_canonical(),
    }
    record["performance_report_registry_record_id"] = stable_id("performance_report_registry", record, 24)
    record["performance_report_registry_record_sha256"] = sha256_json(record)
    return record


#: This registry is a write-only audit trail — every consumer reads the
#: separately persisted latest record, so an oversized file can be archived to
#: a timestamped sibling without changing any runtime input.
PERFORMANCE_REPORT_REGISTRY_MAX_BYTES = 10 * 1024 * 1024


def persist_performance_report(cfg: AppConfig, report: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(report or {})
    atomic_write_json(_latest_path(cfg, "performance_report.json"), payload)
    registry_record = build_performance_report_registry_record(payload)
    from crypto_ai_system.registry.base_registry import rotate_registry_if_large

    rotate_registry_if_large(
        registry_path(cfg, PERFORMANCE_REPORT_REGISTRY_NAME),
        max_bytes=PERFORMANCE_REPORT_REGISTRY_MAX_BYTES,
    )
    persisted = append_registry_record(
        registry_path(cfg, PERFORMANCE_REPORT_REGISTRY_NAME),
        registry_record,
        registry_name=PERFORMANCE_REPORT_REGISTRY_NAME,
        id_field="performance_report_registry_record_id",
        hash_field="performance_report_registry_record_sha256",
        id_prefix="performance_report_registry",
    )
    atomic_write_json(_latest_path(cfg, "performance_report_registry_record.json"), persisted)
    payload["performance_report_registry_record_id"] = persisted.get("performance_report_registry_record_id")
    payload["performance_report_registry_record_sha256"] = persisted.get("performance_report_registry_record_sha256")
    atomic_write_json(_latest_path(cfg, "performance_report.json"), payload)
    return persisted


def generate_and_persist_performance_report(
    outcomes: Iterable[Mapping[str, Any]],
    *,
    cfg: AppConfig | None = None,
    profile_id: str | None = None,
    research_signal_id: str | None = None,
    min_sample_size: int = 3,
    min_signal_sample_size: int = 3,
) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    report = build_performance_report(
        outcomes,
        profile_id=profile_id,
        research_signal_id=research_signal_id,
        min_sample_size=min_sample_size,
        min_signal_sample_size=min_signal_sample_size,
    )
    registry_record = persist_performance_report(cfg, report)
    report["performance_report_registry_record_id"] = registry_record.get("performance_report_registry_record_id")
    report["performance_report_registry_record_sha256"] = registry_record.get("performance_report_registry_record_sha256")
    atomic_write_json(_latest_path(cfg, "performance_report.json"), report)
    return report


def run_performance_report_latest(
    *,
    cfg: AppConfig | None = None,
    profile_id: str | None = None,
    research_signal_id: str | None = None,
    min_sample_size: int = 3,
    min_signal_sample_size: int | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    if min_signal_sample_size is None:
        import config.settings as settings

        min_signal_sample_size = getattr(settings, "MIN_SIGNAL_SAMPLE_SIZE", 3)
    rows = _registry_rows(cfg)
    return generate_and_persist_performance_report(
        rows,
        cfg=cfg,
        profile_id=profile_id,
        research_signal_id=research_signal_id,
        min_sample_size=min_sample_size,
        min_signal_sample_size=min_signal_sample_size,
    )
