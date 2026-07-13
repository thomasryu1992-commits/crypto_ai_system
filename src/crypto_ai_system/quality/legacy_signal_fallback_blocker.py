from __future__ import annotations

from typing import Any, Mapping

from crypto_ai_system.quality.signal_qa import (
    BLOCK_FALLBACK_OR_SYNTHETIC,
    BLOCK_INVALID_LINEAGE,
    BLOCK_LEGACY_FALLBACK,
    BLOCK_MISSING_SIGNAL,
    BLOCK_STALE_DATA,
    PASS_PAPER_ONLY,
    PASS_REVIEW_ONLY,
)
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

LEGACY_SIGNAL_FALLBACK_BLOCKER_VERSION = "step290_legacy_signal_fallback_blocker_v1"

PASS_GATE_DISABLED_REVIEW_ONLY = "PASS_GATE_DISABLED_REVIEW_ONLY"
PASS_RESEARCH_SIGNAL_QA = "PASS_RESEARCH_SIGNAL_QA"
BLOCK_SIGNAL_QA_UNAVAILABLE = "BLOCK_SIGNAL_QA_UNAVAILABLE"
BLOCK_SIGNAL_QA_NOT_MATCHING_SIGNAL = "BLOCK_SIGNAL_QA_NOT_MATCHING_SIGNAL"
BLOCK_SIGNAL_QA_NOT_PASSING = "BLOCK_SIGNAL_QA_NOT_PASSING"

PASS_RESULTS = {PASS_GATE_DISABLED_REVIEW_ONLY, PASS_RESEARCH_SIGNAL_QA}
BLOCK_RESULTS = {
    BLOCK_INVALID_LINEAGE,
    BLOCK_STALE_DATA,
    BLOCK_FALLBACK_OR_SYNTHETIC,
    BLOCK_MISSING_SIGNAL,
    BLOCK_LEGACY_FALLBACK,
    BLOCK_SIGNAL_QA_UNAVAILABLE,
    BLOCK_SIGNAL_QA_NOT_MATCHING_SIGNAL,
    BLOCK_SIGNAL_QA_NOT_PASSING,
}
SIGNAL_QA_PASS_RESULTS = {PASS_REVIEW_ONLY, PASS_PAPER_ONLY}
SIGNAL_QA_BLOCK_RESULTS = {
    BLOCK_INVALID_LINEAGE,
    BLOCK_STALE_DATA,
    BLOCK_FALLBACK_OR_SYNTHETIC,
    BLOCK_MISSING_SIGNAL,
    BLOCK_LEGACY_FALLBACK,
}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled", "allowed"}


def _signal_id(signal: Mapping[str, Any] | None) -> str:
    signal = signal or {}
    return str(signal.get("research_signal_id") or signal.get("signal_id") or "")


def _qa_signal_id(signal_qa_report: Mapping[str, Any] | None) -> str:
    signal_qa_report = signal_qa_report or {}
    return str(signal_qa_report.get("research_signal_id") or "")


def legacy_fallback_used(payload: Mapping[str, Any] | None) -> bool:
    payload = payload or {}
    if _truthy(payload.get("legacy_fallback_used")):
        return True
    if _truthy(payload.get("legacy_signal_used")):
        return True
    if _truthy(payload.get("used_legacy_signal")):
        return True
    source = str(payload.get("source") or payload.get("signal_source") or "").lower()
    if source in {"legacy", "legacy_fallback", "legacy_research_result", "legacy_signal_fallback"}:
        return True
    if "legacy" in str(payload.get("signal_version") or "").lower():
        return True
    return False


