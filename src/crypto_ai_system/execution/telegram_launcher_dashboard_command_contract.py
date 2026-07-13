from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.operator_decision_matrix_dashboard_export import (
    STATUS_BLOCKED_FAIL_CLOSED as P31_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY as P31_STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P31_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P32_TELEGRAM_LAUNCHER_DASHBOARD_COMMAND_CONTRACT_VERSION = "p32_telegram_launcher_dashboard_command_contract_v1"
P32_TELEGRAM_LAUNCHER_DASHBOARD_COMMAND_CONTRACT_REGISTRY_NAME = "p32_telegram_launcher_dashboard_command_contract_registry"

STATUS_GENERATED_REVIEW_ONLY = "P32_TELEGRAM_LAUNCHER_DASHBOARD_COMMAND_CONTRACT_GENERATED_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P32_TELEGRAM_LAUNCHER_DASHBOARD_COMMAND_CONTRACT_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P32_TELEGRAM_LAUNCHER_DASHBOARD_COMMAND_CONTRACT_BLOCKED_FAIL_CLOSED"

_ALLOWED_COMMANDS = ("status", "matrix", "waiting", "no_go", "export_paths")
_ALLOWED_SURFACES = ("telegram", "launcher")

_EXECUTION_FIELDS_FOR_P32 = {
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
    "dashboard_command_is_runtime_authority",
    "telegram_command_executes_runtime",
    "launcher_command_executes_runtime",
    "telegram_command_allows_order_submission",
    "launcher_command_allows_order_submission",
    "telegram_dashboard_allows_runtime",
    "launcher_dashboard_allows_runtime",
    "scheduler_start_requested",
    "order_submission_requested",
    "endpoint_call_allowed",
    "secret_file_accessed",
    "secret_file_created",
    "command_mutates_runtime",
    "command_writes_runtime_settings",
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
                if key in _EXECUTION_FIELDS_FOR_P32 and _bool(value):
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


def _artifact_paths(cfg: AppConfig) -> dict[str, str]:
    latest = _latest_dir(cfg)
    return {
        "markdown_dashboard": str((latest / "p31_operator_decision_matrix_dashboard.md").resolve()),
        "csv_dashboard": str((latest / "p31_operator_decision_matrix_dashboard.csv").resolve()),
        "compact_dashboard_json": str((latest / "p31_operator_decision_matrix_compact_dashboard.json").resolve()),
        "telegram_summary_txt": str((latest / "p31_operator_decision_matrix_telegram_summary.txt").resolve()),
        "launcher_card_json": str((latest / "p31_operator_decision_matrix_launcher_card.json").resolve()),
        "p31_report_json": str((latest / "p31_operator_decision_matrix_dashboard_export_report.json").resolve()),
        "p31_summary_json": str((latest / "p31_operator_decision_matrix_dashboard_export_summary.json").resolve()),
    }


def _command_spec(command: str, surface: str) -> dict[str, Any]:
    aliases = {
        "status": ["/crypto_status", "status"],
        "matrix": ["/crypto_matrix", "matrix"],
        "waiting": ["/crypto_waiting", "waiting"],
        "no_go": ["/crypto_no_go", "no-go", "no_go"],
        "export_paths": ["/crypto_export_paths", "export paths", "export_paths"],
    }
    descriptions = {
        "status": "Show final activation decision, runtime status, scheduler status, and order-submission status.",
        "matrix": "Show Go / Waiting / No-Go counts and dashboard artifact pointers.",
        "waiting": "Show waiting phases and the next evidence collection action.",
        "no_go": "Show No-Go phases and blockers, if any.",
        "export_paths": "Show review-only dashboard artifact paths for Markdown, CSV, Telegram, and Launcher outputs.",
    }
    return {
        "command_id": f"p32_{surface}_{command}",
        "surface": surface,
        "command": command,
        "aliases": aliases[command],
        "description": descriptions[command],
        "read_sources": [
            "storage/latest/p31_operator_decision_matrix_compact_dashboard.json",
            "storage/latest/p31_operator_decision_matrix_launcher_card.json",
            "storage/latest/p31_operator_decision_matrix_telegram_summary.txt",
            "storage/latest/p31_operator_decision_matrix_dashboard.md",
            "storage/latest/p31_operator_decision_matrix_dashboard.csv",
        ],
        "writes_runtime_state": False,
        "mutates_launcher_registry": False,
        "mutates_telegram_router": False,
        "enables_runtime": False,
        "enables_scheduler": False,
        "allows_order_submission": False,
        "calls_endpoint": False,
        "reads_secret_value": False,
        "runtime_authority": False,
        "review_only": True,
        "forbidden_actions": [
            "enable_runtime",
            "start_scheduler",
            "submit_order",
            "call_order_endpoint",
            "read_secret_value",
            "mutate_settings",
            "auto_promote_stage",
        ],
    }


def _build_command_contract() -> dict[str, Any]:
    commands = [_command_spec(command, surface) for surface in _ALLOWED_SURFACES for command in _ALLOWED_COMMANDS]
    return {
        "p32_telegram_launcher_dashboard_command_contract_version": P32_TELEGRAM_LAUNCHER_DASHBOARD_COMMAND_CONTRACT_VERSION,
        "created_at_utc": utc_now_canonical(),
        "contract_status": "review_only_read_only_commands",
        "allowed_commands": list(_ALLOWED_COMMANDS),
        "surfaces": list(_ALLOWED_SURFACES),
        "commands": commands,
        "read_only": True,
        "runtime_authority": False,
        "dashboard_command_is_runtime_authority": False,
        "telegram_command_executes_runtime": False,
        "launcher_command_executes_runtime": False,
        "telegram_command_allows_order_submission": False,
        "launcher_command_allows_order_submission": False,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def _command_responses(compact: Mapping[str, Any], launcher_card: Mapping[str, Any], paths: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    waiting_phases = list(compact.get("waiting_phases") or [])
    no_go_phases = list(compact.get("no_go_phases") or [])
    decision = str(compact.get("operator_final_activation_decision") or "UNKNOWN")
    status_payload = {
        "decision": decision,
        "status": compact.get("status"),
        "runtime": "DISABLED",
        "scheduler": "DISABLED",
        "orders": "DISABLED",
        "authority": "REVIEW_ONLY",
        "next_action": compact.get("next_operator_action"),
        "runtime_authority": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
    }
    matrix_payload = {
        "decision": decision,
        "go_review_only": int(compact.get("go_review_only_phase_count") or 0),
        "waiting": int(compact.get("waiting_phase_count") or len(waiting_phases)),
        "no_go": int(compact.get("no_go_phase_count") or len(no_go_phases)),
        "required_phase_count": int(compact.get("required_phase_count") or 0),
        "present_phase_count": int(compact.get("present_phase_count") or 0),
        "dashboard_path": paths.get("markdown_dashboard"),
        "csv_path": paths.get("csv_dashboard"),
        "runtime_authority": False,
    }
    waiting_payload = {
        "waiting_count": len(waiting_phases),
        "waiting_phases": waiting_phases,
        "next_action": compact.get("next_operator_action"),
        "runtime_authority": False,
    }
    no_go_payload = {
        "no_go_count": len(no_go_phases),
        "no_go_phases": no_go_phases,
        "next_action": "Resolve NO-GO blockers before runtime review." if no_go_phases else "No No-Go phases reported by P30/P31.",
        "runtime_authority": False,
    }
    export_paths_payload = {
        "paths": dict(paths),
        "launcher_card_title": launcher_card.get("title"),
        "runtime_authority": False,
    }
    return {
        "status": status_payload,
        "matrix": matrix_payload,
        "waiting": waiting_payload,
        "no_go": no_go_payload,
        "export_paths": export_paths_payload,
    }


def _telegram_text_responses(responses: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    status = responses["status"]
    matrix = responses["matrix"]
    waiting = responses["waiting"]
    no_go = responses["no_go"]
    return {
        "status": (
            "Crypto_AI_System Status\n"
            f"Decision: {status['decision']}\n"
            "Runtime: DISABLED | Scheduler: DISABLED | Orders: DISABLED\n"
            "Authority: REVIEW_ONLY"
        ),
        "matrix": (
            "Crypto_AI_System Matrix\n"
            f"Go/Waiting/No-Go: {matrix['go_review_only']} / {matrix['waiting']} / {matrix['no_go']}\n"
            f"Dashboard: {matrix['dashboard_path']}\n"
            "Authority: REVIEW_ONLY"
        ),
        "waiting": (
            "Crypto_AI_System Waiting Phases\n"
            f"Count: {waiting['waiting_count']}\n"
            f"Phases: {', '.join(waiting['waiting_phases'][:12]) if waiting['waiting_phases'] else 'none'}\n"
            f"Next: {waiting['next_action']}"
        ),
        "no_go": (
            "Crypto_AI_System No-Go Phases\n"
            f"Count: {no_go['no_go_count']}\n"
            f"Phases: {', '.join(no_go['no_go_phases']) if no_go['no_go_phases'] else 'none'}\n"
            f"Next: {no_go['next_action']}"
        ),
        "export_paths": (
            "Crypto_AI_System Export Paths\n"
            f"Markdown: {responses['export_paths']['paths'].get('markdown_dashboard')}\n"
            f"CSV: {responses['export_paths']['paths'].get('csv_dashboard')}\n"
            "Authority: REVIEW_ONLY"
        ),
    }


def build_telegram_launcher_dashboard_command_contract_report(
    *,
    root: Path | None = None,
    p31_report: Mapping[str, Any] | None = None,
    p31_summary: Mapping[str, Any] | None = None,
    compact_dashboard: Mapping[str, Any] | None = None,
    launcher_card: Mapping[str, Any] | None = None,
    telegram_summary_text: str | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] | None = None,
) -> dict[str, Any]:
    root = root or Path.cwd()
    cfg = load_config(root)
    if p31_report is None:
        loaded = _read_latest_json(cfg, "p31_operator_decision_matrix_dashboard_export_report.json")
        p31_report = dict(loaded) if isinstance(loaded, Mapping) else {}
    if p31_summary is None:
        loaded_summary = _read_latest_json(cfg, "p31_operator_decision_matrix_dashboard_export_summary.json")
        p31_summary = dict(loaded_summary) if isinstance(loaded_summary, Mapping) else {}
    if compact_dashboard is None:
        loaded_compact = _read_latest_json(cfg, "p31_operator_decision_matrix_compact_dashboard.json")
        compact_dashboard = dict(loaded_compact) if isinstance(loaded_compact, Mapping) else {}
    if launcher_card is None:
        loaded_launcher = _read_latest_json(cfg, "p31_operator_decision_matrix_launcher_card.json")
        launcher_card = dict(loaded_launcher) if isinstance(loaded_launcher, Mapping) else {}
    if telegram_summary_text is None:
        telegram_summary_text = _read_latest_text(cfg, "p31_operator_decision_matrix_telegram_summary.txt")

    missing_p31_report = not bool(p31_report)
    missing_compact = not bool(compact_dashboard)
    missing_launcher = not bool(launcher_card)
    missing_telegram_summary = not bool(telegram_summary_text.strip())
    upstream_blocked = bool(p31_report.get("blocked", False)) or p31_report.get("status") == P31_STATUS_BLOCKED_FAIL_CLOSED

    contract = _build_command_contract()
    paths = _artifact_paths(cfg)
    responses = _command_responses(compact_dashboard, launcher_card, paths)
    telegram_text = _telegram_text_responses(responses)
    launcher_payload = {
        "contract_id": "p32_launcher_dashboard_command_contract",
        "surface": "launcher",
        "available_commands": list(_ALLOWED_COMMANDS),
        "responses": responses,
        "runtime_enabled": False,
        "scheduler_enabled": False,
        "order_submission_allowed": False,
        "runtime_authority": False,
    }

    scan_payloads: list[tuple[str, Any]] = [
        ("p31_report", p31_report),
        ("p31_summary", p31_summary),
        ("compact_dashboard", compact_dashboard),
        ("launcher_card", launcher_card),
        ("telegram_summary_text", telegram_summary_text),
        ("command_contract", contract),
        ("command_responses", responses),
        ("telegram_text_responses", telegram_text),
        ("launcher_payload", launcher_payload),
    ]
    scan_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(scan_payloads)
    secret_hits = _scan_secret_value_patterns(scan_payloads)
    endpoint_hits = [hit for hit in unsafe_hits if hit["field"] in {"order_endpoint_called", "live_order_endpoint_called", "order_status_endpoint_called", "cancel_endpoint_called", "http_request_sent", "endpoint_call_allowed"}]
    truthy_disabled = truthy_execution_flags(default_execution_flag_state())

    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if missing_p31_report:
        waiting_reasons.append("P32_SOURCE_P31_REPORT_MISSING")
    if missing_compact:
        waiting_reasons.append("P32_SOURCE_P31_COMPACT_DASHBOARD_MISSING")
    if missing_launcher:
        waiting_reasons.append("P32_SOURCE_P31_LAUNCHER_CARD_MISSING")
    if missing_telegram_summary:
        waiting_reasons.append("P32_SOURCE_P31_TELEGRAM_SUMMARY_MISSING")
    if upstream_blocked:
        block_reasons.append("P32_SOURCE_P31_BLOCKED_FAIL_CLOSED")
    if unsafe_hits:
        block_reasons.append("P32_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND")
    if endpoint_hits:
        block_reasons.append("P32_ENDPOINT_CALL_EVIDENCE_FOUND")
    if secret_hits:
        block_reasons.append("P32_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P32_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED
    elif waiting_reasons:
        status = STATUS_WAITING_REVIEW_ONLY
    else:
        status = STATUS_GENERATED_REVIEW_ONLY

    report: dict[str, Any] = {
        "p32_telegram_launcher_dashboard_command_contract_version": P32_TELEGRAM_LAUNCHER_DASHBOARD_COMMAND_CONTRACT_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": not blocked,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "source_p31_report_present": not missing_p31_report,
        "source_p31_compact_dashboard_present": not missing_compact,
        "source_p31_launcher_card_present": not missing_launcher,
        "source_p31_telegram_summary_present": not missing_telegram_summary,
        "source_p31_report_status": p31_report.get("status"),
        "source_p31_report_sha256": sha256_json(p31_report) if p31_report else None,
        "source_p31_summary_sha256": sha256_json(p31_summary) if p31_summary else None,
        "source_p31_compact_dashboard_sha256": sha256_json(compact_dashboard) if compact_dashboard else None,
        "source_p31_launcher_card_sha256": sha256_json(launcher_card) if launcher_card else None,
        "source_p31_telegram_summary_sha256": sha256_json({"telegram_summary_text": telegram_summary_text}) if telegram_summary_text else None,
        "allowed_command_count": len(_ALLOWED_COMMANDS),
        "surface_count": len(_ALLOWED_SURFACES),
        "contract_command_count": len(contract["commands"]),
        "command_contract_generated_review_only": not blocked,
        "telegram_command_responses_generated_review_only": not blocked,
        "launcher_command_responses_generated_review_only": not blocked,
        "status_command_available": True,
        "matrix_command_available": True,
        "waiting_command_available": True,
        "no_go_command_available": True,
        "export_paths_command_available": True,
        "command_contract": contract,
        "command_responses": responses,
        "telegram_text_responses": telegram_text,
        "launcher_command_payload": launcher_payload,
        "artifact_paths": dict(paths),
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "endpoint_call_evidence_hits": endpoint_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "runtime_authority": False,
        "dashboard_command_is_runtime_authority": False,
        "telegram_command_executes_runtime": False,
        "launcher_command_executes_runtime": False,
        "telegram_command_allows_order_submission": False,
        "launcher_command_allows_order_submission": False,
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
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    report["p32_telegram_launcher_dashboard_command_contract_id"] = stable_id("p32_telegram_launcher_dashboard_command_contract", report, 24)
    report["p32_telegram_launcher_dashboard_command_contract_sha256"] = sha256_json(report)
    return report


def build_p32_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    valid_compact = {
        "status": P31_STATUS_GENERATED_REVIEW_ONLY,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "required_phase_count": 30,
        "present_phase_count": 30,
        "go_review_only_phase_count": 10,
        "waiting_phase_count": 20,
        "no_go_phase_count": 0,
        "waiting_phases": ["P7", "P8"],
        "no_go_phases": [],
        "next_operator_action": "Collect missing evidence.",
        "runtime_authority": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    valid_report = {
        "status": P31_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "operator_final_activation_decision": valid_compact["operator_final_activation_decision"],
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    valid_summary = {
        "status": P31_STATUS_GENERATED_REVIEW_ONLY,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    valid_launcher = {"runtime_enabled": False, "scheduler_enabled": False, "order_submission_allowed": False, "title": "Crypto AI System Activation Matrix"}
    valid_telegram = "Crypto_AI_System P31 Dashboard\nRuntime: DISABLED | Scheduler: DISABLED | Orders: DISABLED\nAuthority: REVIEW_ONLY"
    cases: dict[str, dict[str, Any]] = {
        "missing_p31_report": {"p31_report": {}, "p31_summary": valid_summary, "compact_dashboard": valid_compact, "launcher_card": valid_launcher, "telegram_summary_text": valid_telegram},
        "missing_compact_dashboard": {"p31_report": valid_report, "p31_summary": valid_summary, "compact_dashboard": {}, "launcher_card": valid_launcher, "telegram_summary_text": valid_telegram},
        "p31_blocked": {"p31_report": {**valid_report, "blocked": True}, "p31_summary": valid_summary, "compact_dashboard": valid_compact, "launcher_card": valid_launcher, "telegram_summary_text": valid_telegram},
        "unsafe_runtime_flag": {"p31_report": {**valid_report, "live_scaled_execution_enabled": True}, "p31_summary": valid_summary, "compact_dashboard": valid_compact, "launcher_card": valid_launcher, "telegram_summary_text": valid_telegram},
        "endpoint_called": {"p31_report": {**valid_report, "order_endpoint_called": True}, "p31_summary": valid_summary, "compact_dashboard": valid_compact, "launcher_card": valid_launcher, "telegram_summary_text": valid_telegram},
        "secret_pattern_found": {"p31_report": valid_report, "p31_summary": valid_summary, "compact_dashboard": valid_compact, "launcher_card": valid_launcher, "telegram_summary_text": "BINANCE_API_SECRET=leaked"},
        "telegram_command_executes_runtime": {"p31_report": valid_report, "p31_summary": valid_summary, "compact_dashboard": valid_compact, "launcher_card": valid_launcher, "telegram_summary_text": valid_telegram, "extra_payloads_for_scan": [("bad_contract", {"telegram_command_executes_runtime": True})]},
        "launcher_command_allows_order_submission": {"p31_report": valid_report, "p31_summary": valid_summary, "compact_dashboard": valid_compact, "launcher_card": valid_launcher, "telegram_summary_text": valid_telegram, "extra_payloads_for_scan": [("bad_launcher", {"launcher_command_allows_order_submission": True})]},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_telegram_launcher_dashboard_command_contract_report(root=root, **kwargs)
        blocked_or_waiting = report["blocked"] or report["waiting"] or report["status"] != STATUS_GENERATED_REVIEW_ONLY
        results[name] = {
            "blocked_or_waiting": blocked_or_waiting,
            "blocked": report["blocked"],
            "waiting": report["waiting"],
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "waiting_reasons": report["waiting_reasons"],
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
            "runtime_scheduler_enabled": report["runtime_scheduler_enabled"],
            "order_endpoint_called": report["order_endpoint_called"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    return {
        "p32_telegram_launcher_dashboard_command_contract_version": P32_TELEGRAM_LAUNCHER_DASHBOARD_COMMAND_CONTRACT_VERSION,
        "status": "P32_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_telegram_launcher_dashboard_command_contract(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p32_telegram_launcher_dashboard_command_contract")
    report = build_telegram_launcher_dashboard_command_contract_report(root=cfg.root)
    negative_results = build_p32_negative_fixture_results(root=cfg.root)

    atomic_write_json(latest / "p32_telegram_launcher_dashboard_command_contract_report.json", report)
    atomic_write_json(storage / "p32_telegram_launcher_dashboard_command_contract_report.json", report)
    atomic_write_json(latest / "p32_telegram_launcher_dashboard_command_contract.json", report["command_contract"])
    atomic_write_json(latest / "p32_telegram_dashboard_command_responses.json", report["command_responses"])
    atomic_write_json(latest / "p32_launcher_dashboard_command_responses.json", report["launcher_command_payload"])
    atomic_write_json(latest / "p32_telegram_launcher_dashboard_command_contract_negative_fixture_results.json", negative_results)
    _atomic_write_text(latest / "p32_telegram_dashboard_command_responses.txt", "\n\n---\n\n".join(report["telegram_text_responses"].values()))
    atomic_write_json(storage / "p32_telegram_launcher_dashboard_command_contract.json", report["command_contract"])
    atomic_write_json(storage / "p32_telegram_dashboard_command_responses.json", report["command_responses"])
    atomic_write_json(storage / "p32_launcher_dashboard_command_responses.json", report["launcher_command_payload"])

    summary = {
        "status": report["status"],
        "p32_telegram_launcher_dashboard_command_contract_sha256": report["p32_telegram_launcher_dashboard_command_contract_sha256"],
        "command_contract_generated_review_only": report["command_contract_generated_review_only"],
        "telegram_command_responses_generated_review_only": report["telegram_command_responses_generated_review_only"],
        "launcher_command_responses_generated_review_only": report["launcher_command_responses_generated_review_only"],
        "allowed_command_count": report["allowed_command_count"],
        "surface_count": report["surface_count"],
        "contract_command_count": report["contract_command_count"],
        "source_p31_report_present": report["source_p31_report_present"],
        "source_p31_compact_dashboard_present": report["source_p31_compact_dashboard_present"],
        "source_p31_launcher_card_present": report["source_p31_launcher_card_present"],
        "source_p31_telegram_summary_present": report["source_p31_telegram_summary_present"],
        "block_reasons": report["block_reasons"],
        "waiting_reasons": report["waiting_reasons"],
        "runtime_authority": False,
        "dashboard_command_is_runtime_authority": False,
        "telegram_command_executes_runtime": False,
        "launcher_command_executes_runtime": False,
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
        "secret_value_accessed": False,
    }
    summary["p32_telegram_launcher_dashboard_command_contract_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p32_telegram_launcher_dashboard_command_contract_summary.json", summary)
    registry_record = append_registry_record(
        registry_path(cfg, P32_TELEGRAM_LAUNCHER_DASHBOARD_COMMAND_CONTRACT_REGISTRY_NAME),
        report,
        registry_name=P32_TELEGRAM_LAUNCHER_DASHBOARD_COMMAND_CONTRACT_REGISTRY_NAME,
        id_field="p32_telegram_launcher_dashboard_command_contract_registry_id",
        hash_field="p32_telegram_launcher_dashboard_command_contract_registry_sha256",
        id_prefix="p32_telegram_launcher_dashboard_command_contract",
    )
    atomic_write_json(latest / "p32_telegram_launcher_dashboard_command_contract_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_telegram_launcher_dashboard_command_contract()
    print(result["status"])
    print(result["p32_telegram_launcher_dashboard_command_contract_sha256"])
