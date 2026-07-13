from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.operator_support_bundle_intake_validator import (
    STATUS_BLOCKED_FAIL_CLOSED as P39_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY as P39_STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P39_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.execution.operator_support_bundle_troubleshooting_export_pack import (
    STATUS_BLOCKED_FAIL_CLOSED as P38_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY as P38_STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P38_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P40_OPERATOR_SUPPORT_BUNDLE_ROUND_TRIP_VERSION = "p40_operator_support_bundle_round_trip_verification_v1"
P40_OPERATOR_SUPPORT_BUNDLE_ROUND_TRIP_REGISTRY_NAME = "p40_operator_support_bundle_round_trip_registry"

STATUS_VERIFIED_REVIEW_ONLY = "P40_OPERATOR_SUPPORT_BUNDLE_ROUND_TRIP_VERIFIED_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P40_OPERATOR_SUPPORT_BUNDLE_ROUND_TRIP_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P40_OPERATOR_SUPPORT_BUNDLE_ROUND_TRIP_BLOCKED_FAIL_CLOSED"

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
_EXECUTION_FIELDS_FOR_P40 = {
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
                if key in _EXECUTION_FIELDS_FOR_P40 and _bool(value):
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


def _manifest_by_filename(manifest: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(manifest, list):
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for item in manifest:
        if isinstance(item, Mapping) and item.get("filename"):
            result[str(item["filename"])] = item
    return result


def _build_round_trip_checklist(report: Mapping[str, Any]) -> str:
    checks = [
        ("P38 share packet exists", bool(report.get("p38_share_packet_present"))),
        ("P38 manifest exists", bool(report.get("p38_manifest_present"))),
        ("P39 intake report exists", bool(report.get("p39_report_present"))),
        ("P39 validation results exist", bool(report.get("p39_validation_present"))),
        ("P38 share packet status is generated review-only", report.get("p38_share_packet_status") == P38_STATUS_GENERATED_REVIEW_ONLY),
        ("P39 intake status is valid review-only", report.get("p39_status") == P39_STATUS_VALID_REVIEW_ONLY),
        ("P38 share packet hash matches P39 observed hash", not any(code == "share_packet_hash_mismatch" for code in report.get("round_trip_issue_codes", []))),
        ("P38 manifest hash matches P39 observed hash", not any(code == "manifest_hash_mismatch" for code in report.get("round_trip_issue_codes", []))),
        ("P39 reported no intake issues", report.get("p39_intake_issue_count") == 0),
        ("Runtime remains disabled", not bool(report.get("runtime_flag_truthy"))),
        ("No endpoint evidence", not bool(report.get("endpoint_called"))),
        ("No secret value patterns", not bool(report.get("secret_detected"))),
        ("Authority remains review-only", not bool(report.get("runtime_authority_claimed"))),
    ]
    lines = ["# P40 Round-trip Checklist", ""]
    for label, passed in checks:
        mark = "x" if passed else " "
        lines.append(f"- [{mark}] {label}")
    return "\n".join(lines).rstrip() + "\n"


def _build_round_trip_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# P40 Support Bundle Round-trip Verification",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "> This pack verifies P38 export -> P39 intake round-trip hashes. It is review-only and never enables runtime, scheduler, orders, endpoints, or secret access.",
        "",
        "## Round-trip Decision",
        "",
        f"- Waiting: `{report.get('waiting')}`",
        f"- Blocked: `{report.get('blocked')}`",
        f"- Issue count: `{report.get('round_trip_issue_count')}`",
        f"- Round-trip hash: `{report.get('round_trip_hash')}`",
        "",
        "## Hash Chain",
        "",
        f"- P38 share packet hash: `{report.get('p38_share_packet_sha256')}`",
        f"- P39 observed share packet hash: `{report.get('p39_observed_share_packet_sha256')}`",
        f"- P38 manifest hash: `{report.get('p38_manifest_sha256')}`",
        f"- P39 observed manifest hash: `{report.get('p39_observed_manifest_sha256')}`",
        "",
        "## Issue Codes",
        "",
    ]
    codes = report.get("round_trip_issue_codes", [])
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
        "",
        "## Allowed Read-only Commands",
        "",
    ])
    for command in _ALLOWED_READ_ONLY_COMMANDS:
        lines.append(f"- `{command}`")
    return "\n".join(lines).rstrip() + "\n"


def build_operator_support_bundle_round_trip_report(
    *,
    root: str | Path | None = None,
    p38_share_packet: Mapping[str, Any] | None = None,
    p38_manifest: Sequence[Mapping[str, Any]] | None = None,
    p39_report: Mapping[str, Any] | None = None,
    p39_validation_results: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] = (),
) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    if p38_share_packet is None:
        loaded_share = _read_latest_json(cfg, "p38_operator_support_bundle_share_packet.json", default={})
        p38_share_packet = loaded_share if isinstance(loaded_share, Mapping) else {}
    if p38_manifest is None:
        loaded_manifest = _read_latest_json(cfg, "p38_operator_support_bundle_manifest.json", default=[])
        p38_manifest = loaded_manifest if isinstance(loaded_manifest, list) else []
    if p39_report is None:
        loaded_p39_report = _read_latest_json(cfg, "p39_operator_support_bundle_intake_validator_report.json", default={})
        p39_report = loaded_p39_report if isinstance(loaded_p39_report, Mapping) else {}
    if p39_validation_results is None:
        loaded_validation = _read_latest_json(cfg, "p39_operator_support_bundle_intake_validation_results.json", default={})
        p39_validation_results = loaded_validation if isinstance(loaded_validation, Mapping) else {}

    p38_share_packet = dict(p38_share_packet)
    p38_manifest_list = [dict(item) for item in p38_manifest if isinstance(item, Mapping)]
    p39_report = dict(p39_report)
    p39_validation_results = dict(p39_validation_results)

    p38_share_packet_sha256 = sha256_json(p38_share_packet) if p38_share_packet else None
    p38_manifest_sha256 = sha256_json(p38_manifest_list) if p38_manifest_list else None
    p39_observed_share_packet_sha256 = p39_report.get("share_packet_sha256")
    p39_observed_manifest_sha256 = p39_report.get("manifest_sha256")

    scan_payloads: list[tuple[str, Any]] = [
        ("p38_share_packet", p38_share_packet),
        ("p38_manifest", p38_manifest_list),
        ("p39_report", p39_report),
        ("p39_validation_results", p39_validation_results),
        *list(extra_payloads_for_scan),
    ]
    unsafe_hits = _scan_truthy_execution_fields(scan_payloads)
    secret_hits = _scan_secret_value_patterns(scan_payloads)
    endpoint_hits = [hit for hit in unsafe_hits if "endpoint" in hit.get("field", "") or hit.get("field") == "http_request_sent"]
    scheduler_hits = [hit for hit in unsafe_hits if "scheduler" in hit.get("field", "")]
    authority_hits = [hit for hit in unsafe_hits if "authority" in hit.get("field", "")]

    issues: list[dict[str, Any]] = []

    def add_issue(code: str, severity: str, message: str, evidence: Any = None) -> None:
        issue = {"code": code, "severity": severity, "message": message}
        if evidence is not None:
            issue["evidence"] = evidence
        issues.append(issue)

    if not p38_share_packet:
        add_issue("missing_p38_share_packet", "waiting", "P38 share packet is missing or empty.")
    if not p38_manifest_list:
        add_issue("missing_p38_manifest", "blocked", "P38 manifest is missing or empty.")
    if not p39_report:
        add_issue("missing_p39_report", "waiting", "P39 intake report is missing or empty.")
    if not p39_validation_results:
        add_issue("missing_p39_validation_results", "waiting", "P39 intake validation results are missing or empty.")

    p38_status = str(p38_share_packet.get("status", "")) if p38_share_packet else ""
    p39_status = str(p39_report.get("status", "")) if p39_report else ""

    if p38_status == P38_STATUS_BLOCKED_FAIL_CLOSED or _bool(p38_share_packet.get("blocked")):
        add_issue("p38_share_packet_blocked", "blocked", "P38 share packet is blocked fail-closed.")
    if p38_status == P38_STATUS_WAITING_REVIEW_ONLY or _bool(p38_share_packet.get("waiting")):
        add_issue("p38_share_packet_waiting", "waiting", "P38 share packet is waiting.")
    if p38_status and p38_status != P38_STATUS_GENERATED_REVIEW_ONLY:
        add_issue("p38_share_packet_not_generated", "waiting", f"P38 share packet status is not generated review-only: {p38_status}")

    if p39_status == P39_STATUS_BLOCKED_FAIL_CLOSED or _bool(p39_report.get("blocked")):
        add_issue("p39_intake_blocked", "blocked", "P39 intake report is blocked fail-closed.")
    if p39_status == P39_STATUS_WAITING_REVIEW_ONLY or _bool(p39_report.get("waiting")):
        add_issue("p39_intake_waiting", "waiting", "P39 intake report is waiting.")
    if p39_status and p39_status != P39_STATUS_VALID_REVIEW_ONLY:
        add_issue("p39_intake_not_valid", "waiting", f"P39 intake status is not valid review-only: {p39_status}")

    if p38_share_packet_sha256 and p39_observed_share_packet_sha256 and p38_share_packet_sha256 != p39_observed_share_packet_sha256:
        add_issue(
            "share_packet_hash_mismatch",
            "blocked",
            "P38 share packet hash does not match the hash observed by P39 intake.",
            {"p38_hash": p38_share_packet_sha256, "p39_observed_hash": p39_observed_share_packet_sha256},
        )
    if p38_manifest_sha256 and p39_observed_manifest_sha256 and p38_manifest_sha256 != p39_observed_manifest_sha256:
        add_issue(
            "manifest_hash_mismatch",
            "blocked",
            "P38 manifest hash does not match the hash observed by P39 intake.",
            {"p38_hash": p38_manifest_sha256, "p39_observed_hash": p39_observed_manifest_sha256},
        )

    p38_manifest_by_name = _manifest_by_filename(p38_manifest_list)
    p38_share_manifest_by_name = _manifest_by_filename(p38_share_packet.get("manifest", []))
    missing_from_share_manifest = sorted(set(p38_manifest_by_name) - set(p38_share_manifest_by_name))
    if p38_share_packet and p38_manifest_by_name and missing_from_share_manifest:
        add_issue("share_manifest_missing_entries", "blocked", "P38 share packet manifest is missing entries from the external manifest.", missing_from_share_manifest)

    if p39_report and int(p39_report.get("hash_mismatch_count", 0) or 0) != 0:
        add_issue("p39_reported_hash_mismatch", "blocked", "P39 intake reported manifest hash mismatches.", p39_report.get("hash_mismatches", []))
    if p39_report and int(p39_report.get("intake_issue_count", 0) or 0) != 0:
        severity = "blocked" if _bool(p39_report.get("blocked")) else "waiting"
        add_issue("p39_reported_intake_issues", severity, "P39 intake reported issues.", p39_report.get("intake_issue_codes", []))
    if p39_validation_results and not _bool(p39_validation_results.get("valid_review_only")):
        severity = "blocked" if _bool(p39_validation_results.get("blocked")) else "waiting"
        add_issue("p39_validation_not_valid_review_only", severity, "P39 validation results are not valid review-only.", p39_validation_results)

    if set(p38_share_packet.get("allowed_read_only_commands", [])) != set(_ALLOWED_READ_ONLY_COMMANDS) and p38_share_packet:
        add_issue("allowed_commands_mismatch", "blocked", "Allowed read-only command set does not match the safety contract.", p38_share_packet.get("allowed_read_only_commands"))
    missing_blocked_keywords = sorted(set(_REQUIRED_BLOCKED_KEYWORDS) - set(p38_share_packet.get("blocked_command_keywords", [])))
    if p38_share_packet and missing_blocked_keywords:
        add_issue("blocked_keywords_missing", "blocked", "Required blocked command keywords are missing.", missing_blocked_keywords)

    if p38_share_packet and p38_share_packet.get("runtime") != "DISABLED":
        add_issue("runtime_not_disabled", "blocked", "P38 runtime state is not DISABLED.", p38_share_packet.get("runtime"))
    if p38_share_packet and p38_share_packet.get("scheduler") != "DISABLED":
        add_issue("scheduler_not_disabled", "blocked", "P38 scheduler state is not DISABLED.", p38_share_packet.get("scheduler"))
    if p38_share_packet and p38_share_packet.get("orders") != "DISABLED":
        add_issue("orders_not_disabled", "blocked", "P38 orders state is not DISABLED.", p38_share_packet.get("orders"))
    if p38_share_packet and p38_share_packet.get("authority") != "REVIEW_ONLY":
        add_issue("authority_not_review_only", "blocked", "P38 authority is not REVIEW_ONLY.", p38_share_packet.get("authority"))
    if _bool(p38_share_packet.get("runtime_authority")):
        add_issue("runtime_authority_claimed", "blocked", "P38 share packet claims runtime authority.")
    if _bool(p38_share_packet.get("contains_secret_values")):
        add_issue("contains_secret_value", "blocked", "P38 share packet reports secret values.")

    if unsafe_hits:
        add_issue("runtime_flag_truthy", "blocked", "Truthy runtime/order/scheduler flag detected in round-trip payloads.", unsafe_hits)
    if scheduler_hits:
        add_issue("scheduler_enabled", "blocked", "Scheduler truthy flag detected in round-trip payloads.", scheduler_hits)
    if endpoint_hits:
        add_issue("endpoint_called", "blocked", "Endpoint-call truthy flag detected in round-trip payloads.", endpoint_hits)
    if authority_hits:
        add_issue("runtime_authority_claimed", "blocked", "Runtime authority truthy flag detected in round-trip payloads.", authority_hits)
    if secret_hits:
        add_issue("secret_detected", "blocked", "Secret value pattern detected in round-trip payloads.", secret_hits)

    blocked = any(issue["severity"] == "blocked" for issue in issues)
    waiting = bool(issues) and not blocked
    status = STATUS_VERIFIED_REVIEW_ONLY
    if waiting:
        status = STATUS_WAITING_REVIEW_ONLY
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED

    round_trip_chain = {
        "chain_id": stable_id("p40_round_trip_chain", {"p38_share_packet_sha256": p38_share_packet_sha256, "p38_manifest_sha256": p38_manifest_sha256, "p39_observed_share_packet_sha256": p39_observed_share_packet_sha256, "p39_observed_manifest_sha256": p39_observed_manifest_sha256}),
        "p38_export_status": p38_status or None,
        "p38_share_packet_sha256": p38_share_packet_sha256,
        "p38_manifest_sha256": p38_manifest_sha256,
        "p39_intake_status": p39_status or None,
        "p39_observed_share_packet_sha256": p39_observed_share_packet_sha256,
        "p39_observed_manifest_sha256": p39_observed_manifest_sha256,
        "p39_validation_status": p39_validation_results.get("status"),
        "round_trip_match": not blocked and not any(code in {"share_packet_hash_mismatch", "manifest_hash_mismatch"} for code in [issue["code"] for issue in issues]),
        "runtime_authority": False,
        "review_only": True,
    }
    round_trip_hash = sha256_json(round_trip_chain)

    report: dict[str, Any] = {
        "version": P40_OPERATOR_SUPPORT_BUNDLE_ROUND_TRIP_VERSION,
        "status": status,
        "waiting": waiting,
        "blocked": blocked,
        "created_at_utc": utc_now_canonical(),
        "p38_share_packet_present": bool(p38_share_packet),
        "p38_manifest_present": bool(p38_manifest_list),
        "p39_report_present": bool(p39_report),
        "p39_validation_present": bool(p39_validation_results),
        "p38_share_packet_status": p38_status or None,
        "p39_status": p39_status or None,
        "p39_validation_status": p39_validation_results.get("status"),
        "p38_share_packet_sha256": p38_share_packet_sha256,
        "p38_manifest_sha256": p38_manifest_sha256,
        "p39_observed_share_packet_sha256": p39_observed_share_packet_sha256,
        "p39_observed_manifest_sha256": p39_observed_manifest_sha256,
        "p38_manifest_entry_count": len(p38_manifest_by_name),
        "p38_share_manifest_entry_count": len(p38_share_manifest_by_name),
        "p39_hash_mismatch_count": int(p39_report.get("hash_mismatch_count", 0) or 0) if p39_report else None,
        "p39_intake_issue_count": int(p39_report.get("intake_issue_count", 0) or 0) if p39_report else None,
        "p39_intake_issue_codes": list(p39_report.get("intake_issue_codes", [])) if p39_report else [],
        "round_trip_chain": round_trip_chain,
        "round_trip_hash": round_trip_hash,
        "round_trip_issues": issues,
        "round_trip_issue_count": len(issues),
        "round_trip_issue_codes": sorted({issue["code"] for issue in issues}),
        "blocked_issue_count": sum(1 for issue in issues if issue["severity"] == "blocked"),
        "waiting_issue_count": sum(1 for issue in issues if issue["severity"] == "waiting"),
        "allowed_read_only_commands": list(_ALLOWED_READ_ONLY_COMMANDS),
        "blocked_command_keywords": list(_REQUIRED_BLOCKED_KEYWORDS),
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "unsafe_truthy_execution_flag_hit_count": len(unsafe_hits),
        "runtime_flag_truthy": bool(unsafe_hits),
        "scheduler_enabled": bool(scheduler_hits),
        "endpoint_called": bool(endpoint_hits),
        "runtime_authority_claimed": bool(authority_hits) or _bool(p38_share_packet.get("runtime_authority")),
        "secret_detected": bool(secret_hits),
        "secret_pattern_hits": secret_hits,
        "secret_pattern_hit_count": len(secret_hits),
        "runtime_authority": False,
        "round_trip_executes_runtime": False,
        "round_trip_enables_scheduler": False,
        "round_trip_allows_order_submission": False,
        "round_trip_calls_endpoint": False,
        "round_trip_reads_secret_value": False,
        "round_trip_grants_runtime_authority": False,
        "runtime_scheduler_enabled": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    flag_state = default_execution_flag_state()
    flag_state.update(
        {
            "runtime_scheduler_enabled": False,
            "live_scaled_execution_enabled": False,
            "live_order_submission_allowed": False,
            "order_endpoint_called": False,
            "secret_value_accessed": False,
            "round_trip_executes_runtime": False,
            "round_trip_enables_scheduler": False,
            "round_trip_allows_order_submission": False,
            "round_trip_calls_endpoint": False,
            "round_trip_reads_secret_value": False,
            "round_trip_grants_runtime_authority": False,
        }
    )
    report["execution_flag_state"] = flag_state
    report["truthy_execution_flags"] = truthy_execution_flags(flag_state)
    if report["truthy_execution_flags"]:
        report["status"] = STATUS_BLOCKED_FAIL_CLOSED
        report["blocked"] = True
        report["waiting"] = False
        report["round_trip_issues"].append(
            {
                "code": "truthy_execution_flag_state",
                "severity": "blocked",
                "message": "Default execution flag state contains truthy runtime flags.",
                "evidence": report["truthy_execution_flags"],
            }
        )
        report["round_trip_issue_codes"] = sorted({issue["code"] for issue in report["round_trip_issues"]})
        report["round_trip_issue_count"] = len(report["round_trip_issues"])
        report["blocked_issue_count"] = sum(1 for issue in report["round_trip_issues"] if issue["severity"] == "blocked")
    return report


def build_p40_negative_fixture_results(root: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    latest = _latest_dir(cfg)
    share_packet = _read_latest_json(cfg, "p38_operator_support_bundle_share_packet.json", default={})
    manifest = _read_latest_json(cfg, "p38_operator_support_bundle_manifest.json", default=[])
    p39_report = _read_latest_json(cfg, "p39_operator_support_bundle_intake_validator_report.json", default={})
    p39_validation = _read_latest_json(cfg, "p39_operator_support_bundle_intake_validation_results.json", default={})
    if not isinstance(share_packet, Mapping):
        share_packet = {}
    if not isinstance(manifest, list):
        manifest = []
    if not isinstance(p39_report, Mapping):
        p39_report = {}
    if not isinstance(p39_validation, Mapping):
        p39_validation = {}

    fixtures: dict[str, dict[str, Any]] = {
        "missing_p38_share_packet": build_operator_support_bundle_round_trip_report(
            root=cfg.root, p38_share_packet={}, p38_manifest=manifest, p39_report=p39_report, p39_validation_results=p39_validation
        ),
        "missing_p38_manifest": build_operator_support_bundle_round_trip_report(
            root=cfg.root, p38_share_packet=share_packet, p38_manifest=[], p39_report=p39_report, p39_validation_results=p39_validation
        ),
        "missing_p39_report": build_operator_support_bundle_round_trip_report(
            root=cfg.root, p38_share_packet=share_packet, p38_manifest=manifest, p39_report={}, p39_validation_results=p39_validation
        ),
        "missing_p39_validation_results": build_operator_support_bundle_round_trip_report(
            root=cfg.root, p38_share_packet=share_packet, p38_manifest=manifest, p39_report=p39_report, p39_validation_results={}
        ),
        "share_packet_hash_mismatch": build_operator_support_bundle_round_trip_report(
            root=cfg.root,
            p38_share_packet={**dict(share_packet), "share_packet_id": "tampered_p38_share_packet"} if share_packet else {"share_packet_id": "tampered"},
            p38_manifest=manifest,
            p39_report=p39_report,
            p39_validation_results=p39_validation,
        ),
        "manifest_hash_mismatch": build_operator_support_bundle_round_trip_report(
            root=cfg.root,
            p38_share_packet=share_packet,
            p38_manifest=[{**dict(manifest[0]), "sha256": "tampered_manifest_hash"}, *manifest[1:]] if manifest else [{"filename": "missing", "sha256": "x"}],
            p39_report=p39_report,
            p39_validation_results=p39_validation,
        ),
        "p39_blocked": build_operator_support_bundle_round_trip_report(
            root=cfg.root,
            p38_share_packet=share_packet,
            p38_manifest=manifest,
            p39_report={**dict(p39_report), "status": P39_STATUS_BLOCKED_FAIL_CLOSED, "blocked": True, "intake_issue_count": 1, "intake_issue_codes": ["fixture_blocked"]},
            p39_validation_results=p39_validation,
        ),
        "p39_waiting": build_operator_support_bundle_round_trip_report(
            root=cfg.root,
            p38_share_packet=share_packet,
            p38_manifest=manifest,
            p39_report={**dict(p39_report), "status": P39_STATUS_WAITING_REVIEW_ONLY, "waiting": True, "intake_issue_count": 1, "intake_issue_codes": ["fixture_waiting"]},
            p39_validation_results=p39_validation,
        ),
        "p39_validation_not_valid": build_operator_support_bundle_round_trip_report(
            root=cfg.root,
            p38_share_packet=share_packet,
            p38_manifest=manifest,
            p39_report=p39_report,
            p39_validation_results={**dict(p39_validation), "valid_review_only": False, "waiting": True},
        ),
        "runtime_flag_truthy": build_operator_support_bundle_round_trip_report(
            root=cfg.root,
            p38_share_packet=share_packet,
            p38_manifest=manifest,
            p39_report=p39_report,
            p39_validation_results=p39_validation,
            extra_payloads_for_scan=[("bad_runtime", {"live_scaled_execution_enabled": True})],
        ),
        "scheduler_enabled": build_operator_support_bundle_round_trip_report(
            root=cfg.root,
            p38_share_packet=share_packet,
            p38_manifest=manifest,
            p39_report=p39_report,
            p39_validation_results=p39_validation,
            extra_payloads_for_scan=[("bad_scheduler", {"runtime_scheduler_enabled": True})],
        ),
        "endpoint_called": build_operator_support_bundle_round_trip_report(
            root=cfg.root,
            p38_share_packet=share_packet,
            p38_manifest=manifest,
            p39_report=p39_report,
            p39_validation_results=p39_validation,
            extra_payloads_for_scan=[("bad_endpoint", {"order_endpoint_called": True})],
        ),
        "secret_detected": build_operator_support_bundle_round_trip_report(
            root=cfg.root,
            p38_share_packet=share_packet,
            p38_manifest=manifest,
            p39_report=p39_report,
            p39_validation_results=p39_validation,
            extra_payloads_for_scan=[("bad_secret", "BINANCE_API_SECRET=leak")],
        ),
        "runtime_authority_claimed": build_operator_support_bundle_round_trip_report(
            root=cfg.root,
            p38_share_packet={**dict(share_packet), "runtime_authority": True} if share_packet else {"runtime_authority": True},
            p38_manifest=manifest,
            p39_report=p39_report,
            p39_validation_results=p39_validation,
        ),
        "round_trip_executes_runtime": build_operator_support_bundle_round_trip_report(
            root=cfg.root,
            p38_share_packet=share_packet,
            p38_manifest=manifest,
            p39_report=p39_report,
            p39_validation_results=p39_validation,
            extra_payloads_for_scan=[("bad_round_trip", {"round_trip_executes_runtime": True})],
        ),
    }
    fixture_summary = {
        name: {
            "status": result["status"],
            "waiting": result["waiting"],
            "blocked": result["blocked"],
            "round_trip_issue_codes": result["round_trip_issue_codes"],
            "round_trip_executes_runtime": result["round_trip_executes_runtime"],
            "runtime_scheduler_enabled": result["runtime_scheduler_enabled"],
            "order_endpoint_called": result["order_endpoint_called"],
            "secret_value_accessed": result["secret_value_accessed"],
        }
        for name, result in fixtures.items()
    }
    all_fail_closed = all(item["waiting"] or item["blocked"] for item in fixture_summary.values())
    return {
        "status": "P40_NEGATIVE_FIXTURES_RECORDED",
        "created_at_utc": utc_now_canonical(),
        "fixture_count": len(fixture_summary),
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all_fail_closed,
        "fixture_results": fixture_summary,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "output_dir": str(latest),
    }


def persist_operator_support_bundle_round_trip_verification(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p40_operator_support_bundle_round_trip_verification")
    report = build_operator_support_bundle_round_trip_report(root=cfg.root)
    checklist = _build_round_trip_checklist(report)
    markdown = _build_round_trip_markdown(report)
    negative = build_p40_negative_fixture_results(root=cfg.root)

    report_path = latest / "p40_operator_support_bundle_round_trip_verification_report.json"
    summary_path = latest / "p40_operator_support_bundle_round_trip_verification_summary.json"
    chain_path = latest / "p40_operator_support_bundle_round_trip_chain.json"
    checklist_path = latest / "p40_operator_support_bundle_round_trip_checklist.md"
    markdown_path = latest / "p40_operator_support_bundle_round_trip_verification.md"
    negative_path = latest / "p40_operator_support_bundle_round_trip_verification_negative_fixture_results.json"
    registry_record_path = latest / "p40_operator_support_bundle_round_trip_verification_registry_record.json"

    output_paths = {
        "report": str(report_path),
        "summary": str(summary_path),
        "round_trip_chain": str(chain_path),
        "checklist": str(checklist_path),
        "markdown": str(markdown_path),
    }
    report["output_paths"] = output_paths

    summary = {
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "round_trip_issue_count": report["round_trip_issue_count"],
        "round_trip_issue_codes": report["round_trip_issue_codes"],
        "round_trip_hash": report["round_trip_hash"],
        "p38_share_packet_present": report["p38_share_packet_present"],
        "p38_manifest_present": report["p38_manifest_present"],
        "p39_report_present": report["p39_report_present"],
        "p39_validation_present": report["p39_validation_present"],
        "p38_share_packet_status": report["p38_share_packet_status"],
        "p39_status": report["p39_status"],
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
        "id": stable_id("p40_operator_support_bundle_round_trip_verification", {"round_trip_hash": report.get("round_trip_hash"), "status": report.get("status")}),
        "version": P40_OPERATOR_SUPPORT_BUNDLE_ROUND_TRIP_VERSION,
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "created_at_utc": report["created_at_utc"],
        "round_trip_hash": report["round_trip_hash"],
        "round_trip_issue_count": report["round_trip_issue_count"],
        "runtime_authority": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }

    for directory in (latest, storage):
        atomic_write_json(directory / report_path.name, report)
        atomic_write_json(directory / summary_path.name, summary)
        atomic_write_json(directory / chain_path.name, report["round_trip_chain"])
        _atomic_write_text(directory / checklist_path.name, checklist)
        _atomic_write_text(directory / markdown_path.name, markdown)
    atomic_write_json(negative_path, negative)
    atomic_write_json(storage / negative_path.name, negative)
    append_registry_record(
        registry_path(cfg, P40_OPERATOR_SUPPORT_BUNDLE_ROUND_TRIP_REGISTRY_NAME),
        registry_record,
        registry_name=P40_OPERATOR_SUPPORT_BUNDLE_ROUND_TRIP_REGISTRY_NAME,
    )
    atomic_write_json(registry_record_path, registry_record)
    atomic_write_json(storage / registry_record_path.name, registry_record)
    return report
