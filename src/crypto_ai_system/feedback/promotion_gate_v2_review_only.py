from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.feedback.paper_feedback_integration_report import (
    execute_paper_feedback_integration_report,
)

STEP215_STATUS_OK = "STEP215_V5_PROMOTION_GATE_V2_REVIEW_ONLY_OK"
STEP215_VALIDATION_OK = "STEP215_V5_PROMOTION_GATE_V2_REVIEW_ONLY_VALIDATION_OK"

MIN_PROMOTION_READY_SCORE = 65.0
MIN_PROMOTION_WATCHLIST_SCORE = 45.0
MIN_PROMOTION_OUTCOMES = 3
MIN_PROMOTION_EXPECTANCY_R = 0.0
MIN_PROMOTION_PROFIT_FACTOR = 1.0
MIN_PROMOTION_QUALITY = 0.95


@dataclass
class PromotionGateDecision:
    promotion_decision_id: str
    feedback_review_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    side: str
    source_feedback_status: str
    feedback_score: float
    feedback_grade: str
    outcome_count: int
    expectancy_r: float
    profit_factor: float
    lifecycle_quality_score: float
    promotion_gate_status: str
    promotion_readiness_score: float
    promotion_blockers: List[str]
    promotion_warnings: List[str]
    next_required_step: str
    operator_review_required: bool
    promotion_gate_applied: bool
    promotion_allowed: bool
    auto_strategy_promotion: bool
    strategy_registry_write_allowed: bool
    strategy_status_write_value: str
    paper_execution_upgrade_allowed: bool
    limited_live_review_allowed: bool
    live_trading_allowed: bool
    paper_order_execution_enabled: bool
    live_order_executed: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step215PromotionGateV2ReviewOnlyResult:
    status: str
    root: str
    source_step214_result_path: str
    promotion_decisions_json_path: str
    promotion_decisions_jsonl_path: str
    promotion_decisions_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_feedback_review_count: int
    promotion_decision_count: int
    promotion_review_ready_count: int
    promotion_watchlist_count: int
    promotion_blocked_count: int
    average_promotion_readiness_score: float
    max_promotion_readiness_score: float
    min_promotion_readiness_score: float
    promotion_gate_v2_review_only_created: bool
    promotion_gate_applied: bool
    promotion_gate_input_ready: bool
    operator_review_required: bool
    promotion_allowed: bool
    auto_strategy_promotion: bool
    strategy_registry_write_allowed: bool
    paper_execution_upgrade_allowed: bool
    limited_live_review_allowed: bool
    live_trading_allowed: bool
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    adapter_routing_enabled: bool
    shadow_execution_enabled: bool
    external_api_call_performed: bool
    live_order_executed: bool
    real_adapter_call_performed: bool
    telegram_real_send: bool
    production_cutover_executable: bool
    live_mode_enable_allowed: bool
    decisions: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: _utc_now())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step215ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step214_present: bool
    promotion_decisions_json_exists: bool
    promotion_decisions_jsonl_exists: bool
    promotion_decisions_csv_exists: bool
    markdown_report_exists: bool
    source_feedback_reviews_present: bool
    promotion_decisions_present: bool
    promotion_gate_created: bool
    promotion_gate_applied: bool
    promotion_gate_input_ready: bool
    operator_review_required: bool
    no_promotion_allowed: bool
    no_auto_strategy_promotion: bool
    no_strategy_registry_write: bool
    no_paper_execution_upgrade: bool
    no_limited_live_review: bool
    no_live_trading: bool
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


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    fieldnames = list(rows[0].keys()) if rows else ["promotion_decision_id", "promotion_gate_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["promotion_blockers"] = "|".join(out.get("promotion_blockers", []))
            out["promotion_warnings"] = "|".join(out.get("promotion_warnings", []))
            writer.writerow(out)


def _ensure_step214(root: Path, *, allow_source_regeneration: bool = False) -> Dict[str, Any]:
    path = root / "storage/latest/step214_paper_feedback_integration_report_latest.json"
    if not path.exists():
        if allow_source_regeneration:
            execute_paper_feedback_integration_report(root, write_output=True, allow_source_regeneration=True)
        else:
            raise FileNotFoundError(
                f"Missing required Step214 source artifact: {path}. Step269 promotion gate fails closed; "
                "run explicit upstream report generation before promotion-gate review."
            )
    return _load_json(path)


def _load_step214_reviews(step214: Dict[str, Any]) -> List[Dict[str, Any]]:
    reviews_path = Path(step214.get("feedback_reviews_json_path", ""))
    if reviews_path.exists():
        return list(_load_json(reviews_path).get("reviews", []) or [])
    return list(step214.get("reviews", []) or [])


def _decision_id(review: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            "step215_promotion_gate_v2_review_only",
            str(review.get("feedback_review_id", "")),
            str(review.get("observation_id", "")),
            str(review.get("feedback_score", "")),
        ]
    )
    return "pgd_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _promotion_readiness_score(review: Dict[str, Any]) -> float:
    feedback_score = float(review.get("feedback_score", 0.0))
    outcome_count = int(review.get("outcome_count", 0))
    expectancy_r = float(review.get("expectancy_r", 0.0))
    profit_factor = float(review.get("profit_factor", 0.0))
    quality = float(review.get("average_lifecycle_quality_score", 0.0))
    sample_bonus = min(10.0, max(0.0, (outcome_count - MIN_PROMOTION_OUTCOMES) * 2.0))
    expectancy_bonus = max(-10.0, min(10.0, expectancy_r * 20.0))
    pf_bonus = max(-10.0, min(10.0, (profit_factor - 1.0) * 10.0))
    quality_bonus = max(-10.0, min(10.0, (quality - MIN_PROMOTION_QUALITY) * 100.0))
    score = feedback_score * 0.7 + sample_bonus + expectancy_bonus + pf_bonus + quality_bonus
    return round(max(0.0, min(100.0, score)), 6)