def build_legacy_signal_fallback_block_report(
    *,
    research_signal: Mapping[str, Any] | None,
    signal_qa_report: Mapping[str, Any] | None,
    use_research_signal_gate: bool = True,
    consumer: str = "unknown",
) -> dict[str, Any]:
    """Gate legacy signal fallback before decision/trading consumers.

    Step290 makes ResearchSignal + Signal QA an explicit precondition whenever
    use_research_signal_gate=true. Legacy research-result or market-snapshot
    fallback can remain as report-only compatibility, but it must not grant new
    position permission, paper execution, signed testnet execution, or live
    execution.
    """
    research_signal = dict(research_signal or {})
    signal_qa_report = dict(signal_qa_report or {})
    block_reasons: list[str] = []
    sid = _signal_id(research_signal)
    qa_sid = _qa_signal_id(signal_qa_report)
    qa_result = str(signal_qa_report.get("signal_qa_result") or "")

    if not use_research_signal_gate:
        result = PASS_GATE_DISABLED_REVIEW_ONLY
    else:
        if not research_signal or not sid:
            block_reasons.append(BLOCK_MISSING_SIGNAL)
        if research_signal and legacy_fallback_used(research_signal):
            block_reasons.append(BLOCK_LEGACY_FALLBACK)
        if not signal_qa_report:
            block_reasons.append(BLOCK_SIGNAL_QA_UNAVAILABLE)
        elif not qa_sid:
            block_reasons.append(BLOCK_SIGNAL_QA_UNAVAILABLE)
        elif sid and qa_sid != sid:
            block_reasons.append(BLOCK_SIGNAL_QA_NOT_MATCHING_SIGNAL)
            block_reasons.append(BLOCK_INVALID_LINEAGE)
        if signal_qa_report and qa_result in SIGNAL_QA_BLOCK_RESULTS:
            block_reasons.append(qa_result)
        elif signal_qa_report and qa_result and qa_result not in SIGNAL_QA_PASS_RESULTS:
            block_reasons.append(BLOCK_SIGNAL_QA_NOT_PASSING)
        elif signal_qa_report and not qa_result:
            block_reasons.append(BLOCK_SIGNAL_QA_UNAVAILABLE)

        block_reasons = sorted(set(block_reasons))
        result = block_reasons[0] if block_reasons else PASS_RESEARCH_SIGNAL_QA

    allowed_for_decision = result in PASS_RESULTS and use_research_signal_gate
    allowed_for_paper = bool(allowed_for_decision and qa_result == PASS_PAPER_ONLY)
    payload = {
        "legacy_signal_fallback_blocker_version": LEGACY_SIGNAL_FALLBACK_BLOCKER_VERSION,
        "legacy_signal_fallback_blocker_result": result,
        "consumer": consumer,
        "research_signal_gate_enabled": bool(use_research_signal_gate),
        "research_signal_id": sid or None,
        "signal_qa_report_id": signal_qa_report.get("signal_qa_report_id"),
        "signal_qa_result": qa_result or None,
        "signal_qa_relevant": bool(sid and qa_sid and sid == qa_sid),
        "legacy_fallback_used": legacy_fallback_used(research_signal),
        "block_reasons": block_reasons,
        "allowed_for_decision": allowed_for_decision,
        "allowed_for_paper": allowed_for_paper,
        "allowed_for_signed_testnet": False,
        "allowed_for_live": False,
        "allow_new_position": allowed_for_paper,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "order_intent_created": False,
        "trade_approved": False,
        "created_at_utc": utc_now_canonical(),
    }
    payload["legacy_signal_fallback_blocker_id"] = stable_id("legacy_signal_fallback_blocker", payload, 24)
    payload["legacy_signal_fallback_blocker_sha256"] = sha256_json(payload)
    return payload


def assert_no_legacy_signal_fallback(
    *,
    research_signal: Mapping[str, Any] | None,
    signal_qa_report: Mapping[str, Any] | None,
    use_research_signal_gate: bool = True,
    consumer: str = "unknown",
) -> dict[str, Any]:
    report = build_legacy_signal_fallback_block_report(
        research_signal=research_signal,
        signal_qa_report=signal_qa_report,
        use_research_signal_gate=use_research_signal_gate,
        consumer=consumer,
    )
    if report["legacy_signal_fallback_blocker_result"] not in PASS_RESULTS:
        reasons = ",".join(report.get("block_reasons") or [])
        raise ValueError(f"Legacy signal fallback blocked: {reasons}")
    return report
