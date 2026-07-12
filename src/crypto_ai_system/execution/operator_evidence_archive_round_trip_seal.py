from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.operator_evidence_archive_index_audit_trail import (
    STATUS_BLOCKED_FAIL_CLOSED as P41_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY as P41_STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P41_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.execution.operator_evidence_archive_intake_validator import (
    STATUS_BLOCKED_FAIL_CLOSED as P42_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY as P42_STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P42_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEAL_VERSION = "p43_operator_evidence_archive_round_trip_seal_v1"
P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEAL_REGISTRY_NAME = "p43_operator_evidence_archive_round_trip_seal_registry"

STATUS_SEALED_REVIEW_ONLY = "P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEALED_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEAL_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEAL_BLOCKED_FAIL_CLOSED"

_REQUIRED_P43_INPUT_FILES = (
    "p41_operator_evidence_archive_index_report.json",
    "p41_operator_evidence_archive_index_summary.json",
    "p41_operator_evidence_archive_index.json",
    "p41_operator_evidence_audit_trail_chain.json",
    "p42_operator_evidence_archive_intake_validator_report.json",
    "p42_operator_evidence_archive_intake_validator_summary.json",
    "p42_operator_evidence_archive_intake_validation_results.json",
    "p42_operator_evidence_archive_hash_recheck_chain.json",
)

_EXECUTION_FIELDS_FOR_P43 = {
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
    "secret_file_accessed",
    "secret_file_created",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "auto_promotion_allowed",
    "runtime_authority",
    "runtime_authority_claimed",
    "archive_index_executes_runtime",
    "archive_index_enables_scheduler",
    "archive_index_allows_order_submission",
    "archive_index_calls_endpoint",
    "archive_index_reads_secret_value",
    "archive_index_grants_runtime_authority",
    "archive_intake_executes_runtime",
    "archive_intake_enables_scheduler",
    "archive_intake_allows_order_submission",
    "archive_intake_calls_endpoint",
    "archive_intake_reads_secret_value",
    "archive_intake_grants_runtime_authority",
    "round_trip_seal_executes_runtime",
    "round_trip_seal_enables_scheduler",
    "round_trip_seal_allows_order_submission",
    "round_trip_seal_calls_endpoint",
    "round_trip_seal_reads_secret_value",
    "round_trip_seal_grants_runtime_authority",
}
_SECRET_VALUE_PATTERNS = (
    "BINANCE_API_SECRET=",
    "BINANCE_API_KEY=",
    "PRIVATE_KEY=",
    "API_SECRET=",
    "API_KEY=",
    "api_secret_value:",
    "api_key_value:",
    "secret_value:",
    "BEGIN PRIVATE KEY",
    "passphrase=",
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


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _read_latest_json(cfg: AppConfig, filename: str, default: Any) -> Any:
    return read_json(_latest_dir(cfg) / filename, default=default)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _scan_truthy_execution_fields(payloads: Sequence[tuple[str, Any]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, source: str, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                next_path = f"{path}.{key}"
                if key in _EXECUTION_FIELDS_FOR_P43 and _bool(value):
                    hits.append({"source": source, "path": next_path, "field": str(key), "value": True})
                walk(value, source, next_path)
        elif isinstance(payload, list):
            for idx, item in enumerate(payload):
                walk(item, source, f"{path}[{idx}]")

    for source, payload in payloads:
        walk(payload, source)
    return hits


def _scan_secret_value_patterns(payloads: Sequence[tuple[str, Any]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, source: str, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                walk(value, source, f"{path}.{key}")
        elif isinstance(payload, list):
            for idx, item in enumerate(payload):
                walk(item, source, f"{path}[{idx}]")
        elif isinstance(payload, str):
            lower_value = payload.lower()
            for pattern in _SECRET_VALUE_PATTERNS:
                if pattern.lower() in lower_value:
                    hits.append({"source": source, "path": path, "pattern": pattern})

    for source, payload in payloads:
        walk(payload, source)
    return hits


def _build_seal_chain(*, p41_report: Mapping[str, Any], p41_summary: Mapping[str, Any], p41_archive_index: Sequence[Mapping[str, Any]], p41_audit_trail_chain: Mapping[str, Any], p42_report: Mapping[str, Any], p42_summary: Mapping[str, Any], p42_validation_results: Mapping[str, Any], p42_hash_recheck_chain: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "p41_status": p41_report.get("status") or p41_summary.get("status"),
        "p42_status": p42_report.get("status") or p42_summary.get("status"),
        "p41_archive_index_hash": p41_report.get("archive_index_hash") or p41_summary.get("archive_index_hash"),
        "observed_p41_archive_index_hash": sha256_json([dict(item) for item in p41_archive_index]),
        "p41_audit_trail_chain_hash": p41_report.get("audit_trail_chain_hash") or p41_summary.get("audit_trail_chain_hash"),
        "observed_p41_audit_trail_chain_hash": sha256_json(dict(p41_audit_trail_chain)),
        "p42_hash_recheck_chain_hash": p42_report.get("hash_recheck_chain_hash") or p42_summary.get("hash_recheck_chain_hash"),
        "observed_p42_hash_recheck_chain_hash": sha256_json(dict(p42_hash_recheck_chain)),
        "p42_intake_issue_count": p42_report.get("intake_issue_count"),
        "p42_validation_results_hash": sha256_json(dict(p42_validation_results)),
        "review_only": True,
        "runtime_authority": False,
    }
    return {
        "chain_id": stable_id("p43_operator_evidence_archive_round_trip_seal_chain", payload),
        **payload,
        "seal_hash": sha256_json(payload),
    }


def _build_external_review_packet(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "packet_type": "operator_evidence_archive_round_trip_external_review_packet",
        "version": P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEAL_VERSION,
        "status": report.get("status"),
        "created_at_utc": report.get("created_at_utc"),
        "review_only": True,
        "runtime_authority": False,
        "decision": "REVIEW_ONLY_EXTERNAL_REVIEW_PACKET_NOT_RUNTIME_AUTHORITY",
        "p41_status": report.get("p41_status"),
        "p42_status": report.get("p42_status"),
        "seal_hash": report.get("seal_hash"),
        "seal_chain_hash": report.get("seal_chain_hash"),
        "issue_count": report.get("seal_issue_count"),
        "issue_codes": report.get("seal_issue_codes"),
        "safe_state": {
            "runtime_scheduler_enabled": False,
            "live_scaled_execution_enabled": False,
            "live_order_submission_allowed": False,
            "order_endpoint_called": False,
            "secret_value_accessed": False,
        },
        "input_hashes": {
            "p41_archive_index_hash": report.get("p41_archive_index_hash"),
            "p41_audit_trail_chain_hash": report.get("p41_audit_trail_chain_hash"),
            "p42_hash_recheck_chain_hash": report.get("p42_hash_recheck_chain_hash"),
        },
        "operator_note": "This sealed review packet may be shared for review. It does not enable runtime, scheduler, order submission, endpoint calls, secret access, settings mutation, or auto-promotion.",
    }


def _build_checklist(report: Mapping[str, Any]) -> str:
    checks = [
        ("P41 archive report exists", bool(report.get("p41_report_present"))),
        ("P41 archive index exists", bool(report.get("p41_archive_index_present"))),
        ("P41 audit trail chain exists", bool(report.get("p41_audit_trail_chain_present"))),
        ("P42 intake report exists", bool(report.get("p42_report_present"))),
        ("P42 validation results exist", bool(report.get("p42_validation_results_present"))),
        ("P42 hash recheck chain exists", bool(report.get("p42_hash_recheck_chain_present"))),
        ("P41 status generated review-only", report.get("p41_status") == P41_STATUS_GENERATED_REVIEW_ONLY),
        ("P42 status valid review-only", report.get("p42_status") == P42_STATUS_VALID_REVIEW_ONLY),
        ("P42 reported no intake issues", report.get("p42_intake_issue_count") == 0),
        ("Seal hash generated", bool(report.get("seal_hash"))),
        ("Seal chain hash generated", bool(report.get("seal_chain_hash"))),
        ("Runtime remains disabled", not bool(report.get("runtime_flag_truthy"))),
        ("Scheduler remains disabled", not bool(report.get("scheduler_enabled"))),
        ("No endpoint evidence", not bool(report.get("endpoint_called"))),
        ("No secret value patterns", not bool(report.get("secret_detected"))),
        ("Authority remains review-only", not bool(report.get("runtime_authority_claimed"))),
    ]
    lines = ["# P43 Evidence Archive Round-trip Seal Checklist", ""]
    for label, passed in checks:
        mark = "x" if passed else " "
        lines.append(f"- [{mark}] {label}")
    return "\n".join(lines).rstrip() + "\n"


def _build_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# P43 Operator Evidence Archive Round-trip Seal / External Review Packet",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "> This sealed packet is review-only. It binds P41 archive evidence and P42 intake hash recheck results for external review, but it does not enable runtime, scheduler, order submission, endpoint calls, secret access, settings mutation, or auto-promotion.",
        "",
        "## Summary",
        "",
        f"- Seal issue count: `{report.get('seal_issue_count')}`",
        f"- P41 status: `{report.get('p41_status')}`",
        f"- P42 status: `{report.get('p42_status')}`",
        f"- Seal hash: `{report.get('seal_hash')}`",
        f"- Seal chain hash: `{report.get('seal_chain_hash')}`",
        f"- P42 intake issue count: `{report.get('p42_intake_issue_count')}`",
        "",
        "## Issue Codes",
        "",
    ]
    codes = report.get("seal_issue_codes", [])
    if not codes:
        lines.append("- None")
    else:
        for code in codes:
            lines.append(f"- `{code}`")
    lines.extend([
        "",
        "## Required Safe State",
        "",
        "- Runtime: DISABLED",
        "- Scheduler: DISABLED",
        "- Orders: DISABLED",
        "- Authority: REVIEW_ONLY",
        "- Secret values: not present",
        "- Endpoint evidence: not present",
    ])
    return "\n".join(lines).rstrip() + "\n"


def build_operator_evidence_archive_round_trip_seal_report(
    *,
    root: str | Path | None = None,
    p41_report: Mapping[str, Any] | None = None,
    p41_summary: Mapping[str, Any] | None = None,
    p41_archive_index: Sequence[Mapping[str, Any]] | None = None,
    p41_audit_trail_chain: Mapping[str, Any] | None = None,
    p42_report: Mapping[str, Any] | None = None,
    p42_summary: Mapping[str, Any] | None = None,
    p42_validation_results: Mapping[str, Any] | None = None,
    p42_hash_recheck_chain: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] = (),
) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    latest = _latest_dir(cfg)

    if p41_report is None:
        loaded = _read_latest_json(cfg, "p41_operator_evidence_archive_index_report.json", default={})
        p41_report = loaded if isinstance(loaded, Mapping) else {}
    if p41_summary is None:
        loaded = _read_latest_json(cfg, "p41_operator_evidence_archive_index_summary.json", default={})
        p41_summary = loaded if isinstance(loaded, Mapping) else {}
    if p41_archive_index is None:
        loaded = _read_latest_json(cfg, "p41_operator_evidence_archive_index.json", default=[])
        p41_archive_index = loaded if isinstance(loaded, list) else []
    if p41_audit_trail_chain is None:
        loaded = _read_latest_json(cfg, "p41_operator_evidence_audit_trail_chain.json", default={})
        p41_audit_trail_chain = loaded if isinstance(loaded, Mapping) else {}
    if p42_report is None:
        loaded = _read_latest_json(cfg, "p42_operator_evidence_archive_intake_validator_report.json", default={})
        p42_report = loaded if isinstance(loaded, Mapping) else {}
    if p42_summary is None:
        loaded = _read_latest_json(cfg, "p42_operator_evidence_archive_intake_validator_summary.json", default={})
        p42_summary = loaded if isinstance(loaded, Mapping) else {}
    if p42_validation_results is None:
        loaded = _read_latest_json(cfg, "p42_operator_evidence_archive_intake_validation_results.json", default={})
        p42_validation_results = loaded if isinstance(loaded, Mapping) else {}
    if p42_hash_recheck_chain is None:
        loaded = _read_latest_json(cfg, "p42_operator_evidence_archive_hash_recheck_chain.json", default={})
        p42_hash_recheck_chain = loaded if isinstance(loaded, Mapping) else {}

    p41_report = dict(p41_report)
    p41_summary = dict(p41_summary)
    p41_archive_index = [dict(item) for item in p41_archive_index]
    p41_audit_trail_chain = dict(p41_audit_trail_chain)
    p42_report = dict(p42_report)
    p42_summary = dict(p42_summary)
    p42_validation_results = dict(p42_validation_results)
    p42_hash_recheck_chain = dict(p42_hash_recheck_chain)

    scan_payloads: list[tuple[str, Any]] = [
        ("p41_report", p41_report),
        ("p41_summary", p41_summary),
        ("p41_archive_index", p41_archive_index),
        ("p41_audit_trail_chain", p41_audit_trail_chain),
        ("p42_report", p42_report),
        ("p42_summary", p42_summary),
        ("p42_validation_results", p42_validation_results),
        ("p42_hash_recheck_chain", p42_hash_recheck_chain),
        *list(extra_payloads_for_scan),
    ]
    unsafe_hits = _scan_truthy_execution_fields(scan_payloads)
    secret_hits = _scan_secret_value_patterns(scan_payloads)
    endpoint_hits = [hit for hit in unsafe_hits if "endpoint" in str(hit.get("field", "")) or hit.get("field") == "http_request_sent"]
    scheduler_hits = [hit for hit in unsafe_hits if "scheduler" in str(hit.get("field", ""))]
    authority_hits = [hit for hit in unsafe_hits if "authority" in str(hit.get("field", ""))]

    p41_status = p41_report.get("status") or p41_summary.get("status")
    p42_status = p42_report.get("status") or p42_summary.get("status")
    missing_input_files = [filename for filename in _REQUIRED_P43_INPUT_FILES if not (latest / filename).exists()]

    seal_chain = _build_seal_chain(
        p41_report=p41_report,
        p41_summary=p41_summary,
        p41_archive_index=p41_archive_index,
        p41_audit_trail_chain=p41_audit_trail_chain,
        p42_report=p42_report,
        p42_summary=p42_summary,
        p42_validation_results=p42_validation_results,
        p42_hash_recheck_chain=p42_hash_recheck_chain,
    )
    seal_chain_hash = sha256_json(seal_chain)

    issues: list[dict[str, Any]] = []

    def add_issue(code: str, severity: str, message: str, evidence: Any = None) -> None:
        issue = {"code": code, "severity": severity, "message": message}
        if evidence is not None:
            issue["evidence"] = evidence
        issues.append(issue)

    if not p41_report:
        add_issue("missing_p41_report", "waiting", "P41 archive report is missing.")
    if not p41_summary:
        add_issue("missing_p41_summary", "waiting", "P41 archive summary is missing.")
    if not p41_archive_index:
        add_issue("missing_p41_archive_index", "waiting", "P41 archive index is missing or empty.")
    if not p41_audit_trail_chain:
        add_issue("missing_p41_audit_trail_chain", "waiting", "P41 audit trail chain is missing.")
    if not p42_report:
        add_issue("missing_p42_report", "waiting", "P42 intake report is missing.")
    if not p42_validation_results:
        add_issue("missing_p42_validation_results", "waiting", "P42 validation results are missing.")
    if not p42_hash_recheck_chain:
        add_issue("missing_p42_hash_recheck_chain", "waiting", "P42 hash recheck chain is missing.")
    if missing_input_files:
        add_issue("missing_round_trip_input_files", "waiting", "One or more required P43 input artifacts are missing.", missing_input_files)

    if p41_status == P41_STATUS_BLOCKED_FAIL_CLOSED:
        add_issue("p41_blocked", "blocked", "P41 archive index is blocked fail-closed.")
    elif p41_status == P41_STATUS_WAITING_REVIEW_ONLY:
        add_issue("p41_waiting", "waiting", "P41 archive index is waiting review-only.")
    elif p41_report and p41_status != P41_STATUS_GENERATED_REVIEW_ONLY:
        add_issue("p41_status_not_generated_review_only", "blocked", "P41 archive index is not generated review-only.", p41_status)

    if p42_status == P42_STATUS_BLOCKED_FAIL_CLOSED:
        add_issue("p42_blocked", "blocked", "P42 archive intake is blocked fail-closed.")
    elif p42_status == P42_STATUS_WAITING_REVIEW_ONLY:
        add_issue("p42_waiting", "waiting", "P42 archive intake is waiting review-only.")
    elif p42_report and p42_status != P42_STATUS_VALID_REVIEW_ONLY:
        add_issue("p42_status_not_valid_review_only", "blocked", "P42 archive intake is not valid review-only.", p42_status)

    if p42_report.get("intake_issue_count", 0):
        add_issue("p42_reported_issues", "blocked", "P42 archive intake reported issues.", p42_report.get("intake_issue_codes", []))
    if p42_report and _bool(p42_report.get("blocked")):
        add_issue("p42_blocked_flag", "blocked", "P42 blocked flag is truthy.")

    # Cross-check the hash recheck chain against P41/P42 payloads.
    observed_archive_index_hash = sha256_json(p41_archive_index)
    observed_audit_trail_chain_hash = sha256_json(p41_audit_trail_chain)
    observed_hash_recheck_chain_hash = sha256_json(p42_hash_recheck_chain)
    if p42_hash_recheck_chain:
        if p42_hash_recheck_chain.get("observed_archive_index_hash") != observed_archive_index_hash:
            add_issue("p42_chain_archive_index_hash_mismatch", "blocked", "P42 hash recheck chain does not match observed P41 archive index hash.", {"chain": p42_hash_recheck_chain.get("observed_archive_index_hash"), "observed": observed_archive_index_hash})
        if p42_hash_recheck_chain.get("observed_audit_trail_chain_hash") != observed_audit_trail_chain_hash:
            add_issue("p42_chain_audit_trail_hash_mismatch", "blocked", "P42 hash recheck chain does not match observed P41 audit trail chain hash.", {"chain": p42_hash_recheck_chain.get("observed_audit_trail_chain_hash"), "observed": observed_audit_trail_chain_hash})
    reported_p42_chain_hash = p42_report.get("hash_recheck_chain_hash") or p42_summary.get("hash_recheck_chain_hash")
    if reported_p42_chain_hash and reported_p42_chain_hash != observed_hash_recheck_chain_hash:
        add_issue("p42_hash_recheck_chain_hash_mismatch", "blocked", "P42 reported hash recheck chain hash does not match observed chain hash.", {"reported": reported_p42_chain_hash, "observed": observed_hash_recheck_chain_hash})

    if unsafe_hits:
        add_issue("runtime_flag_truthy", "blocked", "Truthy runtime/order/scheduler flag detected in P43 seal payloads.", unsafe_hits)
    if scheduler_hits:
        add_issue("scheduler_enabled", "blocked", "Scheduler truthy flag detected in P43 seal payloads.", scheduler_hits)
    if endpoint_hits:
        add_issue("endpoint_called", "blocked", "Endpoint-call truthy flag detected in P43 seal payloads.", endpoint_hits)
    if authority_hits or _bool(seal_chain.get("runtime_authority")):
        add_issue("runtime_authority_claimed", "blocked", "Runtime authority truthy flag detected in P43 seal payloads.", authority_hits)
    if secret_hits:
        add_issue("secret_detected", "blocked", "Secret value pattern detected in P43 seal payloads.", secret_hits)

    blocked = any(issue["severity"] == "blocked" for issue in issues)
    waiting = bool(issues) and not blocked
    status = STATUS_SEALED_REVIEW_ONLY
    if waiting:
        status = STATUS_WAITING_REVIEW_ONLY
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED

    report: dict[str, Any] = {
        "version": P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEAL_VERSION,
        "status": status,
        "waiting": waiting,
        "blocked": blocked,
        "created_at_utc": utc_now_canonical(),
        "p41_status": p41_status,
        "p42_status": p42_status,
        "p41_report_present": bool(p41_report),
        "p41_summary_present": bool(p41_summary),
        "p41_archive_index_present": bool(p41_archive_index),
        "p41_audit_trail_chain_present": bool(p41_audit_trail_chain),
        "p42_report_present": bool(p42_report),
        "p42_summary_present": bool(p42_summary),
        "p42_validation_results_present": bool(p42_validation_results),
        "p42_hash_recheck_chain_present": bool(p42_hash_recheck_chain),
        "missing_input_file_count": len(missing_input_files),
        "missing_input_files": missing_input_files,
        "p41_archive_index_hash": p41_report.get("archive_index_hash") or p41_summary.get("archive_index_hash"),
        "p41_audit_trail_chain_hash": p41_report.get("audit_trail_chain_hash") or p41_summary.get("audit_trail_chain_hash"),
        "p42_hash_recheck_chain_hash": reported_p42_chain_hash,
        "observed_p42_hash_recheck_chain_hash": observed_hash_recheck_chain_hash,
        "p42_intake_issue_count": p42_report.get("intake_issue_count"),
        "seal_chain": seal_chain,
        "seal_hash": seal_chain.get("seal_hash"),
        "seal_chain_hash": seal_chain_hash,
        "seal_issue_count": len(issues),
        "seal_issue_codes": [issue["code"] for issue in issues],
        "seal_issues": issues,
        "runtime_flag_truthy": bool(unsafe_hits),
        "scheduler_enabled": bool(scheduler_hits),
        "endpoint_called": bool(endpoint_hits),
        "secret_detected": bool(secret_hits),
        "runtime_authority_claimed": bool(authority_hits),
        "round_trip_seal_executes_runtime": False,
        "round_trip_seal_enables_scheduler": False,
        "round_trip_seal_allows_order_submission": False,
        "round_trip_seal_calls_endpoint": False,
        "round_trip_seal_reads_secret_value": False,
        "round_trip_seal_grants_runtime_authority": False,
        "runtime_scheduler_enabled": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "review_only": True,
        "runtime_authority": False,
        "execution_flags": default_execution_flag_state(),
    }
    report["external_review_packet"] = _build_external_review_packet(report)
    return report


def build_p43_negative_fixture_results(root: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    p41_report = _read_latest_json(cfg, "p41_operator_evidence_archive_index_report.json", default={})
    p41_summary = _read_latest_json(cfg, "p41_operator_evidence_archive_index_summary.json", default={})
    p41_index = _read_latest_json(cfg, "p41_operator_evidence_archive_index.json", default=[])
    p41_chain = _read_latest_json(cfg, "p41_operator_evidence_audit_trail_chain.json", default={})
    p42_report = _read_latest_json(cfg, "p42_operator_evidence_archive_intake_validator_report.json", default={})
    p42_summary = _read_latest_json(cfg, "p42_operator_evidence_archive_intake_validator_summary.json", default={})
    p42_validation = _read_latest_json(cfg, "p42_operator_evidence_archive_intake_validation_results.json", default={})
    p42_hash_chain = _read_latest_json(cfg, "p42_operator_evidence_archive_hash_recheck_chain.json", default={})
    if not isinstance(p41_report, Mapping):
        p41_report = {}
    if not isinstance(p41_summary, Mapping):
        p41_summary = {}
    if not isinstance(p41_index, list):
        p41_index = []
    if not isinstance(p41_chain, Mapping):
        p41_chain = {}
    if not isinstance(p42_report, Mapping):
        p42_report = {}
    if not isinstance(p42_summary, Mapping):
        p42_summary = {}
    if not isinstance(p42_validation, Mapping):
        p42_validation = {}
    if not isinstance(p42_hash_chain, Mapping):
        p42_hash_chain = {}

    fixtures: dict[str, dict[str, Any]] = {
        "missing_p41_report": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report={}, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain=p42_hash_chain),
        "missing_p42_report": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report={}, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain=p42_hash_chain),
        "missing_p42_validation_results": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results={}, p42_hash_recheck_chain=p42_hash_chain),
        "missing_p42_hash_recheck_chain": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain={}),
        "p41_blocked": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report={**dict(p41_report), "status": P41_STATUS_BLOCKED_FAIL_CLOSED, "blocked": True}, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain=p42_hash_chain),
        "p42_blocked": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report={**dict(p42_report), "status": P42_STATUS_BLOCKED_FAIL_CLOSED, "blocked": True}, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain=p42_hash_chain),
        "p42_waiting": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report={**dict(p42_report), "status": P42_STATUS_WAITING_REVIEW_ONLY, "waiting": True}, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain=p42_hash_chain),
        "p42_reported_issues": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report={**dict(p42_report), "intake_issue_count": 1, "intake_issue_codes": ["fixture_issue"]}, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain=p42_hash_chain),
        "p42_hash_recheck_chain_hash_mismatch": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report={**dict(p42_report), "hash_recheck_chain_hash": "bad_hash"}, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain=p42_hash_chain),
        "p42_chain_archive_index_hash_mismatch": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain={**dict(p42_hash_chain), "observed_archive_index_hash": "bad_hash"}),
        "secret_detected": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain=p42_hash_chain, extra_payloads_for_scan=[("bad_secret", "BINANCE_API_SECRET=leak")]),
        "runtime_flag_truthy": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain=p42_hash_chain, extra_payloads_for_scan=[("bad_runtime", {"live_scaled_execution_enabled": True})]),
        "scheduler_enabled": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain=p42_hash_chain, extra_payloads_for_scan=[("bad_scheduler", {"runtime_scheduler_enabled": True})]),
        "endpoint_called": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain=p42_hash_chain, extra_payloads_for_scan=[("bad_endpoint", {"order_endpoint_called": True})]),
        "runtime_authority_claimed": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain={**dict(p41_chain), "runtime_authority": True}, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain=p42_hash_chain),
        "round_trip_seal_executes_runtime": build_operator_evidence_archive_round_trip_seal_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=p42_validation, p42_hash_recheck_chain=p42_hash_chain, extra_payloads_for_scan=[("bad_seal", {"round_trip_seal_executes_runtime": True})]),
    }
    fixture_summary = {
        name: {
            "status": result["status"],
            "waiting": result["waiting"],
            "blocked": result["blocked"],
            "seal_issue_codes": result["seal_issue_codes"],
            "round_trip_seal_executes_runtime": result["round_trip_seal_executes_runtime"],
            "runtime_scheduler_enabled": result["runtime_scheduler_enabled"],
            "order_endpoint_called": result["order_endpoint_called"],
            "secret_value_accessed": result["secret_value_accessed"],
        }
        for name, result in fixtures.items()
    }
    all_fail_closed = all(item["waiting"] or item["blocked"] for item in fixture_summary.values())
    return {
        "status": "P43_NEGATIVE_FIXTURES_RECORDED",
        "created_at_utc": utc_now_canonical(),
        "fixture_count": len(fixture_summary),
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all_fail_closed,
        "fixture_results": fixture_summary,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def persist_operator_evidence_archive_round_trip_seal(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p43_operator_evidence_archive_round_trip_seal")
    report = build_operator_evidence_archive_round_trip_seal_report(root=cfg.root)
    checklist = _build_checklist(report)
    markdown = _build_markdown(report)
    negative = build_p43_negative_fixture_results(root=cfg.root)

    report_path = latest / "p43_operator_evidence_archive_round_trip_seal_report.json"
    summary_path = latest / "p43_operator_evidence_archive_round_trip_seal_summary.json"
    packet_path = latest / "p43_operator_evidence_archive_external_review_packet.json"
    chain_path = latest / "p43_operator_evidence_archive_round_trip_seal_chain.json"
    checklist_path = latest / "p43_operator_evidence_archive_round_trip_seal_checklist.md"
    markdown_path = latest / "p43_operator_evidence_archive_external_review_packet.md"
    negative_path = latest / "p43_operator_evidence_archive_round_trip_seal_negative_fixture_results.json"
    registry_record_path = latest / "p43_operator_evidence_archive_round_trip_seal_registry_record.json"

    output_paths = {
        "report": str(report_path),
        "summary": str(summary_path),
        "external_review_packet": str(packet_path),
        "seal_chain": str(chain_path),
        "checklist": str(checklist_path),
        "markdown": str(markdown_path),
    }
    report["output_paths"] = output_paths
    external_review_packet = _build_external_review_packet(report)
    report["external_review_packet"] = external_review_packet
    summary = {
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "seal_issue_count": report["seal_issue_count"],
        "seal_issue_codes": report["seal_issue_codes"],
        "p41_status": report["p41_status"],
        "p42_status": report["p42_status"],
        "seal_hash": report["seal_hash"],
        "seal_chain_hash": report["seal_chain_hash"],
        "p42_intake_issue_count": report["p42_intake_issue_count"],
        "runtime_flag_truthy": report["runtime_flag_truthy"],
        "scheduler_enabled": report["scheduler_enabled"],
        "endpoint_called": report["endpoint_called"],
        "secret_detected": report["secret_detected"],
        "runtime_scheduler_enabled": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "output_paths": output_paths,
    }
    registry_record = {
        "id": stable_id("p43_operator_evidence_archive_round_trip_seal", {"seal_hash": report.get("seal_hash"), "seal_chain_hash": report.get("seal_chain_hash"), "status": report.get("status")}),
        "version": P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEAL_VERSION,
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "created_at_utc": report["created_at_utc"],
        "seal_hash": report["seal_hash"],
        "seal_chain_hash": report["seal_chain_hash"],
        "seal_issue_count": report["seal_issue_count"],
        "runtime_authority": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }

    atomic_write_json(report_path, report)
    atomic_write_json(summary_path, summary)
    atomic_write_json(packet_path, external_review_packet)
    atomic_write_json(chain_path, report["seal_chain"])
    _atomic_write_text(checklist_path, checklist)
    _atomic_write_text(markdown_path, markdown)
    atomic_write_json(negative_path, negative)
    atomic_write_json(registry_record_path, registry_record)

    atomic_write_json(storage / report_path.name, report)
    atomic_write_json(storage / summary_path.name, summary)
    atomic_write_json(storage / packet_path.name, external_review_packet)
    atomic_write_json(storage / chain_path.name, report["seal_chain"])
    _atomic_write_text(storage / checklist_path.name, checklist)
    _atomic_write_text(storage / markdown_path.name, markdown)
    atomic_write_json(storage / negative_path.name, negative)
    atomic_write_json(storage / registry_record_path.name, registry_record)

    append_registry_record(
        registry_path(cfg, P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEAL_REGISTRY_NAME),
        registry_record,
        registry_name=P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEAL_REGISTRY_NAME,
    )
    return report