def _promotion_blockers(review: Dict[str, Any], readiness_score: float) -> List[str]:
    blockers = list(review.get("blockers", []) or [])
    source_status = str(review.get("feedback_status", ""))
    outcome_count = int(review.get("outcome_count", 0))
    expectancy_r = float(review.get("expectancy_r", 0.0))
    profit_factor = float(review.get("profit_factor", 0.0))
    quality = float(review.get("average_lifecycle_quality_score", 0.0))
    min_quality = float(review.get("min_lifecycle_quality_score", 0.0))
    rejected_count = int(review.get("rejected_count", 0))

    if source_status == "PAPER_FEEDBACK_BLOCKED":
        blockers.append("SOURCE_FEEDBACK_BLOCKED")
    if source_status not in {"PAPER_FEEDBACK_REVIEW_ONLY", "PAPER_FEEDBACK_WATCHLIST"}:
        blockers.append("SOURCE_FEEDBACK_STATUS_NOT_ELIGIBLE")
    if outcome_count < MIN_PROMOTION_OUTCOMES:
        blockers.append("PROMOTION_SAMPLE_TOO_LOW")
    if expectancy_r < MIN_PROMOTION_EXPECTANCY_R:
        blockers.append("PROMOTION_EXPECTANCY_BELOW_ZERO")
    if profit_factor < MIN_PROMOTION_PROFIT_FACTOR:
        blockers.append("PROMOTION_PROFIT_FACTOR_BELOW_ONE")
    if quality < MIN_PROMOTION_QUALITY or min_quality < MIN_PROMOTION_QUALITY:
        blockers.append("PROMOTION_LIFECYCLE_QUALITY_BELOW_THRESHOLD")
    if rejected_count > 0:
        blockers.append("PROMOTION_REJECTED_OUTCOMES_PRESENT")
    if readiness_score < MIN_PROMOTION_WATCHLIST_SCORE:
        blockers.append("PROMOTION_READINESS_SCORE_TOO_LOW")
    return sorted(set(str(b) for b in blockers if str(b)))


def _promotion_warnings(review: Dict[str, Any], readiness_score: float) -> List[str]:
    warnings = list(review.get("warnings", []) or [])
    if str(review.get("feedback_status", "")) == "PAPER_FEEDBACK_WATCHLIST":
        warnings.append("SOURCE_FEEDBACK_WATCHLIST")
    if readiness_score < MIN_PROMOTION_READY_SCORE:
        warnings.append("PROMOTION_READY_SCORE_NOT_REACHED")
    if int(review.get("outcome_count", 0)) < MIN_PROMOTION_OUTCOMES * 2:
        warnings.append("MORE_PROMOTION_EVIDENCE_RECOMMENDED")
    warnings.append("REVIEW_ONLY_NO_REGISTRY_WRITE")
    warnings.append("OPERATOR_REVIEW_REQUIRED_BEFORE_ANY_FUTURE_PROMOTION")
    return sorted(set(str(w) for w in warnings if str(w)))


