from __future__ import annotations

from config.settings import LATEST_DIR, PROJECT_ROOT, RESEARCH_DECISION_PATH, RESEARCH_RESULT_PATH, RESEARCH_SIGNAL_PATH, USE_RESEARCH_SIGNAL_GATE
from core.json_io import atomic_write_json, read_json
from crypto_ai_system.utils.audit import utc_now_canonical
from crypto_ai_system.config import load_config
from crypto_ai_system.registry.decision_pipeline_registry import persist_decision_pipeline_registry_record
from crypto_ai_system.trading.order_id_chain import ORDER_ID_CHAIN_VERSION, decision_id_from_signal
from core.event_log import log_event
from crypto_ai_system.quality.legacy_signal_fallback_blocker import build_legacy_signal_fallback_block_report


RESEARCH_DECISION_MODE = "DECISION_GENERATION_ONLY"
TRADING_EXECUTION_ENABLED_BY_THIS_MODULE = False
ORDER_ROUTING_ENABLED_BY_THIS_MODULE = False
SIGNAL_QA_REPORT_PATH = LATEST_DIR / "signal_qa_report.json"
LEGACY_SIGNAL_FALLBACK_BLOCKER_REPORT_PATH = LATEST_DIR / "legacy_signal_fallback_blocker_report.json"
DECISION_PIPELINE_REGISTRY_RECORD_PATH = LATEST_DIR / "decision_pipeline_registry_record.json"
SIGNAL_QA_BLOCK_RESULTS = {
    "BLOCK_INVALID_LINEAGE",
    "BLOCK_STALE_DATA",
    "BLOCK_FALLBACK_OR_SYNTHETIC",
    "BLOCK_MISSING_SIGNAL",
    "BLOCK_LEGACY_FALLBACK",
}


