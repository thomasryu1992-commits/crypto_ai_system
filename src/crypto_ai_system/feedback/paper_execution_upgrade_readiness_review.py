from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.feedback.promotion_gate_v2_review_only import (
    execute_promotion_gate_v2_review_only,
)

STEP216_STATUS_OK = "STEP216_V5_PAPER_EXECUTION_UPGRADE_READINESS_REVIEW_ONLY_OK"
STEP216_VALIDATION_OK = "STEP216_V5_PAPER_EXECUTION_UPGRADE_READINESS_REVIEW_ONLY_VALIDATION_OK"

MIN_UPGRADE_READINESS_SCORE = 70.0
MIN_WATCHLIST_READINESS_SCORE = 45.0


@dataclass
class PaperExecutionUpgradeReadinessReview:
    upgrade_review_id: str
    promotion_decision_id: str
    feedback_review_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    side: str
    source_promotion_gate_status: str
    promotion_readiness_score: float
    upgrade_readiness_score: float
    upgrade_readiness_status: str
    has_promotion_review_ready: bool
    has_no_promotion_blockers: bool
    has_operator_review_required: bool
    has_replay_evidence: bool
    has_dry_run_intent_evidence: bool
    has_lifecycle_evidence: bool
    has_outcome_evidence: bool
    has_feedback_evidence: bool
    has_promotion_decision_evidence: bool
    evidence_completeness_score: float
    readiness_blockers: List[str]
    readiness_warnings: List[str]
    next_required_step: str
    operator_review_required: bool
    manual_approval_required: bool
    paper_execution_upgrade_allowed: bool
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    adapter_routing_enabled: bool
    shadow_execution_enabled: bool
    limited_live_review_allowed: bool
    live_trading_allowed: bool
    strategy_registry_write_allowed: bool
    promotion_allowed: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step216PaperExecutionUpgradeReadinessResult:
    status: str
    root: str
    source_step215_result_path: str
    upgrade_reviews_json_path: str
    upgrade_reviews_jsonl_path: str
    upgrade_reviews_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_promotion_decision_count: int
    upgrade_review_count: int
    upgrade_review_ready_count: int
    upgrade_watchlist_count: int
    upgrade_blocked_count: int
    average_upgrade_readiness_score: float
    max_upgrade_readiness_score: float
    min_upgrade_readiness_score: float
    evidence_files_present_count: int
    evidence_files_required_count: int
    paper_execution_upgrade_readiness_review_created: bool
    readiness_checklist_applied: bool
    operator_review_required: bool
    manual_approval_required: bool
    paper_execution_upgrade_allowed: bool
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    adapter_routing_enabled: bool
    shadow_execution_enabled: bool
    limited_live_review_allowed: bool
    live_trading_allowed: bool
    strategy_registry_write_allowed: bool
    promotion_allowed: bool
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
class Step216ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step215_present: bool
    upgrade_reviews_json_exists: bool
    upgrade_reviews_jsonl_exists: bool
    upgrade_reviews_csv_exists: bool
    markdown_report_exists: bool
    source_promotion_decisions_present: bool
    upgrade_reviews_present: bool
    readiness_review_created: bool
    readiness_checklist_applied: bool
    operator_review_required: bool
    manual_approval_required: bool
    no_paper_execution_upgrade: bool
    no_paper_order_execution: bool
    no_adapter_routing: bool
    no_shadow_execution: bool
    no_limited_live_review: bool
    no_live_trading: bool
    no_strategy_registry_write: bool
    no_promotion_allowed: bool
    no_auto_strategy_promotion: bool
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
    fieldnames = list(rows[0].keys()) if rows else ["upgrade_review_id", "upgrade_readiness_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["readiness_blockers"] = "|".join(out.get("readiness_blockers", []))
            out["readiness_warnings"] = "|".join(out.get("readiness_warnings", []))
            writer.writerow(out)


def _ensure_step215(root: Path, *, allow_source_regeneration: bool = False) -> Dict[str, Any]:
    path = root / "storage/latest/step215_promotion_gate_v2_review_only_latest.json"
    if not path.exists():
        if allow_source_regeneration:
            execute_promotion_gate_v2_review_only(root, write_output=True, allow_source_regeneration=True)
        else:
            raise FileNotFoundError(
                f"Missing required Step215 source artifact: {path}. Step269 upgrade readiness fails closed; "
                "run explicit upstream report generation before upgrade-readiness review."
            )
    return _load_json(path)


def _load_step215_decisions(step215: Dict[str, Any]) -> List[Dict[str, Any]]:
    decisions_path = Path(step215.get("promotion_decisions_json_path", ""))
    if decisions_path.exists():
        return list(_load_json(decisions_path).get("decisions", []) or [])
    return list(step215.get("decisions", []) or [])


def _evidence_paths(root: Path) -> Dict[str, Path]:
    return {
        "replay": root / "storage/latest/step210_paper_signal_replay_latest.json",
        "dry_run_intent": root / "storage/latest/step211_paper_execution_dry_run_bridge_latest.json",
        "lifecycle": root / "storage/latest/step212_simulated_paper_order_lifecycle_latest.json",
        "outcome": root / "storage/latest/step213_paper_lifecycle_outcome_store_latest.json",
        "feedback": root / "storage/latest/step214_paper_feedback_integration_report_latest.json",
        "promotion": root / "storage/latest/step215_promotion_gate_v2_review_only_latest.json",
    }


def _evidence_flags(root: Path) -> Dict[str, bool]:
    return {name: path.exists() for name, path in _evidence_paths(root).items()}


def _evidence_completeness_score(flags: Dict[str, bool]) -> float:
    if not flags:
        return 0.0
    return round(sum(1 for value in flags.values() if value) / len(flags) * 100.0, 6)


def _review_id(decision: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            "step216_paper_execution_upgrade_readiness",
            str(decision.get("promotion_decision_id", "")),
            str(decision.get("observation_id", "")),
            str(decision.get("promotion_readiness_score", "")),
        ]
    )
    return "peur_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _readiness_score(decision: Dict[str, Any], evidence_score: float) -> float:
    promotion_score = float(decision.get("promotion_readiness_score", 0.0))
    source_status = str(decision.get("promotion_gate_status", ""))
    status_bonus = 10.0 if source_status == "PROMOTION_REVIEW_READY" else (0.0 if source_status == "PROMOTION_WATCHLIST" else -20.0)
    blocker_penalty = min(30.0, len(decision.get("promotion_blockers", []) or []) * 7.5)
    warning_penalty = min(10.0, len(decision.get("promotion_warnings", []) or []) * 1.5)
    score = promotion_score * 0.55 + evidence_score * 0.35 + status_bonus - blocker_penalty - warning_penalty
    return round(max(0.0, min(100.0, score)), 6)


