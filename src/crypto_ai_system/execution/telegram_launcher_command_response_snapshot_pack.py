from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.execution.telegram_launcher_command_router_fixture_validator import (
    STATUS_BLOCKED_FAIL_CLOSED as P33_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY as P33_STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P33_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P34_TELEGRAM_LAUNCHER_COMMAND_RESPONSE_SNAPSHOT_PACK_VERSION = "p34_telegram_launcher_command_response_snapshot_pack_v1"
P34_TELEGRAM_LAUNCHER_COMMAND_RESPONSE_SNAPSHOT_PACK_REGISTRY_NAME = "p34_telegram_launcher_command_response_snapshot_pack_registry"

STATUS_GENERATED_REVIEW_ONLY = "P34_TELEGRAM_LAUNCHER_COMMAND_RESPONSE_SNAPSHOT_PACK_GENERATED_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P34_TELEGRAM_LAUNCHER_COMMAND_RESPONSE_SNAPSHOT_PACK_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P34_TELEGRAM_LAUNCHER_COMMAND_RESPONSE_SNAPSHOT_PACK_BLOCKED_FAIL_CLOSED"

_ALLOWED_COMMANDS = ("status", "matrix", "waiting", "no_go", "export_paths")
_ALLOWED_SURFACES = ("telegram", "launcher")
_UNSAFE_COMMAND_SAMPLES = (
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
)
_EXECUTION_FIELDS_FOR_P34 = {
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
    "router_command_executes_runtime",
    "router_command_allows_order_submission",
    "router_command_mutates_runtime",
    "router_command_enables_scheduler",
    "router_command_calls_endpoint",
    "snapshot_command_executes_runtime",
    "snapshot_command_allows_order_submission",
    "snapshot_command_calls_endpoint",
    "snapshot_pack_mutates_runtime",
    "snapshot_pack_enables_scheduler",
    "telegram_snapshot_executes_runtime",
    "launcher_snapshot_executes_runtime",
    "telegram_snapshot_allows_order_submission",
    "launcher_snapshot_allows_order_submission",
    "telegram_router_mutated_by_this_module",
    "launcher_router_mutated_by_this_module",
    "command_mutates_runtime",
    "command_writes_runtime_settings",
    "scheduler_start_requested",
    "order_submission_requested",
    "endpoint_call_allowed",
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
                if key in _EXECUTION_FIELDS_FOR_P34 and _bool(value):
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


def _command_response_source(surface: str, command: str, telegram_responses: Mapping[str, Any], launcher_payload: Mapping[str, Any]) -> Any:
    if surface == "telegram":
        return telegram_responses.get(command, {"missing_response": True, "command": command})
    launcher_responses = launcher_payload.get("responses", {})
    if isinstance(launcher_responses, Mapping):
        return launcher_responses.get(command, {"missing_response": True, "command": command})
    return {"missing_response": True, "command": command}


def _render_text_response(command: str, payload: Any) -> str:
    if command == "status" and isinstance(payload, Mapping):
        decision = payload.get("decision") or payload.get("operator_final_activation_decision") or "UNKNOWN"
        runtime = payload.get("runtime") or payload.get("runtime_state") or "DISABLED"
        scheduler = payload.get("scheduler") or payload.get("scheduler_state") or "DISABLED"
        orders = payload.get("orders") or payload.get("order_state") or "DISABLED"
        authority = payload.get("authority") or ("REVIEW_ONLY" if payload.get("runtime_authority") is False else "UNKNOWN")
        return f"Crypto_AI_System Status\nDecision: {decision}\nRuntime: {runtime} | Scheduler: {scheduler} | Orders: {orders}\nAuthority: {authority}"
    if command == "matrix" and isinstance(payload, Mapping):
        return (
            "Crypto_AI_System Matrix\n"
            f"Decision: {payload.get('decision', 'UNKNOWN')}\n"
            f"Go/Waiting/No-Go: {payload.get('go_review_only', payload.get('go_review_only_phase_count', 'n/a'))} / "
            f"{payload.get('waiting', payload.get('waiting_phase_count', 'n/a'))} / {payload.get('no_go', payload.get('no_go_phase_count', 'n/a'))}\n"
            f"Dashboard: {payload.get('dashboard_path', payload.get('markdown_dashboard', 'n/a'))}"
        )
    if command == "waiting" and isinstance(payload, Mapping):
        phases = payload.get("waiting_phases") or payload.get("phases") or []
        if isinstance(phases, list):
            phase_text = ", ".join(str(item) for item in phases[:12]) or "None"
        else:
            phase_text = str(phases)
        return f"Crypto_AI_System Waiting Phases\n{phase_text}\nRuntime remains DISABLED."
    if command == "no_go" and isinstance(payload, Mapping):
        phases = payload.get("no_go_phases") or payload.get("phases") or []
        if isinstance(phases, list):
            phase_text = ", ".join(str(item) for item in phases[:12]) or "None"
        else:
            phase_text = str(phases)
        return f"Crypto_AI_System No-Go Phases\n{phase_text}\nRuntime remains DISABLED."
    if command == "export_paths" and isinstance(payload, Mapping):
        paths = payload.get("paths", {})
        if isinstance(paths, Mapping):
            path_lines = [f"- {key}: {value}" for key, value in sorted(paths.items())]
        else:
            path_lines = [str(paths)]
        return "Crypto_AI_System Export Paths\n" + "\n".join(path_lines[:12])
    return f"Crypto_AI_System {command}\n{payload}"


def _find_first_allowed_route(router_fixture: Mapping[str, Any], command: str) -> Mapping[str, Any]:
    for route in router_fixture.get("router_routes", []):
        if isinstance(route, Mapping) and route.get("canonical_command") == command and route.get("status") == "ROUTE_ALLOWED_READ_ONLY":
            return route
    return {}


def _find_first_denied_route(router_fixture: Mapping[str, Any], command: str) -> Mapping[str, Any]:
    for route in router_fixture.get("unsafe_routes", []):
        if isinstance(route, Mapping) and route.get("input_command") == command:
            return route
    return {}


def _build_surface_snapshots(surface: str, router_fixture: Mapping[str, Any], response_payloads: Mapping[str, Any], launcher_payload: Mapping[str, Any]) -> dict[str, Any]:
    command_snapshots: list[dict[str, Any]] = []
    for command in _ALLOWED_COMMANDS:
        route = _find_first_allowed_route(router_fixture, command)
        response_payload = _command_response_source(surface, command, response_payloads, launcher_payload)
        snapshot = {
            "surface": surface,
            "command": command,
            "input_command": route.get("input_command", f"/crypto_{command}" if surface == "telegram" else command),
            "route_status": route.get("status", "ROUTE_MISSING_FAIL_CLOSED"),
            "route_blocked": bool(route.get("blocked", True)),
            "read_only": True,
            "runtime_authority": False,
            "response_source": router_fixture.get("responses_source"),
            "response_payload": response_payload,
            "rendered_text": _render_text_response(command, response_payload),
            "executes_runtime": False,
            "allows_order_submission": False,
            "enables_scheduler": False,
            "calls_endpoint": False,
            "reads_secret_value": False,
            "mutates_runtime": False,
        }
        snapshot["response_payload_sha256"] = sha256_json(response_payload)
        snapshot["snapshot_sha256"] = sha256_json(snapshot)
        command_snapshots.append(snapshot)
    blocked_command_snapshots: list[dict[str, Any]] = []
    for command in _UNSAFE_COMMAND_SAMPLES:
        route = _find_first_denied_route(router_fixture, command)
        blocked = {
            "surface": surface,
            "input_command": command,
            "route_status": route.get("status", "ROUTE_BLOCKED_FAIL_CLOSED"),
            "blocked": True,
            "denied_reason": route.get("denied_reason", "P34_UNSAFE_COMMAND_BLOCKED_BY_SNAPSHOT_PACK"),
            "read_only": True,
            "rendered_text": f"Command blocked: {command}\nReason: unsafe command is not in the read-only dashboard allowlist.\nRuntime remains DISABLED.",
            "executes_runtime": False,
            "allows_order_submission": False,
            "enables_scheduler": False,
            "calls_endpoint": False,
            "reads_secret_value": False,
            "mutates_runtime": False,
            "runtime_authority": False,
        }
        blocked["snapshot_sha256"] = sha256_json(blocked)
        blocked_command_snapshots.append(blocked)
    return {
        "surface": surface,
        "snapshot_status": "P34_SURFACE_COMMAND_RESPONSE_SNAPSHOTS_GENERATED_REVIEW_ONLY",
        "allowed_command_count": len(command_snapshots),
        "blocked_command_sample_count": len(blocked_command_snapshots),
        "command_snapshots": command_snapshots,
        "blocked_command_snapshots": blocked_command_snapshots,
        "read_only": True,
        "runtime_authority": False,
        "snapshot_command_executes_runtime": False,
        "snapshot_command_allows_order_submission": False,
        "snapshot_command_calls_endpoint": False,
        "secret_value_accessed": False,
    }


def _build_markdown(snapshot_pack: Mapping[str, Any]) -> str:
    lines = [
        "# P34 Telegram / Launcher Command Response Snapshot Pack",
        "",
        f"Status: `{snapshot_pack.get('status')}`",
        f"Decision: `{snapshot_pack.get('operator_final_activation_decision')}`",
        "",
        "Runtime remains **DISABLED**. These snapshots are read-only previews only.",
        "",
    ]
    for surface in _ALLOWED_SURFACES:
        surface_pack = snapshot_pack.get(f"{surface}_snapshots", {})
        lines.append(f"## {surface.title()} allowed command snapshots")
        for item in surface_pack.get("command_snapshots", []):
            lines.append(f"### `{item.get('input_command')}` → `{item.get('command')}`")
            lines.append("```text")
            lines.append(str(item.get("rendered_text", "")))
            lines.append("```")
            lines.append("")
        lines.append(f"## {surface.title()} blocked unsafe command examples")
        for item in surface_pack.get("blocked_command_snapshots", [])[:5]:
            lines.append(f"- `{item.get('input_command')}`: {item.get('denied_reason')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_text(snapshot_pack: Mapping[str, Any]) -> str:
    lines = [
        "Crypto_AI_System P34 Command Response Snapshot Pack",
        f"Status: {snapshot_pack.get('status')}",
        f"Decision: {snapshot_pack.get('operator_final_activation_decision')}",
        "Runtime: DISABLED | Scheduler: DISABLED | Orders: DISABLED | Authority: REVIEW_ONLY",
        "",
    ]
    for surface in _ALLOWED_SURFACES:
        surface_pack = snapshot_pack.get(f"{surface}_snapshots", {})
        lines.append(f"[{surface.upper()}]")
        for item in surface_pack.get("command_snapshots", []):
            rendered = str(item.get("rendered_text", "")).replace("\n", " | ")
            lines.append(f"{item.get('input_command')}: {rendered}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_telegram_launcher_command_response_snapshot_pack_report(
    *,
    root: Path | None = None,
    p33_report: Mapping[str, Any] | None = None,
    p33_summary: Mapping[str, Any] | None = None,
    p33_router_contract: Mapping[str, Any] | None = None,
    p33_telegram_router: Mapping[str, Any] | None = None,
    p33_launcher_router: Mapping[str, Any] | None = None,
    p32_telegram_responses: Mapping[str, Any] | None = None,
    p32_launcher_payload: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] | None = None,
) -> dict[str, Any]:
    root = root or Path.cwd()
    cfg = load_config(root)
    if p33_report is None:
        loaded = _read_latest_json(cfg, "p33_telegram_launcher_command_router_fixture_validator_report.json")
        p33_report = dict(loaded) if isinstance(loaded, Mapping) else {}
    if p33_summary is None:
        loaded_summary = _read_latest_json(cfg, "p33_telegram_launcher_command_router_fixture_validator_summary.json")
        p33_summary = dict(loaded_summary) if isinstance(loaded_summary, Mapping) else {}
    if p33_router_contract is None:
        loaded_contract = _read_latest_json(cfg, "p33_telegram_launcher_command_router_contract.json")
        p33_router_contract = dict(loaded_contract) if isinstance(loaded_contract, Mapping) else {}
    if p33_telegram_router is None:
        loaded_tel_router = _read_latest_json(cfg, "p33_telegram_command_router_fixture.json")
        p33_telegram_router = dict(loaded_tel_router) if isinstance(loaded_tel_router, Mapping) else {}
    if p33_launcher_router is None:
        loaded_launcher_router = _read_latest_json(cfg, "p33_launcher_command_router_fixture.json")
        p33_launcher_router = dict(loaded_launcher_router) if isinstance(loaded_launcher_router, Mapping) else {}
    if p32_telegram_responses is None:
        loaded_tel = _read_latest_json(cfg, "p32_telegram_dashboard_command_responses.json")
        p32_telegram_responses = dict(loaded_tel) if isinstance(loaded_tel, Mapping) else {}
    if p32_launcher_payload is None:
        loaded_launcher = _read_latest_json(cfg, "p32_launcher_dashboard_command_responses.json")
        p32_launcher_payload = dict(loaded_launcher) if isinstance(loaded_launcher, Mapping) else {}

    missing_report = not bool(p33_report)
    missing_summary = not bool(p33_summary)
    missing_contract = not bool(p33_router_contract)
    missing_telegram_router = not bool(p33_telegram_router)
    missing_launcher_router = not bool(p33_launcher_router)
    missing_telegram_responses = not bool(p32_telegram_responses)
    missing_launcher_payload = not bool(p32_launcher_payload)
    upstream_blocked = bool(p33_report.get("blocked", False)) or p33_report.get("status") == P33_STATUS_BLOCKED_FAIL_CLOSED
    upstream_waiting = bool(p33_report.get("waiting", False)) or p33_report.get("status") == P33_STATUS_WAITING_REVIEW_ONLY
    upstream_generated = p33_report.get("status") == P33_STATUS_GENERATED_REVIEW_ONLY

    telegram_snapshots = _build_surface_snapshots("telegram", p33_telegram_router or {}, p32_telegram_responses or {}, p32_launcher_payload or {})
    launcher_snapshots = _build_surface_snapshots("launcher", p33_launcher_router or {}, p32_telegram_responses or {}, p32_launcher_payload or {})
    snapshot_pack = {
        "p34_telegram_launcher_command_response_snapshot_pack_version": P34_TELEGRAM_LAUNCHER_COMMAND_RESPONSE_SNAPSHOT_PACK_VERSION,
        "created_at_utc": utc_now_canonical(),
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "telegram_snapshots": telegram_snapshots,
        "launcher_snapshots": launcher_snapshots,
        "allowed_commands": list(_ALLOWED_COMMANDS),
        "read_only": True,
        "runtime_authority": False,
        "snapshot_command_executes_runtime": False,
        "snapshot_command_allows_order_submission": False,
        "snapshot_command_calls_endpoint": False,
        "snapshot_pack_mutates_runtime": False,
        "snapshot_pack_enables_scheduler": False,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    snapshot_pack["snapshot_pack_sha256"] = sha256_json(snapshot_pack)

    scan_payloads: list[tuple[str, Any]] = [
        ("p33_report", p33_report),
        ("p33_summary", p33_summary),
        ("p33_router_contract", p33_router_contract),
        ("p33_telegram_router", p33_telegram_router),
        ("p33_launcher_router", p33_launcher_router),
        ("p32_telegram_responses", p32_telegram_responses),
        ("p32_launcher_payload", p32_launcher_payload),
        ("snapshot_pack", snapshot_pack),
    ]
    scan_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(scan_payloads)
    secret_hits = _scan_secret_value_patterns(scan_payloads)
    endpoint_fields = {"order_endpoint_called", "live_order_endpoint_called", "order_status_endpoint_called", "cancel_endpoint_called", "http_request_sent", "endpoint_call_allowed", "router_command_calls_endpoint", "snapshot_command_calls_endpoint"}
    endpoint_hits = [hit for hit in unsafe_hits if hit["field"] in endpoint_fields]
    truthy_disabled = truthy_execution_flags(default_execution_flag_state())

    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if missing_report:
        waiting_reasons.append("P34_SOURCE_P33_REPORT_MISSING")
    if missing_summary:
        waiting_reasons.append("P34_SOURCE_P33_SUMMARY_MISSING")
    if missing_contract:
        waiting_reasons.append("P34_SOURCE_P33_ROUTER_CONTRACT_MISSING")
    if missing_telegram_router:
        waiting_reasons.append("P34_SOURCE_P33_TELEGRAM_ROUTER_MISSING")
    if missing_launcher_router:
        waiting_reasons.append("P34_SOURCE_P33_LAUNCHER_ROUTER_MISSING")
    if missing_telegram_responses:
        waiting_reasons.append("P34_SOURCE_P32_TELEGRAM_RESPONSES_MISSING")
    if missing_launcher_payload:
        waiting_reasons.append("P34_SOURCE_P32_LAUNCHER_RESPONSES_MISSING")
    if upstream_blocked:
        block_reasons.append("P34_SOURCE_P33_BLOCKED_FAIL_CLOSED")
    if upstream_waiting and not upstream_blocked:
        waiting_reasons.append("P34_SOURCE_P33_WAITING_REVIEW_ONLY")
    if not upstream_generated and not upstream_blocked and not missing_report:
        waiting_reasons.append("P34_SOURCE_P33_NOT_GENERATED_REVIEW_ONLY")
    all_snapshots_safe = all(
        item.get("route_status") == "ROUTE_ALLOWED_READ_ONLY"
        and item.get("executes_runtime") is False
        and item.get("allows_order_submission") is False
        and item.get("calls_endpoint") is False
        and item.get("reads_secret_value") is False
        for surface_pack in (telegram_snapshots, launcher_snapshots)
        for item in surface_pack.get("command_snapshots", [])
    ) and all(
        item.get("blocked") is True
        and item.get("executes_runtime") is False
        and item.get("allows_order_submission") is False
        and item.get("calls_endpoint") is False
        and item.get("reads_secret_value") is False
        for surface_pack in (telegram_snapshots, launcher_snapshots)
        for item in surface_pack.get("blocked_command_snapshots", [])
    )
    if not all_snapshots_safe and not (missing_report or missing_telegram_router or missing_launcher_router):
        block_reasons.append("P34_COMMAND_RESPONSE_SNAPSHOT_VALIDATION_FAILED")
    if unsafe_hits:
        block_reasons.append("P34_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND")
    if endpoint_hits:
        block_reasons.append("P34_ENDPOINT_CALL_EVIDENCE_FOUND")
    if secret_hits:
        block_reasons.append("P34_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P34_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED
    elif waiting_reasons:
        status = STATUS_WAITING_REVIEW_ONLY
    else:
        status = STATUS_GENERATED_REVIEW_ONLY
    snapshot_pack["status"] = status

    report: dict[str, Any] = {
        "p34_telegram_launcher_command_response_snapshot_pack_version": P34_TELEGRAM_LAUNCHER_COMMAND_RESPONSE_SNAPSHOT_PACK_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": not blocked,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "source_p33_report_present": not missing_report,
        "source_p33_summary_present": not missing_summary,
        "source_p33_router_contract_present": not missing_contract,
        "source_p33_telegram_router_present": not missing_telegram_router,
        "source_p33_launcher_router_present": not missing_launcher_router,
        "source_p32_telegram_responses_present": not missing_telegram_responses,
        "source_p32_launcher_responses_present": not missing_launcher_payload,
        "source_p33_report_status": p33_report.get("status"),
        "source_p33_report_sha256": sha256_json(p33_report) if p33_report else None,
        "source_p33_summary_sha256": sha256_json(p33_summary) if p33_summary else None,
        "source_p33_router_contract_sha256": sha256_json(p33_router_contract) if p33_router_contract else None,
        "source_p33_telegram_router_sha256": sha256_json(p33_telegram_router) if p33_telegram_router else None,
        "source_p33_launcher_router_sha256": sha256_json(p33_launcher_router) if p33_launcher_router else None,
        "source_p32_telegram_responses_sha256": sha256_json(p32_telegram_responses) if p32_telegram_responses else None,
        "source_p32_launcher_responses_sha256": sha256_json(p32_launcher_payload) if p32_launcher_payload else None,
        "allowed_command_count": len(_ALLOWED_COMMANDS),
        "surface_count": len(_ALLOWED_SURFACES),
        "telegram_snapshot_count": len(telegram_snapshots["command_snapshots"]),
        "launcher_snapshot_count": len(launcher_snapshots["command_snapshots"]),
        "telegram_blocked_snapshot_count": len(telegram_snapshots["blocked_command_snapshots"]),
        "launcher_blocked_snapshot_count": len(launcher_snapshots["blocked_command_snapshots"]),
        "all_snapshots_safe_review_only": all_snapshots_safe,
        "snapshot_pack": snapshot_pack,
        "telegram_snapshots": telegram_snapshots,
        "launcher_snapshots": launcher_snapshots,
        "markdown_snapshot_preview": _build_markdown({**snapshot_pack, "status": status}),
        "text_snapshot_preview": _build_text({**snapshot_pack, "status": status}),
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "endpoint_call_evidence_hits": endpoint_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "runtime_authority": False,
        "snapshot_command_executes_runtime": False,
        "snapshot_command_allows_order_submission": False,
        "snapshot_command_calls_endpoint": False,
        "snapshot_pack_mutates_runtime": False,
        "snapshot_pack_enables_scheduler": False,
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
    report["p34_telegram_launcher_command_response_snapshot_pack_id"] = stable_id("p34_telegram_launcher_command_response_snapshot_pack", report, 24)
    report["p34_telegram_launcher_command_response_snapshot_pack_sha256"] = sha256_json(report)
    return report


def build_p34_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    base_p33_report = {"status": P33_STATUS_GENERATED_REVIEW_ONLY, "blocked": False, "waiting": False, "live_scaled_execution_enabled": False, "runtime_scheduler_enabled": False, "order_endpoint_called": False, "secret_value_accessed": False}
    base_p33_summary = dict(base_p33_report)
    base_contract = {"read_only": True, "runtime_authority": False, "allowed_commands": list(_ALLOWED_COMMANDS)}
    route = {"status": "ROUTE_ALLOWED_READ_ONLY", "blocked": False, "read_only": True, "executes_runtime": False, "allows_order_submission": False, "calls_endpoint": False, "reads_secret_value": False, "canonical_command": "status", "input_command": "/crypto_status"}
    base_router = {"read_only": True, "responses_source": "p32_telegram_dashboard_command_responses.json", "router_routes": [{**route, "canonical_command": command, "input_command": f"/crypto_{command}"} for command in _ALLOWED_COMMANDS], "unsafe_routes": []}
    base_tel = {command: {"decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE", "runtime_authority": False} for command in _ALLOWED_COMMANDS}
    base_launcher = {"responses": base_tel, "runtime_enabled": False, "scheduler_enabled": False, "order_submission_allowed": False}
    cases: dict[str, dict[str, Any]] = {
        "missing_p33_report": {"p33_report": {}, "p33_summary": base_p33_summary, "p33_router_contract": base_contract, "p33_telegram_router": base_router, "p33_launcher_router": base_router, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher},
        "p33_blocked": {"p33_report": {**base_p33_report, "blocked": True}, "p33_summary": base_p33_summary, "p33_router_contract": base_contract, "p33_telegram_router": base_router, "p33_launcher_router": base_router, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher},
        "missing_router_contract": {"p33_report": base_p33_report, "p33_summary": base_p33_summary, "p33_router_contract": {}, "p33_telegram_router": base_router, "p33_launcher_router": base_router, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher},
        "missing_response_payloads": {"p33_report": base_p33_report, "p33_summary": base_p33_summary, "p33_router_contract": base_contract, "p33_telegram_router": base_router, "p33_launcher_router": base_router, "p32_telegram_responses": {}, "p32_launcher_payload": {}},
        "unsafe_runtime_flag": {"p33_report": {**base_p33_report, "live_scaled_execution_enabled": True}, "p33_summary": base_p33_summary, "p33_router_contract": base_contract, "p33_telegram_router": base_router, "p33_launcher_router": base_router, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher},
        "endpoint_called": {"p33_report": {**base_p33_report, "order_endpoint_called": True}, "p33_summary": base_p33_summary, "p33_router_contract": base_contract, "p33_telegram_router": base_router, "p33_launcher_router": base_router, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher},
        "secret_pattern_found": {"p33_report": base_p33_report, "p33_summary": base_p33_summary, "p33_router_contract": base_contract, "p33_telegram_router": base_router, "p33_launcher_router": base_router, "p32_telegram_responses": {"status": "BINANCE_API_SECRET=leaked"}, "p32_launcher_payload": base_launcher},
        "snapshot_executes_runtime": {"p33_report": base_p33_report, "p33_summary": base_p33_summary, "p33_router_contract": base_contract, "p33_telegram_router": base_router, "p33_launcher_router": base_router, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher, "extra_payloads_for_scan": [("bad_snapshot", {"snapshot_command_executes_runtime": True})]},
        "snapshot_allows_order_submission": {"p33_report": base_p33_report, "p33_summary": base_p33_summary, "p33_router_contract": base_contract, "p33_telegram_router": base_router, "p33_launcher_router": base_router, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher, "extra_payloads_for_scan": [("bad_snapshot", {"snapshot_command_allows_order_submission": True})]},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_telegram_launcher_command_response_snapshot_pack_report(root=root, **kwargs)
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
        "p34_telegram_launcher_command_response_snapshot_pack_version": P34_TELEGRAM_LAUNCHER_COMMAND_RESPONSE_SNAPSHOT_PACK_VERSION,
        "status": "P34_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_telegram_launcher_command_response_snapshot_pack(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p34_telegram_launcher_command_response_snapshot_pack")
    report = build_telegram_launcher_command_response_snapshot_pack_report(root=cfg.root)
    negative_results = build_p34_negative_fixture_results(root=cfg.root)

    atomic_write_json(latest / "p34_telegram_launcher_command_response_snapshot_pack_report.json", report)
    atomic_write_json(storage / "p34_telegram_launcher_command_response_snapshot_pack_report.json", report)
    atomic_write_json(latest / "p34_telegram_command_response_snapshots.json", report["telegram_snapshots"])
    atomic_write_json(latest / "p34_launcher_command_response_snapshots.json", report["launcher_snapshots"])
    atomic_write_json(latest / "p34_command_response_snapshot_pack.json", report["snapshot_pack"])
    atomic_write_json(latest / "p34_telegram_launcher_command_response_snapshot_pack_negative_fixture_results.json", negative_results)
    _atomic_write_text(latest / "p34_command_response_snapshot_pack.md", report["markdown_snapshot_preview"])
    _atomic_write_text(latest / "p34_command_response_snapshot_pack.txt", report["text_snapshot_preview"])
    atomic_write_json(storage / "p34_telegram_command_response_snapshots.json", report["telegram_snapshots"])
    atomic_write_json(storage / "p34_launcher_command_response_snapshots.json", report["launcher_snapshots"])
    _atomic_write_text(storage / "p34_command_response_snapshot_pack.md", report["markdown_snapshot_preview"])

    summary = {
        "status": report["status"],
        "p34_telegram_launcher_command_response_snapshot_pack_sha256": report["p34_telegram_launcher_command_response_snapshot_pack_sha256"],
        "all_snapshots_safe_review_only": report["all_snapshots_safe_review_only"],
        "telegram_snapshot_count": report["telegram_snapshot_count"],
        "launcher_snapshot_count": report["launcher_snapshot_count"],
        "telegram_blocked_snapshot_count": report["telegram_blocked_snapshot_count"],
        "launcher_blocked_snapshot_count": report["launcher_blocked_snapshot_count"],
        "block_reasons": report["block_reasons"],
        "waiting_reasons": report["waiting_reasons"],
        "runtime_authority": False,
        "snapshot_command_executes_runtime": False,
        "snapshot_command_allows_order_submission": False,
        "snapshot_command_calls_endpoint": False,
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
    summary["p34_telegram_launcher_command_response_snapshot_pack_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p34_telegram_launcher_command_response_snapshot_pack_summary.json", summary)
    registry_record = append_registry_record(
        registry_path(cfg, P34_TELEGRAM_LAUNCHER_COMMAND_RESPONSE_SNAPSHOT_PACK_REGISTRY_NAME),
        report,
        registry_name=P34_TELEGRAM_LAUNCHER_COMMAND_RESPONSE_SNAPSHOT_PACK_REGISTRY_NAME,
        id_field="p34_telegram_launcher_command_response_snapshot_pack_registry_id",
        hash_field="p34_telegram_launcher_command_response_snapshot_pack_registry_sha256",
        id_prefix="p34_telegram_launcher_command_response_snapshot_pack",
    )
    atomic_write_json(latest / "p34_telegram_launcher_command_response_snapshot_pack_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_telegram_launcher_command_response_snapshot_pack()
    print(result["status"])
    print(result["p34_telegram_launcher_command_response_snapshot_pack_sha256"])
