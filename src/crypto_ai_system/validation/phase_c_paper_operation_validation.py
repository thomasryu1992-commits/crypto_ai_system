from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_file, sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.paper_data_quality_gate import (
    STATUS_PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY,
    persist_paper_data_quality_gate_report,
)
from crypto_ai_system.validation.paper_strategy_validation import (
    STATUS_PAPER_STRATEGY_VALIDATION_RECORDED_REVIEW_ONLY,
    persist_paper_strategy_validation_report,
)
from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import (
    STATUS_RECORDED_REVIEW_ONLY as STATUS_PHASE4_1_RECORDED_REVIEW_ONLY,
    persist_phase4_1_paper_outcome_sample_accumulation_report,
)
from crypto_ai_system.validation.phase4_3_research_signal_score_bucket_replay import (
    STATUS_RECORDED_REVIEW_ONLY as STATUS_PHASE4_3_RECORDED_REVIEW_ONLY,
    persist_phase4_3_research_signal_score_bucket_replay_report,
)
from crypto_ai_system.validation.phase4_4_candidate_profile_review_packet import (
    STATUS_RECORDED_REVIEW_ONLY as STATUS_PHASE4_4_RECORDED_REVIEW_ONLY,
    persist_phase4_4_candidate_profile_review_packet_report,
)

PHASE_C_VERSION = "phase_c_paper_operation_validation_v1"
PHASE_C_REGISTRY_NAME = "phase_c_paper_operation_validation_registry"

STATUS_PHASE_C_RECORDED_REVIEW_ONLY = "PHASE_C_PAPER_OPERATION_VALIDATION_RECORDED_REVIEW_ONLY"
STATUS_PHASE_C_BLOCKED_REVIEW_ONLY = "PHASE_C_PAPER_OPERATION_VALIDATION_BLOCKED_REVIEW_ONLY"

RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE = False
APPROVAL_PACKET_CREATED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE = False
SIGNED_TESTNET_PROMOTION_ALLOWED_BY_THIS_MODULE = False
LIVE_EXECUTION_UNLOCK_AUTHORITY_BY_THIS_MODULE = False


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _storage_dir(cfg: AppConfig, rel: str) -> Path:
    path = cfg.root / rel
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_latest_json(cfg: AppConfig, name: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / name, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _hash_latest(cfg: AppConfig, name: str) -> str | None:
    path = _latest_dir(cfg) / name
    return sha256_file(path) if path.exists() else None


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        out = float(value)
        if out != out:
            return default
        return out
    except Exception:
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _collect_chain_ids(
    *,
    research_signal: Mapping[str, Any],
    decision: Mapping[str, Any],
    risk_gate: Mapping[str, Any],
    order_intent: Mapping[str, Any],
    paper_execution: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "data_snapshot_id": research_signal.get("data_snapshot_id") or outcome.get("data_snapshot_id"),
        "feature_snapshot_id": research_signal.get("feature_snapshot_id") or outcome.get("feature_snapshot_id"),
        "research_signal_id": research_signal.get("research_signal_id") or decision.get("research_signal_id") or outcome.get("research_signal_id"),
        "profile_id": research_signal.get("profile_id") or decision.get("profile_id") or outcome.get("profile_id"),
        "approval_packet_id": None,
        "approval_intake_id": None,
        "decision_id": decision.get("decision_id") or outcome.get("decision_id"),
        "risk_gate_id": risk_gate.get("risk_gate_id") or order_intent.get("risk_gate_id") or outcome.get("risk_gate_id"),
        "order_intent_id": order_intent.get("order_intent_id") or paper_execution.get("order_intent_id") or outcome.get("order_intent_id"),
        "execution_id": paper_execution.get("execution_id") or reconciliation.get("execution_id") or outcome.get("execution_id"),
        "reconciliation_id": reconciliation.get("reconciliation_id") or outcome.get("reconciliation_id"),
        "outcome_id": outcome.get("outcome_id"),
        "feedback_cycle_id": outcome.get("feedback_cycle_id"),
    }


def _chain_status(chain: Mapping[str, Any]) -> dict[str, Any]:
    paper_required = [
        "data_snapshot_id",
        "feature_snapshot_id",
        "research_signal_id",
        "profile_id",
        "decision_id",
        "risk_gate_id",
        "order_intent_id",
        "execution_id",
        "reconciliation_id",
        "outcome_id",
        "feedback_cycle_id",
    ]
    full_required = ["approval_packet_id", "approval_intake_id", *paper_required]
    missing_paper = [name for name in paper_required if not _present(chain.get(name))]
    missing_full = [name for name in full_required if not _present(chain.get(name))]
    return {
        "paper_stage_chain_complete": not missing_paper,
        "missing_paper_stage_chain_fields": missing_paper,
        "full_canonical_id_chain_complete": not missing_full,
        "missing_full_canonical_id_chain_fields": missing_full,
        "approval_chain_missing_by_design_for_phase_c": all(name in missing_full for name in ["approval_packet_id", "approval_intake_id"]),
    }


def _side_effect_flags(*artifacts: Mapping[str, Any]) -> dict[str, bool]:
    flag_names = [
        "runtime_settings_mutated",
        "score_weights_mutated",
        "candidate_profile_applied",
        "approval_packet_created",
        "auto_promotion_allowed",
        "live_trading_allowed_by_this_module",
        "external_order_submission_performed",
        "live_order_executed",
        "adapter_called",
        "testnet_order_submission_allowed_by_this_module",
        "testnet_order_submission_allowed",
        "signed_testnet_promotion_allowed",
        "signed_testnet_unlock_authority",
        "live_execution_unlock_authority",
        "runtime_permission_source",
    ]
    out: dict[str, bool] = {}
    for name in flag_names:
        out[name] = any(_bool(item.get(name)) for item in artifacts if isinstance(item, Mapping))
    return out


def _source_artifacts(cfg: AppConfig) -> dict[str, dict[str, Any]]:
    latest = _latest_dir(cfg)
    names = [
        "paper_data_quality_gate_report.json",
        "paper_strategy_validation_report.json",
        "research_signal.json",
        "signal_qa_report.json",
        "legacy_signal_fallback_blocker_report.json",
        "paper_trade_decision.json",
        "pre_order_risk_gate_report.json",
        "paper_order_intent.json",
        "paper_execution_record.json",
        "paper_reconciliation_record.json",
        "outcome_analytics_record.json",
        "phase4_1_paper_outcome_sample_accumulation_report.json",
        "paper_outcome_sample_accumulation_outcomes.json",
        "performance_report.json",
        "phase4_3_research_signal_score_bucket_replay_report.json",
        "paper_outcome_score_bucket_enriched_outcomes.json",
        "drift_reduced_candidate_profile_draft.json",
        "phase4_4_candidate_profile_review_packet_report.json",
        "candidate_profile_review_packet.json",
        "approval_packet_draft_review_only.json",
    ]
    return {
        name: {
            "path": str(latest / name),
            "exists": (latest / name).exists(),
            "sha256": _hash_latest(cfg, name),
        }
        for name in names
    }


def _blockers(
    *,
    paper_data_gate: Mapping[str, Any],
    paper_strategy: Mapping[str, Any],
    research_signal: Mapping[str, Any],
    signal_qa: Mapping[str, Any],
    legacy_blocker: Mapping[str, Any],
    risk_gate: Mapping[str, Any],
    order_intent: Mapping[str, Any],
    paper_execution: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    outcome: Mapping[str, Any],
    phase4_1: Mapping[str, Any],
    performance_report: Mapping[str, Any],
    phase4_3: Mapping[str, Any],
    drift_reduced_candidate: Mapping[str, Any],
    phase4_4: Mapping[str, Any],
    chain_report: Mapping[str, Any],
    unsafe_flags: Mapping[str, bool],
    source_artifacts: Mapping[str, Mapping[str, Any]],
    min_closed_sample_size: int,
    max_reconciliation_mismatch_count: int,
    min_expectancy: float,
    max_drawdown: float,
    max_slippage_bps: float,
    max_latency_ms: float,
    max_rejection_rate: float,
    max_stale_data_rate: float,
    max_signal_alignment_drift_rate: float,
    max_api_error_rate: float,
) -> list[str]:
    blockers: list[str] = []
    required_files = [
        "paper_data_quality_gate_report.json",
        "paper_strategy_validation_report.json",
        "research_signal.json",
        "signal_qa_report.json",
        "pre_order_risk_gate_report.json",
        "paper_order_intent.json",
        "paper_execution_record.json",
        "paper_reconciliation_record.json",
        "outcome_analytics_record.json",
        "phase4_1_paper_outcome_sample_accumulation_report.json",
        "paper_outcome_sample_accumulation_outcomes.json",
        "performance_report.json",
        "phase4_3_research_signal_score_bucket_replay_report.json",
        "drift_reduced_candidate_profile_draft.json",
        "phase4_4_candidate_profile_review_packet_report.json",
    ]
    for name in required_files:
        if not source_artifacts.get(name, {}).get("exists"):
            blockers.append(f"MISSING_REQUIRED_PHASE_C_ARTIFACT:{name}")

    if paper_data_gate.get("status") != STATUS_PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY:
        blockers.append("PAPER_DATA_QUALITY_GATE_NOT_PASSED")
    if paper_strategy.get("status") != STATUS_PAPER_STRATEGY_VALIDATION_RECORDED_REVIEW_ONLY:
        blockers.append("PAPER_STRATEGY_VALIDATION_NOT_RECORDED")
    if not research_signal.get("research_signal_id") or "research_signal_v2" not in _text(research_signal.get("signal_version")):
        blockers.append("RESEARCH_SIGNAL_V2_MISSING_OR_INVALID")
    if signal_qa.get("signal_qa_result") not in {"PASS", "PASS_REVIEW_ONLY"}:
        blockers.append("SIGNAL_QA_NOT_PASSING")
    signal_qa_passed_for_paper_context = (
        signal_qa.get("allowed_for_paper") is True
        or (
            signal_qa.get("signal_qa_result") in {"PASS", "PASS_REVIEW_ONLY"}
            and paper_strategy.get("status") == STATUS_PAPER_STRATEGY_VALIDATION_RECORDED_REVIEW_ONLY
            and paper_strategy.get("pre_order_risk_gate_status") == "PASS_PAPER"
        )
    )
    if not signal_qa_passed_for_paper_context:
        blockers.append("SIGNAL_QA_NOT_PASSING_FOR_PAPER_CONTEXT")
    if signal_qa.get("allowed_for_live") is True or signal_qa.get("allowed_for_signed_testnet") is True:
        blockers.append("SIGNAL_QA_UNSAFE_NON_PAPER_PERMISSION")
    if legacy_blocker and legacy_blocker.get("allowed_for_live") is True:
        blockers.append("LEGACY_FALLBACK_ALLOWED_FOR_LIVE")
    if risk_gate.get("status") != "PASS_PAPER" or risk_gate.get("approved") is not True:
        blockers.append("PRE_ORDER_RISK_GATE_NOT_PASS_PAPER")
    if order_intent.get("status") != "ORDER_INTENT_CREATED" or order_intent.get("paper_only") is not True:
        blockers.append("PAPER_ORDER_INTENT_NOT_CREATED")
    if paper_execution.get("paper_order_submitted") is not True:
        blockers.append("PAPER_EXECUTION_NOT_SUBMITTED_TO_SIMULATOR")
    if paper_execution.get("external_order_submission_performed") is True or paper_execution.get("adapter_called") is True:
        blockers.append("PAPER_EXECUTION_UNSAFE_EXTERNAL_SUBMISSION")
    if reconciliation.get("reconciled") is not True or reconciliation.get("reconciliation_mismatch") is True:
        blockers.append("PAPER_RECONCILIATION_NOT_CLEAN")
    if outcome.get("status") != "OUTCOME_RECORDED" or outcome.get("outcome_closed") is not True:
        blockers.append("LATEST_OUTCOME_NOT_CLOSED_RECORDED")
    if phase4_1.get("status") != STATUS_PHASE4_1_RECORDED_REVIEW_ONLY:
        blockers.append("PHASE4_1_SAMPLE_ACCUMULATION_NOT_RECORDED")
    if int(_float(phase4_1.get("closed_count"), 0.0)) < min_closed_sample_size:
        blockers.append("INSUFFICIENT_CLOSED_PAPER_OUTCOMES")
    if performance_report.get("status") != "PERFORMANCE_REPORT_RECORDED":
        blockers.append("PERFORMANCE_REPORT_NOT_RECORDED")
    if int(_float(performance_report.get("reconciliation_mismatch_count"), 0.0)) > max_reconciliation_mismatch_count:
        blockers.append("RECONCILIATION_MISMATCH_COUNT_ABOVE_LIMIT")
    if _float(performance_report.get("expectancy"), 0.0) < min_expectancy:
        blockers.append("EXPECTANCY_BELOW_LIMIT")
    if _float(performance_report.get("max_drawdown"), 0.0) > max_drawdown:
        blockers.append("MAX_DRAWDOWN_ABOVE_LIMIT")
    if _float(performance_report.get("average_slippage"), 0.0) > max_slippage_bps:
        blockers.append("AVERAGE_SLIPPAGE_ABOVE_LIMIT")
    if _float(performance_report.get("average_latency_ms"), 0.0) > max_latency_ms:
        blockers.append("AVERAGE_LATENCY_ABOVE_LIMIT")
    if _float(performance_report.get("rejection_rate"), 0.0) > max_rejection_rate:
        blockers.append("REJECTION_RATE_ABOVE_LIMIT")
    if _float(performance_report.get("stale_data_rate"), 0.0) > max_stale_data_rate:
        blockers.append("STALE_DATA_RATE_ABOVE_LIMIT")
    if _float(performance_report.get("api_error_rate"), 0.0) > max_api_error_rate:
        blockers.append("API_ERROR_RATE_ABOVE_LIMIT")

    phase4_3_summary = phase4_3.get("overall_summary") or {}
    if phase4_3.get("status") != STATUS_PHASE4_3_RECORDED_REVIEW_ONLY:
        blockers.append("PHASE4_3_SCORE_BUCKET_REPLAY_NOT_RECORDED")
    if _float(phase4_3_summary.get("alignment_drift_rate"), 1.0) > max_signal_alignment_drift_rate:
        blockers.append("SIGNAL_ALIGNMENT_DRIFT_RATE_ABOVE_LIMIT")
    if int(_float(phase4_3_summary.get("missing_signal_score_count"), 1.0)) > 0:
        blockers.append("MISSING_SIGNAL_SCORE_BUCKETS")
    if phase4_3.get("candidate_profile_draft_created") is not True:
        blockers.append("DRIFT_REDUCED_CANDIDATE_PROFILE_DRAFT_NOT_CREATED")
    if drift_reduced_candidate.get("status") != "review_only_draft":
        blockers.append("DRIFT_REDUCED_CANDIDATE_PROFILE_NOT_REVIEW_ONLY_DRAFT")
    if drift_reduced_candidate.get("candidate_profile_applied") is True:
        blockers.append("CANDIDATE_PROFILE_WAS_APPLIED_UNSAFELY")
    if phase4_4.get("status") != STATUS_PHASE4_4_RECORDED_REVIEW_ONLY:
        blockers.append("PHASE4_4_CANDIDATE_REVIEW_PACKET_NOT_RECORDED")
    if phase4_4.get("approval_packet_created") is True or phase4_4.get("approval_intake_submitted") is True:
        blockers.append("PHASE_C_UNEXPECTED_APPROVAL_COMPLETION")
    if chain_report.get("paper_stage_chain_complete") is not True:
        blockers.append("PAPER_STAGE_CANONICAL_CHAIN_INCOMPLETE")
    if chain_report.get("full_canonical_id_chain_complete") is True:
        blockers.append("FULL_CANONICAL_CHAIN_UNEXPECTEDLY_COMPLETE_BEFORE_MANUAL_APPROVAL")
    unsafe_allowed = [name for name, value in unsafe_flags.items() if value and name not in {"adapter_called"}]
    # adapter_called is unsafe in paper execution above when it comes from the execution evidence;
    # keep this aggregate check explicit for all runtime-impacting flags.
    if unsafe_allowed:
        blockers.extend([f"UNSAFE_RUNTIME_FLAG_TRUE:{name}" for name in unsafe_allowed])
    return sorted(dict.fromkeys(blockers))


def build_phase_c_paper_operation_validation_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    run_upstream: bool = False,
    min_closed_sample_size: int = 30,
    sample_size: int = 50,
    horizon_bars: int = 12,
    max_reconciliation_mismatch_count: int = 0,
    min_expectancy: float = 0.0,
    max_drawdown: float = 20.0,
    max_slippage_bps: float = 10.0,
    max_latency_ms: float = 1000.0,
    max_rejection_rate: float = 0.0,
    max_stale_data_rate: float = 0.0,
    max_signal_alignment_drift_rate: float = 0.0,
    max_api_error_rate: float = 0.0,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    if run_upstream:
        persist_paper_data_quality_gate_report(cfg=cfg)
        persist_paper_strategy_validation_report(cfg=cfg)
        persist_phase4_1_paper_outcome_sample_accumulation_report(
            cfg=cfg,
            sample_size=sample_size,
            horizon_bars=horizon_bars,
            min_closed_sample_size=min_closed_sample_size,
        )
        # Phase 4.2 intentionally remains a diagnostic blocker in some packages until
        # score-bucket replay attaches pre-trade score metadata. Phase C uses Phase 4.3
        # as the drift-controlled candidate-readiness source.
        persist_phase4_3_research_signal_score_bucket_replay_report(cfg=cfg)
        persist_phase4_4_candidate_profile_review_packet_report(cfg=cfg)

    paper_data_gate = _read_latest_json(cfg, "paper_data_quality_gate_report.json")
    paper_strategy = _read_latest_json(cfg, "paper_strategy_validation_report.json")
    research_signal = _read_latest_json(cfg, "research_signal.json")
    signal_qa = _read_latest_json(cfg, "signal_qa_report.json")
    legacy_blocker = _read_latest_json(cfg, "legacy_signal_fallback_blocker_report.json")
    decision = _read_latest_json(cfg, "paper_trade_decision.json")
    risk_gate = _read_latest_json(cfg, "pre_order_risk_gate_report.json")
    order_intent = _read_latest_json(cfg, "paper_order_intent.json")
    paper_execution = _read_latest_json(cfg, "paper_execution_record.json")
    reconciliation = _read_latest_json(cfg, "paper_reconciliation_record.json")
    outcome = _read_latest_json(cfg, "outcome_analytics_record.json")
    phase4_1 = _read_latest_json(cfg, "phase4_1_paper_outcome_sample_accumulation_report.json")
    performance_report = _read_latest_json(cfg, "performance_report.json")
    phase4_3 = _read_latest_json(cfg, "phase4_3_research_signal_score_bucket_replay_report.json")
    drift_reduced_candidate = _read_latest_json(cfg, "drift_reduced_candidate_profile_draft.json")
    phase4_4 = _read_latest_json(cfg, "phase4_4_candidate_profile_review_packet_report.json")
    source_artifacts = _source_artifacts(cfg)
    chain = _collect_chain_ids(
        research_signal=research_signal,
        decision=decision,
        risk_gate=risk_gate,
        order_intent=order_intent,
        paper_execution=paper_execution,
        reconciliation=reconciliation,
        outcome=outcome,
    )
    chain_report = _chain_status(chain)
    unsafe_flags = _side_effect_flags(
        paper_strategy,
        research_signal,
        signal_qa,
        legacy_blocker,
        decision,
        risk_gate,
        order_intent,
        paper_execution,
        reconciliation,
        outcome,
        phase4_1,
        performance_report,
        phase4_3,
        drift_reduced_candidate,
        phase4_4,
    )
    blockers = _blockers(
        paper_data_gate=paper_data_gate,
        paper_strategy=paper_strategy,
        research_signal=research_signal,
        signal_qa=signal_qa,
        legacy_blocker=legacy_blocker,
        risk_gate=risk_gate,
        order_intent=order_intent,
        paper_execution=paper_execution,
        reconciliation=reconciliation,
        outcome=outcome,
        phase4_1=phase4_1,
        performance_report=performance_report,
        phase4_3=phase4_3,
        drift_reduced_candidate=drift_reduced_candidate,
        phase4_4=phase4_4,
        chain_report=chain_report,
        unsafe_flags=unsafe_flags,
        source_artifacts=source_artifacts,
        min_closed_sample_size=min_closed_sample_size,
        max_reconciliation_mismatch_count=max_reconciliation_mismatch_count,
        min_expectancy=min_expectancy,
        max_drawdown=max_drawdown,
        max_slippage_bps=max_slippage_bps,
        max_latency_ms=max_latency_ms,
        max_rejection_rate=max_rejection_rate,
        max_stale_data_rate=max_stale_data_rate,
        max_signal_alignment_drift_rate=max_signal_alignment_drift_rate,
        max_api_error_rate=max_api_error_rate,
    )
    blocked = bool(blockers)
    status = STATUS_PHASE_C_BLOCKED_REVIEW_ONLY if blocked else STATUS_PHASE_C_RECORDED_REVIEW_ONLY
    phase4_3_summary = phase4_3.get("overall_summary") or {}
    created = utc_now_canonical()
    seed = {
        "version": PHASE_C_VERSION,
        "status": status,
        "research_signal_id": research_signal.get("research_signal_id"),
        "phase4_1_id": phase4_1.get("phase4_1_paper_outcome_sample_accumulation_id"),
        "phase4_3_id": phase4_3.get("phase4_3_research_signal_score_bucket_replay_id"),
        "created_at_utc": created,
    }
    payload: dict[str, Any] = {
        "phase_c_paper_operation_validation_id": stable_id("phase_c_paper_operation_validation", seed, 24),
        "phase_c_version": PHASE_C_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "paper_only": True,
        "run_upstream_performed": run_upstream,
        "paper_operation_loop_validated": not blocked,
        "research_signal_v2_generated": bool(research_signal.get("research_signal_id")) and "research_signal_v2" in _text(research_signal.get("signal_version")),
        "signal_qa_passed_for_paper": (
            signal_qa.get("allowed_for_paper") is True
            or (
                signal_qa.get("signal_qa_result") in {"PASS", "PASS_REVIEW_ONLY"}
                and paper_strategy.get("status") == STATUS_PAPER_STRATEGY_VALIDATION_RECORDED_REVIEW_ONLY
                and paper_strategy.get("pre_order_risk_gate_status") == "PASS_PAPER"
            )
        ),
        "legacy_fallback_permission_blocked_for_live": legacy_blocker.get("allowed_for_live") is not True,
        "trading_decision_price_structure_only": decision.get("signal_permission_authoritative") is True and decision.get("external_order_submission_performed") is False,
        "pre_order_risk_gate_paper_passed": risk_gate.get("status") == "PASS_PAPER" and risk_gate.get("approved") is True,
        "paper_order_intent_created_after_risk_gate": order_intent.get("status") == "ORDER_INTENT_CREATED" and order_intent.get("risk_gate_id") == risk_gate.get("risk_gate_id"),
        "paper_execution_simulated_fill_created": bool((paper_execution.get("simulated_fill") or {}).get("fill_id") or paper_execution.get("paper_order_submitted") is True),
        "paper_reconciliation_clean": reconciliation.get("reconciled") is True and reconciliation.get("reconciliation_mismatch") is not True,
        "outcome_analytics_recorded": outcome.get("status") == "OUTCOME_RECORDED" and outcome.get("outcome_closed") is True,
        "performance_report_recorded": performance_report.get("status") == "PERFORMANCE_REPORT_RECORDED",
        "closed_paper_outcome_sample_count": int(_float(phase4_1.get("closed_count"), 0.0)),
        "min_closed_paper_outcome_sample_size": min_closed_sample_size,
        "performance_metrics": {
            "expectancy": performance_report.get("expectancy"),
            "average_R": performance_report.get("average_R"),
            "max_drawdown": performance_report.get("max_drawdown"),
            "average_slippage": performance_report.get("average_slippage"),
            "average_latency_ms": performance_report.get("average_latency_ms"),
            "rejection_rate": performance_report.get("rejection_rate"),
            "stale_data_rate": performance_report.get("stale_data_rate"),
            "api_error_rate": performance_report.get("api_error_rate"),
            "reconciliation_mismatch_count": performance_report.get("reconciliation_mismatch_count"),
            "raw_signal_to_outcome_drift": performance_report.get("signal_to_outcome_drift"),
            "score_bucket_alignment_drift_rate": phase4_3_summary.get("alignment_drift_rate"),
            "missing_signal_score_count": phase4_3_summary.get("missing_signal_score_count"),
        },
        "drift_control_source": "phase4_3_score_bucket_replay_pre_trade_metadata",
        "drift_controlled_candidate_profile_draft_created": phase4_3.get("candidate_profile_draft_created") is True,
        "drift_controlled_candidate_profile_id": drift_reduced_candidate.get("candidate_profile_id"),
        "candidate_profile_review_packet_created": phase4_4.get("candidate_review_packet_created") is True,
        "approval_packet_draft_created_review_only": phase4_4.get("approval_packet_draft_created") is True,
        "approval_packet_created": False,
        "approval_intake_submitted": False,
        "manual_approval_required_next": True,
        "candidate_profile_ready_for_manual_review": not blocked and phase4_4.get("status") == STATUS_PHASE4_4_RECORDED_REVIEW_ONLY,
        "candidate_profile_runtime_applied": False,
        "canonical_id_chain": chain,
        **chain_report,
        "block_reasons": blockers,
        "thresholds": {
            "min_closed_sample_size": min_closed_sample_size,
            "max_reconciliation_mismatch_count": max_reconciliation_mismatch_count,
            "min_expectancy": min_expectancy,
            "max_drawdown": max_drawdown,
            "max_slippage_bps": max_slippage_bps,
            "max_latency_ms": max_latency_ms,
            "max_rejection_rate": max_rejection_rate,
            "max_stale_data_rate": max_stale_data_rate,
            "max_signal_alignment_drift_rate": max_signal_alignment_drift_rate,
            "max_api_error_rate": max_api_error_rate,
        },
        "source_artifacts": source_artifacts,
        "unsafe_runtime_flags_detected": unsafe_flags,
        "live_candidate_eligible": False,
        "signed_testnet_unlock_authority": False,
        "signed_testnet_promotion_allowed": False,
        "testnet_order_submission_allowed": False,
        "live_execution_unlock_authority": False,
        "live_trading_allowed_by_this_module": False,
        "external_order_submission_performed": False,
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "auto_promotion_allowed": False,
        "recommended_next_action": "prepare_phase_d_manual_approval_chain_review" if not blocked else "continue_paper_validation_until_blockers_clear",
        "created_at_utc": created,
    }
    payload["phase_c_report_sha256"] = sha256_json(payload)
    return payload


def persist_phase_c_paper_operation_validation_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    run_upstream: bool = False,
    min_closed_sample_size: int = 30,
    sample_size: int = 50,
    horizon_bars: int = 12,
    max_reconciliation_mismatch_count: int = 0,
    min_expectancy: float = 0.0,
    max_drawdown: float = 20.0,
    max_slippage_bps: float = 10.0,
    max_latency_ms: float = 1000.0,
    max_rejection_rate: float = 0.0,
    max_stale_data_rate: float = 0.0,
    max_signal_alignment_drift_rate: float = 0.0,
    max_api_error_rate: float = 0.0,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    report = build_phase_c_paper_operation_validation_report(
        cfg=cfg,
        run_upstream=run_upstream,
        min_closed_sample_size=min_closed_sample_size,
        sample_size=sample_size,
        horizon_bars=horizon_bars,
        max_reconciliation_mismatch_count=max_reconciliation_mismatch_count,
        min_expectancy=min_expectancy,
        max_drawdown=max_drawdown,
        max_slippage_bps=max_slippage_bps,
        max_latency_ms=max_latency_ms,
        max_rejection_rate=max_rejection_rate,
        max_stale_data_rate=max_stale_data_rate,
        max_signal_alignment_drift_rate=max_signal_alignment_drift_rate,
        max_api_error_rate=max_api_error_rate,
    )
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase_c_paper_operation_validation")
    atomic_write_json(latest / "phase_c_paper_operation_validation_report.json", report)
    atomic_write_json(phase_dir / "phase_c_paper_operation_validation_report.json", report)
    registry_record = {
        "phase_c_registry_version": PHASE_C_VERSION,
        "phase_c_paper_operation_validation_id": report.get("phase_c_paper_operation_validation_id"),
        "status": report.get("status"),
        "blocked": report.get("blocked"),
        "fail_closed": report.get("fail_closed"),
        "paper_operation_loop_validated": report.get("paper_operation_loop_validated"),
        "closed_paper_outcome_sample_count": report.get("closed_paper_outcome_sample_count"),
        "candidate_profile_ready_for_manual_review": report.get("candidate_profile_ready_for_manual_review"),
        "paper_stage_chain_complete": report.get("paper_stage_chain_complete"),
        "full_canonical_id_chain_complete": report.get("full_canonical_id_chain_complete"),
        "block_reasons": report.get("block_reasons"),
        "phase_c_report_sha256": report.get("phase_c_report_sha256"),
        "live_candidate_eligible": False,
        "signed_testnet_unlock_authority": False,
        "testnet_order_submission_allowed": False,
        "live_execution_unlock_authority": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "approval_packet_created": False,
        "auto_promotion_allowed": False,
        "external_order_submission_performed": False,
        "created_at_utc": report.get("created_at_utc") or utc_now_canonical(),
    }
    registry_record["phase_c_registry_record_sha256"] = sha256_json(registry_record)
    persisted = append_registry_record(
        registry_path(cfg, PHASE_C_REGISTRY_NAME),
        registry_record,
        registry_name=PHASE_C_REGISTRY_NAME,
        id_field="phase_c_paper_operation_validation_registry_record_id",
        hash_field="phase_c_paper_operation_validation_registry_record_sha256",
        id_prefix="phase_c_paper_operation_validation_registry",
    )
    atomic_write_json(latest / "phase_c_paper_operation_validation_registry_record.json", persisted)
    report["phase_c_paper_operation_validation_registry_record_id"] = persisted.get("phase_c_paper_operation_validation_registry_record_id")
    report["phase_c_paper_operation_validation_registry_record_sha256"] = persisted.get("phase_c_paper_operation_validation_registry_record_sha256")
    atomic_write_json(latest / "phase_c_paper_operation_validation_report.json", report)
    atomic_write_json(phase_dir / "phase_c_paper_operation_validation_report.json", report)
    return report


def run_phase_c_paper_operation_validation_latest(cfg: AppConfig | None = None) -> dict[str, Any]:
    return persist_phase_c_paper_operation_validation_report(cfg=cfg, run_upstream=True)