def _readiness_blockers(decision: Dict[str, Any], flags: Dict[str, bool], readiness_score: float) -> List[str]:
    blockers: List[str] = []
    source_status = str(decision.get("promotion_gate_status", ""))
    promotion_blockers = list(decision.get("promotion_blockers", []) or [])

    if source_status != "PROMOTION_REVIEW_READY":
        blockers.append("SOURCE_PROMOTION_NOT_REVIEW_READY")
    if promotion_blockers:
        blockers.append("SOURCE_PROMOTION_BLOCKERS_PRESENT")
    if not bool(decision.get("operator_review_required", False)):
        blockers.append("OPERATOR_REVIEW_NOT_REQUIRED_BY_SOURCE")
    if not flags.get("replay", False):
        blockers.append("REPLAY_EVIDENCE_MISSING")
    if not flags.get("dry_run_intent", False):
        blockers.append("DRY_RUN_INTENT_EVIDENCE_MISSING")
    if not flags.get("lifecycle", False):
        blockers.append("LIFECYCLE_EVIDENCE_MISSING")
    if not flags.get("outcome", False):
        blockers.append("OUTCOME_EVIDENCE_MISSING")
    if not flags.get("feedback", False):
        blockers.append("FEEDBACK_EVIDENCE_MISSING")
    if not flags.get("promotion", False):
        blockers.append("PROMOTION_DECISION_EVIDENCE_MISSING")
    if readiness_score < MIN_WATCHLIST_READINESS_SCORE:
        blockers.append("UPGRADE_READINESS_SCORE_TOO_LOW")
    return sorted(set(blockers))


def _readiness_warnings(decision: Dict[str, Any], readiness_score: float) -> List[str]:
    warnings = list(decision.get("promotion_warnings", []) or [])
    if readiness_score < MIN_UPGRADE_READINESS_SCORE:
        warnings.append("UPGRADE_REVIEW_READY_SCORE_NOT_REACHED")
    warnings.append("REVIEW_ONLY_NO_PAPER_EXECUTION_UPGRADE")
    warnings.append("MANUAL_APPROVAL_REQUIRED_BEFORE_ANY_FUTURE_UPGRADE")
    warnings.append("NO_ADAPTER_ROUTING_IN_STEP216")
    return sorted(set(str(w) for w in warnings if str(w)))


