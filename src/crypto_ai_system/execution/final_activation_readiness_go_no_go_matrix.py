from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P30_FINAL_ACTIVATION_READINESS_GO_NO_GO_MATRIX_VERSION = "p30_final_activation_readiness_go_no_go_matrix_v1"
P30_FINAL_ACTIVATION_READINESS_GO_NO_GO_MATRIX_REGISTRY_NAME = "p30_final_activation_readiness_go_no_go_matrix_registry"

STATUS_GENERATED_REVIEW_ONLY = "P30_FINAL_ACTIVATION_READINESS_GO_NO_GO_MATRIX_GENERATED_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P30_FINAL_ACTIVATION_READINESS_GO_NO_GO_MATRIX_BLOCKED_FAIL_CLOSED"

OPERATOR_DECISION_GO_REVIEW_ONLY = "GO_REVIEW_ONLY_FOR_SEPARATE_OPERATOR_RUNTIME_ACTIVATION_DECISION_NOT_RUNTIME_AUTHORITY"
OPERATOR_DECISION_WAITING = "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE"
OPERATOR_DECISION_NO_GO = "NO_GO_FAIL_CLOSED"

_PHASE_SUMMARY_FILES: tuple[tuple[str, str, str], ...] = (
    ("P0", "Baseline hygiene", "p0_baseline_hygiene_completion_summary.json"),
    ("P1", "Live candidate data foundation", "p1_live_candidate_data_foundation_summary.json"),
    ("P2", "Paper operation validation", "p2_paper_operation_validation_summary.json"),
    ("P3", "Candidate/manual approval chain", "p3_candidate_manual_approval_chain_summary.json"),
    ("P4", "Signed testnet runtime package", "p4_signed_testnet_one_order_runtime_package_summary.json"),
    ("P5", "Action-time submit approval boundary", "p5_action_time_submit_approval_boundary_summary.json"),
    ("P6", "Single signed testnet submit runtime action boundary", "p6_single_signed_testnet_submit_runtime_action_summary.json"),
    ("P7", "Post-submit signed testnet evidence intake", "p7_post_submit_evidence_intake_summary.json"),
    ("P8", "Repeated clean signed testnet sessions", "p8_repeated_clean_signed_testnet_sessions_summary.json"),
    ("P9", "Live read-only canary preparation", "p9_live_read_only_canary_preparation_summary.json"),
    ("P10", "Live canary one-order execution boundary", "p10_live_canary_one_order_execution_boundary_summary.json"),
    ("P11", "Live canary post-submit evidence review", "p11_live_canary_post_submit_evidence_review_summary.json"),
    ("P12", "Repeated clean live canary sessions", "p12_repeated_clean_live_canary_sessions_summary.json"),
    ("P13", "Live scaled readiness review", "p13_live_scaled_readiness_review_summary.json"),
    ("P14", "Separate live scaled approval intake", "p14_live_scaled_approval_intake_validation_summary.json"),
    ("P15", "Limited live scaled runtime enablement boundary", "p15_limited_live_scaled_runtime_enablement_boundary_summary.json"),
    ("P16", "Limited live scaled loop dry-run harness", "p16_limited_live_scaled_loop_dry_run_harness_summary.json"),
    ("P17", "Runtime release gate/operator handoff", "p17_runtime_release_gate_operator_handoff_summary.json"),
    ("P18", "Full regression CI release gate hardening", "p18_full_regression_ci_release_gate_summary.json"),
    ("P19", "Docker/Launcher evidence intake", "p19_docker_launcher_evidence_intake_summary.json"),
    ("P20", "External evidence template/export pack", "p20_external_evidence_template_export_pack_summary.json"),
    ("P21", "CI filled evidence release candidate bundle", "p21_ci_filled_evidence_release_candidate_bundle_summary.json"),
    ("P22", "Operator release candidate acceptance review", "p22_operator_release_candidate_acceptance_review_summary.json"),
    ("P23", "Accepted RC handoff/runtime enablement template", "p23_operator_accepted_release_candidate_handoff_summary.json"),
    ("P24", "Runtime enablement request intake validator", "p24_runtime_enablement_request_intake_validator_summary.json"),
    ("P25", "Final runtime enablement boundary review packet", "p25_final_runtime_enablement_boundary_review_packet_summary.json"),
    ("P26", "Operator runtime activation request template gate", "p26_operator_runtime_activation_request_template_gate_summary.json"),
    ("P27", "Operator runtime activation request intake validator", "p27_operator_runtime_activation_request_intake_validator_summary.json"),
    ("P28", "Final operator runtime activation gate review", "p28_final_operator_runtime_activation_gate_review_summary.json"),
    ("P29", "Final runtime activation dry-run evidence bundle", "p29_final_runtime_activation_dry_run_evidence_bundle_summary.json"),
)