def run_research_decision() -> dict:
    research = read_json(RESEARCH_RESULT_PATH, {})
    research_signal = read_json(RESEARCH_SIGNAL_PATH, {})
    signal_qa_report = read_json(SIGNAL_QA_REPORT_PATH, {})
    if not research and not research_signal:
        raise RuntimeError("No research result or ResearchSignal found.")

    scenario = research.get("scenario") or research_signal.get("market_condition") or research_signal.get("scenario")
    timing = research.get("signal_timing") or research_signal.get("signal_timing")
    score = float(research.get("scores", {}).get("final_score", research_signal.get("score_total_score", 0)))

    bias = "NEUTRAL"
    if scenario in {"Bullish", "Constructive"} and timing not in {"Data-Blocked", "Late"}:
        bias = "ALLOW_LONG_BIAS"
    elif scenario in {"Bearish", "Cautious"}:
        bias = "ALLOW_SHORT_OR_RISK_OFF"

    # Step280 runtime hygiene: avoid global latest ResearchSignal state leaking into
    # isolated legacy research-result tests/runs. A ResearchSignal permission override
    # is only authoritative when the research result explicitly references the same
    # research_signal_id, or when no legacy research result is supplied.
    research_signal_id = str(research_signal.get("research_signal_id") or research_signal.get("signal_id") or "")
    research_result_signal_id = str(research.get("research_signal_id") or research.get("signal_id") or "")
    signal_qa_result = str(signal_qa_report.get("signal_qa_result") or "")
    signal_qa_signal_id = str(signal_qa_report.get("research_signal_id") or "")
    signal_qa_relevant = bool(signal_qa_signal_id and signal_qa_signal_id == research_signal_id)
    legacy_block_report = build_legacy_signal_fallback_block_report(
        research_signal=research_signal,
        signal_qa_report=signal_qa_report if signal_qa_relevant else {},
        use_research_signal_gate=USE_RESEARCH_SIGNAL_GATE,
        consumer="research_decision_engine",
    )
    legacy_blocker_blocks_decision = bool(
        USE_RESEARCH_SIGNAL_GATE
        and legacy_block_report.get("legacy_signal_fallback_blocker_result")
        not in {"PASS_RESEARCH_SIGNAL_QA", "PASS_GATE_DISABLED_REVIEW_ONLY"}
    )
    signal_qa_blocks_decision = bool(signal_qa_relevant and signal_qa_result in SIGNAL_QA_BLOCK_RESULTS)
    # Step290: when the ResearchSignal gate is enabled, legacy research-result
    # fallback cannot grant position permission. A matching ResearchSignal and
    # matching Signal QA pass are required before signal permission is authoritative.
    signal_permission_authoritative = (
        bool(research_signal)
        and not signal_qa_blocks_decision
        and not legacy_blocker_blocks_decision
        and (not USE_RESEARCH_SIGNAL_GATE or bool(signal_qa_relevant))
        and (not research or (bool(research_result_signal_id) and research_result_signal_id == research_signal_id))
    )
    trade_permission = (
        research_signal.get("trade_permission")
        if signal_permission_authoritative and isinstance(research_signal.get("trade_permission"), dict)
        else {}
    )
    side = "LONG" if bias == "ALLOW_LONG_BIAS" else "SHORT" if bias == "ALLOW_SHORT_OR_RISK_OFF" and scenario == "Bearish" else "NONE"
    decision_seed = {"side": side, "scenario": scenario, "final_score": score, "created_from": "step271_research_decision"}
    decision_id = decision_id_from_signal(research_signal, decision_seed)

    decision = {
        "created_at": utc_now_canonical(),
        "created_at_utc": utc_now_canonical(),
        "decision_id": decision_id,
        "decision_version": ORDER_ID_CHAIN_VERSION,
        "research_signal_id": research_signal_id if signal_permission_authoritative or not research else research_result_signal_id,
        "profile_id": str(research_signal.get("profile_id") or ""),
        "data_snapshot_id": str(research_signal.get("data_snapshot_id") or ""),
        "feature_snapshot_id": str(research_signal.get("feature_snapshot_id") or "") if signal_permission_authoritative or not research else "",
        "signal_permission_authoritative": signal_permission_authoritative,
        "signal_qa_result": signal_qa_result or None,
        "signal_qa_report_id": signal_qa_report.get("signal_qa_report_id") if signal_qa_relevant else None,
        "signal_qa_relevant": signal_qa_relevant,
        "signal_qa_blocks_decision": signal_qa_blocks_decision,
        "legacy_signal_fallback_blocker_result": legacy_block_report.get("legacy_signal_fallback_blocker_result"),
        "legacy_signal_fallback_blocker_id": legacy_block_report.get("legacy_signal_fallback_blocker_id"),
        "legacy_signal_fallback_blocker_blocks_decision": legacy_blocker_blocks_decision,
        "legacy_signal_fallback_blocker_block_reasons": legacy_block_report.get("block_reasons") or [],
        "side": side,
        "research_bias": bias,
        "scenario": scenario,
        "signal_quality": research.get("signal_quality"),
        "signal_timing": timing,
        "final_score": score,
        "allow_long": bool(trade_permission.get("allow_long", bias == "ALLOW_LONG_BIAS")) and not signal_qa_blocks_decision and not legacy_blocker_blocks_decision,
        "allow_short": bool(trade_permission.get("allow_short", bias == "ALLOW_SHORT_OR_RISK_OFF" and scenario == "Bearish")) and not signal_qa_blocks_decision and not legacy_blocker_blocks_decision,
        "allow_new_position": bool(trade_permission.get("allow_new_position", side in {"LONG", "SHORT"})) and not signal_qa_blocks_decision and not legacy_blocker_blocks_decision,
        "risk_level": "blocked" if (signal_qa_blocks_decision or legacy_blocker_blocks_decision) else str(trade_permission.get("risk_level", "normal" if side in {"LONG", "SHORT"} else "blocked")),
        "reasons": research.get("scores", {}).get("positives", []) + research.get("scores", {}).get("risks", []),
        "research_decision_mode": RESEARCH_DECISION_MODE,
        "trading_execution_enabled_by_this_module": TRADING_EXECUTION_ENABLED_BY_THIS_MODULE,
        "order_routing_enabled_by_this_module": ORDER_ROUTING_ENABLED_BY_THIS_MODULE,
    }
    decision_pipeline_record = persist_decision_pipeline_registry_record(
        load_config(PROJECT_ROOT),
        decision=decision,
        research_signal=research_signal,
        signal_qa_report=signal_qa_report if signal_qa_relevant else {},
        legacy_blocker=legacy_block_report,
    )
    decision["decision_pipeline_registry_record_id"] = decision_pipeline_record.get("decision_pipeline_record_id")
    decision["decision_pipeline_registry_record_sha256"] = decision_pipeline_record.get("decision_pipeline_registry_record_sha256")
    decision["decision_pipeline_current_stage_id_chain_complete"] = decision_pipeline_record.get("current_stage_id_chain_complete")
    decision["decision_pipeline_missing_current_stage_id_fields"] = decision_pipeline_record.get("missing_current_stage_id_fields") or []
    decision["decision_pipeline_missing_canonical_id_fields"] = decision_pipeline_record.get("missing_canonical_id_fields") or []

    atomic_write_json(RESEARCH_DECISION_PATH, decision)
    atomic_write_json(DECISION_PIPELINE_REGISTRY_RECORD_PATH, decision_pipeline_record)
    log_event("research_decision_created", {"research_bias": bias})
    return decision


def main() -> None:
    decision = run_research_decision()
    print(f"Research decision: {decision['research_bias']}")


if __name__ == "__main__":
    main()
