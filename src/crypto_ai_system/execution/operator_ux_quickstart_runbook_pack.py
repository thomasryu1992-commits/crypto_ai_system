from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.execution.telegram_launcher_command_response_snapshot_pack import (
    STATUS_BLOCKED_FAIL_CLOSED as P34_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY as P34_STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P34_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_VERSION = "p35_operator_ux_quickstart_runbook_pack_v1"
P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_REGISTRY_NAME = "p35_operator_ux_quickstart_runbook_pack_registry"

STATUS_GENERATED_REVIEW_ONLY = "P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_GENERATED_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_BLOCKED_FAIL_CLOSED"

_ALLOWED_COMMANDS = ("status", "matrix", "waiting", "no_go", "export_paths")
_REQUIRED_ARTIFACTS = (
    "p34_telegram_launcher_command_response_snapshot_pack_report.json",
    "p34_telegram_launcher_command_response_snapshot_pack_summary.json",
    "p34_command_response_snapshot_pack.json",
    "p34_command_response_snapshot_pack.md",
    "p34_command_response_snapshot_pack.txt",
    "p34_telegram_command_response_snapshots.json",
    "p34_launcher_command_response_snapshots.json",
)
_EXECUTION_FIELDS_FOR_P35 = {
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
    "quickstart_executes_runtime",
    "quickstart_allows_order_submission",
    "quickstart_enables_scheduler",
    "quickstart_calls_endpoint",
    "quickstart_reads_secret_value",
    "runbook_executes_runtime",
    "runbook_allows_order_submission",
    "runbook_enables_scheduler",
    "runbook_calls_endpoint",
    "runbook_reads_secret_value",
    "operator_checklist_allows_runtime",
    "operator_checklist_allows_order_submission",
    "safe_command_guide_allows_runtime",
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


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any] | list[Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, list):
        return list(payload)
    return {}


def _read_latest_text(cfg: AppConfig, filename: str) -> str:
    path = _latest_dir(cfg) / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


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
                if key in _EXECUTION_FIELDS_FOR_P35 and _bool(value):
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
            for pattern in _SECRET_VALUE_PATTERNS:
                if pattern.lower() in payload.lower():
                    hits.append({"source": source, "path": path, "pattern": pattern})

    for source, payload in payloads:
        walk(payload, source)
    return hits


def _command_line(command: str) -> str:
    return f"PYTHONPATH=src:. python scripts/run_command_response_snapshot_pack.py --print-{command.replace('_', '-') if command == 'no_go' else command}"


def _build_quickstart_markdown(pack: Mapping[str, Any]) -> str:
    safe_commands = pack.get("safe_commands", [])
    blocked_examples = pack.get("blocked_command_examples", [])
    lines = [
        "# P35 Operator UX Quickstart / Non-Developer Runbook",
        "",
        f"Status: `{pack.get('status')}`",
        f"Decision: `{pack.get('operator_final_activation_decision')}`",
        "",
        "This runbook is a review-only operator guide. It does not enable runtime, scheduler, live orders, testnet orders, or secret access.",
        "",
        "## 1. Unpack and open the package",
        "",
        "```bash",
        "unzip crypto_ai_system_v0.286.0-agent.14-feature-snapshot_p35_operator_ux_quickstart_runbook_pack.zip -d crypto_ai_system",
        "cd crypto_ai_system",
        "```",
        "",
        "## 2. Check the operator dashboard",
        "",
        "Run these read-only commands only:",
        "",
        "```bash",
        "PYTHONPATH=src:. python scripts/run_command_response_snapshot_pack.py --print-telegram",
        "PYTHONPATH=src:. python scripts/run_command_response_snapshot_pack.py --print-launcher",
        "PYTHONPATH=src:. python scripts/run_operator_ux_quickstart_runbook_pack.py --print-checklist",
        "```",
        "",
        "## 3. Allowed dashboard commands",
        "",
    ]
    for command in safe_commands:
        lines.append(f"- `{command}`: read-only dashboard lookup")
    lines.extend([
        "",
        "## 4. Commands that must stay blocked",
        "",
    ])
    for command in blocked_examples[:12]:
        lines.append(f"- `{command}`")
    lines.extend([
        "",
        "## 5. Operator interpretation",
        "",
        "- `WAITING` means required external/operator evidence is missing.",
        "- `NO-GO` means the package must not proceed until blockers are fixed.",
        "- `GO-REVIEW-ONLY` still does not mean runtime authority.",
        "- Runtime remains disabled unless a separate future runtime boundary performs activation after all required evidence is valid.",
        "",
        "## 6. Safety invariants",
        "",
        "- Do not paste API keys, API secrets, private keys, passphrases, or secret files into the package.",
        "- Do not run enable/start/submit/order/live/trade/activate/scheduler commands.",
        "- Do not edit settings.yaml or score_weights to force promotion.",
        "- Do not treat mock, sample, fallback, or review-only evidence as exchange execution evidence.",
        "- Keep runtime, scheduler, and order submission disabled.",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _build_checklist_markdown(pack: Mapping[str, Any]) -> str:
    items = pack.get("operator_checklist", [])
    lines = ["# P35 Non-Developer Operator Checklist", ""]
    for item in items:
        lines.append(f"- [ ] {item}")
    lines.extend([
        "",
        "Runtime must remain DISABLED after completing this checklist.",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _build_safe_command_guide_markdown(pack: Mapping[str, Any]) -> str:
    lines = [
        "# P35 Safe Command Guide",
        "",
        "Allowed commands are read-only dashboard lookups. They cannot enable runtime, submit orders, start a scheduler, call endpoints, or read secrets.",
        "",
        "## Allowed",
        "",
    ]
    for command in pack.get("safe_commands", []):
        lines.append(f"- `{command}`")
    lines.extend(["", "## Blocked examples", ""])
    for command in pack.get("blocked_command_examples", []):
        lines.append(f"- `{command}`")
    lines.extend([
        "",
        "If a command sounds like enable, start, submit, order, live, trade, activate, scheduler, place, cancel, or runtime, treat it as blocked.",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _build_plain_text(pack: Mapping[str, Any]) -> str:
    return (
        "Crypto_AI_System P35 Quickstart\n"
        f"Status: {pack.get('status')}\n"
        f"Decision: {pack.get('operator_final_activation_decision')}\n"
        "Runtime: DISABLED | Scheduler: DISABLED | Orders: DISABLED | Authority: REVIEW_ONLY\n"
        f"Allowed commands: {', '.join(pack.get('safe_commands', []))}\n"
        "Blocked command families: enable/start/submit/order/live/trade/activate/scheduler/place/cancel/runtime\n"
    )


def _build_pack(*, status: str, p34_report: Mapping[str, Any], p34_summary: Mapping[str, Any], p34_pack: Mapping[str, Any], p34_text: str, p34_markdown: str) -> dict[str, Any]:
    waiting_phases = []
    decision = "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE"
    if isinstance(p34_pack, Mapping):
        decision = str(p34_pack.get("operator_final_activation_decision") or decision)
    safe_commands = list(_ALLOWED_COMMANDS)
    blocked_examples = [
        "/crypto_enable",
        "/crypto_start",
        "/crypto_submit",
        "/crypto_order",
        "/crypto_live",
        "/crypto_activate",
        "/crypto_trade",
        "/crypto_scheduler_start",
        "/crypto_place_order",
        "/crypto_cancel_order",
        "enable live",
        "start runtime",
        "submit order",
        "activate scheduler",
    ]
    operator_checklist = [
        "Confirm the package is review-only and not live auto-trading authority.",
        "Run the status command and confirm Runtime/Scheduler/Orders are DISABLED.",
        "Run the matrix command and confirm the final decision is WAITING unless external/operator evidence is valid.",
        "Review waiting phases before requesting any further runtime work.",
        "Review no_go phases and stop if any blocker appears.",
        "Use export_paths to locate Markdown, CSV, Telegram, and Launcher dashboard artifacts.",
        "Do not run enable/start/submit/order/live/trade/activate/scheduler commands.",
        "Do not paste API keys, API secrets, private keys, passphrases, or secret files.",
        "Do not mutate settings.yaml, score_weights, runtime flags, or launcher routers.",
        "Keep all order endpoint and HTTP request evidence false unless a later approved runtime boundary explicitly performs execution.",
    ]
    quickstart_paths = {
        "quickstart_markdown": "storage/latest/p35_operator_ux_quickstart_runbook.md",
        "operator_checklist_markdown": "storage/latest/p35_operator_ux_checklist.md",
        "safe_command_guide_markdown": "storage/latest/p35_safe_command_guide.md",
        "quickstart_text": "storage/latest/p35_operator_ux_quickstart.txt",
        "runbook_pack_json": "storage/latest/p35_operator_ux_quickstart_runbook_pack.json",
    }
    pack: dict[str, Any] = {
        "p35_operator_ux_quickstart_runbook_pack_version": P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_VERSION,
        "status": status,
        "created_at_utc": utc_now_canonical(),
        "operator_final_activation_decision": decision,
        "source_p34_status": p34_report.get("status"),
        "source_p34_report_sha256": sha256_json(p34_report) if p34_report else None,
        "source_p34_summary_sha256": sha256_json(p34_summary) if p34_summary else None,
        "source_p34_snapshot_pack_sha256": sha256_json(p34_pack) if p34_pack else None,
        "safe_commands": safe_commands,
        "blocked_command_examples": blocked_examples,
        "operator_checklist": operator_checklist,
        "quickstart_paths": quickstart_paths,
        "p34_snapshot_text_preview": p34_text[:1000],
        "p34_snapshot_markdown_preview": p34_markdown[:1000],
        "read_only": True,
        "runtime_authority": False,
        "quickstart_executes_runtime": False,
        "quickstart_allows_order_submission": False,
        "quickstart_enables_scheduler": False,
        "quickstart_calls_endpoint": False,
        "quickstart_reads_secret_value": False,
        "runbook_executes_runtime": False,
        "runbook_allows_order_submission": False,
        "runbook_enables_scheduler": False,
        "runbook_calls_endpoint": False,
        "runbook_reads_secret_value": False,
        "operator_checklist_allows_runtime": False,
        "operator_checklist_allows_order_submission": False,
        "safe_command_guide_allows_runtime": False,
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
        "waiting_phases": waiting_phases,
    }
    pack["runbook_pack_sha256"] = sha256_json(pack)
    return pack


def build_operator_ux_quickstart_runbook_pack_report(
    *,
    root: Path | None = None,
    p34_report: Mapping[str, Any] | None = None,
    p34_summary: Mapping[str, Any] | None = None,
    p34_snapshot_pack: Mapping[str, Any] | None = None,
    p34_text_snapshot: str | None = None,
    p34_markdown_snapshot: str | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] | None = None,
) -> dict[str, Any]:
    root = root or Path.cwd()
    cfg = load_config(root)
    latest = _latest_dir(cfg)
    if p34_report is None:
        loaded = _read_latest_json(cfg, "p34_telegram_launcher_command_response_snapshot_pack_report.json")
        p34_report = dict(loaded) if isinstance(loaded, Mapping) else {}
    if p34_summary is None:
        loaded_summary = _read_latest_json(cfg, "p34_telegram_launcher_command_response_snapshot_pack_summary.json")
        p34_summary = dict(loaded_summary) if isinstance(loaded_summary, Mapping) else {}
    if p34_snapshot_pack is None:
        loaded_pack = _read_latest_json(cfg, "p34_command_response_snapshot_pack.json")
        p34_snapshot_pack = dict(loaded_pack) if isinstance(loaded_pack, Mapping) else {}
    if p34_text_snapshot is None:
        p34_text_snapshot = _read_latest_text(cfg, "p34_command_response_snapshot_pack.txt")
    if p34_markdown_snapshot is None:
        p34_markdown_snapshot = _read_latest_text(cfg, "p34_command_response_snapshot_pack.md")

    missing_artifacts = [name for name in _REQUIRED_ARTIFACTS if not (latest / name).exists()]
    missing_report = not bool(p34_report)
    missing_summary = not bool(p34_summary)
    missing_pack = not bool(p34_snapshot_pack)
    upstream_blocked = bool(p34_report.get("blocked", False)) or p34_report.get("status") == P34_STATUS_BLOCKED_FAIL_CLOSED
    upstream_waiting = bool(p34_report.get("waiting", False)) or p34_report.get("status") == P34_STATUS_WAITING_REVIEW_ONLY
    upstream_generated = p34_report.get("status") == P34_STATUS_GENERATED_REVIEW_ONLY

    provisional_pack = _build_pack(
        status=STATUS_GENERATED_REVIEW_ONLY,
        p34_report=p34_report,
        p34_summary=p34_summary,
        p34_pack=p34_snapshot_pack,
        p34_text=p34_text_snapshot or "",
        p34_markdown=p34_markdown_snapshot or "",
    )
    scan_payloads: list[tuple[str, Any]] = [
        ("p34_report", p34_report),
        ("p34_summary", p34_summary),
        ("p34_snapshot_pack", p34_snapshot_pack),
        ("p34_text_snapshot", p34_text_snapshot or ""),
        ("p34_markdown_snapshot", p34_markdown_snapshot or ""),
        ("p35_runbook_pack", provisional_pack),
    ]
    scan_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(scan_payloads)
    secret_hits = _scan_secret_value_patterns(scan_payloads)
    endpoint_fields = {"order_endpoint_called", "live_order_endpoint_called", "order_status_endpoint_called", "cancel_endpoint_called", "http_request_sent", "quickstart_calls_endpoint", "runbook_calls_endpoint"}
    endpoint_hits = [hit for hit in unsafe_hits if hit["field"] in endpoint_fields]
    truthy_disabled = truthy_execution_flags(default_execution_flag_state())

    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if missing_artifacts:
        waiting_reasons.append("P35_REQUIRED_P34_SNAPSHOT_ARTIFACTS_MISSING")
    if missing_report:
        waiting_reasons.append("P35_SOURCE_P34_REPORT_MISSING")
    if missing_summary:
        waiting_reasons.append("P35_SOURCE_P34_SUMMARY_MISSING")
    if missing_pack:
        waiting_reasons.append("P35_SOURCE_P34_SNAPSHOT_PACK_MISSING")
    if upstream_blocked:
        block_reasons.append("P35_SOURCE_P34_BLOCKED_FAIL_CLOSED")
    if upstream_waiting and not upstream_blocked:
        waiting_reasons.append("P35_SOURCE_P34_WAITING_REVIEW_ONLY")
    if not upstream_generated and not upstream_blocked and not missing_report:
        waiting_reasons.append("P35_SOURCE_P34_NOT_GENERATED_REVIEW_ONLY")
    if unsafe_hits:
        block_reasons.append("P35_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND")
    if endpoint_hits:
        block_reasons.append("P35_ENDPOINT_CALL_EVIDENCE_FOUND")
    if secret_hits:
        block_reasons.append("P35_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P35_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED
    elif waiting_reasons:
        status = STATUS_WAITING_REVIEW_ONLY
    else:
        status = STATUS_GENERATED_REVIEW_ONLY

    pack = _build_pack(
        status=status,
        p34_report=p34_report,
        p34_summary=p34_summary,
        p34_pack=p34_snapshot_pack,
        p34_text=p34_text_snapshot or "",
        p34_markdown=p34_markdown_snapshot or "",
    )
    quickstart_markdown = _build_quickstart_markdown(pack)
    checklist_markdown = _build_checklist_markdown(pack)
    safe_command_guide_markdown = _build_safe_command_guide_markdown(pack)
    quickstart_text = _build_plain_text(pack)
    artifacts = {
        "quickstart_markdown_sha256": sha256_json(quickstart_markdown),
        "operator_checklist_markdown_sha256": sha256_json(checklist_markdown),
        "safe_command_guide_markdown_sha256": sha256_json(safe_command_guide_markdown),
        "quickstart_text_sha256": sha256_json(quickstart_text),
        "runbook_pack_sha256": sha256_json(pack),
    }

    report: dict[str, Any] = {
        "p35_operator_ux_quickstart_runbook_pack_version": P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": not blocked,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "missing_artifacts": missing_artifacts,
        "source_p34_report_present": not missing_report,
        "source_p34_summary_present": not missing_summary,
        "source_p34_snapshot_pack_present": not missing_pack,
        "source_p34_status": p34_report.get("status"),
        "operator_final_activation_decision": pack["operator_final_activation_decision"],
        "safe_command_count": len(pack["safe_commands"]),
        "blocked_command_example_count": len(pack["blocked_command_examples"]),
        "operator_checklist_item_count": len(pack["operator_checklist"]),
        "quickstart_paths": pack["quickstart_paths"],
        "artifact_hashes": artifacts,
        "quickstart_markdown_preview": quickstart_markdown[:1600],
        "operator_checklist_preview": checklist_markdown[:1600],
        "safe_command_guide_preview": safe_command_guide_markdown[:1600],
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "unsafe_truthy_execution_flag_hit_count": len(unsafe_hits),
        "endpoint_call_evidence_hits": endpoint_hits,
        "endpoint_call_evidence_hit_count": len(endpoint_hits),
        "secret_value_scan_hits": secret_hits,
        "secret_value_scan_hit_count": len(secret_hits),
        "all_quickstart_artifacts_safe_review_only": not blocked,
        "read_only": True,
        "runtime_authority": False,
        "quickstart_executes_runtime": False,
        "quickstart_allows_order_submission": False,
        "quickstart_enables_scheduler": False,
        "quickstart_calls_endpoint": False,
        "quickstart_reads_secret_value": False,
        "runbook_executes_runtime": False,
        "runbook_allows_order_submission": False,
        "runbook_enables_scheduler": False,
        "runbook_calls_endpoint": False,
        "runbook_reads_secret_value": False,
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
        "live_order_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "runbook_pack": pack,
        "quickstart_markdown": quickstart_markdown,
        "operator_checklist_markdown": checklist_markdown,
        "safe_command_guide_markdown": safe_command_guide_markdown,
        "quickstart_text": quickstart_text,
    }
    report["report_sha256"] = sha256_json({k: v for k, v in report.items() if k != "report_sha256"})
    return report


def build_p35_negative_fixture_results(*, root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    safe_p34_report = {
        "status": P34_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "snapshot_command_executes_runtime": False,
        "snapshot_command_allows_order_submission": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    safe_summary = dict(safe_p34_report)
    safe_pack = {
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "read_only": True,
        "runtime_authority": False,
        "snapshot_command_executes_runtime": False,
        "snapshot_command_allows_order_submission": False,
        "secret_value_accessed": False,
    }
    fixtures = {
        "missing_p34_report": build_operator_ux_quickstart_runbook_pack_report(root=root, p34_report={}, p34_summary={}, p34_snapshot_pack={}, p34_text_snapshot="", p34_markdown_snapshot=""),
        "p34_blocked": build_operator_ux_quickstart_runbook_pack_report(root=root, p34_report={**safe_p34_report, "status": P34_STATUS_BLOCKED_FAIL_CLOSED, "blocked": True}, p34_summary=safe_summary, p34_snapshot_pack=safe_pack, p34_text_snapshot="ok", p34_markdown_snapshot="ok"),
        "unsafe_runtime_flag": build_operator_ux_quickstart_runbook_pack_report(root=root, p34_report={**safe_p34_report, "live_scaled_execution_enabled": True}, p34_summary=safe_summary, p34_snapshot_pack=safe_pack, p34_text_snapshot="ok", p34_markdown_snapshot="ok"),
        "endpoint_called": build_operator_ux_quickstart_runbook_pack_report(root=root, p34_report={**safe_p34_report, "order_endpoint_called": True}, p34_summary=safe_summary, p34_snapshot_pack=safe_pack, p34_text_snapshot="ok", p34_markdown_snapshot="ok"),
        "secret_pattern_found": build_operator_ux_quickstart_runbook_pack_report(root=root, p34_report=safe_p34_report, p34_summary=safe_summary, p34_snapshot_pack=safe_pack, p34_text_snapshot="BINANCE_API_SECRET=leak", p34_markdown_snapshot="ok"),
        "quickstart_executes_runtime": build_operator_ux_quickstart_runbook_pack_report(root=root, p34_report=safe_p34_report, p34_summary=safe_summary, p34_snapshot_pack=safe_pack, p34_text_snapshot="ok", p34_markdown_snapshot="ok", extra_payloads_for_scan=[("bad_quickstart", {"quickstart_executes_runtime": True})]),
        "quickstart_allows_order_submission": build_operator_ux_quickstart_runbook_pack_report(root=root, p34_report=safe_p34_report, p34_summary=safe_summary, p34_snapshot_pack=safe_pack, p34_text_snapshot="ok", p34_markdown_snapshot="ok", extra_payloads_for_scan=[("bad_quickstart", {"quickstart_allows_order_submission": True})]),
    }
    fixture_results: dict[str, Any] = {}
    for name, report in fixtures.items():
        fixture_results[name] = {
            "status": report.get("status"),
            "blocked": bool(report.get("blocked", False)),
            "waiting": bool(report.get("waiting", False)),
            "block_reasons": report.get("block_reasons", []),
            "waiting_reasons": report.get("waiting_reasons", []),
        }
    all_fail_closed = all(item["blocked"] or item["waiting"] for item in fixture_results.values())
    return {
        "status": "P35_NEGATIVE_FIXTURES_RECORDED",
        "created_at_utc": utc_now_canonical(),
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all_fail_closed,
        "fixture_results": fixture_results,
    }


def persist_operator_ux_quickstart_runbook_pack(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    report = build_operator_ux_quickstart_runbook_pack_report(root=cfg.root)
    negative = build_p35_negative_fixture_results(root=cfg.root)
    pack = report["runbook_pack"]
    quickstart_markdown = str(report["quickstart_markdown"])
    checklist_markdown = str(report["operator_checklist_markdown"])
    safe_command_guide_markdown = str(report["safe_command_guide_markdown"])
    quickstart_text = str(report["quickstart_text"])

    atomic_write_json(latest / "p35_operator_ux_quickstart_runbook_pack_report.json", {k: v for k, v in report.items() if k not in {"quickstart_markdown", "operator_checklist_markdown", "safe_command_guide_markdown", "quickstart_text", "runbook_pack"}})
    summary = {
        "status": report["status"],
        "blocked": report["blocked"],
        "waiting": report["waiting"],
        "operator_final_activation_decision": report["operator_final_activation_decision"],
        "safe_command_count": report["safe_command_count"],
        "blocked_command_example_count": report["blocked_command_example_count"],
        "operator_checklist_item_count": report["operator_checklist_item_count"],
        "all_quickstart_artifacts_safe_review_only": report["all_quickstart_artifacts_safe_review_only"],
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "quickstart_paths": report["quickstart_paths"],
    }
    atomic_write_json(latest / "p35_operator_ux_quickstart_runbook_pack_summary.json", summary)
    atomic_write_json(latest / "p35_operator_ux_quickstart_runbook_pack.json", pack)
    _atomic_write_text(latest / "p35_operator_ux_quickstart_runbook.md", quickstart_markdown)
    _atomic_write_text(latest / "p35_operator_ux_checklist.md", checklist_markdown)
    _atomic_write_text(latest / "p35_safe_command_guide.md", safe_command_guide_markdown)
    _atomic_write_text(latest / "p35_operator_ux_quickstart.txt", quickstart_text)
    atomic_write_json(latest / "p35_operator_ux_quickstart_runbook_pack_negative_fixture_results.json", negative)

    registry_record = {
        "id": stable_id("p35_operator_ux_quickstart_runbook_pack", report, 24),
        "status": report["status"],
        "created_at_utc": utc_now_canonical(),
        "report_sha256": report["report_sha256"],
        "summary_sha256": sha256_json(summary),
        "runbook_pack_sha256": sha256_json(pack),
        "quickstart_markdown_sha256": sha256_json(quickstart_markdown),
        "operator_checklist_markdown_sha256": sha256_json(checklist_markdown),
        "safe_command_guide_markdown_sha256": sha256_json(safe_command_guide_markdown),
        "negative_fixture_results_sha256": sha256_json(negative),
        "review_only": True,
        "runtime_authority": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    atomic_write_json(latest / "p35_operator_ux_quickstart_runbook_pack_registry_record.json", registry_record)
    append_registry_record(
        registry_path(cfg, P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_REGISTRY_NAME),
        registry_record,
        registry_name=P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_REGISTRY_NAME,
    )

    storage = _storage_dir(cfg, "storage/p35_operator_ux_quickstart_runbook_pack")
    atomic_write_json(storage / "p35_operator_ux_quickstart_runbook_pack_report.json", {k: v for k, v in report.items() if k not in {"quickstart_markdown", "operator_checklist_markdown", "safe_command_guide_markdown", "quickstart_text", "runbook_pack"}})
    _atomic_write_text(cfg.root / "P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_REPORT.md", quickstart_markdown)
    return report
