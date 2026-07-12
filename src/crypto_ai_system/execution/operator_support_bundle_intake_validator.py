from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.operator_support_bundle_troubleshooting_export_pack import (
    STATUS_BLOCKED_FAIL_CLOSED as P38_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY as P38_STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P38_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P39_OPERATOR_SUPPORT_BUNDLE_INTAKE_VALIDATOR_VERSION = "p39_operator_support_bundle_intake_validator_v1"
P39_OPERATOR_SUPPORT_BUNDLE_INTAKE_VALIDATOR_REGISTRY_NAME = "p39_operator_support_bundle_intake_validator_registry"

STATUS_VALID_REVIEW_ONLY = "P39_OPERATOR_SUPPORT_BUNDLE_INTAKE_VALIDATOR_VALID_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P39_OPERATOR_SUPPORT_BUNDLE_INTAKE_VALIDATOR_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P39_OPERATOR_SUPPORT_BUNDLE_INTAKE_VALIDATOR_BLOCKED_FAIL_CLOSED"

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
_REQUIRED_SHARE_FIELDS = (
    "share_packet_id",
    "status",
    "operator_final_activation_decision",
    "manifest",
    "allowed_read_only_commands",
    "blocked_command_keywords",
    "runtime",
    "scheduler",
    "orders",
    "authority",
    "contains_secret_values",
    "runtime_authority",
)
_EXECUTION_FIELDS_FOR_P39 = {
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
                if key in _EXECUTION_FIELDS_FOR_P39 and _bool(value):
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


def _build_validation_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# P39 Operator Support Bundle Intake Validator",
        "",
        f"Status: `{report.get('status')}`",
        f"Share packet status: `{report.get('share_packet_status')}`",
        "",
        "> This validator is review-only. It validates a P38 support bundle intake and never enables runtime, scheduler, orders, endpoints, or secret access.",
        "",
        "## Intake Decision",
        "",
        f"- Waiting: `{report.get('waiting')}`",
        f"- Blocked: `{report.get('blocked')}`",
        f"- Intake issue count: {report.get('intake_issue_count')}",
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
        "",
        "## Allowed Read-only Commands",
        "",
    ])
    for command in _ALLOWED_READ_ONLY_COMMANDS:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Blocked Command Keywords", ""])
    for keyword in _REQUIRED_BLOCKED_KEYWORDS:
        lines.append(f"- `{keyword}`")
    return "\n".join(lines).rstrip() + "\n"


def _build_checklist(report: Mapping[str, Any]) -> str:
    checks = [
        ("P38 share packet exists", bool(report.get("share_packet_present"))),
        ("Share packet required fields exist", not any(code == "missing_required_share_fields" for code in report.get("intake_issue_codes", []))),
        ("Manifest exists", bool(report.get("manifest_present"))),
        ("Manifest hashes match share packet", not any(code == "hash_mismatch" for code in report.get("intake_issue_codes", []))),
        ("Runtime remains disabled", not bool(report.get("runtime_flag_truthy"))),
        ("No endpoint evidence", not bool(report.get("endpoint_called"))),
        ("No secret value patterns", not bool(report.get("secret_detected"))),
        ("Authority remains review-only", not bool(report.get("runtime_authority_claimed"))),
    ]
    lines = ["# P39 Intake Checklist", ""]
    for label, passed in checks:
        mark = "x" if passed else " "
        lines.append(f"- [{mark}] {label}")
    return "\n".join(lines).rstrip() + "\n"


