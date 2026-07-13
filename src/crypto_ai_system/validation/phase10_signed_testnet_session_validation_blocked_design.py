from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_3_9_4_blocked_design_hardening import (
    STATUS_PHASE9_3_9_4_HARDENING_RECORDED_BLOCKED_REVIEW_ONLY,
    persist_phase9_3_9_4_blocked_design_hardening_report,
)

PHASE10_SESSION_VALIDATION_VERSION = "phase10_signed_testnet_session_validation_blocked_design_v1"
PHASE10_SESSION_VALIDATION_REGISTRY_NAME = "phase10_signed_testnet_session_validation_blocked_design_registry"
STATUS_PHASE10_SESSION_VALIDATION_RECORDED_BLOCKED_REVIEW_ONLY = (
    "PHASE10_SIGNED_TESTNET_SESSION_VALIDATION_DESIGN_RECORDED_BLOCKED_REVIEW_ONLY"
)
STATUS_PHASE10_SESSION_VALIDATION_BLOCKED_REVIEW_ONLY = "PHASE10_SIGNED_TESTNET_SESSION_VALIDATION_DESIGN_BLOCKED_REVIEW_ONLY"

REQUIRED_PHASE9_4_FILES = {
    "phase9_3_9_4_hardening_report": "phase9_3_9_4_blocked_design_hardening_report.json",
    "phase9_4_reconciliation_design": "phase9_4_testnet_reconciliation_DESIGN_BLOCKED_REVIEW_ONLY.json",
    "phase9_4_reconciliation_validation": "phase9_4_testnet_reconciliation_validation_report.json",
}

SESSION_SCENARIOS_REQUIRED = [
    "long_session",
    "short_session",
    "neutral_no_trade_session",
    "reject_case",
    "cancel_case",
    "partial_fill_case",
]

SESSION_METRICS_REQUIRED = [
    "expectancy",
    "win_loss_ratio",
    "average_R",
    "max_drawdown",
    "slippage",
    "latency_ms",
    "rejection_rate",
    "stale_data_rate",
    "signal_to_outcome_drift",
    "paper_testnet_gap",
    "api_error_rate",
    "manual_override_count",
]

UNSAFE_TRUTHY_FIELDS = list(FALSE_FLAGS) + [
    "phase9_2_order_submission_authorized",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
    "phase10_signed_testnet_session_validation_may_begin",
    "phase10_session_validation_started",
    "phase10_promotion_review_packet_created",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_order_submission_performed",
    "reconciliation_started",
    "exchange_execution_record_present",
    "real_order_id_created",
]


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


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _flag_false_payload() -> dict[str, bool]:
    return {field: False for field in FALSE_FLAGS}


