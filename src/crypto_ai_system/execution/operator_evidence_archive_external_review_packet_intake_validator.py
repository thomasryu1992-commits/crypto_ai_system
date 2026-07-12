from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.operator_evidence_archive_round_trip_seal import (
    P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEAL_VERSION,
    STATUS_BLOCKED_FAIL_CLOSED as P43_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_SEALED_REVIEW_ONLY as P43_STATUS_SEALED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P43_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P44_EXTERNAL_REVIEW_PACKET_INTAKE_VALIDATOR_VERSION = "p44_external_review_packet_intake_validator_v1"
P44_EXTERNAL_REVIEW_PACKET_INTAKE_VALIDATOR_REGISTRY_NAME = "p44_external_review_packet_intake_validator_registry"

STATUS_VALID_REVIEW_ONLY = "P44_EXTERNAL_REVIEW_PACKET_INTAKE_VALIDATOR_VALID_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P44_EXTERNAL_REVIEW_PACKET_INTAKE_VALIDATOR_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P44_EXTERNAL_REVIEW_PACKET_INTAKE_VALIDATOR_BLOCKED_FAIL_CLOSED"

_EXPECTED_PACKET_TYPE = "operator_evidence_archive_round_trip_external_review_packet"
_EXPECTED_DECISION = "REVIEW_ONLY_EXTERNAL_REVIEW_PACKET_NOT_RUNTIME_AUTHORITY"
_REQUIRED_INPUT_FILES = (
    "p43_operator_evidence_archive_round_trip_seal_report.json",
    "p43_operator_evidence_archive_round_trip_seal_summary.json",
    "p43_operator_evidence_archive_external_review_packet.json",
    "p43_operator_evidence_archive_round_trip_seal_chain.json",
)
_SAFE_STATE_FALSE_FIELDS = (
    "runtime_scheduler_enabled",
    "live_scaled_execution_enabled",
    "live_order_submission_allowed",
    "order_endpoint_called",
    "secret_value_accessed",
)
_EXECUTION_FIELDS_FOR_P44 = {
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
    "round_trip_seal_executes_runtime",
    "round_trip_seal_enables_scheduler",
    "round_trip_seal_allows_order_submission",
    "round_trip_seal_calls_endpoint",
    "round_trip_seal_reads_secret_value",
    "round_trip_seal_grants_runtime_authority",
    "external_review_packet_intake_executes_runtime",
    "external_review_packet_intake_enables_scheduler",
    "external_review_packet_intake_allows_order_submission",
    "external_review_packet_intake_calls_endpoint",
    "external_review_packet_intake_reads_secret_value",
    "external_review_packet_intake_grants_runtime_authority",
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
                if key in _EXECUTION_FIELDS_FOR_P44 and _bool(value):
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


def _recompute_seal_hash_from_chain(seal_chain: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in dict(seal_chain).items() if key not in {"chain_id", "seal_hash"}}
    return sha256_json(payload)


def _build_validation_results(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "valid_review_only": report.get("status") == STATUS_VALID_REVIEW_ONLY,
        "waiting": bool(report.get("waiting")),
        "blocked": bool(report.get("blocked")),
        "intake_issue_count": report.get("intake_issue_count"),
        "intake_issue_codes": report.get("intake_issue_codes", []),
        "packet_hash": report.get("packet_hash"),
        "seal_hash": report.get("packet_seal_hash"),
        "observed_seal_hash": report.get("observed_seal_hash"),
        "seal_chain_hash": report.get("packet_seal_chain_hash"),
        "observed_seal_chain_hash": report.get("observed_seal_chain_hash"),
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "runtime_authority": False,
    }


def _build_hash_recheck_chain(report: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "p43_status": report.get("p43_status"),
        "packet_status": report.get("packet_status"),
        "packet_hash": report.get("packet_hash"),
        "reported_seal_hash": report.get("packet_seal_hash"),
        "observed_seal_hash": report.get("observed_seal_hash"),
        "reported_seal_chain_hash": report.get("packet_seal_chain_hash"),
        "observed_seal_chain_hash": report.get("observed_seal_chain_hash"),
        "safe_state_hash": report.get("safe_state_hash"),
        "intake_issue_count": report.get("intake_issue_count"),
        "review_only": True,
        "runtime_authority": False,
    }
    return {
        "chain_id": stable_id("p44_external_review_packet_intake_hash_recheck_chain", payload),
        **payload,
        "hash_recheck_chain_hash": sha256_json(payload),
    }


def _build_checklist(report: Mapping[str, Any]) -> str:
    checks = [
        ("P43 report exists", bool(report.get("p43_report_present"))),
        ("P43 summary exists", bool(report.get("p43_summary_present"))),
        ("P43 external review packet exists", bool(report.get("p43_packet_present"))),
        ("P43 seal chain exists", bool(report.get("p43_seal_chain_present"))),
        ("P43 status sealed review-only", report.get("p43_status") == P43_STATUS_SEALED_REVIEW_ONLY),
        ("Packet status sealed review-only", report.get("packet_status") == P43_STATUS_SEALED_REVIEW_ONLY),
        ("Packet is review-only", bool(report.get("packet_review_only"))),
        ("Packet grants no runtime authority", not bool(report.get("packet_runtime_authority"))),
        ("Seal hash matches", not bool(report.get("seal_hash_mismatch"))),
        ("Seal chain hash matches", not bool(report.get("seal_chain_hash_mismatch"))),
        ("Safe state remains disabled", not bool(report.get("safe_state_truthy"))),
        ("No intake issues", report.get("intake_issue_count") == 0),
        ("Runtime remains disabled", not bool(report.get("runtime_flag_truthy"))),
        ("Scheduler remains disabled", not bool(report.get("scheduler_enabled"))),
        ("No endpoint evidence", not bool(report.get("endpoint_called"))),
        ("No secret value patterns", not bool(report.get("secret_detected"))),
        ("Authority remains review-only", not bool(report.get("runtime_authority_claimed"))),
    ]
    lines = ["# P44 External Review Packet Intake Checklist", ""]
    for label, passed in checks:
        mark = "x" if passed else " "
        lines.append(f"- [{mark}] {label}")
    return "\n".join(lines).rstrip() + "\n"


def _build_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# P44 External Review Packet Intake Validator / Hash Recheck Pack",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "> This validator checks a P43 sealed external review packet. It is review-only and cannot enable runtime, scheduler, order submission, endpoint calls, secret access, settings mutation, or auto-promotion.",
        "",
        "## Summary",
        "",
        f"- Intake issue count: `{report.get('intake_issue_count')}`",
        f"- P43 status: `{report.get('p43_status')}`",
        f"- Packet status: `{report.get('packet_status')}`",
        f"- Packet hash: `{report.get('packet_hash')}`",
        f"- Seal hash mismatch: `{report.get('seal_hash_mismatch')}`",
        f"- Seal chain hash mismatch: `{report.get('seal_chain_hash_mismatch')}`",
        f"- Secret detected: `{report.get('secret_detected')}`",
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


def build_external_review_packet_intake_validator_report(
    *,
    root: str | Path | None = None,
    p43_report: Mapping[str, Any] | None = None,
    p43_summary: Mapping[str, Any] | None = None,
    p43_packet: Mapping[str, Any] | None = None,
    p43_seal_chain: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] = (),
) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    latest = _latest_dir(cfg)

    if p43_report is None:
        loaded = _read_latest_json(cfg, "p43_operator_evidence_archive_round_trip_seal_report.json", default={})
        p43_report = loaded if isinstance(loaded, Mapping) else {}
    if p43_summary is None:
        loaded = _read_latest_json(cfg, "p43_operator_evidence_archive_round_trip_seal_summary.json", default={})
        p43_summary = loaded if isinstance(loaded, Mapping) else {}
    if p43_packet is None:
        loaded = _read_latest_json(cfg, "p43_operator_evidence_archive_external_review_packet.json", default={})
        p43_packet = loaded if isinstance(loaded, Mapping) else {}
    if p43_seal_chain is None:
        loaded = _read_latest_json(cfg, "p43_operator_evidence_archive_round_trip_seal_chain.json", default={})
        p43_seal_chain = loaded if isinstance(loaded, Mapping) else {}

    p43_report = dict(p43_report)
    p43_summary = dict(p43_summary)
    p43_packet = dict(p43_packet)
    p43_seal_chain = dict(p43_seal_chain)

    scan_payloads: list[tuple[str, Any]] = [
        ("p43_report", p43_report),
        ("p43_summary", p43_summary),
        ("p43_packet", p43_packet),
        ("p43_seal_chain", p43_seal_chain),
        *list(extra_payloads_for_scan),
    ]
    unsafe_hits = _scan_truthy_execution_fields(scan_payloads)
    secret_hits = _scan_secret_value_patterns(scan_payloads)
    endpoint_hits = [hit for hit in unsafe_hits if "endpoint" in str(hit.get("field", "")) or hit.get("field") == "http_request_sent"]
    scheduler_hits = [hit for hit in unsafe_hits if "scheduler" in str(hit.get("field", ""))]
    authority_hits = [hit for hit in unsafe_hits if "authority" in str(hit.get("field", ""))]

    p43_status = p43_report.get("status") or p43_summary.get("status")
    packet_status = p43_packet.get("status")
    missing_input_files = [filename for filename in _REQUIRED_INPUT_FILES if not (latest / filename).exists()]

    observed_seal_hash = _recompute_seal_hash_from_chain(p43_seal_chain) if p43_seal_chain else ""
    observed_seal_chain_hash = sha256_json(p43_seal_chain) if p43_seal_chain else ""
    packet_hash = sha256_json(p43_packet) if p43_packet else ""
    safe_state = p43_packet.get("safe_state") if isinstance(p43_packet.get("safe_state"), Mapping) else {}
    safe_state_truthy_hits = [field for field in _SAFE_STATE_FALSE_FIELDS if _bool(safe_state.get(field))]
    safe_state_hash = sha256_json(dict(safe_state)) if isinstance(safe_state, Mapping) else ""

    issues: list[dict[str, Any]] = []

    def add_issue(code: str, severity: str, message: str, evidence: Any = None) -> None:
        issue = {"code": code, "severity": severity, "message": message}
        if evidence is not None:
            issue["evidence"] = evidence
        issues.append(issue)

    if not p43_report:
        add_issue("missing_p43_report", "waiting", "P43 seal report is missing.")
    if not p43_summary:
        add_issue("missing_p43_summary", "waiting", "P43 seal summary is missing.")
    if not p43_packet:
        add_issue("missing_p43_external_review_packet", "waiting", "P43 external review packet is missing.")
    if not p43_seal_chain:
        add_issue("missing_p43_seal_chain", "waiting", "P43 seal chain is missing.")
    if missing_input_files:
        add_issue("missing_p43_input_files", "waiting", "One or more required P43 intake input artifacts are missing.", missing_input_files)

    if p43_status == P43_STATUS_BLOCKED_FAIL_CLOSED:
        add_issue("p43_blocked", "blocked", "P43 seal report is blocked fail-closed.")
    elif p43_status == P43_STATUS_WAITING_REVIEW_ONLY:
        add_issue("p43_waiting", "waiting", "P43 seal report is waiting review-only.")
    elif p43_report and p43_status != P43_STATUS_SEALED_REVIEW_ONLY:
        add_issue("p43_status_not_sealed_review_only", "blocked", "P43 seal report is not sealed review-only.", p43_status)

    if p43_report.get("seal_issue_count", 0):
        add_issue("p43_reported_issues", "blocked", "P43 seal report contains issues.", p43_report.get("seal_issue_codes", []))
    if _bool(p43_report.get("blocked")):
        add_issue("p43_blocked_flag", "blocked", "P43 blocked flag is truthy.")

    if p43_packet:
        if p43_packet.get("packet_type") != _EXPECTED_PACKET_TYPE:
            add_issue("packet_type_mismatch", "blocked", "P43 packet type does not match the expected external review packet type.", p43_packet.get("packet_type"))
        if p43_packet.get("version") != P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEAL_VERSION:
            add_issue("packet_version_mismatch", "blocked", "P43 packet version mismatch.", p43_packet.get("version"))
        if packet_status != P43_STATUS_SEALED_REVIEW_ONLY:
            add_issue("packet_status_not_sealed_review_only", "blocked", "P43 packet status is not sealed review-only.", packet_status)
        if p43_packet.get("decision") != _EXPECTED_DECISION:
            add_issue("packet_decision_mismatch", "blocked", "P43 packet decision is not the expected review-only decision.", p43_packet.get("decision"))
        if p43_packet.get("review_only") is not True:
            add_issue("packet_not_review_only", "blocked", "P43 packet review_only flag is not true.")
        if _bool(p43_packet.get("runtime_authority")):
            add_issue("runtime_authority_claimed", "blocked", "P43 packet claims runtime authority.")
        if p43_packet.get("issue_count") not in {0, None}:
            add_issue("packet_reported_issues", "blocked", "P43 packet reported issues.", p43_packet.get("issue_codes", []))
        if safe_state_truthy_hits:
            add_issue("safe_state_truthy", "blocked", "P43 packet safe_state contains truthy runtime/order/secret fields.", safe_state_truthy_hits)

    packet_seal_hash = p43_packet.get("seal_hash")
    report_seal_hash = p43_report.get("seal_hash") or p43_summary.get("seal_hash")
    chain_seal_hash = p43_seal_chain.get("seal_hash")
    if p43_packet and p43_seal_chain:
        if packet_seal_hash != chain_seal_hash or packet_seal_hash != observed_seal_hash or (report_seal_hash and packet_seal_hash != report_seal_hash):
            add_issue("seal_hash_mismatch", "blocked", "P43 seal hash does not match packet/report/chain recomputation.", {"packet": packet_seal_hash, "report": report_seal_hash, "chain": chain_seal_hash, "observed": observed_seal_hash})

    packet_seal_chain_hash = p43_packet.get("seal_chain_hash")
    report_seal_chain_hash = p43_report.get("seal_chain_hash") or p43_summary.get("seal_chain_hash")
    if p43_packet and p43_seal_chain:
        if packet_seal_chain_hash != observed_seal_chain_hash or (report_seal_chain_hash and packet_seal_chain_hash != report_seal_chain_hash):
            add_issue("seal_chain_hash_mismatch", "blocked", "P43 seal chain hash does not match packet/report/observed chain.", {"packet": packet_seal_chain_hash, "report": report_seal_chain_hash, "observed": observed_seal_chain_hash})

    packet_input_hashes = p43_packet.get("input_hashes") if isinstance(p43_packet.get("input_hashes"), Mapping) else {}
    if p43_seal_chain and packet_input_hashes:
        for packet_key, chain_key in (
            ("p41_archive_index_hash", "p41_archive_index_hash"),
            ("p41_audit_trail_chain_hash", "p41_audit_trail_chain_hash"),
            ("p42_hash_recheck_chain_hash", "p42_hash_recheck_chain_hash"),
        ):
            if packet_input_hashes.get(packet_key) != p43_seal_chain.get(chain_key):
                add_issue("input_hash_mismatch", "blocked", "P43 packet input hash does not match seal chain.", {"packet_key": packet_key, "packet": packet_input_hashes.get(packet_key), "chain": p43_seal_chain.get(chain_key)})

    if unsafe_hits:
        add_issue("runtime_flag_truthy", "blocked", "Truthy runtime/order/scheduler flag detected in P44 intake payloads.", unsafe_hits)
    if scheduler_hits:
        add_issue("scheduler_enabled", "blocked", "Scheduler truthy flag detected in P44 intake payloads.", scheduler_hits)
    if endpoint_hits:
        add_issue("endpoint_called", "blocked", "Endpoint-call truthy flag detected in P44 intake payloads.", endpoint_hits)
    if authority_hits:
        add_issue("runtime_authority_claimed", "blocked", "Runtime authority truthy flag detected in P44 intake payloads.", authority_hits)
    if secret_hits:
        add_issue("secret_detected", "blocked", "Secret value pattern detected in P44 intake payloads.", secret_hits)

    blocked = any(issue["severity"] == "blocked" for issue in issues)
    waiting = bool(issues) and not blocked
    status = STATUS_VALID_REVIEW_ONLY
    if waiting:
        status = STATUS_WAITING_REVIEW_ONLY
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED

    report: dict[str, Any] = {
        "version": P44_EXTERNAL_REVIEW_PACKET_INTAKE_VALIDATOR_VERSION,
        "status": status,
        "waiting": waiting,
        "blocked": blocked,
        "created_at_utc": utc_now_canonical(),
        "p43_status": p43_status,
        "packet_status": packet_status,
        "p43_report_present": bool(p43_report),
        "p43_summary_present": bool(p43_summary),
        "p43_packet_present": bool(p43_packet),
        "p43_seal_chain_present": bool(p43_seal_chain),
        "packet_type": p43_packet.get("packet_type"),
        "packet_version": p43_packet.get("version"),
        "packet_review_only": p43_packet.get("review_only") is True,
        "packet_runtime_authority": _bool(p43_packet.get("runtime_authority")),
        "missing_input_file_count": len(missing_input_files),
        "missing_input_files": missing_input_files,
        "packet_hash": packet_hash,
        "packet_seal_hash": packet_seal_hash,
        "observed_seal_hash": observed_seal_hash,
        "packet_seal_chain_hash": packet_seal_chain_hash,
        "observed_seal_chain_hash": observed_seal_chain_hash,
        "safe_state_hash": safe_state_hash,
        "seal_hash_mismatch": any(issue["code"] == "seal_hash_mismatch" for issue in issues),
        "seal_chain_hash_mismatch": any(issue["code"] == "seal_chain_hash_mismatch" for issue in issues),
        "safe_state_truthy": bool(safe_state_truthy_hits),
        "intake_issue_count": len(issues),
        "intake_issue_codes": [issue["code"] for issue in issues],
        "intake_issues": issues,
        "runtime_flag_truthy": bool(unsafe_hits),
        "scheduler_enabled": bool(scheduler_hits),
        "endpoint_called": bool(endpoint_hits),
        "secret_detected": bool(secret_hits),
        "runtime_authority_claimed": bool(authority_hits) or _bool(p43_packet.get("runtime_authority")),
        "external_review_packet_intake_executes_runtime": False,
        "external_review_packet_intake_enables_scheduler": False,
        "external_review_packet_intake_allows_order_submission": False,
        "external_review_packet_intake_calls_endpoint": False,
        "external_review_packet_intake_reads_secret_value": False,
        "external_review_packet_intake_grants_runtime_authority": False,
        "runtime_scheduler_enabled": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "review_only": True,
        "runtime_authority": False,
        "execution_flags": default_execution_flag_state(),
    }
    report["validation_results"] = _build_validation_results(report)
    report["hash_recheck_chain"] = _build_hash_recheck_chain(report)
    report["hash_recheck_chain_hash"] = sha256_json(report["hash_recheck_chain"])
    return report


def build_p44_negative_fixture_results(root: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    p43_report = _read_latest_json(cfg, "p43_operator_evidence_archive_round_trip_seal_report.json", default={})
    p43_summary = _read_latest_json(cfg, "p43_operator_evidence_archive_round_trip_seal_summary.json", default={})
    p43_packet = _read_latest_json(cfg, "p43_operator_evidence_archive_external_review_packet.json", default={})
    p43_chain = _read_latest_json(cfg, "p43_operator_evidence_archive_round_trip_seal_chain.json", default={})
    if not isinstance(p43_report, Mapping):
        p43_report = {}
    if not isinstance(p43_summary, Mapping):
        p43_summary = {}
    if not isinstance(p43_packet, Mapping):
        p43_packet = {}
    if not isinstance(p43_chain, Mapping):
        p43_chain = {}

    fixtures: list[tuple[str, dict[str, Any]]] = []

    def add(name: str, **kwargs: Any) -> None:
        params: dict[str, Any] = {
            "root": cfg.root,
            "p43_report": p43_report,
            "p43_summary": p43_summary,
            "p43_packet": p43_packet,
            "p43_seal_chain": p43_chain,
        }
        params.update(kwargs)
        report = build_external_review_packet_intake_validator_report(**params)
        fixtures.append({"fixture": name, "status": report["status"], "blocked": report["blocked"], "waiting": report["waiting"], "issue_codes": report["intake_issue_codes"]})

    add("missing_p43_report", p43_report={})
    add("missing_p43_summary", p43_summary={})
    add("missing_p43_external_review_packet", p43_packet={})
    add("missing_p43_seal_chain", p43_seal_chain={})
    add("p43_blocked", p43_report={**dict(p43_report), "status": P43_STATUS_BLOCKED_FAIL_CLOSED, "blocked": True})
    add("p43_waiting", p43_report={**dict(p43_report), "status": P43_STATUS_WAITING_REVIEW_ONLY, "waiting": True})
    add("packet_status_not_sealed_review_only", p43_packet={**dict(p43_packet), "status": "BAD_STATUS"})
    add("seal_hash_mismatch", p43_packet={**dict(p43_packet), "seal_hash": "bad_hash"})
    add("seal_chain_hash_mismatch", p43_packet={**dict(p43_packet), "seal_chain_hash": "bad_hash"})
    add("safe_state_truthy", p43_packet={**dict(p43_packet), "safe_state": {**dict(p43_packet.get("safe_state", {})), "live_order_submission_allowed": True}})
    add("secret_detected", extra_payloads_for_scan=[("secret", "BINANCE_API_SECRET=leak")])
    add("runtime_flag_truthy", extra_payloads_for_scan=[("runtime", {"live_scaled_execution_enabled": True})])
    add("scheduler_enabled", extra_payloads_for_scan=[("scheduler", {"runtime_scheduler_enabled": True})])
    add("endpoint_called", extra_payloads_for_scan=[("endpoint", {"order_endpoint_called": True})])
    add("runtime_authority_claimed", p43_packet={**dict(p43_packet), "runtime_authority": True})
    add("intake_validator_executes_runtime", extra_payloads_for_scan=[("p44", {"external_review_packet_intake_executes_runtime": True})])

    all_fail_closed = all(item["blocked"] or item["waiting"] for item in fixtures)
    return {
        "status": "P44_NEGATIVE_FIXTURES_RECORDED",
        "fixture_count": len(fixtures),
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all_fail_closed,
        "fixtures": fixtures,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def persist_external_review_packet_intake_validator(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p44_external_review_packet_intake_validator")
    report = build_external_review_packet_intake_validator_report(root=cfg.root)
    checklist = _build_checklist(report)
    markdown = _build_markdown(report)
    negative = build_p44_negative_fixture_results(root=cfg.root)

    report_path = latest / "p44_external_review_packet_intake_validator_report.json"
    summary_path = latest / "p44_external_review_packet_intake_validator_summary.json"
    validation_path = latest / "p44_external_review_packet_intake_validation_results.json"
    chain_path = latest / "p44_external_review_packet_hash_recheck_chain.json"
    checklist_path = latest / "p44_external_review_packet_intake_checklist.md"
    markdown_path = latest / "p44_external_review_packet_intake_validator.md"
    negative_path = latest / "p44_external_review_packet_intake_validator_negative_fixture_results.json"
    registry_record_path = latest / "p44_external_review_packet_intake_validator_registry_record.json"

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
        "p43_status": report["p43_status"],
        "packet_status": report["packet_status"],
        "packet_hash": report["packet_hash"],
        "packet_seal_hash": report["packet_seal_hash"],
        "observed_seal_hash": report["observed_seal_hash"],
        "packet_seal_chain_hash": report["packet_seal_chain_hash"],
        "observed_seal_chain_hash": report["observed_seal_chain_hash"],
        "hash_recheck_chain_hash": report["hash_recheck_chain_hash"],
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
        "id": stable_id("p44_external_review_packet_intake_validator", {"packet_hash": report.get("packet_hash"), "status": report.get("status"), "hash_recheck_chain_hash": report.get("hash_recheck_chain_hash")}),
        "version": P44_EXTERNAL_REVIEW_PACKET_INTAKE_VALIDATOR_VERSION,
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "created_at_utc": report["created_at_utc"],
        "packet_hash": report["packet_hash"],
        "hash_recheck_chain_hash": report["hash_recheck_chain_hash"],
        "intake_issue_count": report["intake_issue_count"],
        "runtime_authority": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }

    atomic_write_json(report_path, report)
    atomic_write_json(summary_path, summary)
    atomic_write_json(validation_path, report["validation_results"])
    atomic_write_json(chain_path, report["hash_recheck_chain"])
    _atomic_write_text(checklist_path, checklist)
    _atomic_write_text(markdown_path, markdown)
    atomic_write_json(negative_path, negative)
    atomic_write_json(registry_record_path, registry_record)

    atomic_write_json(storage / report_path.name, report)
    atomic_write_json(storage / summary_path.name, summary)
    atomic_write_json(storage / validation_path.name, report["validation_results"])
    atomic_write_json(storage / chain_path.name, report["hash_recheck_chain"])
    _atomic_write_text(storage / checklist_path.name, checklist)
    _atomic_write_text(storage / markdown_path.name, markdown)
    atomic_write_json(storage / negative_path.name, negative)
    atomic_write_json(storage / registry_record_path.name, registry_record)

    append_registry_record(
        registry_path(cfg, P44_EXTERNAL_REVIEW_PACKET_INTAKE_VALIDATOR_REGISTRY_NAME),
        registry_record,
        registry_name=P44_EXTERNAL_REVIEW_PACKET_INTAKE_VALIDATOR_REGISTRY_NAME,
    )
    return report