def _promotion_status(review: Dict[str, Any], blockers: List[str], readiness_score: float) -> str:
    source_status = str(review.get("feedback_status", ""))
    hard = {
        "SOURCE_FEEDBACK_BLOCKED",
        "SOURCE_FEEDBACK_STATUS_NOT_ELIGIBLE",
        "PROMOTION_EXPECTANCY_BELOW_ZERO",
        "PROMOTION_PROFIT_FACTOR_BELOW_ONE",
        "PROMOTION_LIFECYCLE_QUALITY_BELOW_THRESHOLD",
        "PROMOTION_REJECTED_OUTCOMES_PRESENT",
        "PROMOTION_READINESS_SCORE_TOO_LOW",
        "FEEDBACK_SCORE_TOO_LOW",
    }
    if any(b in hard for b in blockers):
        return "PROMOTION_BLOCKED"
    if source_status == "PAPER_FEEDBACK_REVIEW_ONLY" and readiness_score >= MIN_PROMOTION_READY_SCORE and not blockers:
        return "PROMOTION_REVIEW_READY"
    return "PROMOTION_WATCHLIST"


def _next_required_step(status: str) -> str:
    if status == "PROMOTION_REVIEW_READY":
        return "STEP216_PAPER_EXECUTION_UPGRADE_READINESS_REVIEW_ONLY"
    if status == "PROMOTION_WATCHLIST":
        return "CONTINUE_PAPER_OBSERVATION_AND_COLLECT_MORE_OUTCOMES"
    return "DO_NOT_PROMOTE_REVIEW_BLOCKERS"


def _build_decision(review: Dict[str, Any]) -> PromotionGateDecision:
    readiness_score = _promotion_readiness_score(review)
    blockers = _promotion_blockers(review, readiness_score)
    warnings = _promotion_warnings(review, readiness_score)
    status = _promotion_status(review, blockers, readiness_score)
    return PromotionGateDecision(
        promotion_decision_id=_decision_id(review),
        feedback_review_id=str(review.get("feedback_review_id", "")),
        observation_id=str(review.get("observation_id", "")),
        registry_id=str(review.get("registry_id", "")),
        comparison_group=str(review.get("comparison_group", "")),
        side=str(review.get("side", "")),
        source_feedback_status=str(review.get("feedback_status", "")),
        feedback_score=float(review.get("feedback_score", 0.0)),
        feedback_grade=str(review.get("feedback_grade", "")),
        outcome_count=int(review.get("outcome_count", 0)),
        expectancy_r=float(review.get("expectancy_r", 0.0)),
        profit_factor=float(review.get("profit_factor", 0.0)),
        lifecycle_quality_score=float(review.get("average_lifecycle_quality_score", 0.0)),
        promotion_gate_status=status,
        promotion_readiness_score=readiness_score,
        promotion_blockers=blockers,
        promotion_warnings=warnings,
        next_required_step=_next_required_step(status),
        operator_review_required=True,
        promotion_gate_applied=True,
        promotion_allowed=False,
        auto_strategy_promotion=False,
        strategy_registry_write_allowed=False,
        strategy_status_write_value="NO_WRITE_REVIEW_ONLY",
        paper_execution_upgrade_allowed=False,
        limited_live_review_allowed=False,
        live_trading_allowed=False,
        paper_order_execution_enabled=False,
        live_order_executed=False,
    )