def _unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    fields = [field for field in UNSAFE_TRUTHY_FIELDS if _safe_bool(data.get(field))]
    for field in unsafe_truthy_fields(data):
        if field not in fields:
            fields.append(field)
    return sorted(dict.fromkeys(fields))


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase10_signed_testnet_session_validation_design_sha256",
        "phase10_signed_testnet_session_validation_report_sha256",
        "phase9_3_9_4_blocked_design_hardening_report_sha256",
        "phase9_4_testnet_reconciliation_design_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _source_summary(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status") or data.get("artifact_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data or _unsafe_fields(data):
        return False
    if name == "phase9_3_9_4_hardening_report":
        return (
            data.get("status") == STATUS_PHASE9_3_9_4_HARDENING_RECORDED_BLOCKED_REVIEW_ONLY
            and data.get("phase9_4_testnet_reconciliation_design_recorded") is True
            and data.get("phase10_signed_testnet_session_validation_may_begin") is False
            and data.get("reconciliation_started") is False
            and data.get("actual_order_submission_performed") is False
        )
    if name == "phase9_4_reconciliation_design":
        return (
            data.get("artifact_type") == "phase9_4_testnet_reconciliation_design_blocked_review_only"
            and data.get("review_only") is True
            and data.get("real_order_id") is None
            and data.get("phase10_signed_testnet_session_validation_may_begin") is False
        )
    if name == "phase9_4_reconciliation_validation":
        return data.get("phase9_4_testnet_reconciliation_design_valid") is True
    return True


def build_phase10_signed_testnet_session_validation_design(
    *, phase9_4_sources: Mapping[str, Mapping[str, Any]], created_at_utc: str
) -> dict[str, Any]:
    source_summary = {name: _source_summary(name, payload) for name, payload in phase9_4_sources.items()}
    design = {
        "artifact_type": "phase10_signed_testnet_session_validation_design_blocked_review_only",
        "phase10_signed_testnet_session_validation_version": PHASE10_SESSION_VALIDATION_VERSION,
        "review_only": True,
        "blocked_design_artifact": True,
        "source_evidence_hash_summary": source_summary,
        "no_real_phase9_2_order_id_available": True,
        "no_phase9_4_reconciliation_evidence_available": True,
        "phase10_session_validation_started": False,
        "phase10_signed_testnet_session_validation_may_begin": False,
        "phase10_promotion_review_packet_created": False,
        "live_canary_preparation_may_begin": False,
        "required_session_scenarios": SESSION_SCENARIOS_REQUIRED,
        "required_session_metrics": SESSION_METRICS_REQUIRED,
        "session_validation_plan": {
            "long_session": "validate a long-side testnet order lifecycle only after a real Phase 9.2 order path is enabled",
            "short_session": "validate a short-side testnet order lifecycle only after a real Phase 9.2 order path is enabled",
            "neutral_no_trade_session": "validate no-trade behavior when signal or risk gate blocks",
            "reject_case": "validate exchange rejection handling and normalized rejection reason capture",
            "cancel_case": "validate cancel request, cancel accepted/rejected, and final status handling",
            "partial_fill_case": "validate cumulative fill, remaining quantity, fee, and reconciliation handling",
        },
        "metric_collection_plan": {
            "expectancy": "aggregate R-based expectancy across signed testnet sessions",
            "win_loss_ratio": "track wins/losses by session and strategy profile",
            "average_R": "track average R-multiple per scenario",
            "max_drawdown": "track signed-testnet drawdown under capped notional",
            "slippage": "compare expected versus actual testnet fill slippage",
            "latency_ms": "record submit/status/cancel endpoint latency when real endpoints are allowed",
            "rejection_rate": "track rejection rate and normalized rejection reasons",
            "stale_data_rate": "track stale data blocks and stale data attempts",
            "signal_to_outcome_drift": "compare ResearchSignal permission and realized outcome",
            "paper_testnet_gap": "compare paper assumptions with signed testnet execution evidence",
            "api_error_rate": "track normalized API error rate by endpoint",
            "manual_override_count": "track operator overrides and reasons",
        },
        "promotion_blocking_policy": {
            "single_testnet_order_is_not_enough_for_live_canary": True,
            "any_phase9_4_reconciliation_mismatch_blocks_phase10": True,
            "missing_fee_slippage_latency_blocks_promotion_review": True,
            "missing_paper_testnet_gap_blocks_live_canary_preparation": True,
            "api_error_spike_blocks_promotion_review": True,
            "manual_override_requires_review": True,
            "phase10_packet_does_not_enable_live_canary": True,
        },
        "requires_before_phase10_may_begin": [
            "real_phase9_2_order_id",
            "phase9_3_final_status_polling_session_close",
            "phase9_4_reconciliation_record",
            "fee_slippage_latency_evidence",
            "paper_testnet_gap_baseline",
            "no_unresolved_reconciliation_mismatch",
        ],
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        "reconciliation_started": False,
        **_flag_false_payload(),
        "created_at_utc": created_at_utc,
    }
    design["phase10_signed_testnet_session_validation_design_sha256"] = sha256_json(design)
    return design


def validate_phase10_signed_testnet_session_validation_design(design: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(design or {})
    blockers: list[str] = []
    unsafe = _unsafe_fields(payload)
    if payload.get("artifact_type") != "phase10_signed_testnet_session_validation_design_blocked_review_only":
        blockers.append("PHASE10_SESSION_VALIDATION_DESIGN_TYPE_INVALID")
    if payload.get("review_only") is not True:
        blockers.append("PHASE10_SESSION_VALIDATION_DESIGN_NOT_REVIEW_ONLY")
    if payload.get("no_real_phase9_2_order_id_available") is not True:
        blockers.append("PHASE10_SESSION_VALIDATION_EXPECTED_NO_REAL_ORDER_ID")
    if payload.get("no_phase9_4_reconciliation_evidence_available") is not True:
        blockers.append("PHASE10_SESSION_VALIDATION_EXPECTED_NO_RECONCILIATION_EVIDENCE")
    for field in (
        "phase10_session_validation_started",
        "phase10_signed_testnet_session_validation_may_begin",
        "phase10_promotion_review_packet_created",
        "live_canary_preparation_may_begin",
        "reconciliation_started",
    ):
        if payload.get(field) is not False:
            blockers.append(f"PHASE10_SESSION_VALIDATION_UNSAFE_FIELD:{field}")
    scenarios = payload.get("required_session_scenarios") or []
    for scenario in SESSION_SCENARIOS_REQUIRED:
        if scenario not in scenarios:
            blockers.append(f"PHASE10_SESSION_SCENARIO_MISSING:{scenario}")
    metrics = payload.get("required_session_metrics") or []
    for metric in SESSION_METRICS_REQUIRED:
        if metric not in metrics:
            blockers.append(f"PHASE10_SESSION_METRIC_MISSING:{metric}")
    metric_plan = payload.get("metric_collection_plan") or {}
    for metric in SESSION_METRICS_REQUIRED:
        if metric not in metric_plan:
            blockers.append(f"PHASE10_SESSION_METRIC_PLAN_MISSING:{metric}")
    policy = payload.get("promotion_blocking_policy") or {}
    for key in (
        "single_testnet_order_is_not_enough_for_live_canary",
        "any_phase9_4_reconciliation_mismatch_blocks_phase10",
        "missing_fee_slippage_latency_blocks_promotion_review",
        "missing_paper_testnet_gap_blocks_live_canary_preparation",
        "phase10_packet_does_not_enable_live_canary",
    ):
        if policy.get(key) is not True:
            blockers.append(f"PHASE10_PROMOTION_BLOCKING_POLICY_MISSING:{key}")
    if unsafe:
        blockers.append("PHASE10_SESSION_VALIDATION_UNSAFE_FLAGS:" + ",".join(unsafe))
    valid = not blockers
    return {
        "artifact_type": "phase10_signed_testnet_session_validation_design_validation_report",
        "phase10_signed_testnet_session_validation_design_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_flag_false_payload(),
    }


def _build_negative_fixture_results(design: Mapping[str, Any]) -> dict[str, Any]:
    cases: dict[str, dict[str, Any]] = {
        "phase10_may_begin_true": {"phase10_signed_testnet_session_validation_may_begin": True},
        "phase10_session_started_true": {"phase10_session_validation_started": True},
        "live_canary_preparation_true": {"live_canary_preparation_may_begin": True},
        "promotion_packet_created_true": {"phase10_promotion_review_packet_created": True},
        "missing_paper_testnet_gap_metric": {"required_session_metrics": [m for m in SESSION_METRICS_REQUIRED if m != "paper_testnet_gap"]},
        "missing_partial_fill_scenario": {"required_session_scenarios": [s for s in SESSION_SCENARIOS_REQUIRED if s != "partial_fill_case"]},
        "reconciliation_started_true": {"reconciliation_started": True},
        "order_status_endpoint_called_true": {"order_status_endpoint_called": True},
    }
    results: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(design)
        payload.update(patch)
        validation = validate_phase10_signed_testnet_session_validation_design(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    all_blocked = all(r["blocked"] and r["fail_closed"] for r in results.values())
    payload = {
        "artifact_type": "phase10_signed_testnet_session_validation_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
        "phase10_signed_testnet_session_validation_may_begin": False,
        "live_canary_preparation_may_begin": False,
        "actual_order_submission_performed": False,
    }
    payload["phase10_signed_testnet_session_validation_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def build_phase10_signed_testnet_session_validation_blocked_design_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_3_9_4_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    if run_phase9_3_9_4_first:
        persist_phase9_3_9_4_blocked_design_hardening_report(cfg=cfg, run_phase9_3_first=True)
    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_PHASE9_4_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if payload and not _source_ready(name, payload)]
    unsafe_source_flags = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    created = utc_now_canonical()
    design = build_phase10_signed_testnet_session_validation_design(phase9_4_sources=sources, created_at_utc=created)
    validation = validate_phase10_signed_testnet_session_validation_design(design)
    negative_fixture_results = _build_negative_fixture_results(design)
    blockers: list[str] = []
    if missing:
        blockers.extend(f"PHASE10_REQUIRED_SOURCE_MISSING:{name}" for name in missing)
    if not_ready:
        blockers.extend(f"PHASE10_REQUIRED_SOURCE_NOT_READY:{name}" for name in not_ready)
    if validation["blocked"]:
        blockers.extend(validation["block_reasons"])
    if not negative_fixture_results["all_negative_fixtures_blocked_fail_closed"]:
        blockers.append("PHASE10_NEGATIVE_FIXTURES_DID_NOT_ALL_BLOCK_FAIL_CLOSED")
    blockers.append("PHASE10_BLOCKED_UNTIL_REAL_PHASE9_4_RECONCILIATION_AND_MULTIPLE_TESTNET_SESSIONS_EXIST")
    status = STATUS_PHASE10_SESSION_VALIDATION_RECORDED_BLOCKED_REVIEW_ONLY
    report = {
        "phase10_signed_testnet_session_validation_id": stable_id("phase10_signed_testnet_session_validation", source_summary),
        "phase10_signed_testnet_session_validation_version": PHASE10_SESSION_VALIDATION_VERSION,
        "status": status,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "phase10_signed_testnet_session_validation_design_recorded": True,
        "phase10_signed_testnet_session_validation_design_valid": validation["phase10_signed_testnet_session_validation_design_valid"],
        "phase10_signed_testnet_session_validation_may_begin": False,
        "phase10_session_validation_started": False,
        "phase10_promotion_review_packet_created": False,
        "live_canary_preparation_may_begin": False,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe_source_flags,
        "required_session_scenarios": SESSION_SCENARIOS_REQUIRED,
        "required_session_metrics": SESSION_METRICS_REQUIRED,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "recommended_next_action": "perform_real_phase9_2_single_testnet_order_then_phase9_3_status_cancel_and_phase9_4_reconciliation_before_phase10_sessions",
        **_flag_false_payload(),
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "reconciliation_started": False,
        "actual_order_submission_performed": False,
        "created_at_utc": created,
    }
    report["phase10_signed_testnet_session_validation_report_sha256"] = sha256_json(report)
    return report, design, validation, negative_fixture_results


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 10 Signed Testnet Session Validation Design - Blocked Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact defines the repeated signed testnet session validation model while Phase 9.2/9.3/9.4 remain without real order evidence.",
            "",
            "## Result",
            "",
            f"- Phase 10 may begin: `{report.get('phase10_signed_testnet_session_validation_may_begin')}`",
            f"- Phase 10 session validation started: `{report.get('phase10_session_validation_started')}`",
            f"- Live canary preparation may begin: `{report.get('live_canary_preparation_may_begin')}`",
            "",
            "## Required before Phase 10",
            "",
            "- Real Phase 9.2 signed testnet order evidence",
            "- Phase 9.3 final status/cancel session close evidence",
            "- Phase 9.4 reconciliation record with no unresolved mismatch",
            "- Fee, slippage, latency, API error, and paper/testnet gap evidence",
            "",
            "## Still Disabled",
            "",
            "- `phase10_signed_testnet_session_validation_may_begin=false`",
            "- `live_canary_preparation_may_begin=false`",
            "- `actual_order_submission_performed=false`",
            "- `runtime_mutation_performed=false`",
            "",
        ]
    )


def persist_phase10_signed_testnet_session_validation_blocked_design_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_3_9_4_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase10_signed_testnet_session_validation_blocked_design")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, design, validation, negative_fixture_results = build_phase10_signed_testnet_session_validation_blocked_design_report(
        cfg=cfg,
        run_phase9_3_9_4_first=run_phase9_3_9_4_first,
    )
    handoff = _build_handoff_markdown(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase10_signed_testnet_session_validation_blocked_design_report.json", report)
        atomic_write_json(base / "phase10_signed_testnet_session_validation_DESIGN_BLOCKED_REVIEW_ONLY.json", design)
        atomic_write_json(base / "phase10_signed_testnet_session_validation_validation_report.json", validation)
        atomic_write_json(base / "phase10_signed_testnet_session_validation_negative_fixture_results.json", negative_fixture_results)
        (base / "PHASE10_SIGNED_TESTNET_SESSION_VALIDATION_HANDOFF_BLOCKED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE10_SESSION_VALIDATION_REGISTRY_NAME),
        {
            "phase10_signed_testnet_session_validation_id": report.get("phase10_signed_testnet_session_validation_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "phase10_signed_testnet_session_validation_design_recorded": report.get("phase10_signed_testnet_session_validation_design_recorded"),
            "phase10_signed_testnet_session_validation_may_begin": False,
            "live_canary_preparation_may_begin": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE10_SESSION_VALIDATION_REGISTRY_NAME,
        id_field="phase10_signed_testnet_session_validation_registry_record_id",
        hash_field="phase10_signed_testnet_session_validation_registry_record_sha256",
        id_prefix="phase10_signed_testnet_session_validation_registry_record",
    )
    atomic_write_json(latest / "phase10_signed_testnet_session_validation_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase10_signed_testnet_session_validation_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE10_SESSION_VALIDATION_VERSION",
    "STATUS_PHASE10_SESSION_VALIDATION_RECORDED_BLOCKED_REVIEW_ONLY",
    "STATUS_PHASE10_SESSION_VALIDATION_BLOCKED_REVIEW_ONLY",
    "SESSION_SCENARIOS_REQUIRED",
    "SESSION_METRICS_REQUIRED",
    "build_phase10_signed_testnet_session_validation_blocked_design_report",
    "persist_phase10_signed_testnet_session_validation_blocked_design_report",
    "validate_phase10_signed_testnet_session_validation_design",
]
