from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.onboarding_wizard_failure_doctor import (
    STATUS_BLOCKED_FAIL_CLOSED as P37_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY as P37_STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P37_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P38_OPERATOR_SUPPORT_BUNDLE_VERSION = "p38_operator_support_bundle_troubleshooting_export_pack_v1"
P38_OPERATOR_SUPPORT_BUNDLE_REGISTRY_NAME = "p38_operator_support_bundle_registry"

STATUS_GENERATED_REVIEW_ONLY = "P38_OPERATOR_SUPPORT_BUNDLE_TROUBLESHOOTING_EXPORT_PACK_GENERATED_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P38_OPERATOR_SUPPORT_BUNDLE_TROUBLESHOOTING_EXPORT_PACK_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P38_OPERATOR_SUPPORT_BUNDLE_TROUBLESHOOTING_EXPORT_PACK_BLOCKED_FAIL_CLOSED"

_ALLOWED_READ_ONLY_COMMANDS = ("status", "matrix", "waiting", "no_go", "export_paths")
_BLOCKED_COMMAND_KEYWORDS = (
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
_SOURCE_ARTIFACTS = (
    ("p37", "json", "p37_onboarding_wizard_failure_doctor_report.json"),
    ("p37", "json", "p37_onboarding_wizard_failure_doctor_summary.json"),
    ("p37", "json", "p37_onboarding_wizard_failure_doctor_pack.json"),
    ("p37", "json", "p37_self_diagnosis_results.json"),
    ("p37", "json", "p37_failure_doctor_lookup.json"),
    ("p37", "text", "p37_self_diagnosis_pack.md"),
    ("p37", "text", "p37_self_diagnosis_checklist.md"),
    ("p37", "json", "p37_operator_self_diagnosis_card.json"),
    ("p36", "json", "p36_non_developer_onboarding_wizard_report.json"),
    ("p36", "json", "p36_non_developer_onboarding_wizard_summary.json"),
    ("p36", "json", "p36_non_developer_onboarding_wizard_pack.json"),
    ("p36", "text", "p36_zip_drop_in_wizard.md"),
    ("p36", "text", "p36_zip_drop_in_checklist.md"),
    ("p36", "text", "p36_failure_message_lookup.md"),
    ("p36", "json", "p36_operator_onboarding_card.json"),
    ("p35", "json", "p35_operator_ux_quickstart_runbook_pack_report.json"),
    ("p35", "json", "p35_operator_ux_quickstart_runbook_pack_summary.json"),
    ("p35", "json", "p35_operator_ux_quickstart_runbook_pack.json"),
    ("p35", "text", "p35_operator_ux_quickstart_runbook.md"),
    ("p35", "text", "p35_operator_ux_checklist.md"),
    ("p35", "text", "p35_safe_command_guide.md"),
    ("p35", "text", "p35_operator_ux_quickstart.txt"),
    ("p34", "json", "p34_telegram_launcher_command_response_snapshot_pack_report.json"),
    ("p34", "json", "p34_command_response_snapshot_pack.json"),
    ("p34", "json", "p34_telegram_command_response_snapshots.json"),
    ("p34", "json", "p34_launcher_command_response_snapshots.json"),
    ("p34", "text", "p34_command_response_snapshot_pack.md"),
    ("p34", "text", "p34_command_response_snapshot_pack.txt"),
    ("p33", "json", "p33_telegram_launcher_command_router_fixture_validator_report.json"),
    ("p33", "json", "p33_command_router_fixture_validation_results.json"),
    ("p33", "json", "p33_telegram_launcher_command_router_contract.json"),
    ("p33", "text", "p33_command_router_read_only_routes.txt"),
)
_REQUIRED_SOURCE_FILENAMES = tuple(name for _phase, _kind, name in _SOURCE_ARTIFACTS)
_EXECUTION_FIELDS_FOR_P38 = {
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


def _read_json_path(path: Path) -> dict[str, Any] | list[Any]:
    payload = read_json(path, default={})
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, list):
        return list(payload)
    return {}


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any] | list[Any]:
    return _read_json_path(_latest_dir(cfg) / filename)


def _read_latest_text(cfg: AppConfig, filename: str) -> str:
    path = _latest_dir(cfg) / filename
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


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
                if key in _EXECUTION_FIELDS_FOR_P38 and _bool(value):
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


def _redacted_excerpt(text: str, *, limit: int = 600) -> str:
    excerpt = text[:limit]
    for pattern in _SECRET_VALUE_PATTERNS:
        if pattern.lower() in excerpt.lower():
            excerpt = excerpt.replace(pattern, f"{pattern}[REDACTED]")
    return excerpt


def _artifact_manifest(cfg: AppConfig) -> tuple[list[dict[str, Any]], list[tuple[str, Any]]]:
    latest = _latest_dir(cfg)
    manifest: list[dict[str, Any]] = []
    payloads: list[tuple[str, Any]] = []
    for phase, kind, filename in _SOURCE_ARTIFACTS:
        path = latest / filename
        exists = path.exists()
        entry: dict[str, Any] = {
            "phase": phase,
            "kind": kind,
            "filename": filename,
            "exists": exists,
            "path": str(path),
            "sha256": None,
            "size_bytes": None,
            "shareable": False,
        }
        if exists:
            entry["size_bytes"] = path.stat().st_size
            if kind == "json":
                payload = _read_json_path(path)
                entry["sha256"] = sha256_json(payload)
                entry["shareable"] = True
                payloads.append((filename, payload))
            else:
                text = _read_latest_text(cfg, filename)
                entry["sha256"] = sha256_json({"filename": filename, "content": text})
                entry["shareable"] = True
                payloads.append((filename, text))
        manifest.append(entry)
    return manifest, payloads


def _build_manifest_csv(manifest: Sequence[Mapping[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["phase", "kind", "filename", "exists", "size_bytes", "sha256", "shareable"])
    writer.writeheader()
    for item in manifest:
        writer.writerow({field: item.get(field) for field in writer.fieldnames})
    return buffer.getvalue()


def _build_markdown(pack: Mapping[str, Any]) -> str:
    lines = [
        "# P38 Operator Support Bundle / Troubleshooting Export Pack",
        "",
        f"Status: `{pack.get('status')}`",
        f"Decision: `{pack.get('operator_final_activation_decision')}`",
        "",
        "> 이 support bundle은 review-only 문제 공유용입니다. runtime, scheduler, order, endpoint, secret access를 활성화하지 않습니다.",
        "",
        "## What to Share",
        "",
        "- `p38_operator_support_bundle_share_packet.json`",
        "- `p38_operator_support_bundle.md`",
        "- `p38_operator_support_bundle_manifest.csv`",
        "",
        "## Source Artifact Coverage",
        "",
        f"- Required source artifacts: {pack.get('required_source_artifact_count')}",
        f"- Present source artifacts: {pack.get('present_source_artifact_count')}",
        f"- Missing source artifacts: {pack.get('missing_source_artifact_count')}",
        "",
        "## Diagnosis Summary",
        "",
        f"- P37 status: `{pack.get('source_p37_status')}`",
        f"- P37 diagnosis issue count: {pack.get('source_p37_diagnosis_issue_count')}",
        f"- Bundle blocked: `{pack.get('blocked')}`",
        f"- Bundle waiting: `{pack.get('waiting')}`",
        "",
        "## Allowed Read-only Commands",
        "",
    ]
    for command in _ALLOWED_READ_ONLY_COMMANDS:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Commands That Must Stay Blocked", ""])
    for keyword in _BLOCKED_COMMAND_KEYWORDS:
        lines.append(f"- `{keyword}`")
    lines.extend(["", "## Missing Artifacts", ""])
    missing = pack.get("missing_source_artifacts", [])
    if not missing:
        lines.append("- None")
    else:
        for name in missing:
            lines.append(f"- `{name}`")
    lines.extend(["", "## Operator Support Steps", ""])
    for item in pack.get("operator_support_steps", []):
        lines.append(f"- {item}")
    return "\n".join(lines).rstrip() + "\n"


def _build_paths_text(pack: Mapping[str, Any]) -> str:
    lines = ["P38 Operator Support Bundle Paths", ""]
    for key, value in dict(pack.get("support_bundle_paths", {})).items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines).rstrip() + "\n"


def _build_share_packet(pack: Mapping[str, Any], manifest: Sequence[Mapping[str, Any]], payloads: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    safe_excerpts: list[dict[str, Any]] = []
    excerpt_filenames = {
        "p37_self_diagnosis_pack.md",
        "p37_self_diagnosis_checklist.md",
        "p36_zip_drop_in_wizard.md",
        "p35_operator_ux_quickstart_runbook.md",
        "p34_command_response_snapshot_pack.txt",
        "p33_command_router_read_only_routes.txt",
    }
    for source, payload in payloads:
        if source in excerpt_filenames and isinstance(payload, str):
            safe_excerpts.append({"filename": source, "redacted_excerpt": _redacted_excerpt(payload)})
    return {
        "share_packet_id": stable_id("p38_share_packet", {"report_id": pack.get("report_id"), "manifest": list(manifest)}),
        "status": pack.get("status"),
        "waiting": pack.get("waiting"),
        "blocked": pack.get("blocked"),
        "operator_final_activation_decision": pack.get("operator_final_activation_decision"),
        "source_p37_status": pack.get("source_p37_status"),
        "source_p37_diagnosis_issue_count": pack.get("source_p37_diagnosis_issue_count"),
        "missing_source_artifacts": list(pack.get("missing_source_artifacts", [])),
        "allowed_read_only_commands": list(_ALLOWED_READ_ONLY_COMMANDS),
        "blocked_command_keywords": list(_BLOCKED_COMMAND_KEYWORDS),
        "manifest": [
            {"phase": item.get("phase"), "filename": item.get("filename"), "exists": item.get("exists"), "sha256": item.get("sha256"), "size_bytes": item.get("size_bytes")}
            for item in manifest
        ],
        "redacted_text_excerpts": safe_excerpts,
        "runtime": "DISABLED",
        "scheduler": "DISABLED",
        "orders": "DISABLED",
        "authority": "REVIEW_ONLY",
        "contains_secret_values": False,
        "runtime_authority": False,
    }


def build_operator_support_bundle_report(
    *,
    root: str | Path | None = None,
    p37_report: Mapping[str, Any] | None = None,
    p37_summary: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] = (),
    require_all_sources: bool = True,
) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    if p37_report is None:
        p37_report_loaded = _read_latest_json(cfg, "p37_onboarding_wizard_failure_doctor_report.json")
        p37_report = p37_report_loaded if isinstance(p37_report_loaded, Mapping) else {}
    if p37_summary is None:
        p37_summary_loaded = _read_latest_json(cfg, "p37_onboarding_wizard_failure_doctor_summary.json")
        p37_summary = p37_summary_loaded if isinstance(p37_summary_loaded, Mapping) else {}

    manifest, source_payloads = _artifact_manifest(cfg)
    missing_sources = [str(item["filename"]) for item in manifest if not item.get("exists")]
    scan_payloads: list[tuple[str, Any]] = [
        ("p37_report", dict(p37_report)),
        ("p37_summary", dict(p37_summary)),
        *source_payloads,
        *list(extra_payloads_for_scan),
    ]
    unsafe_hits = _scan_truthy_execution_fields(scan_payloads)
    secret_hits = _scan_secret_value_patterns(scan_payloads)
    p37_status = str(p37_report.get("status", "")) if isinstance(p37_report, Mapping) else ""

    issues: list[dict[str, Any]] = []

    def add_issue(code: str, severity: str, message: str, evidence: Any = None) -> None:
        issue = {"code": code, "severity": severity, "message": message}
        if evidence is not None:
            issue["evidence"] = evidence
        issues.append(issue)

    if not p37_report:
        add_issue("missing_p37_report", "waiting", "P37 failure doctor report is missing or empty.")
    if not p37_summary:
        add_issue("missing_p37_summary", "waiting", "P37 failure doctor summary is missing or empty.")
    if require_all_sources and missing_sources:
        add_issue("missing_support_source_artifacts", "waiting", "One or more P33~P37 support source artifacts are missing.", missing_sources)
    if p37_status == P37_STATUS_WAITING_REVIEW_ONLY or _bool(p37_report.get("waiting")):
        add_issue("p37_waiting", "waiting", "Source P37 failure doctor is waiting.")
    if p37_status == P37_STATUS_BLOCKED_FAIL_CLOSED or _bool(p37_report.get("blocked")):
        add_issue("p37_blocked", "blocked", "Source P37 failure doctor is blocked fail-closed.")
    if p37_status and p37_status != P37_STATUS_GENERATED_REVIEW_ONLY:
        add_issue("p37_not_generated", "waiting", f"Source P37 status is not generated: {p37_status}")
    if unsafe_hits:
        add_issue("runtime_flag_truthy", "blocked", "Truthy runtime/order/scheduler flag detected in support bundle sources.", unsafe_hits)
        scheduler_hits = [hit for hit in unsafe_hits if "scheduler" in hit.get("field", "")]
        endpoint_hits = [hit for hit in unsafe_hits if "endpoint" in hit.get("field", "") or hit.get("field") == "http_request_sent"]
        if scheduler_hits:
            add_issue("scheduler_enabled", "blocked", "Scheduler truthy flag detected.", scheduler_hits)
        if endpoint_hits:
            add_issue("endpoint_called", "blocked", "Endpoint-call truthy flag detected.", endpoint_hits)
    if secret_hits:
        add_issue("secret_detected", "blocked", "Secret value pattern detected in support bundle sources.", secret_hits)

    blocked = any(issue["severity"] == "blocked" for issue in issues)
    waiting = bool(issues) and not blocked
    status = STATUS_GENERATED_REVIEW_ONLY
    if waiting:
        status = STATUS_WAITING_REVIEW_ONLY
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED

    operator_steps = [
        "Share only the P38 redacted share packet, support bundle markdown, and manifest CSV.",
        "Do not paste API keys, API secrets, private keys, passphrases, or secret file contents.",
        "Confirm runtime, scheduler, and orders all remain DISABLED before sharing.",
        "Use status/matrix/waiting/no_go/export_paths only while troubleshooting.",
        "If any support bundle issue is blocked, stop and review the issue code before continuing.",
    ]
    pack: dict[str, Any] = {
        "version": P38_OPERATOR_SUPPORT_BUNDLE_VERSION,
        "status": status,
        "waiting": waiting,
        "blocked": blocked,
        "created_at_utc": utc_now_canonical(),
        "source_p37_status": p37_status or None,
        "source_p37_report_sha256": sha256_json(p37_report) if p37_report else None,
        "source_p37_summary_sha256": sha256_json(p37_summary) if p37_summary else None,
        "source_p37_diagnosis_issue_count": p37_report.get("diagnosis_issue_count") if isinstance(p37_report, Mapping) else None,
        "source_p37_diagnosis_codes": list(p37_report.get("diagnosis_codes", [])) if isinstance(p37_report, Mapping) else [],
        "operator_final_activation_decision": p37_report.get("operator_final_activation_decision") or p37_summary.get("operator_final_activation_decision") or "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "support_issues": issues,
        "support_issue_count": len(issues),
        "support_issue_codes": sorted({issue["code"] for issue in issues}),
        "blocked_issue_count": sum(1 for issue in issues if issue["severity"] == "blocked"),
        "waiting_issue_count": sum(1 for issue in issues if issue["severity"] == "waiting"),
        "source_manifest": manifest,
        "required_source_artifact_count": len(_REQUIRED_SOURCE_FILENAMES),
        "present_source_artifact_count": sum(1 for item in manifest if item.get("exists")),
        "missing_source_artifact_count": len(missing_sources),
        "missing_source_artifacts": missing_sources,
        "manifest_csv": _build_manifest_csv(manifest),
        "allowed_read_only_commands": list(_ALLOWED_READ_ONLY_COMMANDS),
        "blocked_command_keywords": list(_BLOCKED_COMMAND_KEYWORDS),
        "operator_support_steps": operator_steps,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "unsafe_truthy_execution_flag_hit_count": len(unsafe_hits),
        "secret_pattern_hits": secret_hits,
        "secret_pattern_hit_count": len(secret_hits),
        "all_support_bundle_artifacts_safe_review_only": not blocked,
        "runtime_authority": False,
        "support_bundle_executes_runtime": False,
        "support_bundle_enables_scheduler": False,
        "support_bundle_allows_order_submission": False,
        "support_bundle_calls_endpoint": False,
        "support_bundle_reads_secret_value": False,
        "support_bundle_contains_secret_value": False,
        "support_bundle_grants_runtime_authority": False,
        "support_bundle_changes_settings": False,
        **{key: False for key in _EXECUTION_FIELDS_FOR_P38 if key not in {"support_bundle_executes_runtime", "support_bundle_enables_scheduler", "support_bundle_allows_order_submission", "support_bundle_calls_endpoint", "support_bundle_reads_secret_value", "support_bundle_contains_secret_value", "support_bundle_grants_runtime_authority", "support_bundle_changes_settings"}},
        "execution_flags": default_execution_flag_state(),
        "truthy_default_execution_flags": truthy_execution_flags(default_execution_flag_state()),
    }
    pack["support_bundle_markdown"] = _build_markdown(pack)
    pack["report_id"] = stable_id("p38_operator_support_bundle", pack)
    pack["redacted_share_packet"] = _build_share_packet(pack, manifest, source_payloads)
    return pack


def build_p38_negative_fixture_results(*, root: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    base_p37_report = {
        "status": P37_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "diagnosis_issue_count": 0,
        "diagnosis_codes": [],
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    base_p37_summary = {
        "status": P37_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    cases: dict[str, dict[str, Any]] = {
        "missing_p37_report": {"p37_report": {}},
        "missing_p37_summary": {"p37_summary": {}},
        "p37_waiting": {"p37_report": {**base_p37_report, "status": P37_STATUS_WAITING_REVIEW_ONLY, "waiting": True}},
        "p37_blocked": {"p37_report": {**base_p37_report, "status": P37_STATUS_BLOCKED_FAIL_CLOSED, "blocked": True}},
        "missing_support_source_artifacts": {"require_all_sources": True},
        "runtime_flag_truthy": {"extra_payloads_for_scan": [("bad_runtime", {"live_scaled_execution_enabled": True})]},
        "scheduler_enabled": {"extra_payloads_for_scan": [("bad_scheduler", {"runtime_scheduler_enabled": True})]},
        "endpoint_called": {"extra_payloads_for_scan": [("bad_endpoint", {"order_endpoint_called": True})]},
        "secret_detected": {"extra_payloads_for_scan": [("bad_secret", "BINANCE_API_SECRET=leak")]},
        "support_bundle_executes_runtime": {"extra_payloads_for_scan": [("bad_bundle", {"support_bundle_executes_runtime": True})]},
        "support_bundle_contains_secret_value": {"extra_payloads_for_scan": [("bad_bundle", {"support_bundle_contains_secret_value": True})]},
    }
    fixtures: dict[str, dict[str, Any]] = {}
    for case, overrides in cases.items():
        report = build_operator_support_bundle_report(
            root=cfg.root,
            p37_report=overrides.get("p37_report", base_p37_report),
            p37_summary=overrides.get("p37_summary", base_p37_summary),
            extra_payloads_for_scan=overrides.get("extra_payloads_for_scan", ()),
            require_all_sources=overrides.get("require_all_sources", False if case != "missing_support_source_artifacts" else True),
        )
        fixtures[case] = {
            "status": report["status"],
            "blocked": bool(report["blocked"]),
            "waiting": bool(report["waiting"]),
            "support_issue_codes": report["support_issue_codes"],
        }
    all_safe = all(item["blocked"] or item["waiting"] for item in fixtures.values())
    return {
        "status": "P38_NEGATIVE_FIXTURES_RECORDED",
        "fixture_results": fixtures,
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all_safe,
        "created_at_utc": utc_now_canonical(),
    }


def persist_operator_support_bundle(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p38_operator_support_bundle")
    report = build_operator_support_bundle_report(root=cfg.root)
    negative = build_p38_negative_fixture_results(root=cfg.root)

    report_path = latest / "p38_operator_support_bundle_report.json"
    summary_path = latest / "p38_operator_support_bundle_summary.json"
    pack_path = latest / "p38_operator_support_bundle_pack.json"
    manifest_path = latest / "p38_operator_support_bundle_manifest.json"
    manifest_csv_path = latest / "p38_operator_support_bundle_manifest.csv"
    markdown_path = latest / "p38_operator_support_bundle.md"
    share_packet_path = latest / "p38_operator_support_bundle_share_packet.json"
    paths_path = latest / "p38_operator_support_bundle_paths.txt"
    negative_path = latest / "p38_operator_support_bundle_negative_fixture_results.json"
    registry_record_path = latest / "p38_operator_support_bundle_registry_record.json"

    support_bundle_paths = {
        "report": str(report_path),
        "summary": str(summary_path),
        "pack": str(pack_path),
        "manifest": str(manifest_path),
        "manifest_csv": str(manifest_csv_path),
        "markdown": str(markdown_path),
        "share_packet": str(share_packet_path),
        "paths": str(paths_path),
    }
    report["support_bundle_paths"] = support_bundle_paths
    report["support_bundle_paths_text"] = _build_paths_text(report)

    summary = {
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "operator_final_activation_decision": report["operator_final_activation_decision"],
        "source_p37_status": report["source_p37_status"],
        "source_p37_diagnosis_issue_count": report["source_p37_diagnosis_issue_count"],
        "support_issue_count": report["support_issue_count"],
        "support_issue_codes": report["support_issue_codes"],
        "required_source_artifact_count": report["required_source_artifact_count"],
        "present_source_artifact_count": report["present_source_artifact_count"],
        "missing_source_artifact_count": report["missing_source_artifact_count"],
        "all_support_bundle_artifacts_safe_review_only": report["all_support_bundle_artifacts_safe_review_only"],
        "allowed_read_only_commands": report["allowed_read_only_commands"],
        "runtime_scheduler_enabled": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "support_bundle_paths": support_bundle_paths,
    }
    pack_without_large_text = {k: v for k, v in report.items() if k not in {"support_bundle_markdown", "manifest_csv", "support_bundle_paths_text"}}

    atomic_write_json(report_path, report)
    atomic_write_json(summary_path, summary)
    atomic_write_json(pack_path, pack_without_large_text)
    atomic_write_json(manifest_path, report["source_manifest"])
    _atomic_write_text(manifest_csv_path, report["manifest_csv"])
    _atomic_write_text(markdown_path, report["support_bundle_markdown"])
    atomic_write_json(share_packet_path, report["redacted_share_packet"])
    _atomic_write_text(paths_path, report["support_bundle_paths_text"])
    atomic_write_json(negative_path, negative)

    atomic_write_json(storage / report_path.name, report)
    atomic_write_json(storage / summary_path.name, summary)
    atomic_write_json(storage / pack_path.name, pack_without_large_text)
    atomic_write_json(storage / manifest_path.name, report["source_manifest"])
    _atomic_write_text(storage / manifest_csv_path.name, report["manifest_csv"])
    _atomic_write_text(storage / markdown_path.name, report["support_bundle_markdown"])
    atomic_write_json(storage / share_packet_path.name, report["redacted_share_packet"])
    _atomic_write_text(storage / paths_path.name, report["support_bundle_paths_text"])

    registry_record = {
        "registry_record_id": stable_id("p38_registry_record", report),
        "report_id": report["report_id"],
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "support_issue_count": report["support_issue_count"],
        "required_source_artifact_count": report["required_source_artifact_count"],
        "present_source_artifact_count": report["present_source_artifact_count"],
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "created_at_utc": utc_now_canonical(),
    }
    atomic_write_json(registry_record_path, registry_record)
    append_registry_record(
        registry_path(cfg, P38_OPERATOR_SUPPORT_BUNDLE_REGISTRY_NAME),
        registry_record,
        registry_name=P38_OPERATOR_SUPPORT_BUNDLE_REGISTRY_NAME,
    )
    return report


__all__ = [
    "P38_OPERATOR_SUPPORT_BUNDLE_VERSION",
    "STATUS_GENERATED_REVIEW_ONLY",
    "STATUS_WAITING_REVIEW_ONLY",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "build_operator_support_bundle_report",
    "build_p38_negative_fixture_results",
    "persist_operator_support_bundle",
]