def _blocker_summary(decisions: List[PromotionGateDecision]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for decision in decisions:
        if not decision.promotion_blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in decision.promotion_blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step215PromotionGateV2ReviewOnlyResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step215PromotionGateV2ReviewOnlyResult) -> str:
    lines = [
        "# Step215 v5 Promotion Gate v2 Review-Only",
        "",
        "Step215 converts Step214 feedback reviews into promotion-gate decision objects.",
        "This step is review-only. It does not promote strategies, write strategy registry state, enable paper execution upgrades, allow limited-live review, execute orders, call adapters, send Telegram messages, or enable live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_feedback_review_count: {result.source_feedback_review_count}",
        f"- promotion_decision_count: {result.promotion_decision_count}",
        f"- promotion_review_ready_count: {result.promotion_review_ready_count}",
        f"- promotion_watchlist_count: {result.promotion_watchlist_count}",
        f"- promotion_blocked_count: {result.promotion_blocked_count}",
        f"- average_promotion_readiness_score: {result.average_promotion_readiness_score:.4f}",
        f"- max_promotion_readiness_score: {result.max_promotion_readiness_score:.4f}",
        f"- min_promotion_readiness_score: {result.min_promotion_readiness_score:.4f}",
        f"- promotion_allowed: {result.promotion_allowed}",
        f"- strategy_registry_write_allowed: {result.strategy_registry_write_allowed}",
        f"- paper_execution_upgrade_allowed: {result.paper_execution_upgrade_allowed}",
        f"- limited_live_review_allowed: {result.limited_live_review_allowed}",
        f"- live_trading_allowed: {result.live_trading_allowed}",
        "",
        "## Promotion decisions",
    ]
    for decision in result.decisions:
        blockers = ", ".join(decision.get("promotion_blockers", [])) if decision.get("promotion_blockers") else "NO_BLOCKER"
        warnings = ", ".join(decision.get("promotion_warnings", [])) if decision.get("promotion_warnings") else "NO_WARNING"
        lines.append(
            "- `{group}` {side}: status={status}, readiness={score:.2f}, feedback={feedback:.2f}, "
            "outcomes={outcomes}, blockers={blockers}, warnings={warnings}, next={next_step}".format(
                group=decision.get("comparison_group", ""),
                side=decision.get("side", ""),
                status=decision.get("promotion_gate_status", ""),
                score=float(decision.get("promotion_readiness_score", 0.0)),
                feedback=float(decision.get("feedback_score", 0.0)),
                outcomes=decision.get("outcome_count", 0),
                blockers=blockers,
                warnings=warnings,
                next_step=decision.get("next_required_step", ""),
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step215 is promotion-gate review only.",
            "- `promotion_allowed` remains false for every decision.",
            "- Strategy registry writes remain disabled.",
            "- Paper execution upgrade remains disabled.",
            "- Limited-live review remains disabled.",
            "- No paper order, adapter, live exchange, Telegram, or external API side effect is performed.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_promotion_gate_v2_review_only(
    root: str | Path, *, write_output: bool = True, allow_source_regeneration: bool = False
) -> Step215PromotionGateV2ReviewOnlyResult:
    root_path = Path(root).resolve()
    step214_path = root_path / "storage/latest/step214_paper_feedback_integration_report_latest.json"
    step214 = _ensure_step214(root_path, allow_source_regeneration=allow_source_regeneration)
    reviews = _load_step214_reviews(step214)
    decisions = [_build_decision(review) for review in reviews]
    decision_dicts = [decision.to_dict() for decision in decisions]
    scores = [decision.promotion_readiness_score for decision in decisions]

    promotion_decisions_json_path = root_path / "data/reports/step215_promotion_gate_v2_review_only_decisions.json"
    promotion_decisions_jsonl_path = root_path / "data/stores/step215_promotion_gate_v2_review_only_decisions.jsonl"
    promotion_decisions_csv_path = root_path / "data/reports/step215_promotion_gate_v2_review_only_decisions.csv"
    markdown_report_path = root_path / "data/reports/step215_promotion_gate_v2_review_only_report.md"
    latest_result_path = root_path / "storage/latest/step215_promotion_gate_v2_review_only_latest.json"

    result = Step215PromotionGateV2ReviewOnlyResult(
        status=STEP215_STATUS_OK,
        root=str(root_path),
        source_step214_result_path=str(step214_path),
        promotion_decisions_json_path=str(promotion_decisions_json_path),
        promotion_decisions_jsonl_path=str(promotion_decisions_jsonl_path),
        promotion_decisions_csv_path=str(promotion_decisions_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        source_feedback_review_count=len(reviews),
        promotion_decision_count=len(decisions),
        promotion_review_ready_count=sum(1 for d in decisions if d.promotion_gate_status == "PROMOTION_REVIEW_READY"),
        promotion_watchlist_count=sum(1 for d in decisions if d.promotion_gate_status == "PROMOTION_WATCHLIST"),
        promotion_blocked_count=sum(1 for d in decisions if d.promotion_gate_status == "PROMOTION_BLOCKED"),
        average_promotion_readiness_score=(sum(scores) / len(scores)) if scores else 0.0,
        max_promotion_readiness_score=max(scores) if scores else 0.0,
        min_promotion_readiness_score=min(scores) if scores else 0.0,
        promotion_gate_v2_review_only_created=True,
        promotion_gate_applied=True,
        promotion_gate_input_ready=bool(decisions),
        operator_review_required=True,
        promotion_allowed=False,
        auto_strategy_promotion=False,
        strategy_registry_write_allowed=False,
        paper_execution_upgrade_allowed=False,
        limited_live_review_allowed=False,
        live_trading_allowed=False,
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        adapter_routing_enabled=False,
        shadow_execution_enabled=False,
        external_api_call_performed=False,
        live_order_executed=False,
        real_adapter_call_performed=False,
        telegram_real_send=False,
        production_cutover_executable=False,
        live_mode_enable_allowed=False,
        decisions=decision_dicts,
        blocker_summary=_blocker_summary(decisions),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(promotion_decisions_json_path, {"decisions": decision_dicts})
        _write_jsonl(promotion_decisions_jsonl_path, decision_dicts)
        _write_csv(promotion_decisions_csv_path, decision_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def validate_promotion_gate_v2_review_only(root: str | Path) -> Step215ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step215_promotion_gate_v2_review_only_latest.json"
    if not result_path.exists():
        raise FileNotFoundError(
            f"Missing required Step215 result artifact: {result_path}. Step269 validation fails closed; "
            "run the explicit Step215 report command before validation."
        )

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    decisions = list(payload.get("decisions", []) or [])

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step214_present": Path(payload.get("source_step214_result_path", "")).exists(),
        "promotion_decisions_json_exists": Path(payload.get("promotion_decisions_json_path", "")).exists(),
        "promotion_decisions_jsonl_exists": Path(payload.get("promotion_decisions_jsonl_path", "")).exists(),
        "promotion_decisions_csv_exists": Path(payload.get("promotion_decisions_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_feedback_reviews_present": int(payload.get("source_feedback_review_count", 0)) > 0,
        "promotion_decisions_present": int(payload.get("promotion_decision_count", 0)) > 0 and bool(decisions),
        "promotion_gate_created": payload.get("promotion_gate_v2_review_only_created") is True,
        "promotion_gate_applied": payload.get("promotion_gate_applied") is True and all(d.get("promotion_gate_applied") is True for d in decisions),
        "promotion_gate_input_ready": payload.get("promotion_gate_input_ready") is True,
        "operator_review_required": payload.get("operator_review_required") is True and all(d.get("operator_review_required") is True for d in decisions),
        "no_promotion_allowed": payload.get("promotion_allowed") is False and all(d.get("promotion_allowed") is False for d in decisions),
        "no_auto_strategy_promotion": payload.get("auto_strategy_promotion") is False and all(d.get("auto_strategy_promotion") is False for d in decisions),
        "no_strategy_registry_write": payload.get("strategy_registry_write_allowed") is False and all(d.get("strategy_registry_write_allowed") is False for d in decisions),
        "no_paper_execution_upgrade": payload.get("paper_execution_upgrade_allowed") is False and all(d.get("paper_execution_upgrade_allowed") is False for d in decisions),
        "no_limited_live_review": payload.get("limited_live_review_allowed") is False and all(d.get("limited_live_review_allowed") is False for d in decisions),
        "no_live_trading": payload.get("live_trading_allowed") is False and all(d.get("live_trading_allowed") is False for d in decisions),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False and all(d.get("paper_order_execution_enabled") is False for d in decisions),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False,
        "no_shadow_execution": payload.get("shadow_execution_enabled") is False,
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False
        and payload.get("real_adapter_call_performed") is False
        and payload.get("telegram_real_send") is False
        and all(d.get("live_order_executed") is False for d in decisions),
        "no_production_cutover": payload.get("production_cutover_executable") is False
        and payload.get("live_mode_enable_allowed") is False,
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step215ValidationResult(
        status=STEP215_VALIDATION_OK if not failures else "STEP215_V5_PROMOTION_GATE_V2_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