def _readiness_status(decision: Dict[str, Any], blockers: List[str], readiness_score: float) -> str:
    hard = {
        "SOURCE_PROMOTION_NOT_REVIEW_READY",
        "SOURCE_PROMOTION_BLOCKERS_PRESENT",
        "REPLAY_EVIDENCE_MISSING",
        "DRY_RUN_INTENT_EVIDENCE_MISSING",
        "LIFECYCLE_EVIDENCE_MISSING",
        "OUTCOME_EVIDENCE_MISSING",
        "FEEDBACK_EVIDENCE_MISSING",
        "PROMOTION_DECISION_EVIDENCE_MISSING",
        "UPGRADE_READINESS_SCORE_TOO_LOW",
    }
    if any(blocker in hard for blocker in blockers):
        return "PAPER_EXECUTION_UPGRADE_BLOCKED"
    if readiness_score >= MIN_UPGRADE_READINESS_SCORE and str(decision.get("promotion_gate_status", "")) == "PROMOTION_REVIEW_READY":
        return "PAPER_EXECUTION_UPGRADE_REVIEW_READY"
    return "PAPER_EXECUTION_UPGRADE_WATCHLIST"


def _next_required_step(status: str) -> str:
    if status == "PAPER_EXECUTION_UPGRADE_REVIEW_READY":
        return "STEP217_OPERATOR_APPROVAL_PACKET_REVIEW_ONLY"
    if status == "PAPER_EXECUTION_UPGRADE_WATCHLIST":
        return "CONTINUE_PAPER_OBSERVATION_BEFORE_UPGRADE_REVIEW"
    return "DO_NOT_UPGRADE_REVIEW_BLOCKERS"


def _build_review(decision: Dict[str, Any], flags: Dict[str, bool]) -> PaperExecutionUpgradeReadinessReview:
    evidence_score = _evidence_completeness_score(flags)
    readiness_score = _readiness_score(decision, evidence_score)
    blockers = _readiness_blockers(decision, flags, readiness_score)
    warnings = _readiness_warnings(decision, readiness_score)
    status = _readiness_status(decision, blockers, readiness_score)

    return PaperExecutionUpgradeReadinessReview(
        upgrade_review_id=_review_id(decision),
        promotion_decision_id=str(decision.get("promotion_decision_id", "")),
        feedback_review_id=str(decision.get("feedback_review_id", "")),
        observation_id=str(decision.get("observation_id", "")),
        registry_id=str(decision.get("registry_id", "")),
        comparison_group=str(decision.get("comparison_group", "")),
        side=str(decision.get("side", "")),
        source_promotion_gate_status=str(decision.get("promotion_gate_status", "")),
        promotion_readiness_score=float(decision.get("promotion_readiness_score", 0.0)),
        upgrade_readiness_score=readiness_score,
        upgrade_readiness_status=status,
        has_promotion_review_ready=str(decision.get("promotion_gate_status", "")) == "PROMOTION_REVIEW_READY",
        has_no_promotion_blockers=not bool(decision.get("promotion_blockers", []) or []),
        has_operator_review_required=bool(decision.get("operator_review_required", False)),
        has_replay_evidence=bool(flags.get("replay", False)),
        has_dry_run_intent_evidence=bool(flags.get("dry_run_intent", False)),
        has_lifecycle_evidence=bool(flags.get("lifecycle", False)),
        has_outcome_evidence=bool(flags.get("outcome", False)),
        has_feedback_evidence=bool(flags.get("feedback", False)),
        has_promotion_decision_evidence=bool(flags.get("promotion", False)),
        evidence_completeness_score=evidence_score,
        readiness_blockers=blockers,
        readiness_warnings=warnings,
        next_required_step=_next_required_step(status),
        operator_review_required=True,
        manual_approval_required=True,
        paper_execution_upgrade_allowed=False,
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        adapter_routing_enabled=False,
        shadow_execution_enabled=False,
        limited_live_review_allowed=False,
        live_trading_allowed=False,
        strategy_registry_write_allowed=False,
        promotion_allowed=False,
    )


