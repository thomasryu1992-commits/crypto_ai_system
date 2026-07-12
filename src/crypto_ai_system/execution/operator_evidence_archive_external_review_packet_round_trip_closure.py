from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.operator_evidence_archive_external_review_packet_intake_validator import (
    P44_EXTERNAL_REVIEW_PACKET_INTAKE_VALIDATOR_VERSION,
    STATUS_BLOCKED_FAIL_CLOSED as P44_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY as P44_STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P44_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.execution.operator_evidence_archive_round_trip_seal import (
    STATUS_SEALED_REVIEW_ONLY as P43_STATUS_SEALED_REVIEW_ONLY,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_VERSION = "p45_external_review_packet_round_trip_closure_v1"
P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_REGISTRY_NAME = "p45_external_review_packet_round_trip_closure_registry"

STATUS_TEMPLATE_READY_REVIEW_ONLY = "P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_TEMPLATE_READY_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_BLOCKED_FAIL_CLOSED"

TEMPLATE_STATUS_READY_REVIEW_ONLY = "P45_REVIEWER_ACCEPTANCE_TEMPLATE_READY_REVIEW_ONLY"
TEMPLATE_TYPE = "external_review_packet_reviewer_acceptance_template"
CHAIN_TYPE = "external_review_packet_round_trip_closure_chain"

PENDING_REVIEW_DECISION = "PENDING_REVIEW"
ALLOWED_REVIEWER_DECISIONS = ("REVIEW_ACCEPTED", "REVIEW_DEFERRED", "REVIEW_REJECTED")
ALLOWED_TEMPLATE_DECISIONS = (PENDING_REVIEW_DECISION, *ALLOWED_REVIEWER_DECISIONS)

_REQUIRED_INPUT_FILES = (
    "p43_operator_evidence_archive_external_review_packet.json",
    "p43_operator_evidence_archive_round_trip_seal_chain.json",
    "p44_external_review_packet_intake_validator_report.json",
    "p44_external_review_packet_intake_validation_results.json",
    "p44_external_review_packet_hash_recheck_chain.json",
)

_EXECUTION_FIELDS_FOR_P45 = {
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
    "external_review_packet_intake_executes_runtime",
    "external_review_packet_intake_enables_scheduler",
    "external_review_packet_intake_allows_order_submission",
    "external_review_packet_intake_calls_endpoint",
    "external_review_packet_intake_reads_secret_value",
    "external_review_packet_intake_grants_runtime_authority",
    "reviewer_acceptance_executes_runtime",
    "reviewer_acceptance_enables_scheduler",
    "reviewer_acceptance_allows_order_submission",
    "reviewer_acceptance_calls_endpoint",
    "reviewer_acceptance_reads_secret_value",
    "reviewer_acceptance_grants_runtime_authority",
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
                if key in _EXECUTION_FIELDS_FOR_P45 and _bool(value):
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


def _build_reviewer_acceptance_template(
    *,
    p43_packet: Mapping[str, Any],
    p44_report: Mapping[str, Any],
    p44_validation_results: Mapping[str, Any],
    reviewer_decision: str = PENDING_REVIEW_DECISION,
) -> dict[str, Any]:
    input_payload = {
        "p43_packet_hash": sha256_json(dict(p43_packet)) if p43_packet else "",
        "p43_packet_seal_hash": p43_packet.get("seal_hash"),
        "p43_packet_seal_chain_hash": p43_packet.get("seal_chain_hash"),
        "p44_status": p44_report.get("status"),
        "p44_packet_hash": p44_report.get("packet_hash") or p44_validation_results.get("packet_hash"),
        "p44_hash_recheck_chain_hash": p44_report.get("hash_recheck_chain_hash"),
    }
    template: dict[str, Any] = {
        "template_type": TEMPLATE_TYPE,
        "version": P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_VERSION,
        "status": TEMPLATE_STATUS_READY_REVIEW_ONLY,
        "created_at_utc": utc_now_canonical(),
        "review_only": True,
        "runtime_authority": False,
        "reviewer_decision": reviewer_decision,
        "allowed_reviewer_decisions": list(ALLOWED_REVIEWER_DECISIONS),
        "decision_meaning": {
            "REVIEW_ACCEPTED": "Reviewer has completed review and accepts the sealed external review packet as review-only evidence. This does not grant runtime authority.",
            "REVIEW_DEFERRED": "Reviewer needs more evidence or operator follow-up. Runtime remains disabled.",
            "REVIEW_REJECTED": "Reviewer rejects the evidence packet. Runtime remains disabled and the packet must not be used for promotion.",
        },
        "required_acknowledgements": {
            "no_runtime_authority": True,
            "does_not_enable_scheduler": True,
            "does_not_allow_order_submission": True,
            "does_not_call_endpoint": True,
            "does_not_read_secret_values": True,
            "does_not_mutate_settings": True,
            "separate_runtime_approval_still_required": True,
        },
        "input_hashes": input_payload,
        "reviewer_fields_to_fill": {
            "reviewer_name_or_role": "",
            "reviewer_reference_id": "",
            "reviewed_at_utc": "",
            "review_notes": "",
        },
        "safe_state": {
            "runtime_scheduler_enabled": False,
            "live_scaled_execution_enabled": False,
            "live_order_submission_allowed": False,
            "order_endpoint_called": False,
            "secret_value_accessed": False,
        },
        "runtime_scheduler_enabled": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "reviewer_acceptance_executes_runtime": False,
        "reviewer_acceptance_enables_scheduler": False,
        "reviewer_acceptance_allows_order_submission": False,
        "reviewer_acceptance_calls_endpoint": False,
        "reviewer_acceptance_reads_secret_value": False,
        "reviewer_acceptance_grants_runtime_authority": False,
    }
    template["template_hash"] = sha256_json({key: value for key, value in template.items() if key != "template_hash"})
    return template


def _validate_template(template: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    def add(code: str, severity: str, message: str, evidence: Any = None) -> None:
        issue: dict[str, Any] = {"code": code, "severity": severity, "message": message}
        if evidence is not None:
            issue["evidence"] = evidence
        issues.append(issue)

    if not template:
        add("missing_reviewer_acceptance_template", "waiting", "Reviewer acceptance template is missing.")
        return issues
    if template.get("template_type") != TEMPLATE_TYPE:
        add("template_type_mismatch", "blocked", "Reviewer acceptance template type mismatch.", template.get("template_type"))
    if template.get("version") != P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_VERSION:
        add("template_version_mismatch", "blocked", "Reviewer acceptance template version mismatch.", template.get("version"))
    if template.get("status") != TEMPLATE_STATUS_READY_REVIEW_ONLY:
        add("template_status_not_ready_review_only", "blocked", "Reviewer acceptance template status is not ready review-only.", template.get("status"))
    if template.get("review_only") is not True:
        add("template_not_review_only", "blocked", "Reviewer acceptance template review_only must be true.")
    if _bool(template.get("runtime_authority")):
        add("runtime_authority_claimed", "blocked", "Reviewer acceptance template claims runtime authority.")
    decision = str(template.get("reviewer_decision", ""))
    if decision not in ALLOWED_TEMPLATE_DECISIONS:
        add("reviewer_decision_not_allowed", "blocked", "Reviewer decision is not in the allowed template decisions.", decision)
    allowed = tuple(template.get("allowed_reviewer_decisions", []))
    if allowed != ALLOWED_REVIEWER_DECISIONS:
        add("allowed_reviewer_decisions_mismatch", "blocked", "Allowed reviewer decisions were modified.", allowed)
    acknowledgements = template.get("required_acknowledgements") if isinstance(template.get("required_acknowledgements"), Mapping) else {}
    for field in (
        "no_runtime_authority",
        "does_not_enable_scheduler",
        "does_not_allow_order_submission",
        "does_not_call_endpoint",
        "does_not_read_secret_values",
        "does_not_mutate_settings",
        "separate_runtime_approval_still_required",
    ):
        if acknowledgements.get(field) is not True:
            add("missing_required_acknowledgement", "blocked", "Required reviewer acknowledgement is missing or false.", field)
    safe_state = template.get("safe_state") if isinstance(template.get("safe_state"), Mapping) else {}
    for field in ("runtime_scheduler_enabled", "live_scaled_execution_enabled", "live_order_submission_allowed", "order_endpoint_called", "secret_value_accessed"):
        if _bool(safe_state.get(field)):
            add("safe_state_truthy", "blocked", "Reviewer acceptance safe_state contains a truthy runtime/order/secret field.", field)
    reported_template_hash = template.get("template_hash")
    observed_template_hash = sha256_json({key: value for key, value in dict(template).items() if key != "template_hash"})
    if reported_template_hash and reported_template_hash != observed_template_hash:
        add("template_hash_mismatch", "blocked", "Reviewer acceptance template hash mismatch.", {"reported": reported_template_hash, "observed": observed_template_hash})
    return issues


def _build_validation_results(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "template_ready_review_only": report.get("status") == STATUS_TEMPLATE_READY_REVIEW_ONLY,
        "waiting": bool(report.get("waiting")),
        "blocked": bool(report.get("blocked")),
        "closure_issue_count": report.get("closure_issue_count"),
        "closure_issue_codes": report.get("closure_issue_codes", []),
        "reviewer_decision": report.get("reviewer_decision"),
        "template_hash": report.get("template_hash"),
        "closure_chain_hash": report.get("closure_chain_hash"),
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "runtime_authority": False,
    }


def _build_closure_chain(report: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "p43_status": report.get("p43_status"),
        "p44_status": report.get("p44_status"),
        "p43_packet_hash": report.get("p43_packet_hash"),
        "p43_seal_hash": report.get("p43_seal_hash"),
        "p43_seal_chain_hash": report.get("p43_seal_chain_hash"),
        "p44_packet_hash": report.get("p44_packet_hash"),
        "p44_hash_recheck_chain_hash": report.get("p44_hash_recheck_chain_hash"),
        "reviewer_decision": report.get("reviewer_decision"),
        "template_hash": report.get("template_hash"),
        "closure_issue_count": report.get("closure_issue_count"),
        "review_only": True,
        "runtime_authority": False,
    }
    return {
        "chain_type": CHAIN_TYPE,
        "chain_id": stable_id(CHAIN_TYPE, payload),
        **payload,
        "closure_chain_hash": sha256_json(payload),
    }


def _build_checklist(report: Mapping[str, Any]) -> str:
    checks = [
        ("P43 external review packet exists", bool(report.get("p43_packet_present"))),
        ("P43 seal chain exists", bool(report.get("p43_seal_chain_present"))),
        ("P44 intake report exists", bool(report.get("p44_report_present"))),
        ("P44 validation results exist", bool(report.get("p44_validation_results_present"))),
        ("P44 hash recheck chain exists", bool(report.get("p44_hash_recheck_chain_present"))),
        ("P43 status sealed review-only", report.get("p43_status") == P43_STATUS_SEALED_REVIEW_ONLY),
        ("P44 status valid review-only", report.get("p44_status") == P44_STATUS_VALID_REVIEW_ONLY),
        ("Reviewer acceptance template ready", report.get("template_status") == TEMPLATE_STATUS_READY_REVIEW_ONLY),
        ("Reviewer decision is allowed", report.get("reviewer_decision") in ALLOWED_TEMPLATE_DECISIONS),
        ("Template hash generated", bool(report.get("template_hash"))),
        ("Closure chain hash generated", bool(report.get("closure_chain_hash"))),
        ("Runtime remains disabled", not bool(report.get("runtime_flag_truthy"))),
        ("Scheduler remains disabled", not bool(report.get("scheduler_enabled"))),
        ("No endpoint evidence", not bool(report.get("endpoint_called"))),
        ("No secret value patterns", not bool(report.get("secret_detected"))),
        ("Authority remains review-only", not bool(report.get("runtime_authority_claimed"))),
    ]
    lines = ["# P45 External Review Packet Round-trip Closure Checklist", ""]
    for label, passed in checks:
        mark = "x" if passed else " "
        lines.append(f"- [{mark}] {label}")
    return "\n".join(lines).rstrip() + "\n"


def _build_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# P45 External Review Packet Round-trip Closure / Reviewer Acceptance Template",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "> This closure pack creates and validates a reviewer acceptance template. It is review-only and cannot enable runtime, scheduler, order submission, endpoint calls, secret access, settings mutation, or auto-promotion.",
        "",
        "## Summary",
        "",
        f"- Closure issue count: `{report.get('closure_issue_count')}`",
        f"- Reviewer decision: `{report.get('reviewer_decision')}`",
        f"- P43 status: `{report.get('p43_status')}`",
        f"- P44 status: `{report.get('p44_status')}`",
        f"- Template hash: `{report.get('template_hash')}`",
        f"- Closure chain hash: `{report.get('closure_chain_hash')}`",
        f"- Runtime authority claimed: `{report.get('runtime_authority_claimed')}`",
        "",
        "## Allowed Reviewer Decisions",
        "",
    ]
    for decision in ALLOWED_REVIEWER_DECISIONS:
        lines.append(f"- `{decision}`")
    lines.extend(["", "## Issue Codes", ""])
    codes = report.get("closure_issue_codes", [])
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


def build_external_review_packet_round_trip_closure_report(
    *,
    root: str | Path | None = None,
    p43_packet: Mapping[str, Any] | None = None,
    p43_seal_chain: Mapping[str, Any] | None = None,
    p44_report: Mapping[str, Any] | None = None,
    p44_validation_results: Mapping[str, Any] | None = None,
    p44_hash_recheck_chain: Mapping[str, Any] | None = None,
    reviewer_acceptance_template: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] = (),
) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    latest = _latest_dir(cfg)

    if p43_packet is None:
        loaded = _read_latest_json(cfg, "p43_operator_evidence_archive_external_review_packet.json", default={})
        p43_packet = loaded if isinstance(loaded, Mapping) else {}
    if p43_seal_chain is None:
        loaded = _read_latest_json(cfg, "p43_operator_evidence_archive_round_trip_seal_chain.json", default={})
        p43_seal_chain = loaded if isinstance(loaded, Mapping) else {}
    if p44_report is None:
        loaded = _read_latest_json(cfg, "p44_external_review_packet_intake_validator_report.json", default={})
        p44_report = loaded if isinstance(loaded, Mapping) else {}
    if p44_validation_results is None:
        loaded = _read_latest_json(cfg, "p44_external_review_packet_intake_validation_results.json", default={})
        p44_validation_results = loaded if isinstance(loaded, Mapping) else {}
    if p44_hash_recheck_chain is None:
        loaded = _read_latest_json(cfg, "p44_external_review_packet_hash_recheck_chain.json", default={})
        p44_hash_recheck_chain = loaded if isinstance(loaded, Mapping) else {}

    p43_packet = dict(p43_packet)
    p43_seal_chain = dict(p43_seal_chain)
    p44_report = dict(p44_report)
    p44_validation_results = dict(p44_validation_results)
    p44_hash_recheck_chain = dict(p44_hash_recheck_chain)
    if reviewer_acceptance_template is None:
        reviewer_acceptance_template = _build_reviewer_acceptance_template(
            p43_packet=p43_packet,
            p44_report=p44_report,
            p44_validation_results=p44_validation_results,
        )
    reviewer_acceptance_template = dict(reviewer_acceptance_template)

    scan_payloads: list[tuple[str, Any]] = [
        ("p43_packet", p43_packet),
        ("p43_seal_chain", p43_seal_chain),
        ("p44_report", p44_report),
        ("p44_validation_results", p44_validation_results),
        ("p44_hash_recheck_chain", p44_hash_recheck_chain),
        ("reviewer_acceptance_template", reviewer_acceptance_template),
        *list(extra_payloads_for_scan),
    ]
    unsafe_hits = _scan_truthy_execution_fields(scan_payloads)
    secret_hits = _scan_secret_value_patterns(scan_payloads)
    endpoint_hits = [hit for hit in unsafe_hits if "endpoint" in str(hit.get("field", "")) or hit.get("field") == "http_request_sent"]
    scheduler_hits = [hit for hit in unsafe_hits if "scheduler" in str(hit.get("field", ""))]
    authority_hits = [hit for hit in unsafe_hits if "authority" in str(hit.get("field", ""))]
    missing_input_files = [filename for filename in _REQUIRED_INPUT_FILES if not (latest / filename).exists()]

    issues: list[dict[str, Any]] = []

    def add_issue(code: str, severity: str, message: str, evidence: Any = None) -> None:
        issue: dict[str, Any] = {"code": code, "severity": severity, "message": message}
        if evidence is not None:
            issue["evidence"] = evidence
        issues.append(issue)

    if not p43_packet:
        add_issue("missing_p43_external_review_packet", "waiting", "P43 external review packet is missing.")
    if not p43_seal_chain:
        add_issue("missing_p43_seal_chain", "waiting", "P43 seal chain is missing.")
    if not p44_report:
        add_issue("missing_p44_report", "waiting", "P44 intake validator report is missing.")
    if not p44_validation_results:
        add_issue("missing_p44_validation_results", "waiting", "P44 validation results are missing.")
    if not p44_hash_recheck_chain:
        add_issue("missing_p44_hash_recheck_chain", "waiting", "P44 hash recheck chain is missing.")
    if missing_input_files:
        add_issue("missing_p45_input_files", "waiting", "One or more P45 input files are missing.", missing_input_files)

    p43_status = p43_packet.get("status")
    p44_status = p44_report.get("status") or p44_validation_results.get("status")
    if p43_packet and p43_status != P43_STATUS_SEALED_REVIEW_ONLY:
        add_issue("p43_packet_not_sealed_review_only", "blocked", "P43 packet status is not sealed review-only.", p43_status)
    if p44_status == P44_STATUS_BLOCKED_FAIL_CLOSED:
        add_issue("p44_blocked", "blocked", "P44 intake validator is blocked fail-closed.")
    elif p44_status == P44_STATUS_WAITING_REVIEW_ONLY:
        add_issue("p44_waiting", "waiting", "P44 intake validator is waiting review-only.")
    elif p44_report and p44_status != P44_STATUS_VALID_REVIEW_ONLY:
        add_issue("p44_not_valid_review_only", "blocked", "P44 intake validator status is not valid review-only.", p44_status)
    if _bool(p44_report.get("blocked")):
        add_issue("p44_blocked_flag", "blocked", "P44 blocked flag is truthy.")
    if p44_report.get("intake_issue_count", 0):
        add_issue("p44_reported_issues", "blocked", "P44 reported intake issues.", p44_report.get("intake_issue_codes", []))

    p43_packet_hash = sha256_json(p43_packet) if p43_packet else ""
    if p44_report and p43_packet_hash and p44_report.get("packet_hash") and p44_report.get("packet_hash") != p43_packet_hash:
        add_issue("p44_packet_hash_mismatch", "blocked", "P44 observed packet hash does not match P43 packet hash.", {"p43": p43_packet_hash, "p44": p44_report.get("packet_hash")})
    if p44_hash_recheck_chain and p44_report and p44_report.get("hash_recheck_chain_hash"):
        reported_chain_hash = p44_report.get("hash_recheck_chain_hash")
        acceptable_hashes = {p44_hash_recheck_chain.get("hash_recheck_chain_hash"), sha256_json(p44_hash_recheck_chain)}
        if reported_chain_hash not in acceptable_hashes:
            add_issue("p44_hash_recheck_chain_hash_mismatch", "blocked", "P44 hash recheck chain hash mismatch.", {"reported": reported_chain_hash, "acceptable": sorted(str(item) for item in acceptable_hashes if item)})

    for template_issue in _validate_template(reviewer_acceptance_template):
        issues.append(template_issue)

    if unsafe_hits:
        add_issue("runtime_flag_truthy", "blocked", "Truthy runtime/order/scheduler flag detected in P45 closure payloads.", unsafe_hits)
    if scheduler_hits:
        add_issue("scheduler_enabled", "blocked", "Scheduler truthy flag detected in P45 closure payloads.", scheduler_hits)
    if endpoint_hits:
        add_issue("endpoint_called", "blocked", "Endpoint-call truthy flag detected in P45 closure payloads.", endpoint_hits)
    if authority_hits:
        add_issue("runtime_authority_claimed", "blocked", "Runtime authority truthy flag detected in P45 closure payloads.", authority_hits)
    if secret_hits:
        add_issue("secret_detected", "blocked", "Secret value pattern detected in P45 closure payloads.", secret_hits)

    blocked = any(issue["severity"] == "blocked" for issue in issues)
    waiting = bool(issues) and not blocked
    status = STATUS_TEMPLATE_READY_REVIEW_ONLY
    if waiting:
        status = STATUS_WAITING_REVIEW_ONLY
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED

    template_hash = reviewer_acceptance_template.get("template_hash") or sha256_json(reviewer_acceptance_template)
    report: dict[str, Any] = {
        "version": P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_VERSION,
        "status": status,
        "waiting": waiting,
        "blocked": blocked,
        "created_at_utc": utc_now_canonical(),
        "p43_packet_present": bool(p43_packet),
        "p43_seal_chain_present": bool(p43_seal_chain),
        "p44_report_present": bool(p44_report),
        "p44_validation_results_present": bool(p44_validation_results),
        "p44_hash_recheck_chain_present": bool(p44_hash_recheck_chain),
        "p43_status": p43_status,
        "p44_status": p44_status,
        "template_status": reviewer_acceptance_template.get("status"),
        "reviewer_decision": reviewer_acceptance_template.get("reviewer_decision"),
        "allowed_reviewer_decisions": list(ALLOWED_REVIEWER_DECISIONS),
        "missing_input_file_count": len(missing_input_files),
        "missing_input_files": missing_input_files,
        "p43_packet_hash": p43_packet_hash,
        "p43_seal_hash": p43_packet.get("seal_hash"),
        "p43_seal_chain_hash": p43_packet.get("seal_chain_hash"),
        "p44_packet_hash": p44_report.get("packet_hash") or p44_validation_results.get("packet_hash"),
        "p44_hash_recheck_chain_hash": p44_report.get("hash_recheck_chain_hash") or p44_hash_recheck_chain.get("hash_recheck_chain_hash"),
        "template_hash": template_hash,
        "closure_issue_count": len(issues),
        "closure_issue_codes": [issue["code"] for issue in issues],
        "closure_issues": issues,
        "runtime_flag_truthy": bool(unsafe_hits),
        "scheduler_enabled": bool(scheduler_hits),
        "endpoint_called": bool(endpoint_hits),
        "secret_detected": bool(secret_hits),
        "runtime_authority_claimed": bool(authority_hits) or _bool(reviewer_acceptance_template.get("runtime_authority")),
        "reviewer_acceptance_executes_runtime": False,
        "reviewer_acceptance_enables_scheduler": False,
        "reviewer_acceptance_allows_order_submission": False,
        "reviewer_acceptance_calls_endpoint": False,
        "reviewer_acceptance_reads_secret_value": False,
        "reviewer_acceptance_grants_runtime_authority": False,
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
    report["closure_chain"] = _build_closure_chain(report)
    report["closure_chain_hash"] = report["closure_chain"]["closure_chain_hash"]
    return report


def build_p45_negative_fixture_results(root: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    p43_packet = _read_latest_json(cfg, "p43_operator_evidence_archive_external_review_packet.json", default={})
    p43_chain = _read_latest_json(cfg, "p43_operator_evidence_archive_round_trip_seal_chain.json", default={})
    p44_report = _read_latest_json(cfg, "p44_external_review_packet_intake_validator_report.json", default={})
    p44_validation = _read_latest_json(cfg, "p44_external_review_packet_intake_validation_results.json", default={})
    p44_chain = _read_latest_json(cfg, "p44_external_review_packet_hash_recheck_chain.json", default={})
    if not isinstance(p43_packet, Mapping):
        p43_packet = {}
    if not isinstance(p43_chain, Mapping):
        p43_chain = {}
    if not isinstance(p44_report, Mapping):
        p44_report = {}
    if not isinstance(p44_validation, Mapping):
        p44_validation = {}
    if not isinstance(p44_chain, Mapping):
        p44_chain = {}
    base_template = _build_reviewer_acceptance_template(p43_packet=p43_packet, p44_report=p44_report, p44_validation_results=p44_validation)

    fixtures: list[dict[str, Any]] = []

    def add(name: str, **kwargs: Any) -> None:
        params: dict[str, Any] = {
            "root": cfg.root,
            "p43_packet": p43_packet,
            "p43_seal_chain": p43_chain,
            "p44_report": p44_report,
            "p44_validation_results": p44_validation,
            "p44_hash_recheck_chain": p44_chain,
            "reviewer_acceptance_template": base_template,
        }
        params.update(kwargs)
        report = build_external_review_packet_round_trip_closure_report(**params)
        fixtures.append({"fixture": name, "status": report["status"], "blocked": report["blocked"], "waiting": report["waiting"], "issue_codes": report["closure_issue_codes"]})

    add("missing_p43_external_review_packet", p43_packet={})
    add("missing_p43_seal_chain", p43_seal_chain={})
    add("missing_p44_report", p44_report={})
    add("missing_p44_validation_results", p44_validation_results={})
    add("missing_p44_hash_recheck_chain", p44_hash_recheck_chain={})
    add("p44_blocked", p44_report={**p44_report, "status": P44_STATUS_BLOCKED_FAIL_CLOSED, "blocked": True})
    add("p44_waiting", p44_report={**p44_report, "status": P44_STATUS_WAITING_REVIEW_ONLY, "waiting": True})
    add("p44_reported_issues", p44_report={**p44_report, "intake_issue_count": 1, "intake_issue_codes": ["fixture_issue"]})
    add("reviewer_decision_not_allowed", reviewer_acceptance_template={**base_template, "reviewer_decision": "APPROVE_RUNTIME"})
    add("template_hash_mismatch", reviewer_acceptance_template={**base_template, "template_hash": "bad_hash"})
    add("secret_detected", extra_payloads_for_scan=[("secret", "BINANCE_API_SECRET=leak")])
    add("runtime_flag_truthy", extra_payloads_for_scan=[("runtime", {"live_scaled_execution_enabled": True})])
    add("scheduler_enabled", extra_payloads_for_scan=[("scheduler", {"runtime_scheduler_enabled": True})])
    add("endpoint_called", extra_payloads_for_scan=[("endpoint", {"order_endpoint_called": True})])
    add("runtime_authority_claimed", reviewer_acceptance_template={**base_template, "runtime_authority": True})
    add("reviewer_acceptance_executes_runtime", extra_payloads_for_scan=[("executes", {"reviewer_acceptance_executes_runtime": True})])

    return {
        "version": P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_VERSION,
        "status": "P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_NEGATIVE_FIXTURES_REVIEW_ONLY",
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked"] or item["waiting"] for item in fixtures),
        "review_only": True,
        "runtime_authority": False,
    }


def persist_external_review_packet_round_trip_closure(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p45_external_review_packet_round_trip_closure")
    report = build_external_review_packet_round_trip_closure_report(root=cfg.root)
    template = _build_reviewer_acceptance_template(
        p43_packet=_read_latest_json(cfg, "p43_operator_evidence_archive_external_review_packet.json", default={}) or {},
        p44_report=_read_latest_json(cfg, "p44_external_review_packet_intake_validator_report.json", default={}) or {},
        p44_validation_results=_read_latest_json(cfg, "p44_external_review_packet_intake_validation_results.json", default={}) or {},
    )
    negative = build_p45_negative_fixture_results(cfg.root)
    summary = {
        "version": P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_VERSION,
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "closure_issue_count": report["closure_issue_count"],
        "closure_issue_codes": report["closure_issue_codes"],
        "reviewer_decision": report["reviewer_decision"],
        "template_hash": report["template_hash"],
        "closure_chain_hash": report["closure_chain_hash"],
        "review_only": True,
        "runtime_authority": False,
    }
    outputs = {
        "p45_external_review_packet_round_trip_closure_report.json": report,
        "p45_external_review_packet_round_trip_closure_summary.json": summary,
        "p45_reviewer_acceptance_template.json": template,
        "p45_reviewer_acceptance_validation_results.json": report["validation_results"],
        "p45_external_review_packet_closure_chain.json": report["closure_chain"],
        "p45_external_review_packet_round_trip_closure_negative_fixture_results.json": negative,
    }
    for filename, payload in outputs.items():
        atomic_write_json(latest / filename, payload)
        atomic_write_json(storage / filename, payload)
    checklist = _build_checklist(report)
    markdown = _build_markdown(report)
    for filename, text in {
        "p45_reviewer_acceptance_checklist.md": checklist,
        "p45_external_review_packet_round_trip_closure.md": markdown,
    }.items():
        _atomic_write_text(latest / filename, text)
        _atomic_write_text(storage / filename, text)
    registry_record = append_registry_record(
        registry_path(cfg, P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_REGISTRY_NAME),
        {
            "version": P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_VERSION,
            "status": report["status"],
            "closure_issue_count": report["closure_issue_count"],
            "reviewer_decision": report["reviewer_decision"],
            "template_hash": report["template_hash"],
            "closure_chain_hash": report["closure_chain_hash"],
            "review_only": True,
            "runtime_authority": False,
            "runtime_scheduler_enabled": False,
            "live_order_submission_allowed": False,
            "order_endpoint_called": False,
            "secret_value_accessed": False,
        },
        registry_name=P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_REGISTRY_NAME,
        id_field="closure_record_id",
        hash_field="closure_record_hash",
        id_prefix="p45_closure",
    )
    atomic_write_json(latest / "p45_external_review_packet_round_trip_closure_registry_record.json", registry_record)
    atomic_write_json(storage / "p45_external_review_packet_round_trip_closure_registry_record.json", registry_record)
    report["registry_record"] = registry_record
    return report


__all__ = [
    "ALLOWED_REVIEWER_DECISIONS",
    "P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_VERSION",
    "STATUS_TEMPLATE_READY_REVIEW_ONLY",
    "STATUS_WAITING_REVIEW_ONLY",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "build_external_review_packet_round_trip_closure_report",
    "build_p45_negative_fixture_results",
    "persist_external_review_packet_round_trip_closure",
]