def build_operator_support_bundle_intake_report(
    *,
    root: str | Path | None = None,
    share_packet: Mapping[str, Any] | None = None,
    manifest: Sequence[Mapping[str, Any]] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] = (),
    require_manifest: bool = True,
) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    if share_packet is None:
        loaded_share_packet = _read_latest_json(cfg, "p38_operator_support_bundle_share_packet.json", default={})
        share_packet = loaded_share_packet if isinstance(loaded_share_packet, Mapping) else {}
    if manifest is None:
        loaded_manifest = _read_latest_json(cfg, "p38_operator_support_bundle_manifest.json", default=[])
        manifest = loaded_manifest if isinstance(loaded_manifest, list) else []

    share_packet = dict(share_packet)
    manifest_list = [dict(item) for item in manifest if isinstance(item, Mapping)]
    share_manifest = share_packet.get("manifest", [])
    share_manifest_by_name = _manifest_by_filename(share_manifest)
    external_manifest_by_name = _manifest_by_filename(manifest_list)
    scan_payloads: list[tuple[str, Any]] = [
        ("share_packet", share_packet),
        ("external_manifest", manifest_list),
        *list(extra_payloads_for_scan),
    ]
    unsafe_hits = _scan_truthy_execution_fields(scan_payloads)
    secret_hits = _scan_secret_value_patterns(scan_payloads)
    endpoint_hits = [hit for hit in unsafe_hits if "endpoint" in hit.get("field", "") or hit.get("field") == "http_request_sent"]
    scheduler_hits = [hit for hit in unsafe_hits if "scheduler" in hit.get("field", "")]

    issues: list[dict[str, Any]] = []

    def add_issue(code: str, severity: str, message: str, evidence: Any = None) -> None:
        issue = {"code": code, "severity": severity, "message": message}
        if evidence is not None:
            issue["evidence"] = evidence
        issues.append(issue)

    if not share_packet:
        add_issue("missing_share_packet", "waiting", "P38 share packet is missing or empty.")
    else:
        missing_fields = [field for field in _REQUIRED_SHARE_FIELDS if field not in share_packet]
        if missing_fields:
            add_issue("missing_required_share_fields", "blocked", "P38 share packet is missing required fields.", missing_fields)

    if require_manifest and not manifest_list:
        add_issue("missing_manifest", "blocked", "P38 manifest is missing or empty.")
    if share_packet and not share_manifest_by_name:
        add_issue("missing_share_packet_manifest", "blocked", "P38 share packet manifest is missing or empty.")

    share_status = str(share_packet.get("status", "")) if share_packet else ""
    if share_status == P38_STATUS_WAITING_REVIEW_ONLY or _bool(share_packet.get("waiting")):
        add_issue("share_packet_waiting", "waiting", "P38 share packet is waiting.")
    if share_status == P38_STATUS_BLOCKED_FAIL_CLOSED or _bool(share_packet.get("blocked")):
        add_issue("share_packet_blocked", "blocked", "P38 share packet is blocked fail-closed.")
    if share_status and share_status != P38_STATUS_GENERATED_REVIEW_ONLY:
        add_issue("share_packet_not_generated", "waiting", f"P38 share packet status is not generated: {share_status}")

    if set(share_packet.get("allowed_read_only_commands", [])) != set(_ALLOWED_READ_ONLY_COMMANDS):
        if share_packet:
            add_issue("allowed_commands_mismatch", "blocked", "Allowed read-only command set does not match the P32~P38 safety contract.", share_packet.get("allowed_read_only_commands"))
    missing_blocked = sorted(set(_REQUIRED_BLOCKED_KEYWORDS) - set(share_packet.get("blocked_command_keywords", [])))
    if share_packet and missing_blocked:
        add_issue("blocked_keywords_missing", "blocked", "Required blocked command keywords are missing from share packet.", missing_blocked)

    if share_packet.get("runtime") != "DISABLED" and share_packet:
        add_issue("runtime_not_disabled", "blocked", "Share packet runtime state is not DISABLED.", share_packet.get("runtime"))
    if share_packet.get("scheduler") != "DISABLED" and share_packet:
        add_issue("scheduler_not_disabled", "blocked", "Share packet scheduler state is not DISABLED.", share_packet.get("scheduler"))
    if share_packet.get("orders") != "DISABLED" and share_packet:
        add_issue("orders_not_disabled", "blocked", "Share packet orders state is not DISABLED.", share_packet.get("orders"))
    if share_packet.get("authority") != "REVIEW_ONLY" and share_packet:
        add_issue("authority_not_review_only", "blocked", "Share packet authority is not REVIEW_ONLY.", share_packet.get("authority"))
    if _bool(share_packet.get("runtime_authority")):
        add_issue("runtime_authority_claimed", "blocked", "Share packet claims runtime authority.")
    if _bool(share_packet.get("contains_secret_values")):
        add_issue("contains_secret_value", "blocked", "Share packet reports secret values.")

    hash_mismatches: list[dict[str, Any]] = []
    if share_manifest_by_name and external_manifest_by_name:
        for filename, share_entry in share_manifest_by_name.items():
            external_entry = external_manifest_by_name.get(filename)
            if not external_entry:
                hash_mismatches.append({"filename": filename, "reason": "missing_from_external_manifest"})
                continue
            if share_entry.get("sha256") != external_entry.get("sha256"):
                hash_mismatches.append(
                    {
                        "filename": filename,
                        "share_sha256": share_entry.get("sha256"),
                        "external_sha256": external_entry.get("sha256"),
                    }
                )
    if hash_mismatches:
        add_issue("hash_mismatch", "blocked", "Share packet manifest hash does not match external manifest.", hash_mismatches)

    if unsafe_hits:
        add_issue("runtime_flag_truthy", "blocked", "Truthy runtime/order/scheduler flag detected in intake packet or manifest.", unsafe_hits)
    if scheduler_hits:
        add_issue("scheduler_enabled", "blocked", "Scheduler truthy flag detected in intake packet or manifest.", scheduler_hits)
    if endpoint_hits:
        add_issue("endpoint_called", "blocked", "Endpoint-call truthy flag detected in intake packet or manifest.", endpoint_hits)
    if secret_hits:
        add_issue("secret_detected", "blocked", "Secret value pattern detected in intake packet or manifest.", secret_hits)

    blocked = any(issue["severity"] == "blocked" for issue in issues)
    waiting = bool(issues) and not blocked
    status = STATUS_VALID_REVIEW_ONLY
    if waiting:
        status = STATUS_WAITING_REVIEW_ONLY
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED

    report: dict[str, Any] = {
        "version": P39_OPERATOR_SUPPORT_BUNDLE_INTAKE_VALIDATOR_VERSION,
        "status": status,
        "waiting": waiting,
        "blocked": blocked,
        "created_at_utc": utc_now_canonical(),
        "share_packet_present": bool(share_packet),
        "manifest_present": bool(manifest_list),
        "share_packet_status": share_status or None,
        "share_packet_sha256": sha256_json(share_packet) if share_packet else None,
        "manifest_sha256": sha256_json(manifest_list) if manifest_list else None,
        "share_packet_manifest_entry_count": len(share_manifest_by_name),
        "external_manifest_entry_count": len(external_manifest_by_name),
        "hash_mismatch_count": len(hash_mismatches),
        "hash_mismatches": hash_mismatches,
        "intake_issues": issues,
        "intake_issue_count": len(issues),
        "intake_issue_codes": sorted({issue["code"] for issue in issues}),
        "blocked_issue_count": sum(1 for issue in issues if issue["severity"] == "blocked"),
        "waiting_issue_count": sum(1 for issue in issues if issue["severity"] == "waiting"),
        "allowed_read_only_commands": list(_ALLOWED_READ_ONLY_COMMANDS),
        "blocked_command_keywords": list(_REQUIRED_BLOCKED_KEYWORDS),
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "unsafe_truthy_execution_flag_hit_count": len(unsafe_hits),
        "runtime_flag_truthy": bool(unsafe_hits),
        "scheduler_enabled": bool(scheduler_hits),
        "endpoint_called": bool(endpoint_hits),
        "secret_detected": bool(secret_hits),
        "secret_pattern_hits": secret_hits,
        "secret_pattern_hit_count": len(secret_hits),
        "runtime_authority": False,
        "intake_validator_executes_runtime": False,
        "intake_validator_enables_scheduler": False,
        "intake_validator_allows_order_submission": False,
        "intake_validator_calls_endpoint": False,
        "intake_validator_reads_secret_value": False,
        "intake_validator_grants_runtime_authority": False,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "actual_live_order_submitted": False,
        "actual_testnet_order_submitted": False,
        "order_endpoint_called": False,
        "live_order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "execution_flags": default_execution_flag_state(),
        "truthy_default_execution_flags": truthy_execution_flags(default_execution_flag_state()),
    }
    report["intake_validation_results"] = {
        "status": status,
        "valid_review_only": status == STATUS_VALID_REVIEW_ONLY,
        "waiting": waiting,
        "blocked": blocked,
        "issue_codes": report["intake_issue_codes"],
        "runtime": "DISABLED",
        "scheduler": "DISABLED",
        "orders": "DISABLED",
        "authority": "REVIEW_ONLY",
    }
    report["intake_checklist_markdown"] = _build_checklist(report)
    report["intake_validator_markdown"] = _build_validation_markdown(report)
    report["report_id"] = stable_id("p39_operator_support_bundle_intake", report)
    return report