_EXECUTION_FIELDS_FOR_P30 = {
    "limited_live_scaled_auto_trading_allowed",
    "live_scaled_runtime_enablement_allowed",
    "live_scaled_execution_enabled",
    "live_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "runtime_scheduler_enabled",
    "runtime_loop_started",
    "runtime_enablement_performed",
    "operator_runtime_activation_performed",
    "final_activation_gate_performed",
    "final_activation_gate_review_performed",
    "final_runtime_activation_dry_run_performed",
    "actual_live_order_submitted",
    "actual_testnet_order_submitted",
    "live_order_endpoint_called",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "secret_value_accessed",
    "secret_value_logged",
    "api_key_value_logged",
    "api_secret_value_logged",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "auto_promotion_allowed",
    "runtime_authority_claimed",
    "matrix_is_runtime_authority",
    "operator_decision_executes_runtime",
    "scheduler_start_requested",
    "order_submission_requested",
    "endpoint_call_allowed",
    "secret_file_accessed",
    "secret_file_created",
}

_SECRET_VALUE_PATTERNS = (
    "BINANCE_API_SECRET=",
    "BINANCE_API_KEY=",
    "PRIVATE_KEY=",
    "api_secret_value:",
    "api_key_value:",
    "secret_value:",
    "BEGIN PRIVATE KEY",
)


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


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _scan_truthy_execution_fields(payloads: Sequence[tuple[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, source: str, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                next_path = f"{path}.{key}"
                if key in _EXECUTION_FIELDS_FOR_P30 and _bool(value):
                    hits.append({"source": source, "path": next_path, "field": str(key), "value": True})
                walk(value, source, next_path)
        elif isinstance(payload, list):
            for idx, item in enumerate(payload):
                walk(item, source, f"{path}[{idx}]")

    for source, payload in payloads:
        walk(payload, source)
    return hits


def _scan_secret_value_patterns(payloads: Sequence[tuple[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, source: str, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                walk(value, source, f"{path}.{key}")
        elif isinstance(payload, list):
            for idx, item in enumerate(payload):
                walk(item, source, f"{path}[{idx}]")
        elif isinstance(payload, str):
            for pattern in _SECRET_VALUE_PATTERNS:
                if pattern.lower() in payload.lower():
                    hits.append({"source": source, "path": path, "pattern": pattern})

    for source, payload in payloads:
        walk(payload, source)
    return hits


def _phase_decision(summary: Mapping[str, Any], *, missing: bool) -> tuple[str, list[str]]:
    if missing:
        return "WAITING", ["SUMMARY_MISSING"]
    status = str(summary.get("status") or summary.get("baseline_status") or summary.get("validation_status") or "").upper()
    reasons: list[str] = []
    if not status:
        return "WAITING", ["STATUS_MISSING"]
    if "BLOCKED" in status or "FAIL_CLOSED" in status:
        reasons.append("SUMMARY_STATUS_BLOCKED")
        return "NO_GO", reasons
    if "WAITING" in status:
        reasons.append("SUMMARY_STATUS_WAITING")
        return "WAITING", reasons
    if _scan_truthy_execution_fields([("summary", summary)]):
        reasons.append("UNSAFE_TRUTHY_EXECUTION_FLAG")
        return "NO_GO", reasons
    if _scan_secret_value_patterns([("summary", summary)]):
        reasons.append("SECRET_PATTERN_FOUND")
        return "NO_GO", reasons
    return "GO_REVIEW_ONLY", reasons


def _read_or_use_phase_summaries(root: Path, phase_summaries: Mapping[str, Mapping[str, Any]] | None) -> dict[str, dict[str, Any]]:
    if phase_summaries is not None:
        return {phase: dict(payload) for phase, payload in phase_summaries.items()}
    cfg = load_config(root)
    return {phase: _read_latest_json(cfg, filename) for phase, _label, filename in _PHASE_SUMMARY_FILES}


def build_final_activation_readiness_go_no_go_matrix_report(
    *,
    root: Path | None = None,
    phase_summaries: Mapping[str, Mapping[str, Any]] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    root = root or Path.cwd()
    summaries = _read_or_use_phase_summaries(root, phase_summaries)
    matrix: list[dict[str, Any]] = []
    named_payloads: list[tuple[str, Mapping[str, Any]]] = []
    waiting_phases: list[str] = []
    no_go_phases: list[str] = []
    go_review_only_phases: list[str] = []

    for phase, label, filename in _PHASE_SUMMARY_FILES:
        summary = summaries.get(phase, {})
        missing = not bool(summary)
        decision, reasons = _phase_decision(summary, missing=missing)
        if decision == "WAITING":
            waiting_phases.append(phase)
        elif decision == "NO_GO":
            no_go_phases.append(phase)
        elif decision == "GO_REVIEW_ONLY":
            go_review_only_phases.append(phase)
        matrix.append({
            "phase": phase,
            "label": label,
            "summary_filename": filename,
            "summary_present": not missing,
            "summary_status": summary.get("status") or summary.get("baseline_status") or summary.get("validation_status"),
            "decision": decision,
            "decision_reasons": reasons,
            "summary_sha256": sha256_json(summary) if summary else None,
            "runtime_authority": False,
            "order_submission_allowed_by_phase": False,
        })
        if summary:
            named_payloads.append((phase, summary))

    named_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(named_payloads)
    secret_hits = _scan_secret_value_patterns(named_payloads)
    endpoint_call_hits = [hit for hit in unsafe_hits if hit["field"] in {"order_endpoint_called", "live_order_endpoint_called", "order_status_endpoint_called", "cancel_endpoint_called", "http_request_sent"}]

    disabled_state = default_execution_flag_state()
    disabled_state.update({field: False for field in _EXECUTION_FIELDS_FOR_P30})
    truthy_disabled = truthy_execution_flags(disabled_state)

    block_reasons: list[str] = []
    if no_go_phases:
        block_reasons.append("P30_ONE_OR_MORE_PHASES_NO_GO")
    if unsafe_hits:
        block_reasons.append("P30_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND")
    if endpoint_call_hits:
        block_reasons.append("P30_ENDPOINT_CALL_EVIDENCE_FOUND")
    if secret_hits:
        block_reasons.append("P30_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P30_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    all_phase_summaries_present = len(go_review_only_phases) + len(waiting_phases) + len(no_go_phases) == len(_PHASE_SUMMARY_FILES) and not any(not item["summary_present"] for item in matrix)
    all_phases_go_review_only = len(go_review_only_phases) == len(_PHASE_SUMMARY_FILES)
    final_activation_readiness_decision = OPERATOR_DECISION_NO_GO if blocked else (OPERATOR_DECISION_GO_REVIEW_ONLY if all_phases_go_review_only else OPERATOR_DECISION_WAITING)

    report: dict[str, Any] = {
        "p30_final_activation_readiness_go_no_go_matrix_version": P30_FINAL_ACTIVATION_READINESS_GO_NO_GO_MATRIX_VERSION,
        "status": STATUS_BLOCKED_FAIL_CLOSED if blocked else STATUS_GENERATED_REVIEW_ONLY,
        "blocked": blocked,
        "waiting": (not blocked and bool(waiting_phases)),
        "valid_review_only": not blocked,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": [f"P30_{phase}_WAITING" for phase in waiting_phases],
        "required_phase_count": len(_PHASE_SUMMARY_FILES),
        "present_phase_count": sum(1 for row in matrix if row["summary_present"]),
        "go_review_only_phase_count": len(go_review_only_phases),
        "waiting_phase_count": len(waiting_phases),
        "no_go_phase_count": len(no_go_phases),
        "all_phase_summaries_present": all_phase_summaries_present,
        "all_phases_go_review_only": all_phases_go_review_only,
        "waiting_phases": waiting_phases,
        "no_go_phases": no_go_phases,
        "go_review_only_phases": go_review_only_phases,
        "go_no_go_matrix": matrix,
        "operator_final_activation_decision": final_activation_readiness_decision,
        "operator_decision_matrix_generated_review_only": True,
        "operator_decision_matrix_is_runtime_authority": False,
        "final_activation_go_review_only": all_phases_go_review_only and not blocked,
        "final_activation_go_runtime_authority": False,
        "final_activation_execution_allowed_by_this_matrix": False,
        "separate_operator_runtime_activation_execution_still_required": True,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "endpoint_call_evidence_hits": endpoint_call_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "runtime_enablement_performed": False,
        "operator_runtime_activation_performed": False,
        "final_activation_gate_performed": False,
        "final_activation_gate_review_performed": False,
        "final_runtime_activation_dry_run_performed": False,
        "actual_live_order_submitted": False,
        "actual_testnet_order_submitted": False,
        "live_order_endpoint_called": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    report["p30_final_activation_readiness_go_no_go_matrix_id"] = stable_id("p30_final_activation_readiness_go_no_go_matrix", report, 24)
    report["p30_final_activation_readiness_go_no_go_matrix_sha256"] = sha256_json(report)
    return report


def _valid_phase_summaries() -> dict[str, dict[str, Any]]:
    return {
        phase: {
            "status": f"{phase}_VALID_REVIEW_ONLY",
            "phase": phase,
            "live_scaled_execution_enabled": False,
            "runtime_scheduler_enabled": False,
            "live_order_submission_allowed": False,
            "order_endpoint_called": False,
            "secret_value_accessed": False,
        }
        for phase, _label, _filename in _PHASE_SUMMARY_FILES
    }


def build_p30_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    valid = _valid_phase_summaries()
    cases: dict[str, Mapping[str, Mapping[str, Any]]] = {
        "missing_required_summary": {key: value for key, value in valid.items() if key != "P29"},
        "blocked_phase_summary": {**valid, "P21": {**valid["P21"], "status": "P21_BLOCKED_FAIL_CLOSED"}},
        "waiting_phase_summary": {**valid, "P29": {**valid["P29"], "status": "P29_WAITING_REVIEW_ONLY"}},
        "unsafe_live_scaled_enabled": {**valid, "P15": {**valid["P15"], "live_scaled_execution_enabled": True}},
        "endpoint_call_evidence_found": {**valid, "P29": {**valid["P29"], "order_endpoint_called": True}},
        "secret_pattern_found": {**valid, "P22": {**valid["P22"], "operator_note": "BINANCE_API_SECRET=leaked"}},
        "runtime_scheduler_enabled": {**valid, "P16": {**valid["P16"], "runtime_scheduler_enabled": True}},
    }
    results: dict[str, Any] = {}
    for name, summaries in cases.items():
        report = build_final_activation_readiness_go_no_go_matrix_report(root=root, phase_summaries=summaries)
        blocked_or_waiting = report["blocked"] or report["waiting"] or report["operator_final_activation_decision"] != OPERATOR_DECISION_GO_REVIEW_ONLY
        results[name] = {
            "blocked_or_waiting": blocked_or_waiting,
            "blocked": report["blocked"],
            "waiting": report["waiting"],
            "status": report["status"],
            "operator_final_activation_decision": report["operator_final_activation_decision"],
            "block_reasons": report["block_reasons"],
            "waiting_reasons": report["waiting_reasons"],
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
            "runtime_scheduler_enabled": report["runtime_scheduler_enabled"],
            "order_endpoint_called": report["order_endpoint_called"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    return {
        "p30_final_activation_readiness_go_no_go_matrix_version": P30_FINAL_ACTIVATION_READINESS_GO_NO_GO_MATRIX_VERSION,
        "status": "P30_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_final_activation_readiness_go_no_go_matrix(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p30_final_activation_readiness_go_no_go_matrix")
    report = build_final_activation_readiness_go_no_go_matrix_report(root=cfg.root)
    negative_results = build_p30_negative_fixture_results(root=cfg.root)
    atomic_write_json(latest / "p30_final_activation_readiness_go_no_go_matrix_report.json", report)
    atomic_write_json(storage / "p30_final_activation_readiness_go_no_go_matrix_report.json", report)
    atomic_write_json(latest / "p30_final_activation_readiness_go_no_go_matrix.json", report["go_no_go_matrix"])
    atomic_write_json(latest / "p30_final_activation_readiness_go_no_go_matrix_negative_fixture_results.json", negative_results)
    summary = {
        "status": report["status"],
        "p30_final_activation_readiness_go_no_go_matrix_sha256": report["p30_final_activation_readiness_go_no_go_matrix_sha256"],
        "operator_decision_matrix_generated_review_only": True,
        "operator_decision_matrix_is_runtime_authority": False,
        "operator_final_activation_decision": report["operator_final_activation_decision"],
        "final_activation_go_review_only": report["final_activation_go_review_only"],
        "final_activation_go_runtime_authority": False,
        "final_activation_execution_allowed_by_this_matrix": False,
        "required_phase_count": report["required_phase_count"],
        "present_phase_count": report["present_phase_count"],
        "go_review_only_phase_count": report["go_review_only_phase_count"],
        "waiting_phase_count": report["waiting_phase_count"],
        "no_go_phase_count": report["no_go_phase_count"],
        "waiting_phases": report["waiting_phases"],
        "no_go_phases": report["no_go_phases"],
        "block_reasons": report["block_reasons"],
        "waiting_reasons": report["waiting_reasons"],
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "runtime_enablement_performed": False,
        "operator_runtime_activation_performed": False,
        "actual_live_order_submitted": False,
        "actual_testnet_order_submitted": False,
        "live_order_endpoint_called": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    summary["p30_final_activation_readiness_go_no_go_matrix_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p30_final_activation_readiness_go_no_go_matrix_summary.json", summary)
    registry_record = append_registry_record(
        registry_path(cfg, P30_FINAL_ACTIVATION_READINESS_GO_NO_GO_MATRIX_REGISTRY_NAME),
        report,
        registry_name=P30_FINAL_ACTIVATION_READINESS_GO_NO_GO_MATRIX_REGISTRY_NAME,
        id_field="p30_final_activation_readiness_go_no_go_matrix_registry_id",
        hash_field="p30_final_activation_readiness_go_no_go_matrix_registry_sha256",
        id_prefix="p30_final_activation_readiness_go_no_go_matrix",
    )
    atomic_write_json(latest / "p30_final_activation_readiness_go_no_go_matrix_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_final_activation_readiness_go_no_go_matrix()
    print(result["status"])
    print(result["p30_final_activation_readiness_go_no_go_matrix_sha256"])
