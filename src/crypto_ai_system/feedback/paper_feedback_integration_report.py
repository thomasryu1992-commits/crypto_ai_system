from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.feedback.paper_lifecycle_outcome_store import (
    execute_paper_lifecycle_outcome_store,
)

STEP214_STATUS_OK = "STEP214_V5_PAPER_FEEDBACK_INTEGRATION_REPORT_OK"
STEP214_VALIDATION_OK = "STEP214_V5_PAPER_FEEDBACK_INTEGRATION_REPORT_VALIDATION_OK"

MIN_REVIEW_OUTCOMES = 3
MIN_FEEDBACK_SCORE_REVIEW = 60.0
MIN_FEEDBACK_SCORE_WATCHLIST = 40.0
MIN_EXPECTANCY_REVIEW = 0.0
MIN_QUALITY_REVIEW = 0.95


@dataclass
class PaperFeedbackCandidateReview:
    feedback_review_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    side: str
    source_outcome_store_status: str
    outcome_count: int
    closed_count: int
    rejected_count: int
    win_rate: float
    expectancy_r: float
    profit_factor: float
    average_lifecycle_quality_score: float
    min_lifecycle_quality_score: float
    feedback_score: float
    feedback_grade: str
    feedback_status: str
    blockers: List[str]
    warnings: List[str]
    review_notes: List[str]
    next_required_step: str
    feedback_engine_input_ready: bool
    promotion_allowed: bool
    strategy_registry_write_allowed: bool
    paper_order_execution_enabled: bool
    live_trading_allowed: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step214PaperFeedbackIntegrationReportResult:
    status: str
    root: str
    source_step213_result_path: str
    feedback_reviews_json_path: str
    feedback_reviews_jsonl_path: str
    feedback_reviews_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_candidate_aggregate_count: int
    feedback_review_count: int
    review_only_candidate_count: int
    watchlist_candidate_count: int
    blocked_candidate_count: int
    average_feedback_score: float
    max_feedback_score: float
    min_feedback_score: float
    feedback_integration_report_created: bool
    feedback_engine_input_ready: bool
    promotion_gate_input_ready: bool
    promotion_allowed: bool
    strategy_registry_write_allowed: bool
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    adapter_routing_enabled: bool
    shadow_execution_enabled: bool
    auto_strategy_promotion: bool
    external_api_call_performed: bool
    live_order_executed: bool
    real_adapter_call_performed: bool
    telegram_real_send: bool
    production_cutover_executable: bool
    live_mode_enable_allowed: bool
    reviews: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: _utc_now())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step214ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step213_present: bool
    feedback_reviews_json_exists: bool
    feedback_reviews_jsonl_exists: bool
    feedback_reviews_csv_exists: bool
    markdown_report_exists: bool
    source_candidate_aggregates_present: bool
    feedback_reviews_present: bool
    feedback_report_created: bool
    feedback_engine_input_ready: bool
    promotion_gate_input_ready: bool
    no_promotion: bool
    no_strategy_registry_write: bool
    no_paper_order_execution: bool
    no_adapter_routing: bool
    no_shadow_execution: bool
    no_external_api_calls: bool
    no_live_side_effects: bool
    no_production_cutover: bool
    blocking_failure_count: int
    blocking_failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["feedback_review_id", "feedback_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["blockers"] = "|".join(out.get("blockers", []))
            out["warnings"] = "|".join(out.get("warnings", []))
            out["review_notes"] = "|".join(out.get("review_notes", []))
            writer.writerow(out)


def _ensure_step213(root: Path, *, allow_source_regeneration: bool = False) -> Dict[str, Any]:
    path = root / "storage/latest/step213_paper_lifecycle_outcome_store_latest.json"
    if not path.exists():
        if allow_source_regeneration:
            execute_paper_lifecycle_outcome_store(root, write_output=True, allow_source_regeneration=True)
        else:
            raise FileNotFoundError(
                f"Missing required Step213 source artifact: {path}. Step269 feedback integration fails closed; "
                "run explicit regeneration command before feedback report generation."
            )
    return _load_json(path)


def _load_step213_aggregates(step213: Dict[str, Any]) -> List[Dict[str, Any]]:
    aggregate_path = Path(step213.get("candidate_aggregate_json_path", ""))
    if aggregate_path.exists():
        return list(_load_json(aggregate_path).get("aggregates", []) or [])
    return list(step213.get("aggregates", []) or [])


def _score_sample_size(outcome_count: int) -> float:
    return min(20.0, max(0.0, outcome_count / MIN_REVIEW_OUTCOMES * 20.0))


def _score_expectancy(expectancy_r: float) -> float:
    # Maps -0.5R to 0, 0R to 15, +0.5R or above to 30.
    clipped = max(-0.5, min(0.5, expectancy_r))
    return (clipped + 0.5) / 1.0 * 30.0


def _score_profit_factor(profit_factor: float) -> float:
    if profit_factor >= 2.0:
        return 20.0
    if profit_factor <= 0.5:
        return 0.0
    return (profit_factor - 0.5) / 1.5 * 20.0


def _score_quality(quality: float) -> float:
    return max(0.0, min(1.0, quality)) * 20.0


def _score_rejection_penalty(rejected_count: int, outcome_count: int) -> float:
    if outcome_count <= 0:
        return 10.0
    reject_rate = rejected_count / outcome_count
    return min(10.0, reject_rate * 20.0)


def _feedback_score(aggregate: Dict[str, Any]) -> float:
    outcome_count = int(aggregate.get("outcome_count", 0))
    rejected_count = int(aggregate.get("rejected_count", 0))
    expectancy_r = float(aggregate.get("expectancy_r", 0.0))
    profit_factor = float(aggregate.get("profit_factor", 0.0))
    quality = float(aggregate.get("average_lifecycle_quality_score", 0.0))
    score = (
        _score_sample_size(outcome_count)
        + _score_expectancy(expectancy_r)
        + _score_profit_factor(profit_factor)
        + _score_quality(quality)
        - _score_rejection_penalty(rejected_count, outcome_count)
    )
    return round(max(0.0, min(100.0, score)), 6)


def _feedback_grade(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "F"


def _build_blockers(aggregate: Dict[str, Any], score: float) -> List[str]:
    blockers = list(aggregate.get("blockers", []) or [])
    outcome_count = int(aggregate.get("outcome_count", 0))
    expectancy_r = float(aggregate.get("expectancy_r", 0.0))
    min_quality = float(aggregate.get("min_lifecycle_quality_score", 0.0))
    rejected_count = int(aggregate.get("rejected_count", 0))
    if outcome_count <= 0:
        blockers.append("NO_FEEDBACK_OUTCOMES")
    if outcome_count < MIN_REVIEW_OUTCOMES:
        blockers.append("FEEDBACK_SAMPLE_TOO_LOW")
    if expectancy_r < MIN_EXPECTANCY_REVIEW:
        blockers.append("FEEDBACK_EXPECTANCY_BELOW_ZERO")
    if min_quality < MIN_QUALITY_REVIEW:
        blockers.append("FEEDBACK_LIFECYCLE_QUALITY_BELOW_THRESHOLD")
    if rejected_count > 0:
        blockers.append("FEEDBACK_REJECTED_OUTCOMES_PRESENT")
    if score < MIN_FEEDBACK_SCORE_WATCHLIST:
        blockers.append("FEEDBACK_SCORE_TOO_LOW")
    return sorted(set(str(b) for b in blockers if str(b)))


def _build_warnings(aggregate: Dict[str, Any], score: float) -> List[str]:
    warnings: List[str] = []
    outcome_count = int(aggregate.get("outcome_count", 0))
    profit_factor = float(aggregate.get("profit_factor", 0.0))
    source_status = str(aggregate.get("outcome_store_status", ""))
    if outcome_count < MIN_REVIEW_OUTCOMES * 2:
        warnings.append("MORE_OUTCOME_SAMPLE_RECOMMENDED")
    if 0.0 <= float(aggregate.get("expectancy_r", 0.0)) < 0.1:
        warnings.append("LOW_POSITIVE_EXPECTANCY")
    if profit_factor < 1.2:
        warnings.append("LOW_PROFIT_FACTOR_MARGIN")
    if source_status == "PAPER_OUTCOME_WATCHLIST":
        warnings.append("SOURCE_OUTCOME_WATCHLIST")
    if MIN_FEEDBACK_SCORE_WATCHLIST <= score < MIN_FEEDBACK_SCORE_REVIEW:
        warnings.append("FEEDBACK_SCORE_WATCHLIST_RANGE")
    return sorted(set(warnings))


def _feedback_status(score: float, blockers: List[str], aggregate: Dict[str, Any]) -> str:
    source_status = str(aggregate.get("outcome_store_status", ""))
    hard_blockers = {
        "NO_FEEDBACK_OUTCOMES",
        "NO_CLOSED_SIMULATED_OUTCOMES",
        "OUTCOME_EXPECTANCY_BELOW_ZERO",
        "FEEDBACK_EXPECTANCY_BELOW_ZERO",
        "LIFECYCLE_QUALITY_BELOW_THRESHOLD",
        "FEEDBACK_LIFECYCLE_QUALITY_BELOW_THRESHOLD",
        "REJECTED_SIMULATED_OUTCOMES_PRESENT",
        "FEEDBACK_REJECTED_OUTCOMES_PRESENT",
        "FEEDBACK_SCORE_TOO_LOW",
    }
    if source_status == "PAPER_OUTCOME_BLOCKED" or any(b in hard_blockers for b in blockers):
        return "PAPER_FEEDBACK_BLOCKED"
    if score >= MIN_FEEDBACK_SCORE_REVIEW and not blockers:
        return "PAPER_FEEDBACK_REVIEW_ONLY"
    return "PAPER_FEEDBACK_WATCHLIST"


def _review_notes(status: str, aggregate: Dict[str, Any], score: float) -> List[str]:
    notes = [
        "Feedback review is evidence-only and does not approve live trading.",
        "Promotion remains disabled until a dedicated promotion gate step is implemented.",
    ]
    if status == "PAPER_FEEDBACK_REVIEW_ONLY":
        notes.append("Candidate has usable paper outcome evidence for promotion-gate review.")
    elif status == "PAPER_FEEDBACK_WATCHLIST":
        notes.append("Candidate needs additional paper observation or blocker review before promotion-gate review.")
    else:
        notes.append("Candidate should not proceed to promotion-gate review under current evidence.")
    if float(aggregate.get("expectancy_r", 0.0)) > 0 and score < MIN_FEEDBACK_SCORE_REVIEW:
        notes.append("Positive expectancy exists, but sample/quality/profit-factor constraints still require review.")
    return notes


def _review_id(aggregate: Dict[str, Any], score: float) -> str:
    raw = "|".join(
        [
            "step214_feedback_review",
            str(aggregate.get("aggregate_id", "")),
            str(aggregate.get("observation_id", "")),
            str(score),
        ]
    )
    return "fbr_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _build_review(aggregate: Dict[str, Any]) -> PaperFeedbackCandidateReview:
    score = _feedback_score(aggregate)
    blockers = _build_blockers(aggregate, score)
    warnings = _build_warnings(aggregate, score)
    status = _feedback_status(score, blockers, aggregate)
    return PaperFeedbackCandidateReview(
        feedback_review_id=_review_id(aggregate, score),
        observation_id=str(aggregate.get("observation_id", "")),
        registry_id=str(aggregate.get("registry_id", "")),
        comparison_group=str(aggregate.get("comparison_group", "")),
        side=str(aggregate.get("side", "")),
        source_outcome_store_status=str(aggregate.get("outcome_store_status", "")),
        outcome_count=int(aggregate.get("outcome_count", 0)),
        closed_count=int(aggregate.get("closed_count", 0)),
        rejected_count=int(aggregate.get("rejected_count", 0)),
        win_rate=float(aggregate.get("win_rate", 0.0)),
        expectancy_r=float(aggregate.get("expectancy_r", 0.0)),
        profit_factor=float(aggregate.get("profit_factor", 0.0)),
        average_lifecycle_quality_score=float(aggregate.get("average_lifecycle_quality_score", 0.0)),
        min_lifecycle_quality_score=float(aggregate.get("min_lifecycle_quality_score", 0.0)),
        feedback_score=score,
        feedback_grade=_feedback_grade(score),
        feedback_status=status,
        blockers=blockers,
        warnings=warnings,
        review_notes=_review_notes(status, aggregate, score),
        next_required_step="STEP215_PROMOTION_GATE_V2_REVIEW_ONLY",
        feedback_engine_input_ready=status in {"PAPER_FEEDBACK_REVIEW_ONLY", "PAPER_FEEDBACK_WATCHLIST"},
        promotion_allowed=False,
        strategy_registry_write_allowed=False,
        paper_order_execution_enabled=False,
        live_trading_allowed=False,
    )


def _blocker_summary(reviews: List[PaperFeedbackCandidateReview]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for review in reviews:
        if not review.blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in review.blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step214PaperFeedbackIntegrationReportResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step214PaperFeedbackIntegrationReportResult) -> str:
    lines = [
        "# Step214 v5 Paper Feedback Integration Report",
        "",
        "Step214 converts Step213 outcome aggregates into candidate feedback reviews.",
        "This report is review-only and does not promote strategies, write strategy registry state, execute orders, call adapters, send Telegram messages, or enable live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_candidate_aggregate_count: {result.source_candidate_aggregate_count}",
        f"- feedback_review_count: {result.feedback_review_count}",
        f"- review_only_candidate_count: {result.review_only_candidate_count}",
        f"- watchlist_candidate_count: {result.watchlist_candidate_count}",
        f"- blocked_candidate_count: {result.blocked_candidate_count}",
        f"- average_feedback_score: {result.average_feedback_score:.4f}",
        f"- max_feedback_score: {result.max_feedback_score:.4f}",
        f"- min_feedback_score: {result.min_feedback_score:.4f}",
        f"- feedback_engine_input_ready: {result.feedback_engine_input_ready}",
        f"- promotion_gate_input_ready: {result.promotion_gate_input_ready}",
        f"- promotion_allowed: {result.promotion_allowed}",
        f"- strategy_registry_write_allowed: {result.strategy_registry_write_allowed}",
        f"- live_order_executed: {result.live_order_executed}",
        "",
        "## Candidate feedback reviews",
    ]
    for review in result.reviews:
        blockers = ", ".join(review.get("blockers", [])) if review.get("blockers") else "NO_BLOCKER"
        warnings = ", ".join(review.get("warnings", [])) if review.get("warnings") else "NO_WARNING"
        lines.append(
            "- `{group}` {side}: status={status}, grade={grade}, score={score:.2f}, "
            "outcomes={outcomes}, expectancy={expectancy:.4f}, pf={pf:.2f}, blockers={blockers}, warnings={warnings}".format(
                group=review.get("comparison_group", ""),
                side=review.get("side", ""),
                status=review.get("feedback_status", ""),
                grade=review.get("feedback_grade", ""),
                score=float(review.get("feedback_score", 0.0)),
                outcomes=review.get("outcome_count", 0),
                expectancy=float(review.get("expectancy_r", 0.0)),
                pf=float(review.get("profit_factor", 0.0)),
                blockers=blockers,
                warnings=warnings,
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step214 is feedback-report integration only.",
            "- Feedback input readiness is not live trading approval.",
            "- Promotion remains disabled.",
            "- Strategy registry writes remain disabled.",
            "- No paper order, adapter, live exchange, Telegram, or external API side effect is performed.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_paper_feedback_integration_report(
    root: str | Path, *, write_output: bool = True, allow_source_regeneration: bool = False
) -> Step214PaperFeedbackIntegrationReportResult:
    root_path = Path(root).resolve()
    step213_path = root_path / "storage/latest/step213_paper_lifecycle_outcome_store_latest.json"
    step213 = _ensure_step213(root_path, allow_source_regeneration=allow_source_regeneration)
    aggregates = _load_step213_aggregates(step213)
    reviews = [_build_review(aggregate) for aggregate in aggregates]
    review_dicts = [review.to_dict() for review in reviews]
    scores = [review.feedback_score for review in reviews]

    feedback_reviews_json_path = root_path / "data/reports/step214_paper_feedback_integration_reviews.json"
    feedback_reviews_jsonl_path = root_path / "data/stores/step214_paper_feedback_candidate_reviews.jsonl"
    feedback_reviews_csv_path = root_path / "data/reports/step214_paper_feedback_integration_reviews.csv"
    markdown_report_path = root_path / "data/reports/step214_paper_feedback_integration_report.md"
    latest_result_path = root_path / "storage/latest/step214_paper_feedback_integration_report_latest.json"

    result = Step214PaperFeedbackIntegrationReportResult(
        status=STEP214_STATUS_OK,
        root=str(root_path),
        source_step213_result_path=str(step213_path),
        feedback_reviews_json_path=str(feedback_reviews_json_path),
        feedback_reviews_jsonl_path=str(feedback_reviews_jsonl_path),
        feedback_reviews_csv_path=str(feedback_reviews_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        source_candidate_aggregate_count=len(aggregates),
        feedback_review_count=len(reviews),
        review_only_candidate_count=sum(1 for review in reviews if review.feedback_status == "PAPER_FEEDBACK_REVIEW_ONLY"),
        watchlist_candidate_count=sum(1 for review in reviews if review.feedback_status == "PAPER_FEEDBACK_WATCHLIST"),
        blocked_candidate_count=sum(1 for review in reviews if review.feedback_status == "PAPER_FEEDBACK_BLOCKED"),
        average_feedback_score=(sum(scores) / len(scores)) if scores else 0.0,
        max_feedback_score=max(scores) if scores else 0.0,
        min_feedback_score=min(scores) if scores else 0.0,
        feedback_integration_report_created=True,
        feedback_engine_input_ready=bool(reviews),
        promotion_gate_input_ready=bool(reviews),
        promotion_allowed=False,
        strategy_registry_write_allowed=False,
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        adapter_routing_enabled=False,
        shadow_execution_enabled=False,
        auto_strategy_promotion=False,
        external_api_call_performed=False,
        live_order_executed=False,
        real_adapter_call_performed=False,
        telegram_real_send=False,
        production_cutover_executable=False,
        live_mode_enable_allowed=False,
        reviews=review_dicts,
        blocker_summary=_blocker_summary(reviews),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(feedback_reviews_json_path, {"reviews": review_dicts})
        _write_jsonl(feedback_reviews_jsonl_path, review_dicts)
        _write_csv(feedback_reviews_csv_path, review_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def validate_paper_feedback_integration_report(root: str | Path) -> Step214ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step214_paper_feedback_integration_report_latest.json"
    if not result_path.exists():
        raise FileNotFoundError(
            f"Missing required Step214 result artifact: {result_path}. Step269 validation fails closed; "
            "run the explicit Step214 report command before validation."
        )

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    reviews = list(payload.get("reviews", []) or [])

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step213_present": Path(payload.get("source_step213_result_path", "")).exists(),
        "feedback_reviews_json_exists": Path(payload.get("feedback_reviews_json_path", "")).exists(),
        "feedback_reviews_jsonl_exists": Path(payload.get("feedback_reviews_jsonl_path", "")).exists(),
        "feedback_reviews_csv_exists": Path(payload.get("feedback_reviews_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_candidate_aggregates_present": int(payload.get("source_candidate_aggregate_count", 0)) > 0,
        "feedback_reviews_present": int(payload.get("feedback_review_count", 0)) > 0 and bool(reviews),
        "feedback_report_created": payload.get("feedback_integration_report_created") is True,
        "feedback_engine_input_ready": payload.get("feedback_engine_input_ready") is True,
        "promotion_gate_input_ready": payload.get("promotion_gate_input_ready") is True,
        "no_promotion": payload.get("promotion_allowed") is False
        and payload.get("auto_strategy_promotion") is False
        and all(review.get("promotion_allowed") is False for review in reviews),
        "no_strategy_registry_write": payload.get("strategy_registry_write_allowed") is False
        and all(review.get("strategy_registry_write_allowed") is False for review in reviews),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False
        and all(review.get("paper_order_execution_enabled") is False for review in reviews),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False,
        "no_shadow_execution": payload.get("shadow_execution_enabled") is False,
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False
        and payload.get("real_adapter_call_performed") is False
        and payload.get("telegram_real_send") is False
        and all(review.get("live_trading_allowed") is False for review in reviews),
        "no_production_cutover": payload.get("production_cutover_executable") is False
        and payload.get("live_mode_enable_allowed") is False,
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step214ValidationResult(
        status=STEP214_VALIDATION_OK if not failures else "STEP214_V5_PAPER_FEEDBACK_INTEGRATION_REPORT_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