def build_p39_negative_fixture_results(*, root: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    base_manifest = [
        {"phase": "p38", "filename": "p38_operator_support_bundle_share_packet.json", "exists": True, "sha256": "sha_good", "size_bytes": 100},
        {"phase": "p37", "filename": "p37_onboarding_wizard_failure_doctor_report.json", "exists": True, "sha256": "sha_p37", "size_bytes": 100},
    ]
    base_share_packet = {
        "share_packet_id": "p38_share_packet_fixture",
        "status": P38_STATUS_GENERATED_REVIEW_ONLY,
        "waiting": False,
        "blocked": False,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "source_p37_status": "P37_ONBOARDING_WIZARD_FAILURE_DOCTOR_GENERATED_REVIEW_ONLY",
        "source_p37_diagnosis_issue_count": 0,
        "missing_source_artifacts": [],
        "allowed_read_only_commands": list(_ALLOWED_READ_ONLY_COMMANDS),
        "blocked_command_keywords": list(_REQUIRED_BLOCKED_KEYWORDS),
        "manifest": base_manifest,
        "redacted_text_excerpts": [],
        "runtime": "DISABLED",
        "scheduler": "DISABLED",
        "orders": "DISABLED",
        "authority": "REVIEW_ONLY",
        "contains_secret_values": False,
        "runtime_authority": False,
    }
    mismatch_manifest = [{**base_manifest[0], "sha256": "sha_bad"}, base_manifest[1]]
    cases: dict[str, dict[str, Any]] = {
        "missing_share_packet": {"share_packet": {}},
        "missing_manifest": {"manifest": []},
        "missing_required_fields": {"share_packet": {"status": P38_STATUS_GENERATED_REVIEW_ONLY}},
        "share_packet_blocked_status": {"share_packet": {**base_share_packet, "status": P38_STATUS_BLOCKED_FAIL_CLOSED, "blocked": True}},
        "share_packet_waiting_status": {"share_packet": {**base_share_packet, "status": P38_STATUS_WAITING_REVIEW_ONLY, "waiting": True}},
        "hash_mismatch": {"manifest": mismatch_manifest},
        "secret_detected": {"extra_payloads_for_scan": [("bad_secret", "BINANCE_API_SECRET=leak")]},
        "runtime_flag_truthy": {"extra_payloads_for_scan": [("bad_runtime", {"live_scaled_execution_enabled": True})]},
        "endpoint_called": {"extra_payloads_for_scan": [("bad_endpoint", {"order_endpoint_called": True})]},
        "scheduler_enabled": {"extra_payloads_for_scan": [("bad_scheduler", {"runtime_scheduler_enabled": True})]},
        "runtime_authority_claimed": {"share_packet": {**base_share_packet, "runtime_authority": True}},
        "contains_secret_value": {"share_packet": {**base_share_packet, "contains_secret_values": True}},
        "orders_enabled": {"share_packet": {**base_share_packet, "orders": "ENABLED"}},
        "intake_validator_executes_runtime": {"extra_payloads_for_scan": [("bad_validator", {"intake_validator_executes_runtime": True})]},
    }
    fixtures: dict[str, dict[str, Any]] = {}
    for case, overrides in cases.items():
        report = build_operator_support_bundle_intake_report(
            root=cfg.root,
            share_packet=overrides.get("share_packet", base_share_packet),
            manifest=overrides.get("manifest", base_manifest),
            extra_payloads_for_scan=overrides.get("extra_payloads_for_scan", ()),
            require_manifest=True,
        )
        fixtures[case] = {
            "status": report["status"],
            "blocked": bool(report["blocked"]),
            "waiting": bool(report["waiting"]),
            "intake_issue_codes": report["intake_issue_codes"],
        }
    all_safe = all(item["blocked"] or item["waiting"] for item in fixtures.values())
    return {
        "status": "P39_NEGATIVE_FIXTURES_RECORDED",
        "fixture_results": fixtures,
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all_safe,
        "created_at_utc": utc_now_canonical(),
    }


def persist_operator_support_bundle_intake_validator(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p39_operator_support_bundle_intake_validator")
    report = build_operator_support_bundle_intake_report(root=cfg.root)
    negative = build_p39_negative_fixture_results(root=cfg.root)

    report_path = latest / "p39_operator_support_bundle_intake_validator_report.json"
    summary_path = latest / "p39_operator_support_bundle_intake_validator_summary.json"
    validation_path = latest / "p39_operator_support_bundle_intake_validation_results.json"
    checklist_path = latest / "p39_operator_support_bundle_intake_checklist.md"
    markdown_path = latest / "p39_operator_support_bundle_intake_validator.md"
    negative_path = latest / "p39_operator_support_bundle_intake_validator_negative_fixture_results.json"
    registry_record_path = latest / "p39_operator_support_bundle_intake_validator_registry_record.json"

    output_paths = {
        "report": str(report_path),
        "summary": str(summary_path),
        "validation_results": str(validation_path),
        "checklist": str(checklist_path),
        "markdown": str(markdown_path),
    }
    report["output_paths"] = output_paths

    summary = {
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "share_packet_present": report["share_packet_present"],
        "manifest_present": report["manifest_present"],
        "share_packet_status": report["share_packet_status"],
        "intake_issue_count": report["intake_issue_count"],
        "intake_issue_codes": report["intake_issue_codes"],
        "hash_mismatch_count": report["hash_mismatch_count"],
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
    report_without_large_text = {k: v for k, v in report.items() if k not in {"intake_checklist_markdown", "intake_validator_markdown"}}

    atomic_write_json(report_path, report)
    atomic_write_json(summary_path, summary)
    atomic_write_json(validation_path, report["intake_validation_results"])
    _atomic_write_text(checklist_path, report["intake_checklist_markdown"])
    _atomic_write_text(markdown_path, report["intake_validator_markdown"])
    atomic_write_json(negative_path, negative)

    atomic_write_json(storage / report_path.name, report_without_large_text)
    atomic_write_json(storage / summary_path.name, summary)
    atomic_write_json(storage / validation_path.name, report["intake_validation_results"])
    _atomic_write_text(storage / checklist_path.name, report["intake_checklist_markdown"])
    _atomic_write_text(storage / markdown_path.name, report["intake_validator_markdown"])

    registry_record = {
        "registry_record_id": stable_id("p39_registry_record", report),
        "report_id": report["report_id"],
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "intake_issue_count": report["intake_issue_count"],
        "hash_mismatch_count": report["hash_mismatch_count"],
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "created_at_utc": utc_now_canonical(),
    }
    atomic_write_json(registry_record_path, registry_record)
    append_registry_record(
        registry_path(cfg, P39_OPERATOR_SUPPORT_BUNDLE_INTAKE_VALIDATOR_REGISTRY_NAME),
        registry_record,
        registry_name=P39_OPERATOR_SUPPORT_BUNDLE_INTAKE_VALIDATOR_REGISTRY_NAME,
    )
    return report


__all__ = [
    "P39_OPERATOR_SUPPORT_BUNDLE_INTAKE_VALIDATOR_VERSION",
    "STATUS_VALID_REVIEW_ONLY",
    "STATUS_WAITING_REVIEW_ONLY",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "build_operator_support_bundle_intake_report",
    "build_p39_negative_fixture_results",
    "persist_operator_support_bundle_intake_validator",
]
