from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.operator_evidence_archive_index_audit_trail import (
    STATUS_BLOCKED_FAIL_CLOSED as P41_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY as P41_STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P41_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P42_OPERATOR_EVIDENCE_ARCHIVE_INTAKE_VALIDATOR_VERSION = "p42_operator_evidence_archive_intake_validator_v1"
P42_OPERATOR_EVIDENCE_ARCHIVE_INTAKE_VALIDATOR_REGISTRY_NAME = "p42_operator_evidence_archive_intake_validator_registry"

STATUS_VALID_REVIEW_ONLY = "P42_OPERATOR_EVIDENCE_ARCHIVE_INTAKE_VALIDATOR_VALID_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P42_OPERATOR_EVIDENCE_ARCHIVE_INTAKE_VALIDATOR_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P42_OPERATOR_EVIDENCE_ARCHIVE_INTAKE_VALIDATOR_BLOCKED_FAIL_CLOSED"

_REQUIRED_P41_FILES = (
    "p41_operator_evidence_archive_index_report.json",
    "p41_operator_evidence_archive_index_summary.json",
    "p41_operator_evidence_archive_index.json",
    "p41_operator_evidence_archive_index.csv",
    "p41_operator_evidence_audit_trail_chain.json",
    "p41_operator_evidence_archive_checklist.md",
    "p41_operator_evidence_audit_trail.md",
    "p41_operator_evidence_archive_index_negative_fixture_results.json",
    "p41_operator_evidence_archive_index_registry_record.json",
)
_EXECUTION_FIELDS_FOR_P42 = {
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


def _sha256_bytes(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan_truthy_execution_fields(payloads: Sequence[tuple[str, Any]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, source: str, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                next_path = f"{path}.{key}"
                if key in _EXECUTION_FIELDS_FOR_P42 and _bool(value):
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


def _validate_archive_entry_hashes(latest: Path, archive_index: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    for item in archive_index:
        filename = str(item.get("filename", ""))
        if not filename:
            mismatches.append({"filename": filename, "reason": "missing_filename"})
            continue
        expected_exists = _bool(item.get("exists"))
        path = latest / filename
        actual_exists = path.exists()
        if expected_exists != actual_exists:
            mismatches.append({"filename": filename, "reason": "exists_mismatch", "expected_exists": expected_exists, "actual_exists": actual_exists})
            continue
        if expected_exists and actual_exists:
            expected_sha = item.get("sha256")
            actual_sha = _sha256_bytes(path)
            if expected_sha != actual_sha:
                mismatches.append({"filename": filename, "reason": "sha256_mismatch", "expected_sha256": expected_sha, "actual_sha256": actual_sha})
    return mismatches


def _build_checklist(report: Mapping[str, Any]) -> str:
    checks = [
        ("P41 report exists", bool(report.get("p41_report_present"))),
        ("P41 summary exists", bool(report.get("p41_summary_present"))),
        ("P41 archive index exists", bool(report.get("p41_archive_index_present"))),
        ("P41 audit trail chain exists", bool(report.get("p41_audit_trail_chain_present"))),
        ("P41 status generated review-only", report.get("p41_status") == P41_STATUS_GENERATED_REVIEW_ONLY),
        ("Archive index hash matches", not bool(report.get("archive_index_hash_mismatch"))),
        ("Audit trail chain hash matches", not bool(report.get("audit_trail_chain_hash_mismatch"))),
        ("Archive entry file hashes match", report.get("archive_entry_hash_mismatch_count") == 0),
        ("No required P41 artifacts missing", report.get("missing_p41_artifact_count") == 0),
        ("Runtime remains disabled", not bool(report.get("runtime_flag_truthy"))),
        ("Scheduler remains disabled", not bool(report.get("scheduler_enabled"))),
        ("No endpoint evidence", not bool(report.get("endpoint_called"))),
        ("No secret value patterns", not bool(report.get("secret_detected"))),
        ("Authority remains review-only", not bool(report.get("runtime_authority_claimed"))),
    ]
    lines = ["# P42 Evidence Archive Intake Checklist", ""]
    for label, passed in checks:
        mark = "x" if passed else " "
        lines.append(f"- [{mark}] {label}")
    return "\n".join(lines).rstrip() + "\n"


def _build_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# P42 Evidence Archive Intake Validator / Hash Recheck Pack",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "> This validator is review-only. It verifies P41 archive evidence hashes and safety state, but it does not enable runtime, scheduler, order submission, endpoint calls, secret access, settings mutation, or auto-promotion.",
        "",
        "## Summary",
        "",
        f"- Intake issue count: `{report.get('intake_issue_count')}`",
        f"- P41 status: `{report.get('p41_status')}`",
        f"- Archive index hash expected: `{report.get('expected_archive_index_hash')}`",
        f"- Archive index hash observed: `{report.get('observed_archive_index_hash')}`",
        f"- Audit trail chain hash expected: `{report.get('expected_audit_trail_chain_hash')}`",
        f"- Audit trail chain hash observed: `{report.get('observed_audit_trail_chain_hash')}`",
        f"- Archive entry hash mismatch count: `{report.get('archive_entry_hash_mismatch_count')}`",
        f"- Missing P41 artifact count: `{report.get('missing_p41_artifact_count')}`",
        "",
        "## Issue Codes",
        "",
    ]
    codes = report.get("intake_issue_codes", [])
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


def build_operator_evidence_archive_intake_validator_report(
    *,
    root: str | Path | None = None,
    p41_report: Mapping[str, Any] | None = None,
    p41_summary: Mapping[str, Any] | None = None,
    p41_archive_index: Sequence[Mapping[str, Any]] | None = None,
    p41_audit_trail_chain: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] = (),
) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    latest = _latest_dir(cfg)

    if p41_report is None:
        loaded_report = _read_latest_json(cfg, "p41_operator_evidence_archive_index_report.json", default={})
        p41_report = loaded_report if isinstance(loaded_report, Mapping) else {}
    if p41_summary is None:
        loaded_summary = _read_latest_json(cfg, "p41_operator_evidence_archive_index_summary.json", default={})
        p41_summary = loaded_summary if isinstance(loaded_summary, Mapping) else {}
    if p41_archive_index is None:
        loaded_index = _read_latest_json(cfg, "p41_operator_evidence_archive_index.json", default=[])
        p41_archive_index = loaded_index if isinstance(loaded_index, list) else []
    if p41_audit_trail_chain is None:
        loaded_chain = _read_latest_json(cfg, "p41_operator_evidence_audit_trail_chain.json", default={})
        p41_audit_trail_chain = loaded_chain if isinstance(loaded_chain, Mapping) else {}

    p41_report = dict(p41_report)
    p41_summary = dict(p41_summary)
    p41_archive_index = [dict(item) for item in p41_archive_index]
    p41_audit_trail_chain = dict(p41_audit_trail_chain)

    scan_payloads: list[tuple[str, Any]] = [
        ("p41_report", p41_report),
        ("p41_summary", p41_summary),
        ("p41_archive_index", p41_archive_index),
        ("p41_audit_trail_chain", p41_audit_trail_chain),
        *list(extra_payloads_for_scan),
    ]
    unsafe_hits = _scan_truthy_execution_fields(scan_payloads)
    secret_hits = _scan_secret_value_patterns(scan_payloads)
    endpoint_hits = [hit for hit in unsafe_hits if "endpoint" in str(hit.get("field", "")) or hit.get("field") == "http_request_sent"]
    scheduler_hits = [hit for hit in unsafe_hits if "scheduler" in str(hit.get("field", ""))]
    authority_hits = [hit for hit in unsafe_hits if "authority" in str(hit.get("field", ""))]

    observed_archive_index_hash = sha256_json(p41_archive_index)
    observed_audit_trail_chain_hash = sha256_json(p41_audit_trail_chain)
    expected_archive_index_hash = p41_report.get("archive_index_hash") or p41_summary.get("archive_index_hash") or p41_audit_trail_chain.get("archive_index_hash")
    expected_audit_trail_chain_hash = p41_report.get("audit_trail_chain_hash") or p41_summary.get("audit_trail_chain_hash")
    archive_entry_hash_mismatches = _validate_archive_entry_hashes(latest, p41_archive_index) if p41_archive_index else []
    missing_p41_artifacts = [filename for filename in _REQUIRED_P41_FILES if not (latest / filename).exists()]

    issues: list[dict[str, Any]] = []

    def add_issue(code: str, severity: str, message: str, evidence: Any = None) -> None:
        issue = {"code": code, "severity": severity, "message": message}
        if evidence is not None:
            issue["evidence"] = evidence
        issues.append(issue)

    if not p41_report:
        add_issue("missing_p41_report", "waiting", "P41 archive index report is missing.")
    if not p41_summary:
        add_issue("missing_p41_summary", "waiting", "P41 archive index summary is missing.")
    if not p41_archive_index:
        add_issue("missing_p41_archive_index", "waiting", "P41 archive index payload is missing or empty.")
    if not p41_audit_trail_chain:
        add_issue("missing_p41_audit_trail_chain", "waiting", "P41 audit trail chain is missing.")
    if missing_p41_artifacts:
        add_issue("missing_p41_artifacts", "waiting", "Required P41 artifact files are missing.", missing_p41_artifacts)

    p41_status = p41_report.get("status") or p41_summary.get("status")
    if p41_status == P41_STATUS_BLOCKED_FAIL_CLOSED:
        add_issue("p41_blocked", "blocked", "P41 archive index status is blocked fail-closed.")
    elif p41_status == P41_STATUS_WAITING_REVIEW_ONLY:
        add_issue("p41_waiting", "waiting", "P41 archive index status is waiting review-only.")
    elif p41_report and p41_status != P41_STATUS_GENERATED_REVIEW_ONLY:
        add_issue("p41_status_not_generated_review_only", "blocked", "P41 archive index status is not generated review-only.", p41_status)

    if p41_report.get("archive_issue_count", 0):
        add_issue("p41_reported_issues", "blocked", "P41 archive index reported archive issues.", p41_report.get("archive_issue_codes", []))
    if p41_report and _bool(p41_report.get("blocked")):
        add_issue("p41_report_blocked_flag", "blocked", "P41 report blocked flag is truthy.")

    if expected_archive_index_hash and expected_archive_index_hash != observed_archive_index_hash:
        add_issue("archive_index_hash_mismatch", "blocked", "Observed archive index hash does not match P41 reported hash.", {"expected": expected_archive_index_hash, "observed": observed_archive_index_hash})
    if expected_audit_trail_chain_hash and expected_audit_trail_chain_hash != observed_audit_trail_chain_hash:
        add_issue("audit_trail_chain_hash_mismatch", "blocked", "Observed audit trail chain hash does not match P41 reported hash.", {"expected": expected_audit_trail_chain_hash, "observed": observed_audit_trail_chain_hash})
    if p41_audit_trail_chain and p41_audit_trail_chain.get("archive_index_hash") != observed_archive_index_hash:
        add_issue("chain_archive_index_hash_mismatch", "blocked", "P41 audit trail chain archive_index_hash does not match observed archive index hash.", {"chain_archive_index_hash": p41_audit_trail_chain.get("archive_index_hash"), "observed": observed_archive_index_hash})
    if archive_entry_hash_mismatches:
        add_issue("archive_entry_hash_mismatch", "blocked", "One or more archive entry file hashes do not match the current storage/latest artifact bytes.", archive_entry_hash_mismatches)
    if p41_archive_index:
        not_review_only = [item.get("filename") for item in p41_archive_index if not _bool(item.get("review_only", True))]
        runtime_authority_entries = [item.get("filename") for item in p41_archive_index if _bool(item.get("runtime_authority"))]
        if not_review_only:
            add_issue("archive_entry_not_review_only", "blocked", "Archive entry is not marked review-only.", not_review_only)
        if runtime_authority_entries:
            add_issue("archive_entry_runtime_authority", "blocked", "Archive entry claims runtime authority.", runtime_authority_entries)

    if unsafe_hits:
        add_issue("runtime_flag_truthy", "blocked", "Truthy runtime/order/scheduler flag detected in P41 intake payloads.", unsafe_hits)
    if scheduler_hits:
        add_issue("scheduler_enabled", "blocked", "Scheduler truthy flag detected in P41 intake payloads.", scheduler_hits)
    if endpoint_hits:
        add_issue("endpoint_called", "blocked", "Endpoint-call truthy flag detected in P41 intake payloads.", endpoint_hits)
    if authority_hits or _bool(p41_audit_trail_chain.get("runtime_authority")):
        add_issue("runtime_authority_claimed", "blocked", "Runtime authority truthy flag detected in P41 intake payloads.", authority_hits)
    if secret_hits:
        add_issue("secret_detected", "blocked", "Secret value pattern detected in P41 intake payloads.", secret_hits)

    blocked = any(issue["severity"] == "blocked" for issue in issues)
    waiting = bool(issues) and not blocked
    status = STATUS_VALID_REVIEW_ONLY
    if waiting:
        status = STATUS_WAITING_REVIEW_ONLY
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED

    validation_results = {
        "p41_report_present": bool(p41_report),
        "p41_summary_present": bool(p41_summary),
        "p41_archive_index_present": bool(p41_archive_index),
        "p41_audit_trail_chain_present": bool(p41_audit_trail_chain),
        "archive_index_hash_match": bool(expected_archive_index_hash) and expected_archive_index_hash == observed_archive_index_hash,
        "audit_trail_chain_hash_match": bool(expected_audit_trail_chain_hash) and expected_audit_trail_chain_hash == observed_audit_trail_chain_hash,
        "chain_archive_index_hash_match": bool(p41_audit_trail_chain) and p41_audit_trail_chain.get("archive_index_hash") == observed_archive_index_hash,
        "archive_entry_hash_mismatch_count": len(archive_entry_hash_mismatches),
        "missing_p41_artifact_count": len(missing_p41_artifacts),
        "review_only": True,
        "runtime_authority": False,
    }
    hash_recheck_chain = {
        "chain_id": stable_id("p42_operator_evidence_archive_intake_chain", {"observed_archive_index_hash": observed_archive_index_hash, "observed_audit_trail_chain_hash": observed_audit_trail_chain_hash, "p41_status": p41_status}),
        "p41_status": p41_status or None,
        "expected_archive_index_hash": expected_archive_index_hash,
        "observed_archive_index_hash": observed_archive_index_hash,
        "expected_audit_trail_chain_hash": expected_audit_trail_chain_hash,
        "observed_audit_trail_chain_hash": observed_audit_trail_chain_hash,
        "p41_chain_archive_index_hash": p41_audit_trail_chain.get("archive_index_hash"),
        "archive_entry_hash_mismatch_count": len(archive_entry_hash_mismatches),
        "missing_p41_artifact_count": len(missing_p41_artifacts),
        "review_only": True,
        "runtime_authority": False,
    }
    hash_recheck_chain_hash = sha256_json(hash_recheck_chain)

    report: dict[str, Any] = {
        "version": P42_OPERATOR_EVIDENCE_ARCHIVE_INTAKE_VALIDATOR_VERSION,
        "status": status,
        "waiting": waiting,
        "blocked": blocked,
        "created_at_utc": utc_now_canonical(),
        "p41_report_present": bool(p41_report),
        "p41_summary_present": bool(p41_summary),
        "p41_archive_index_present": bool(p41_archive_index),
        "p41_audit_trail_chain_present": bool(p41_audit_trail_chain),
        "p41_status": p41_status or None,
        "expected_archive_index_hash": expected_archive_index_hash,
        "observed_archive_index_hash": observed_archive_index_hash,
        "archive_index_hash_mismatch": bool(expected_archive_index_hash and expected_archive_index_hash != observed_archive_index_hash),
        "expected_audit_trail_chain_hash": expected_audit_trail_chain_hash,
        "observed_audit_trail_chain_hash": observed_audit_trail_chain_hash,
        "audit_trail_chain_hash_mismatch": bool(expected_audit_trail_chain_hash and expected_audit_trail_chain_hash != observed_audit_trail_chain_hash),
        "chain_archive_index_hash_mismatch": bool(p41_audit_trail_chain and p41_audit_trail_chain.get("archive_index_hash") != observed_archive_index_hash),
        "archive_entry_hash_mismatches": archive_entry_hash_mismatches,
        "archive_entry_hash_mismatch_count": len(archive_entry_hash_mismatches),
        "missing_p41_artifacts": missing_p41_artifacts,
        "missing_p41_artifact_count": len(missing_p41_artifacts),
        "validation_results": validation_results,
        "hash_recheck_chain": hash_recheck_chain,
        "hash_recheck_chain_hash": hash_recheck_chain_hash,
        "intake_issues": issues,
        "intake_issue_count": len(issues),
        "intake_issue_codes": sorted({issue["code"] for issue in issues}),
        "blocked_issue_count": sum(1 for issue in issues if issue["severity"] == "blocked"),
        "waiting_issue_count": sum(1 for issue in issues if issue["severity"] == "waiting"),
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "unsafe_truthy_execution_flag_hit_count": len(unsafe_hits),
        "runtime_flag_truthy": bool(unsafe_hits),
        "scheduler_enabled": bool(scheduler_hits),
        "endpoint_called": bool(endpoint_hits),
        "runtime_authority_claimed": bool(authority_hits) or _bool(p41_audit_trail_chain.get("runtime_authority")),
        "secret_detected": bool(secret_hits),
        "secret_pattern_hits": secret_hits,
        "secret_pattern_hit_count": len(secret_hits),
        "runtime_authority": False,
        "archive_intake_executes_runtime": False,
        "archive_intake_enables_scheduler": False,
        "archive_intake_allows_order_submission": False,
        "archive_intake_calls_endpoint": False,
        "archive_intake_reads_secret_value": False,
        "archive_intake_grants_runtime_authority": False,
        "runtime_scheduler_enabled": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "latest_dir": str(latest),
    }
    flag_state = default_execution_flag_state()
    flag_state.update(
        {
            "runtime_scheduler_enabled": False,
            "live_scaled_execution_enabled": False,
            "live_order_submission_allowed": False,
            "order_endpoint_called": False,
            "secret_value_accessed": False,
            "archive_intake_executes_runtime": False,
            "archive_intake_enables_scheduler": False,
            "archive_intake_allows_order_submission": False,
            "archive_intake_calls_endpoint": False,
            "archive_intake_reads_secret_value": False,
            "archive_intake_grants_runtime_authority": False,
        }
    )
    report["execution_flag_state"] = flag_state
    report["truthy_execution_flags"] = truthy_execution_flags(flag_state)
    if report["truthy_execution_flags"]:
        report["status"] = STATUS_BLOCKED_FAIL_CLOSED
        report["blocked"] = True
        report["waiting"] = False
        report["intake_issues"].append({"code": "truthy_execution_flag_state", "severity": "blocked", "message": "Default execution flag state contains truthy runtime flags.", "evidence": report["truthy_execution_flags"]})
        report["intake_issue_codes"] = sorted({issue["code"] for issue in report["intake_issues"]})
        report["intake_issue_count"] = len(report["intake_issues"])
        report["blocked_issue_count"] = sum(1 for issue in report["intake_issues"] if issue["severity"] == "blocked")
    return report


def build_p42_negative_fixture_results(root: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    p41_report = _read_latest_json(cfg, "p41_operator_evidence_archive_index_report.json", default={})
    p41_summary = _read_latest_json(cfg, "p41_operator_evidence_archive_index_summary.json", default={})
    p41_index = _read_latest_json(cfg, "p41_operator_evidence_archive_index.json", default=[])
    p41_chain = _read_latest_json(cfg, "p41_operator_evidence_audit_trail_chain.json", default={})
    if not isinstance(p41_report, Mapping):
        p41_report = {}
    if not isinstance(p41_summary, Mapping):
        p41_summary = {}
    if not isinstance(p41_index, list):
        p41_index = []
    if not isinstance(p41_chain, Mapping):
        p41_chain = {}

    mutated_index = [dict(item) for item in p41_index]
    if mutated_index:
        mutated_index[0] = {**mutated_index[0], "sha256": "tampered_sha"}
    fixtures: dict[str, dict[str, Any]] = {
        "missing_p41_report": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report={}, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain),
        "missing_p41_summary": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report=p41_report, p41_summary={}, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain),
        "missing_p41_archive_index": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=[], p41_audit_trail_chain=p41_chain),
        "missing_p41_audit_trail_chain": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain={}),
        "p41_blocked": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report={**dict(p41_report), "status": P41_STATUS_BLOCKED_FAIL_CLOSED, "blocked": True}, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain),
        "p41_waiting": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report={**dict(p41_report), "status": P41_STATUS_WAITING_REVIEW_ONLY, "waiting": True}, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain),
        "archive_index_hash_mismatch": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report={**dict(p41_report), "archive_index_hash": "bad_hash"}, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain),
        "audit_trail_chain_hash_mismatch": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report={**dict(p41_report), "audit_trail_chain_hash": "bad_hash"}, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain),
        "chain_archive_index_hash_mismatch": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain={**dict(p41_chain), "archive_index_hash": "bad_hash"}),
        "archive_entry_hash_mismatch": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=mutated_index, p41_audit_trail_chain=p41_chain),
        "secret_detected": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, extra_payloads_for_scan=[("bad_secret", "BINANCE_API_SECRET=leak")]),
        "runtime_flag_truthy": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, extra_payloads_for_scan=[("bad_runtime", {"live_scaled_execution_enabled": True})]),
        "scheduler_enabled": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, extra_payloads_for_scan=[("bad_scheduler", {"runtime_scheduler_enabled": True})]),
        "endpoint_called": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, extra_payloads_for_scan=[("bad_endpoint", {"order_endpoint_called": True})]),
        "runtime_authority_claimed": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain={**dict(p41_chain), "runtime_authority": True}),
        "archive_intake_executes_runtime": build_operator_evidence_archive_intake_validator_report(root=cfg.root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=p41_index, p41_audit_trail_chain=p41_chain, extra_payloads_for_scan=[("bad_intake", {"archive_intake_executes_runtime": True})]),
    }
    fixture_summary = {
        name: {
            "status": result["status"],
            "waiting": result["waiting"],
            "blocked": result["blocked"],
            "intake_issue_codes": result["intake_issue_codes"],
            "archive_intake_executes_runtime": result["archive_intake_executes_runtime"],
            "runtime_scheduler_enabled": result["runtime_scheduler_enabled"],
            "order_endpoint_called": result["order_endpoint_called"],
            "secret_value_accessed": result["secret_value_accessed"],
        }
        for name, result in fixtures.items()
    }
    all_fail_closed = all(item["waiting"] or item["blocked"] for item in fixture_summary.values())
    return {
        "status": "P42_NEGATIVE_FIXTURES_RECORDED",
        "created_at_utc": utc_now_canonical(),
        "fixture_count": len(fixture_summary),
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all_fail_closed,
        "fixture_results": fixture_summary,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def persist_operator_evidence_archive_intake_validator(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p42_operator_evidence_archive_intake_validator")
    report = build_operator_evidence_archive_intake_validator_report(root=cfg.root)
    checklist = _build_checklist(report)
    markdown = _build_markdown(report)
    negative = build_p42_negative_fixture_results(root=cfg.root)

    report_path = latest / "p42_operator_evidence_archive_intake_validator_report.json"
    summary_path = latest / "p42_operator_evidence_archive_intake_validator_summary.json"
    validation_path = latest / "p42_operator_evidence_archive_intake_validation_results.json"
    chain_path = latest / "p42_operator_evidence_archive_hash_recheck_chain.json"
    checklist_path = latest / "p42_operator_evidence_archive_intake_checklist.md"
    markdown_path = latest / "p42_operator_evidence_archive_intake_validator.md"
    negative_path = latest / "p42_operator_evidence_archive_intake_validator_negative_fixture_results.json"
    registry_record_path = latest / "p42_operator_evidence_archive_intake_validator_registry_record.json"

    output_paths = {
        "report": str(report_path),
        "summary": str(summary_path),
        "validation_results": str(validation_path),
        "hash_recheck_chain": str(chain_path),
        "checklist": str(checklist_path),
        "markdown": str(markdown_path),
    }
    report["output_paths"] = output_paths
    summary = {
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "intake_issue_count": report["intake_issue_count"],
        "intake_issue_codes": report["intake_issue_codes"],
        "expected_archive_index_hash": report["expected_archive_index_hash"],
        "observed_archive_index_hash": report["observed_archive_index_hash"],
        "expected_audit_trail_chain_hash": report["expected_audit_trail_chain_hash"],
        "observed_audit_trail_chain_hash": report["observed_audit_trail_chain_hash"],
        "hash_recheck_chain_hash": report["hash_recheck_chain_hash"],
        "archive_entry_hash_mismatch_count": report["archive_entry_hash_mismatch_count"],
        "missing_p41_artifact_count": report["missing_p41_artifact_count"],
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
        "id": stable_id("p42_operator_evidence_archive_intake_validator", {"hash_recheck_chain_hash": report.get("hash_recheck_chain_hash"), "status": report.get("status")}),
        "version": P42_OPERATOR_EVIDENCE_ARCHIVE_INTAKE_VALIDATOR_VERSION,
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "created_at_utc": report["created_at_utc"],
        "hash_recheck_chain_hash": report["hash_recheck_chain_hash"],
        "intake_issue_count": report["intake_issue_count"],
        "runtime_authority": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }

    for directory in (latest, storage):
        atomic_write_json(directory / report_path.name, report)
        atomic_write_json(directory / summary_path.name, summary)
        atomic_write_json(directory / validation_path.name, report["validation_results"])
        atomic_write_json(directory / chain_path.name, report["hash_recheck_chain"])
        _atomic_write_text(directory / checklist_path.name, checklist)
        _atomic_write_text(directory / markdown_path.name, markdown)
    atomic_write_json(negative_path, negative)
    atomic_write_json(storage / negative_path.name, negative)
    append_registry_record(
        registry_path(cfg, P42_OPERATOR_EVIDENCE_ARCHIVE_INTAKE_VALIDATOR_REGISTRY_NAME),
        registry_record,
        registry_name=P42_OPERATOR_EVIDENCE_ARCHIVE_INTAKE_VALIDATOR_REGISTRY_NAME,
    )
    atomic_write_json(registry_record_path, registry_record)
    atomic_write_json(storage / registry_record_path.name, registry_record)
    return report
