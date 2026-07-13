from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.operator_support_bundle_round_trip_verification import (
    STATUS_BLOCKED_FAIL_CLOSED as P40_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VERIFIED_REVIEW_ONLY as P40_STATUS_VERIFIED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P40_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P41_OPERATOR_EVIDENCE_ARCHIVE_INDEX_VERSION = "p41_operator_evidence_archive_index_audit_trail_v1"
P41_OPERATOR_EVIDENCE_ARCHIVE_INDEX_REGISTRY_NAME = "p41_operator_evidence_archive_index_registry"

STATUS_GENERATED_REVIEW_ONLY = "P41_OPERATOR_EVIDENCE_ARCHIVE_INDEX_GENERATED_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P41_OPERATOR_EVIDENCE_ARCHIVE_INDEX_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P41_OPERATOR_EVIDENCE_ARCHIVE_INDEX_BLOCKED_FAIL_CLOSED"

_ALLOWED_READ_ONLY_COMMANDS = ("status", "matrix", "waiting", "no_go", "export_paths")
_REQUIRED_BLOCKED_KEYWORDS = (
    "enable",
    "start",
    "submit",
    "order",
    "live",
    "trade",
    "activate",
    "scheduler",
    "place",
    "cancel",
    "runtime",
)
_SOURCE_ARTIFACTS: tuple[tuple[str, str, str], ...] = (
    # P33 command router fixture validator
    ("p33", "json", "p33_telegram_launcher_command_router_fixture_validator_report.json"),
    ("p33", "json", "p33_telegram_launcher_command_router_fixture_validator_summary.json"),
    ("p33", "json", "p33_telegram_launcher_command_router_contract.json"),
    ("p33", "json", "p33_telegram_command_router_fixture.json"),
    ("p33", "json", "p33_launcher_command_router_fixture.json"),
    ("p33", "json", "p33_command_router_fixture_validation_results.json"),
    ("p33", "text", "p33_command_router_read_only_routes.txt"),
    ("p33", "json", "p33_telegram_launcher_command_router_fixture_validator_negative_fixture_results.json"),
    ("p33", "json", "p33_telegram_launcher_command_router_fixture_validator_registry_record.json"),
    # P34 command response snapshots
    ("p34", "json", "p34_telegram_launcher_command_response_snapshot_pack_report.json"),
    ("p34", "json", "p34_telegram_launcher_command_response_snapshot_pack_summary.json"),
    ("p34", "json", "p34_telegram_command_response_snapshots.json"),
    ("p34", "json", "p34_launcher_command_response_snapshots.json"),
    ("p34", "json", "p34_command_response_snapshot_pack.json"),
    ("p34", "text", "p34_command_response_snapshot_pack.md"),
    ("p34", "text", "p34_command_response_snapshot_pack.txt"),
    ("p34", "json", "p34_telegram_launcher_command_response_snapshot_pack_negative_fixture_results.json"),
    ("p34", "json", "p34_telegram_launcher_command_response_snapshot_pack_registry_record.json"),
    # P35 operator UX runbook
    ("p35", "json", "p35_operator_ux_quickstart_runbook_pack_report.json"),
    ("p35", "json", "p35_operator_ux_quickstart_runbook_pack_summary.json"),
    ("p35", "json", "p35_operator_ux_quickstart_runbook_pack.json"),
    ("p35", "text", "p35_operator_ux_quickstart_runbook.md"),
    ("p35", "text", "p35_operator_ux_checklist.md"),
    ("p35", "text", "p35_safe_command_guide.md"),
    ("p35", "text", "p35_operator_ux_quickstart.txt"),
    ("p35", "json", "p35_operator_ux_quickstart_runbook_pack_negative_fixture_results.json"),
    ("p35", "json", "p35_operator_ux_quickstart_runbook_pack_registry_record.json"),
    # P36 onboarding wizard
    ("p36", "json", "p36_non_developer_onboarding_wizard_report.json"),
    ("p36", "json", "p36_non_developer_onboarding_wizard_summary.json"),
    ("p36", "json", "p36_non_developer_onboarding_wizard_pack.json"),
    ("p36", "json", "p36_onboarding_wizard_steps.json"),
    ("p36", "text", "p36_zip_drop_in_wizard.md"),
    ("p36", "text", "p36_zip_drop_in_checklist.md"),
    ("p36", "text", "p36_failure_message_lookup.md"),
    ("p36", "json", "p36_operator_onboarding_card.json"),
    ("p36", "json", "p36_non_developer_onboarding_wizard_negative_fixture_results.json"),
    ("p36", "json", "p36_non_developer_onboarding_wizard_registry_record.json"),
    # P37 failure doctor
    ("p37", "json", "p37_onboarding_wizard_failure_doctor_report.json"),
    ("p37", "json", "p37_onboarding_wizard_failure_doctor_summary.json"),
    ("p37", "json", "p37_onboarding_wizard_failure_doctor_pack.json"),
    ("p37", "json", "p37_self_diagnosis_results.json"),
    ("p37", "json", "p37_failure_doctor_lookup.json"),
    ("p37", "text", "p37_self_diagnosis_pack.md"),
    ("p37", "text", "p37_self_diagnosis_checklist.md"),
    ("p37", "json", "p37_operator_self_diagnosis_card.json"),
    ("p37", "json", "p37_onboarding_wizard_failure_doctor_negative_fixture_results.json"),
    ("p37", "json", "p37_onboarding_wizard_failure_doctor_registry_record.json"),
    # P38 support bundle export
    ("p38", "json", "p38_operator_support_bundle_report.json"),
    ("p38", "json", "p38_operator_support_bundle_summary.json"),
    ("p38", "json", "p38_operator_support_bundle_pack.json"),
    ("p38", "json", "p38_operator_support_bundle_manifest.json"),
    ("p38", "text", "p38_operator_support_bundle_manifest.csv"),
    ("p38", "text", "p38_operator_support_bundle.md"),
    ("p38", "json", "p38_operator_support_bundle_share_packet.json"),
    ("p38", "text", "p38_operator_support_bundle_paths.txt"),
    ("p38", "json", "p38_operator_support_bundle_negative_fixture_results.json"),
    ("p38", "json", "p38_operator_support_bundle_registry_record.json"),
    # P39 intake validator
    ("p39", "json", "p39_operator_support_bundle_intake_validator_report.json"),
    ("p39", "json", "p39_operator_support_bundle_intake_validator_summary.json"),
    ("p39", "json", "p39_operator_support_bundle_intake_validation_results.json"),
    ("p39", "text", "p39_operator_support_bundle_intake_checklist.md"),
    ("p39", "text", "p39_operator_support_bundle_intake_validator.md"),
    ("p39", "json", "p39_operator_support_bundle_intake_validator_negative_fixture_results.json"),
    ("p39", "json", "p39_operator_support_bundle_intake_validator_registry_record.json"),
    # P40 round-trip verification
    ("p40", "json", "p40_operator_support_bundle_round_trip_verification_report.json"),
    ("p40", "json", "p40_operator_support_bundle_round_trip_verification_summary.json"),
    ("p40", "json", "p40_operator_support_bundle_round_trip_chain.json"),
    ("p40", "text", "p40_operator_support_bundle_round_trip_checklist.md"),
    ("p40", "text", "p40_operator_support_bundle_round_trip_verification.md"),
    ("p40", "json", "p40_operator_support_bundle_round_trip_verification_negative_fixture_results.json"),
    ("p40", "json", "p40_operator_support_bundle_round_trip_verification_registry_record.json"),
)
_REQUIRED_SOURCE_FILENAMES = tuple(filename for _phase, _kind, filename in _SOURCE_ARTIFACTS)
_EXECUTION_FIELDS_FOR_P41 = {
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
    "runtime_authority_claimed",
    "support_bundle_executes_runtime",
    "support_bundle_enables_scheduler",
    "support_bundle_allows_order_submission",
    "support_bundle_calls_endpoint",
    "support_bundle_reads_secret_value",
    "support_bundle_contains_secret_value",
    "support_bundle_grants_runtime_authority",
    "support_bundle_changes_settings",
    "intake_validator_executes_runtime",
    "intake_validator_enables_scheduler",
    "intake_validator_allows_order_submission",
    "intake_validator_calls_endpoint",
    "intake_validator_reads_secret_value",
    "intake_validator_grants_runtime_authority",
    "round_trip_executes_runtime",
    "round_trip_enables_scheduler",
    "round_trip_allows_order_submission",
    "round_trip_calls_endpoint",
    "round_trip_reads_secret_value",
    "round_trip_grants_runtime_authority",
    "archive_index_executes_runtime",
    "archive_index_enables_scheduler",
    "archive_index_allows_order_submission",
    "archive_index_calls_endpoint",
    "archive_index_reads_secret_value",
    "archive_index_grants_runtime_authority",
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


def _read_artifact_payload(path: Path, kind: str) -> Any:
    if not path.exists():
        return None
    if kind == "json":
        return read_json(path, default={})
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _scan_truthy_execution_fields(payloads: Sequence[tuple[str, Any]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, source: str, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                next_path = f"{path}.{key}"
                if key in _EXECUTION_FIELDS_FOR_P41 and _bool(value):
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


def _build_archive_index(cfg: AppConfig) -> tuple[list[dict[str, Any]], list[tuple[str, Any]]]:
    latest = _latest_dir(cfg)
    index: list[dict[str, Any]] = []
    payloads: list[tuple[str, Any]] = []
    for ordinal, (phase, kind, filename) in enumerate(_SOURCE_ARTIFACTS, start=1):
        path = latest / filename
        exists = path.exists()
        payload = _read_artifact_payload(path, kind) if exists else None
        entry: dict[str, Any] = {
            "ordinal": ordinal,
            "phase": phase,
            "kind": kind,
            "filename": filename,
            "path": str(path),
            "exists": exists,
            "size_bytes": path.stat().st_size if exists else None,
            "sha256": _sha256_bytes(path) if exists else None,
            "artifact_payload_sha256": sha256_json(payload) if exists and payload is not None else None,
            "review_only": True,
            "runtime_authority": False,
            "shareable_reference": True if exists else False,
        }
        if exists and payload is not None:
            payloads.append((filename, payload))
        index.append(entry)
    return index, payloads


def _phase_counts(index: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for item in index:
        phase = str(item.get("phase"))
        bucket = counts.setdefault(phase, {"expected": 0, "present": 0, "missing": 0})
        bucket["expected"] += 1
        if item.get("exists"):
            bucket["present"] += 1
        else:
            bucket["missing"] += 1
    return counts


def _index_csv(index: Sequence[Mapping[str, Any]]) -> str:
    output = io.StringIO()
    fields = ["ordinal", "phase", "kind", "filename", "exists", "size_bytes", "sha256", "artifact_payload_sha256", "review_only", "runtime_authority"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in index:
        writer.writerow({field: item.get(field) for field in fields})
    return output.getvalue()


def _build_archive_checklist(report: Mapping[str, Any]) -> str:
    checks = [
        ("P40 round-trip report exists", bool(report.get("p40_report_present"))),
        ("P40 round-trip status verified review-only", report.get("p40_status") == P40_STATUS_VERIFIED_REVIEW_ONLY),
        ("All P33-P40 archive artifacts present", report.get("missing_archive_artifact_count") == 0),
        ("Archive index hash generated", bool(report.get("archive_index_hash"))),
        ("Audit trail chain hash generated", bool(report.get("audit_trail_chain_hash"))),
        ("Runtime remains disabled", not bool(report.get("runtime_flag_truthy"))),
        ("Scheduler remains disabled", not bool(report.get("scheduler_enabled"))),
        ("No endpoint evidence", not bool(report.get("endpoint_called"))),
        ("No secret value patterns", not bool(report.get("secret_detected"))),
        ("Authority remains review-only", not bool(report.get("runtime_authority_claimed"))),
    ]
    lines = ["# P41 Operator Evidence Archive Checklist", ""]
    for label, passed in checks:
        mark = "x" if passed else " "
        lines.append(f"- [{mark}] {label}")
    return "\n".join(lines).rstrip() + "\n"


def _build_audit_trail_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# P41 Operator Evidence Archive Index / Audit Trail",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "> This archive index is review-only. It does not enable runtime, scheduler, order submission, endpoint calls, secret access, settings mutation, or auto-promotion.",
        "",
        "## Summary",
        "",
        f"- Expected archive artifacts: `{report.get('expected_archive_artifact_count')}`",
        f"- Present archive artifacts: `{report.get('present_archive_artifact_count')}`",
        f"- Missing archive artifacts: `{report.get('missing_archive_artifact_count')}`",
        f"- Archive index hash: `{report.get('archive_index_hash')}`",
        f"- Audit trail chain hash: `{report.get('audit_trail_chain_hash')}`",
        f"- P40 status: `{report.get('p40_status')}`",
        "",
        "## Phase Counts",
        "",
        "| Phase | Expected | Present | Missing |",
        "|---|---:|---:|---:|",
    ]
    phase_counts = report.get("phase_counts", {})
    if isinstance(phase_counts, Mapping):
        for phase in sorted(phase_counts):
            counts = phase_counts[phase]
            if isinstance(counts, Mapping):
                lines.append(f"| {phase} | {counts.get('expected', 0)} | {counts.get('present', 0)} | {counts.get('missing', 0)} |")
    lines.extend(["", "## Issue Codes", ""])
    codes = report.get("archive_issue_codes", [])
    if not codes:
        lines.append("- None")
    else:
        for code in codes:
            lines.append(f"- `{code}`")
    lines.extend(["", "## Required Safe State", "", "- Runtime: DISABLED", "- Scheduler: DISABLED", "- Orders: DISABLED", "- Authority: REVIEW_ONLY", "- Secret values: not present", "- Endpoint evidence: not present", "", "## Archive Entries", ""])
    for item in report.get("archive_index", []):
        if isinstance(item, Mapping):
            mark = "present" if item.get("exists") else "missing"
            lines.append(f"- `{item.get('phase')}` `{mark}` `{item.get('filename')}` sha256=`{item.get('sha256')}`")
    return "\n".join(lines).rstrip() + "\n"


def build_operator_evidence_archive_index_report(
    *,
    root: str | Path | None = None,
    archive_index: Sequence[Mapping[str, Any]] | None = None,
    p40_report: Mapping[str, Any] | None = None,
    p40_chain: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] = (),
) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    latest = _latest_dir(cfg)
    if archive_index is None:
        index, payloads = _build_archive_index(cfg)
    else:
        index = [dict(item) for item in archive_index]
        payloads = []
    if p40_report is None:
        loaded = _read_latest_json(cfg, "p40_operator_support_bundle_round_trip_verification_report.json", default={})
        p40_report = loaded if isinstance(loaded, Mapping) else {}
    if p40_chain is None:
        loaded_chain = _read_latest_json(cfg, "p40_operator_support_bundle_round_trip_chain.json", default={})
        p40_chain = loaded_chain if isinstance(loaded_chain, Mapping) else {}
    p40_report = dict(p40_report)
    p40_chain = dict(p40_chain)

    scan_payloads: list[tuple[str, Any]] = [
        ("p41_archive_index", index),
        ("p40_report", p40_report),
        ("p40_chain", p40_chain),
        *payloads,
        *list(extra_payloads_for_scan),
    ]
    unsafe_hits = _scan_truthy_execution_fields(scan_payloads)
    secret_hits = _scan_secret_value_patterns(scan_payloads)
    endpoint_hits = [hit for hit in unsafe_hits if "endpoint" in str(hit.get("field", "")) or hit.get("field") == "http_request_sent"]
    scheduler_hits = [hit for hit in unsafe_hits if "scheduler" in str(hit.get("field", ""))]
    authority_hits = [hit for hit in unsafe_hits if "authority" in str(hit.get("field", ""))]

    issues: list[dict[str, Any]] = []

    def add_issue(code: str, severity: str, message: str, evidence: Any = None) -> None:
        issue = {"code": code, "severity": severity, "message": message}
        if evidence is not None:
            issue["evidence"] = evidence
        issues.append(issue)

    missing = [item["filename"] for item in index if not item.get("exists")]
    if missing:
        add_issue("missing_archive_artifacts", "waiting", "One or more P33-P40 archive artifacts are missing.", missing)
    if not p40_report:
        add_issue("missing_p40_report", "waiting", "P40 round-trip report is missing or empty.")
    if not p40_chain:
        add_issue("missing_p40_chain", "waiting", "P40 round-trip chain is missing or empty.")

    p40_status = str(p40_report.get("status", "")) if p40_report else ""
    if p40_status == P40_STATUS_BLOCKED_FAIL_CLOSED or _bool(p40_report.get("blocked")):
        add_issue("p40_blocked", "blocked", "P40 round-trip verification is blocked fail-closed.")
    if p40_status == P40_STATUS_WAITING_REVIEW_ONLY or _bool(p40_report.get("waiting")):
        add_issue("p40_waiting", "waiting", "P40 round-trip verification is waiting.")
    if p40_status and p40_status != P40_STATUS_VERIFIED_REVIEW_ONLY:
        add_issue("p40_not_verified_review_only", "waiting", f"P40 status is not verified review-only: {p40_status}")

    if p40_report and int(p40_report.get("round_trip_issue_count", 0) or 0) != 0:
        severity = "blocked" if _bool(p40_report.get("blocked")) else "waiting"
        add_issue("p40_reported_round_trip_issues", severity, "P40 reported round-trip issues.", p40_report.get("round_trip_issue_codes", []))
    if p40_chain and not _bool(p40_chain.get("review_only")):
        add_issue("p40_chain_not_review_only", "blocked", "P40 round-trip chain is not marked review-only.")
    if p40_chain and _bool(p40_chain.get("runtime_authority")):
        add_issue("runtime_authority_claimed", "blocked", "P40 chain claims runtime authority.")

    if unsafe_hits:
        add_issue("runtime_flag_truthy", "blocked", "Truthy runtime/order/scheduler flag detected in archive payloads.", unsafe_hits)
    if scheduler_hits:
        add_issue("scheduler_enabled", "blocked", "Scheduler truthy flag detected in archive payloads.", scheduler_hits)
    if endpoint_hits:
        add_issue("endpoint_called", "blocked", "Endpoint-call truthy flag detected in archive payloads.", endpoint_hits)
    if authority_hits:
        add_issue("runtime_authority_claimed", "blocked", "Runtime authority truthy flag detected in archive payloads.", authority_hits)
    if secret_hits:
        add_issue("secret_detected", "blocked", "Secret value pattern detected in archive payloads.", secret_hits)

    blocked = any(issue["severity"] == "blocked" for issue in issues)
    waiting = bool(issues) and not blocked
    status = STATUS_GENERATED_REVIEW_ONLY
    if waiting:
        status = STATUS_WAITING_REVIEW_ONLY
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED

    phase_counts = _phase_counts(index)
    archive_index_hash = sha256_json(index)
    audit_trail_chain = {
        "chain_id": stable_id("p41_operator_evidence_archive_chain", {"archive_index_hash": archive_index_hash, "p40_round_trip_hash": p40_report.get("round_trip_hash")}),
        "p40_status": p40_status or None,
        "p40_round_trip_hash": p40_report.get("round_trip_hash"),
        "p40_chain_id": p40_chain.get("chain_id"),
        "archive_index_hash": archive_index_hash,
        "archive_artifact_count": len(index),
        "present_archive_artifact_count": sum(1 for item in index if item.get("exists")),
        "missing_archive_artifact_count": len(missing),
        "review_only": True,
        "runtime_authority": False,
    }
    audit_trail_chain_hash = sha256_json(audit_trail_chain)

    report: dict[str, Any] = {
        "version": P41_OPERATOR_EVIDENCE_ARCHIVE_INDEX_VERSION,
        "status": status,
        "waiting": waiting,
        "blocked": blocked,
        "created_at_utc": utc_now_canonical(),
        "p40_report_present": bool(p40_report),
        "p40_chain_present": bool(p40_chain),
        "p40_status": p40_status or None,
        "p40_round_trip_hash": p40_report.get("round_trip_hash"),
        "archive_index": index,
        "archive_index_hash": archive_index_hash,
        "audit_trail_chain": audit_trail_chain,
        "audit_trail_chain_hash": audit_trail_chain_hash,
        "expected_archive_artifact_count": len(index),
        "present_archive_artifact_count": sum(1 for item in index if item.get("exists")),
        "missing_archive_artifact_count": len(missing),
        "missing_archive_artifacts": missing,
        "phase_counts": phase_counts,
        "archive_issues": issues,
        "archive_issue_count": len(issues),
        "archive_issue_codes": sorted({issue["code"] for issue in issues}),
        "blocked_issue_count": sum(1 for issue in issues if issue["severity"] == "blocked"),
        "waiting_issue_count": sum(1 for issue in issues if issue["severity"] == "waiting"),
        "allowed_read_only_commands": list(_ALLOWED_READ_ONLY_COMMANDS),
        "blocked_command_keywords": list(_REQUIRED_BLOCKED_KEYWORDS),
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "unsafe_truthy_execution_flag_hit_count": len(unsafe_hits),
        "runtime_flag_truthy": bool(unsafe_hits),
        "scheduler_enabled": bool(scheduler_hits),
        "endpoint_called": bool(endpoint_hits),
        "runtime_authority_claimed": bool(authority_hits) or _bool(p40_chain.get("runtime_authority")),
        "secret_detected": bool(secret_hits),
        "secret_pattern_hits": secret_hits,
        "secret_pattern_hit_count": len(secret_hits),
        "runtime_authority": False,
        "archive_index_executes_runtime": False,
        "archive_index_enables_scheduler": False,
        "archive_index_allows_order_submission": False,
        "archive_index_calls_endpoint": False,
        "archive_index_reads_secret_value": False,
        "archive_index_grants_runtime_authority": False,
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
            "archive_index_executes_runtime": False,
            "archive_index_enables_scheduler": False,
            "archive_index_allows_order_submission": False,
            "archive_index_calls_endpoint": False,
            "archive_index_reads_secret_value": False,
            "archive_index_grants_runtime_authority": False,
        }
    )
    report["execution_flag_state"] = flag_state
    report["truthy_execution_flags"] = truthy_execution_flags(flag_state)
    if report["truthy_execution_flags"]:
        report["status"] = STATUS_BLOCKED_FAIL_CLOSED
        report["blocked"] = True
        report["waiting"] = False
        report["archive_issues"].append({"code": "truthy_execution_flag_state", "severity": "blocked", "message": "Default execution flag state contains truthy runtime flags.", "evidence": report["truthy_execution_flags"]})
        report["archive_issue_codes"] = sorted({issue["code"] for issue in report["archive_issues"]})
        report["archive_issue_count"] = len(report["archive_issues"])
        report["blocked_issue_count"] = sum(1 for issue in report["archive_issues"] if issue["severity"] == "blocked")
    return report


def build_p41_negative_fixture_results(root: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    base_report = build_operator_evidence_archive_index_report(root=cfg.root)
    base_index = base_report.get("archive_index", [])
    p40_report = _read_latest_json(cfg, "p40_operator_support_bundle_round_trip_verification_report.json", default={})
    p40_chain = _read_latest_json(cfg, "p40_operator_support_bundle_round_trip_chain.json", default={})
    if not isinstance(p40_report, Mapping):
        p40_report = {}
    if not isinstance(p40_chain, Mapping):
        p40_chain = {}
    fixtures: dict[str, dict[str, Any]] = {
        "missing_p40_report": build_operator_evidence_archive_index_report(root=cfg.root, archive_index=base_index, p40_report={}, p40_chain=p40_chain),
        "missing_p40_chain": build_operator_evidence_archive_index_report(root=cfg.root, archive_index=base_index, p40_report=p40_report, p40_chain={}),
        "missing_archive_artifacts": build_operator_evidence_archive_index_report(root=cfg.root, archive_index=[{**dict(item), "exists": False} for item in base_index], p40_report=p40_report, p40_chain=p40_chain),
        "p40_blocked": build_operator_evidence_archive_index_report(root=cfg.root, archive_index=base_index, p40_report={**dict(p40_report), "status": P40_STATUS_BLOCKED_FAIL_CLOSED, "blocked": True}, p40_chain=p40_chain),
        "p40_waiting": build_operator_evidence_archive_index_report(root=cfg.root, archive_index=base_index, p40_report={**dict(p40_report), "status": P40_STATUS_WAITING_REVIEW_ONLY, "waiting": True}, p40_chain=p40_chain),
        "p40_reported_issues": build_operator_evidence_archive_index_report(root=cfg.root, archive_index=base_index, p40_report={**dict(p40_report), "round_trip_issue_count": 1, "round_trip_issue_codes": ["fixture_issue"]}, p40_chain=p40_chain),
        "runtime_flag_truthy": build_operator_evidence_archive_index_report(root=cfg.root, archive_index=base_index, p40_report=p40_report, p40_chain=p40_chain, extra_payloads_for_scan=[("bad_runtime", {"live_scaled_execution_enabled": True})]),
        "scheduler_enabled": build_operator_evidence_archive_index_report(root=cfg.root, archive_index=base_index, p40_report=p40_report, p40_chain=p40_chain, extra_payloads_for_scan=[("bad_scheduler", {"runtime_scheduler_enabled": True})]),
        "endpoint_called": build_operator_evidence_archive_index_report(root=cfg.root, archive_index=base_index, p40_report=p40_report, p40_chain=p40_chain, extra_payloads_for_scan=[("bad_endpoint", {"order_endpoint_called": True})]),
        "secret_detected": build_operator_evidence_archive_index_report(root=cfg.root, archive_index=base_index, p40_report=p40_report, p40_chain=p40_chain, extra_payloads_for_scan=[("bad_secret", "BINANCE_API_SECRET=leak")]),
        "runtime_authority_claimed": build_operator_evidence_archive_index_report(root=cfg.root, archive_index=base_index, p40_report=p40_report, p40_chain={**dict(p40_chain), "runtime_authority": True}),
        "archive_index_executes_runtime": build_operator_evidence_archive_index_report(root=cfg.root, archive_index=base_index, p40_report=p40_report, p40_chain=p40_chain, extra_payloads_for_scan=[("bad_archive", {"archive_index_executes_runtime": True})]),
    }
    fixture_summary = {
        name: {
            "status": result["status"],
            "waiting": result["waiting"],
            "blocked": result["blocked"],
            "archive_issue_codes": result["archive_issue_codes"],
            "archive_index_executes_runtime": result["archive_index_executes_runtime"],
            "runtime_scheduler_enabled": result["runtime_scheduler_enabled"],
            "order_endpoint_called": result["order_endpoint_called"],
            "secret_value_accessed": result["secret_value_accessed"],
        }
        for name, result in fixtures.items()
    }
    all_fail_closed = all(item["waiting"] or item["blocked"] for item in fixture_summary.values())
    return {
        "status": "P41_NEGATIVE_FIXTURES_RECORDED",
        "created_at_utc": utc_now_canonical(),
        "fixture_count": len(fixture_summary),
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all_fail_closed,
        "fixture_results": fixture_summary,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def persist_operator_evidence_archive_index(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p41_operator_evidence_archive_index_audit_trail")
    report = build_operator_evidence_archive_index_report(root=cfg.root)
    checklist = _build_archive_checklist(report)
    markdown = _build_audit_trail_markdown(report)
    csv_text = _index_csv(report["archive_index"])
    negative = build_p41_negative_fixture_results(root=cfg.root)

    report_path = latest / "p41_operator_evidence_archive_index_report.json"
    summary_path = latest / "p41_operator_evidence_archive_index_summary.json"
    index_path = latest / "p41_operator_evidence_archive_index.json"
    csv_path = latest / "p41_operator_evidence_archive_index.csv"
    chain_path = latest / "p41_operator_evidence_audit_trail_chain.json"
    checklist_path = latest / "p41_operator_evidence_archive_checklist.md"
    markdown_path = latest / "p41_operator_evidence_audit_trail.md"
    negative_path = latest / "p41_operator_evidence_archive_index_negative_fixture_results.json"
    registry_record_path = latest / "p41_operator_evidence_archive_index_registry_record.json"

    output_paths = {
        "report": str(report_path),
        "summary": str(summary_path),
        "archive_index": str(index_path),
        "archive_index_csv": str(csv_path),
        "audit_trail_chain": str(chain_path),
        "checklist": str(checklist_path),
        "markdown": str(markdown_path),
    }
    report["output_paths"] = output_paths
    summary = {
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "archive_issue_count": report["archive_issue_count"],
        "archive_issue_codes": report["archive_issue_codes"],
        "expected_archive_artifact_count": report["expected_archive_artifact_count"],
        "present_archive_artifact_count": report["present_archive_artifact_count"],
        "missing_archive_artifact_count": report["missing_archive_artifact_count"],
        "archive_index_hash": report["archive_index_hash"],
        "audit_trail_chain_hash": report["audit_trail_chain_hash"],
        "p40_status": report["p40_status"],
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
        "id": stable_id("p41_operator_evidence_archive_index", {"archive_index_hash": report.get("archive_index_hash"), "audit_trail_chain_hash": report.get("audit_trail_chain_hash"), "status": report.get("status")}),
        "version": P41_OPERATOR_EVIDENCE_ARCHIVE_INDEX_VERSION,
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "created_at_utc": report["created_at_utc"],
        "archive_index_hash": report["archive_index_hash"],
        "audit_trail_chain_hash": report["audit_trail_chain_hash"],
        "archive_issue_count": report["archive_issue_count"],
        "runtime_authority": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }

    for directory in (latest, storage):
        atomic_write_json(directory / report_path.name, report)
        atomic_write_json(directory / summary_path.name, summary)
        atomic_write_json(directory / index_path.name, report["archive_index"])
        _atomic_write_text(directory / csv_path.name, csv_text)
        atomic_write_json(directory / chain_path.name, report["audit_trail_chain"])
        _atomic_write_text(directory / checklist_path.name, checklist)
        _atomic_write_text(directory / markdown_path.name, markdown)
    atomic_write_json(negative_path, negative)
    atomic_write_json(storage / negative_path.name, negative)
    append_registry_record(
        registry_path(cfg, P41_OPERATOR_EVIDENCE_ARCHIVE_INDEX_REGISTRY_NAME),
        registry_record,
        registry_name=P41_OPERATOR_EVIDENCE_ARCHIVE_INDEX_REGISTRY_NAME,
    )
    atomic_write_json(registry_record_path, registry_record)
    atomic_write_json(storage / registry_record_path.name, registry_record)
    return report