def _blocker_summary(reviews: List[PaperExecutionUpgradeReadinessReview]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for review in reviews:
        if not review.readiness_blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in review.readiness_blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step216PaperExecutionUpgradeReadinessResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step216PaperExecutionUpgradeReadinessResult) -> str:
    lines = [
        "# Step216 v5 Paper Execution Upgrade Readiness Review-Only",
        "",
        "Step216 reviews whether Step215 promotion decisions have enough evidence to be considered for a future paper execution upgrade.",
        "This step is review-only. It does not enable paper execution, route adapters, submit orders, allow limited-live review, write strategy registry state, send Telegram messages, or enable live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_promotion_decision_count: {result.source_promotion_decision_count}",
        f"- upgrade_review_count: {result.upgrade_review_count}",
        f"- upgrade_review_ready_count: {result.upgrade_review_ready_count}",
        f"- upgrade_watchlist_count: {result.upgrade_watchlist_count}",
        f"- upgrade_blocked_count: {result.upgrade_blocked_count}",
        f"- average_upgrade_readiness_score: {result.average_upgrade_readiness_score:.4f}",
        f"- evidence_files_present_count: {result.evidence_files_present_count}/{result.evidence_files_required_count}",
        f"- paper_execution_upgrade_allowed: {result.paper_execution_upgrade_allowed}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        f"- limited_live_review_allowed: {result.limited_live_review_allowed}",
        f"- live_trading_allowed: {result.live_trading_allowed}",
        "",
        "## Upgrade readiness reviews",
    ]
    for review in result.reviews:
        blockers = ", ".join(review.get("readiness_blockers", [])) if review.get("readiness_blockers") else "NO_BLOCKER"
        warnings = ", ".join(review.get("readiness_warnings", [])) if review.get("readiness_warnings") else "NO_WARNING"
        lines.append(
            "- `{group}` {side}: status={status}, upgrade_score={score:.2f}, promotion_score={p_score:.2f}, "
            "evidence={evidence:.2f}, blockers={blockers}, warnings={warnings}, next={next_step}".format(
                group=review.get("comparison_group", ""),
                side=review.get("side", ""),
                status=review.get("upgrade_readiness_status", ""),
                score=float(review.get("upgrade_readiness_score", 0.0)),
                p_score=float(review.get("promotion_readiness_score", 0.0)),
                evidence=float(review.get("evidence_completeness_score", 0.0)),
                blockers=blockers,
                warnings=warnings,
                next_step=review.get("next_required_step", ""),
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step216 is paper-execution-upgrade readiness review only.",
            "- `paper_execution_upgrade_allowed` remains false.",
            "- Paper order execution remains disabled.",
            "- Adapter routing and ShadowExecutionEngine remain disabled.",
            "- Limited-live review and live trading remain disabled.",
            "- No strategy registry write or promotion is performed.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_paper_execution_upgrade_readiness_review(
    root: str | Path, *, write_output: bool = True, allow_source_regeneration: bool = False
) -> Step216PaperExecutionUpgradeReadinessResult:
    root_path = Path(root).resolve()
    step215_path = root_path / "storage/latest/step215_promotion_gate_v2_review_only_latest.json"
    step215 = _ensure_step215(root_path, allow_source_regeneration=allow_source_regeneration)
    decisions = _load_step215_decisions(step215)
    flags = _evidence_flags(root_path)
    reviews = [_build_review(decision, flags) for decision in decisions]
    review_dicts = [review.to_dict() for review in reviews]
    scores = [review.upgrade_readiness_score for review in reviews]

    upgrade_reviews_json_path = root_path / "data/reports/step216_paper_execution_upgrade_readiness_reviews.json"
    upgrade_reviews_jsonl_path = root_path / "data/stores/step216_paper_execution_upgrade_readiness_reviews.jsonl"
    upgrade_reviews_csv_path = root_path / "data/reports/step216_paper_execution_upgrade_readiness_reviews.csv"
    markdown_report_path = root_path / "data/reports/step216_paper_execution_upgrade_readiness_review_report.md"
    latest_result_path = root_path / "storage/latest/step216_paper_execution_upgrade_readiness_review_latest.json"

    result = Step216PaperExecutionUpgradeReadinessResult(
        status=STEP216_STATUS_OK,
        root=str(root_path),
        source_step215_result_path=str(step215_path),
        upgrade_reviews_json_path=str(upgrade_reviews_json_path),
        upgrade_reviews_jsonl_path=str(upgrade_reviews_jsonl_path),
        upgrade_reviews_csv_path=str(upgrade_reviews_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        source_promotion_decision_count=len(decisions),
        upgrade_review_count=len(reviews),
        upgrade_review_ready_count=sum(1 for review in reviews if review.upgrade_readiness_status == "PAPER_EXECUTION_UPGRADE_REVIEW_READY"),
        upgrade_watchlist_count=sum(1 for review in reviews if review.upgrade_readiness_status == "PAPER_EXECUTION_UPGRADE_WATCHLIST"),
        upgrade_blocked_count=sum(1 for review in reviews if review.upgrade_readiness_status == "PAPER_EXECUTION_UPGRADE_BLOCKED"),
        average_upgrade_readiness_score=(sum(scores) / len(scores)) if scores else 0.0,
        max_upgrade_readiness_score=max(scores) if scores else 0.0,
        min_upgrade_readiness_score=min(scores) if scores else 0.0,
        evidence_files_present_count=sum(1 for value in flags.values() if value),
        evidence_files_required_count=len(flags),
        paper_execution_upgrade_readiness_review_created=True,
        readiness_checklist_applied=True,
        operator_review_required=True,
        manual_approval_required=True,
        paper_execution_upgrade_allowed=False,
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        adapter_routing_enabled=False,
        shadow_execution_enabled=False,
        limited_live_review_allowed=False,
        live_trading_allowed=False,
        strategy_registry_write_allowed=False,
        promotion_allowed=False,
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
        _write_json(upgrade_reviews_json_path, {"reviews": review_dicts})
        _write_jsonl(upgrade_reviews_jsonl_path, review_dicts)
        _write_csv(upgrade_reviews_csv_path, review_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def validate_paper_execution_upgrade_readiness_review(root: str | Path) -> Step216ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step216_paper_execution_upgrade_readiness_review_latest.json"
    if not result_path.exists():
        raise FileNotFoundError(
            f"Missing required Step216 result artifact: {result_path}. Step269 validation fails closed; "
            "run the explicit Step216 report command before validation."
        )

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    reviews = list(payload.get("reviews", []) or [])

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step215_present": Path(payload.get("source_step215_result_path", "")).exists(),
        "upgrade_reviews_json_exists": Path(payload.get("upgrade_reviews_json_path", "")).exists(),
        "upgrade_reviews_jsonl_exists": Path(payload.get("upgrade_reviews_jsonl_path", "")).exists(),
        "upgrade_reviews_csv_exists": Path(payload.get("upgrade_reviews_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_promotion_decisions_present": int(payload.get("source_promotion_decision_count", 0)) > 0,
        "upgrade_reviews_present": int(payload.get("upgrade_review_count", 0)) > 0 and bool(reviews),
        "readiness_review_created": payload.get("paper_execution_upgrade_readiness_review_created") is True,
        "readiness_checklist_applied": payload.get("readiness_checklist_applied") is True,
        "operator_review_required": payload.get("operator_review_required") is True and all(review.get("operator_review_required") is True for review in reviews),
        "manual_approval_required": payload.get("manual_approval_required") is True and all(review.get("manual_approval_required") is True for review in reviews),
        "no_paper_execution_upgrade": payload.get("paper_execution_upgrade_allowed") is False and all(review.get("paper_execution_upgrade_allowed") is False for review in reviews),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False and all(review.get("paper_order_execution_enabled") is False for review in reviews),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False and all(review.get("adapter_routing_enabled") is False for review in reviews),
        "no_shadow_execution": payload.get("shadow_execution_enabled") is False and all(review.get("shadow_execution_enabled") is False for review in reviews),
        "no_limited_live_review": payload.get("limited_live_review_allowed") is False and all(review.get("limited_live_review_allowed") is False for review in reviews),
        "no_live_trading": payload.get("live_trading_allowed") is False and all(review.get("live_trading_allowed") is False for review in reviews),
        "no_strategy_registry_write": payload.get("strategy_registry_write_allowed") is False and all(review.get("strategy_registry_write_allowed") is False for review in reviews),
        "no_promotion_allowed": payload.get("promotion_allowed") is False and all(review.get("promotion_allowed") is False for review in reviews),
        "no_auto_strategy_promotion": payload.get("auto_strategy_promotion") is False,
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False
        and payload.get("real_adapter_call_performed") is False
        and payload.get("telegram_real_send") is False,
        "no_production_cutover": payload.get("production_cutover_executable") is False
        and payload.get("live_mode_enable_allowed") is False,
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step216ValidationResult(
        status=STEP216_VALIDATION_OK if not failures else "STEP216_V5_PAPER_EXECUTION_UPGRADE_READINESS_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
