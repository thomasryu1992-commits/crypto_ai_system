from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.execution.telegram_launcher_dashboard_command_contract import (
    STATUS_BLOCKED_FAIL_CLOSED as P32_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY as P32_STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P32_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P33_TELEGRAM_LAUNCHER_COMMAND_ROUTER_FIXTURE_VALIDATOR_VERSION = "p33_telegram_launcher_command_router_fixture_validator_v1"
P33_TELEGRAM_LAUNCHER_COMMAND_ROUTER_FIXTURE_VALIDATOR_REGISTRY_NAME = "p33_telegram_launcher_command_router_fixture_validator_registry"

STATUS_GENERATED_REVIEW_ONLY = "P33_TELEGRAM_LAUNCHER_COMMAND_ROUTER_FIXTURE_VALIDATOR_GENERATED_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P33_TELEGRAM_LAUNCHER_COMMAND_ROUTER_FIXTURE_VALIDATOR_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P33_TELEGRAM_LAUNCHER_COMMAND_ROUTER_FIXTURE_VALIDATOR_BLOCKED_FAIL_CLOSED"

_ALLOWED_COMMANDS = ("status", "matrix", "waiting", "no_go", "export_paths")
_ALLOWED_SURFACES = ("telegram", "launcher")
_ALLOWED_ALIASES = {
    "status": ("/crypto_status", "crypto_status", "status"),
    "matrix": ("/crypto_matrix", "crypto_matrix", "matrix"),
    "waiting": ("/crypto_waiting", "crypto_waiting", "waiting"),
    "no_go": ("/crypto_no_go", "crypto_no_go", "no-go", "no_go"),
    "export_paths": ("/crypto_export_paths", "crypto_export_paths", "export paths", "export_paths"),
}
_UNSAFE_COMMANDS = (
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
    "place order",
    "cancel order",
    "activate scheduler",
)
_UNSAFE_PATTERNS = (
    "enable",
    "start",
    "submit",
    "order",
    "live",
    "activate",
    "trade",
    "scheduler",
    "place",
    "cancel",
    "runtime",
)
_EXECUTION_FIELDS_FOR_P33 = {
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
    "command_router_mutates_runtime",
    "telegram_router_mutated_by_this_module",
    "launcher_router_mutated_by_this_module",
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
                if key in _EXECUTION_FIELDS_FOR_P33 and _bool(value):
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


def _normalize_command(command: str) -> str:
    normalized = command.strip().lower().replace("_", "-")
    if normalized.startswith("/"):
        normalized = normalized[1:]
    if normalized.startswith("crypto-"):
        normalized = normalized[len("crypto-"):]
    if normalized.startswith("crypto_"):
        normalized = normalized[len("crypto_"):]
    return normalized.replace("-", "_")


def _command_to_contract(command: str) -> str | None:
    raw = command.strip().lower()
    for canonical, aliases in _ALLOWED_ALIASES.items():
        if raw in {alias.lower() for alias in aliases}:
            return canonical
        if _normalize_command(raw) == canonical:
            return canonical
    return None


def _is_unsafe_command(command: str) -> bool:
    canonical = _command_to_contract(command)
    if canonical in _ALLOWED_COMMANDS:
        return False
    normalized = _normalize_command(command)
    raw = command.strip().lower()
    return any(pattern in normalized or pattern in raw for pattern in _UNSAFE_PATTERNS)


def _route_command(surface: str, command: str, command_contract: Mapping[str, Any]) -> dict[str, Any]:
    canonical = _command_to_contract(command)
    contract_commands = {
        item.get("command"): item
        for item in command_contract.get("commands", [])
        if isinstance(item, Mapping) and item.get("surface") == surface
    }
    if surface not in _ALLOWED_SURFACES:
        return {
            "surface": surface,
            "input_command": command,
            "status": "ROUTE_BLOCKED_FAIL_CLOSED",
            "blocked": True,
            "denied_reason": "P33_SURFACE_NOT_ALLOWED",
            "read_only": True,
            "executes_runtime": False,
            "allows_order_submission": False,
            "calls_endpoint": False,
            "reads_secret_value": False,
        }
    if canonical in contract_commands:
        return {
            "surface": surface,
            "input_command": command,
            "canonical_command": canonical,
            "status": "ROUTE_ALLOWED_READ_ONLY",
            "blocked": False,
            "read_only": True,
            "response_source": "p32_command_contract",
            "contract_command_id": contract_commands[canonical].get("command_id"),
            "executes_runtime": False,
            "allows_order_submission": False,
            "enables_scheduler": False,
            "calls_endpoint": False,
            "reads_secret_value": False,
            "mutates_runtime": False,
            "runtime_authority": False,
        }
    return {
        "surface": surface,
        "input_command": command,
        "canonical_command": canonical,
        "status": "ROUTE_BLOCKED_FAIL_CLOSED",
        "blocked": True,
        "denied_reason": "P33_UNSAFE_OR_UNKNOWN_COMMAND_BLOCKED" if _is_unsafe_command(command) else "P33_COMMAND_NOT_IN_READ_ONLY_ALLOWLIST",
        "read_only": True,
        "executes_runtime": False,
        "allows_order_submission": False,
        "enables_scheduler": False,
        "calls_endpoint": False,
        "reads_secret_value": False,
        "mutates_runtime": False,
        "runtime_authority": False,
    }


def _build_router_contract(command_contract: Mapping[str, Any]) -> dict[str, Any]:
    allowed_routes = {
        surface: [_route_command(surface, alias, command_contract) for command in _ALLOWED_COMMANDS for alias in _ALLOWED_ALIASES[command]]
        for surface in _ALLOWED_SURFACES
    }
    denied_routes = {
        surface: [_route_command(surface, command, command_contract) for command in _UNSAFE_COMMANDS]
        for surface in _ALLOWED_SURFACES
    }
    return {
        "p33_telegram_launcher_command_router_fixture_validator_version": P33_TELEGRAM_LAUNCHER_COMMAND_ROUTER_FIXTURE_VALIDATOR_VERSION,
        "created_at_utc": utc_now_canonical(),
        "router_contract_status": "review_only_read_only_router_fixture",
        "allowed_commands": list(_ALLOWED_COMMANDS),
        "surfaces": list(_ALLOWED_SURFACES),
        "allowed_aliases": {k: list(v) for k, v in _ALLOWED_ALIASES.items()},
        "denied_unsafe_commands": list(_UNSAFE_COMMANDS),
        "denied_unsafe_patterns": list(_UNSAFE_PATTERNS),
        "allowed_routes": allowed_routes,
        "denied_routes": denied_routes,
        "read_only": True,
        "runtime_authority": False,
        "router_command_executes_runtime": False,
        "router_command_allows_order_submission": False,
        "router_command_mutates_runtime": False,
        "router_command_enables_scheduler": False,
        "router_command_calls_endpoint": False,
        "telegram_router_mutated_by_this_module": False,
        "launcher_router_mutated_by_this_module": False,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def _fixture_validation_results(router_contract: Mapping[str, Any]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for surface in _ALLOWED_SURFACES:
        allowed_routes = [route for routes in router_contract.get("allowed_routes", {}).get(surface, []) for route in [routes]]
        denied_routes = [route for routes in router_contract.get("denied_routes", {}).get(surface, []) for route in [routes]]
        results[surface] = {
            "allowed_route_count": len(allowed_routes),
            "denied_route_count": len(denied_routes),
            "all_allowed_routes_read_only": all(route.get("status") == "ROUTE_ALLOWED_READ_ONLY" and route.get("read_only") is True for route in allowed_routes),
            "all_denied_routes_blocked": all(route.get("blocked") is True and route.get("status") == "ROUTE_BLOCKED_FAIL_CLOSED" for route in denied_routes),
            "all_routes_do_not_execute_runtime": all(route.get("executes_runtime") is False for route in allowed_routes + denied_routes),
            "all_routes_do_not_allow_order_submission": all(route.get("allows_order_submission") is False for route in allowed_routes + denied_routes),
            "all_routes_do_not_call_endpoint": all(route.get("calls_endpoint") is False for route in allowed_routes + denied_routes),
            "all_routes_do_not_read_secret": all(route.get("reads_secret_value") is False for route in allowed_routes + denied_routes),
        }
    results["all_surfaces_valid_review_only"] = all(
        item["all_allowed_routes_read_only"]
        and item["all_denied_routes_blocked"]
        and item["all_routes_do_not_execute_runtime"]
        and item["all_routes_do_not_allow_order_submission"]
        and item["all_routes_do_not_call_endpoint"]
        and item["all_routes_do_not_read_secret"]
        for item in results.values()
        if isinstance(item, Mapping)
    )
    return results


def build_telegram_launcher_command_router_fixture_validator_report(
    *,
    root: Path | None = None,
    p32_report: Mapping[str, Any] | None = None,
    p32_summary: Mapping[str, Any] | None = None,
    p32_contract: Mapping[str, Any] | None = None,
    p32_telegram_responses: Mapping[str, Any] | None = None,
    p32_launcher_payload: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] | None = None,
) -> dict[str, Any]:
    root = root or Path.cwd()
    cfg = load_config(root)
    if p32_report is None:
        loaded = _read_latest_json(cfg, "p32_telegram_launcher_dashboard_command_contract_report.json")
        p32_report = dict(loaded) if isinstance(loaded, Mapping) else {}
    if p32_summary is None:
        loaded_summary = _read_latest_json(cfg, "p32_telegram_launcher_dashboard_command_contract_summary.json")
        p32_summary = dict(loaded_summary) if isinstance(loaded_summary, Mapping) else {}
    if p32_contract is None:
        loaded_contract = _read_latest_json(cfg, "p32_telegram_launcher_dashboard_command_contract.json")
        p32_contract = dict(loaded_contract) if isinstance(loaded_contract, Mapping) else {}
    if p32_telegram_responses is None:
        loaded_tel = _read_latest_json(cfg, "p32_telegram_dashboard_command_responses.json")
        p32_telegram_responses = dict(loaded_tel) if isinstance(loaded_tel, Mapping) else {}
    if p32_launcher_payload is None:
        loaded_launcher = _read_latest_json(cfg, "p32_launcher_dashboard_command_responses.json")
        p32_launcher_payload = dict(loaded_launcher) if isinstance(loaded_launcher, Mapping) else {}

    missing_report = not bool(p32_report)
    missing_summary = not bool(p32_summary)
    missing_contract = not bool(p32_contract)
    missing_telegram = not bool(p32_telegram_responses)
    missing_launcher = not bool(p32_launcher_payload)
    upstream_blocked = bool(p32_report.get("blocked", False)) or p32_report.get("status") == P32_STATUS_BLOCKED_FAIL_CLOSED
    upstream_waiting = bool(p32_report.get("waiting", False)) or p32_report.get("status") == P32_STATUS_WAITING_REVIEW_ONLY
    upstream_generated = p32_report.get("status") == P32_STATUS_GENERATED_REVIEW_ONLY

    router_contract = _build_router_contract(p32_contract or {"commands": []})
    validation_results = _fixture_validation_results(router_contract)
    telegram_router_fixture = {
        "surface": "telegram",
        "read_only": True,
        "allowed_commands": list(_ALLOWED_COMMANDS),
        "router_routes": router_contract["allowed_routes"]["telegram"],
        "unsafe_routes": router_contract["denied_routes"]["telegram"],
        "responses_source": "p32_telegram_dashboard_command_responses.json",
        "mutates_telegram_router": False,
        "executes_runtime": False,
        "allows_order_submission": False,
        "calls_endpoint": False,
        "reads_secret_value": False,
    }
    launcher_router_fixture = {
        "surface": "launcher",
        "read_only": True,
        "allowed_commands": list(_ALLOWED_COMMANDS),
        "router_routes": router_contract["allowed_routes"]["launcher"],
        "unsafe_routes": router_contract["denied_routes"]["launcher"],
        "responses_source": "p32_launcher_dashboard_command_responses.json",
        "mutates_launcher_router": False,
        "executes_runtime": False,
        "allows_order_submission": False,
        "calls_endpoint": False,
        "reads_secret_value": False,
    }

    scan_payloads: list[tuple[str, Any]] = [
        ("p32_report", p32_report),
        ("p32_summary", p32_summary),
        ("p32_contract", p32_contract),
        ("p32_telegram_responses", p32_telegram_responses),
        ("p32_launcher_payload", p32_launcher_payload),
        ("router_contract", router_contract),
        ("telegram_router_fixture", telegram_router_fixture),
        ("launcher_router_fixture", launcher_router_fixture),
        ("fixture_validation_results", validation_results),
    ]
    scan_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(scan_payloads)
    secret_hits = _scan_secret_value_patterns(scan_payloads)
    endpoint_fields = {"order_endpoint_called", "live_order_endpoint_called", "order_status_endpoint_called", "cancel_endpoint_called", "http_request_sent", "endpoint_call_allowed", "router_command_calls_endpoint"}
    endpoint_hits = [hit for hit in unsafe_hits if hit["field"] in endpoint_fields]
    truthy_disabled = truthy_execution_flags(default_execution_flag_state())

    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if missing_report:
        waiting_reasons.append("P33_SOURCE_P32_REPORT_MISSING")
    if missing_summary:
        waiting_reasons.append("P33_SOURCE_P32_SUMMARY_MISSING")
    if missing_contract:
        waiting_reasons.append("P33_SOURCE_P32_COMMAND_CONTRACT_MISSING")
    if missing_telegram:
        waiting_reasons.append("P33_SOURCE_P32_TELEGRAM_RESPONSES_MISSING")
    if missing_launcher:
        waiting_reasons.append("P33_SOURCE_P32_LAUNCHER_RESPONSES_MISSING")
    if upstream_blocked:
        block_reasons.append("P33_SOURCE_P32_BLOCKED_FAIL_CLOSED")
    if upstream_waiting and not upstream_blocked:
        waiting_reasons.append("P33_SOURCE_P32_WAITING_REVIEW_ONLY")
    if not upstream_generated and not upstream_blocked and not missing_report:
        waiting_reasons.append("P33_SOURCE_P32_NOT_GENERATED_REVIEW_ONLY")
    if (not validation_results.get("all_surfaces_valid_review_only", False)) and not (missing_report or missing_summary or missing_contract or missing_telegram or missing_launcher or upstream_waiting):
        block_reasons.append("P33_ROUTER_FIXTURE_VALIDATION_FAILED")
    if unsafe_hits:
        block_reasons.append("P33_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND")
    if endpoint_hits:
        block_reasons.append("P33_ENDPOINT_CALL_EVIDENCE_FOUND")
    if secret_hits:
        block_reasons.append("P33_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P33_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED
    elif waiting_reasons:
        status = STATUS_WAITING_REVIEW_ONLY
    else:
        status = STATUS_GENERATED_REVIEW_ONLY

    report: dict[str, Any] = {
        "p33_telegram_launcher_command_router_fixture_validator_version": P33_TELEGRAM_LAUNCHER_COMMAND_ROUTER_FIXTURE_VALIDATOR_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": not blocked,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "source_p32_report_present": not missing_report,
        "source_p32_summary_present": not missing_summary,
        "source_p32_command_contract_present": not missing_contract,
        "source_p32_telegram_responses_present": not missing_telegram,
        "source_p32_launcher_responses_present": not missing_launcher,
        "source_p32_report_status": p32_report.get("status"),
        "source_p32_report_sha256": sha256_json(p32_report) if p32_report else None,
        "source_p32_summary_sha256": sha256_json(p32_summary) if p32_summary else None,
        "source_p32_command_contract_sha256": sha256_json(p32_contract) if p32_contract else None,
        "source_p32_telegram_responses_sha256": sha256_json(p32_telegram_responses) if p32_telegram_responses else None,
        "source_p32_launcher_responses_sha256": sha256_json(p32_launcher_payload) if p32_launcher_payload else None,
        "allowed_command_count": len(_ALLOWED_COMMANDS),
        "surface_count": len(_ALLOWED_SURFACES),
        "unsafe_command_fixture_count": len(_UNSAFE_COMMANDS),
        "telegram_allowed_route_count": len(router_contract["allowed_routes"]["telegram"]),
        "launcher_allowed_route_count": len(router_contract["allowed_routes"]["launcher"]),
        "telegram_denied_route_count": len(router_contract["denied_routes"]["telegram"]),
        "launcher_denied_route_count": len(router_contract["denied_routes"]["launcher"]),
        "router_contract_generated_review_only": not blocked,
        "telegram_router_fixture_generated_review_only": not blocked,
        "launcher_router_fixture_generated_review_only": not blocked,
        "all_surfaces_valid_review_only": validation_results.get("all_surfaces_valid_review_only", False),
        "router_contract": router_contract,
        "telegram_router_fixture": telegram_router_fixture,
        "launcher_router_fixture": launcher_router_fixture,
        "fixture_validation_results": validation_results,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "endpoint_call_evidence_hits": endpoint_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "runtime_authority": False,
        "router_command_executes_runtime": False,
        "router_command_allows_order_submission": False,
        "router_command_mutates_runtime": False,
        "router_command_enables_scheduler": False,
        "router_command_calls_endpoint": False,
        "telegram_router_mutated_by_this_module": False,
        "launcher_router_mutated_by_this_module": False,
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
    report["p33_telegram_launcher_command_router_fixture_validator_id"] = stable_id("p33_telegram_launcher_command_router_fixture_validator", report, 24)
    report["p33_telegram_launcher_command_router_fixture_validator_sha256"] = sha256_json(report)
    return report


def build_p33_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    base_contract = {
        "read_only": True,
        "runtime_authority": False,
        "commands": [
            {"surface": surface, "command": command, "command_id": f"p32_{surface}_{command}"}
            for surface in _ALLOWED_SURFACES
            for command in _ALLOWED_COMMANDS
        ],
    }
    base_report = {
        "status": P32_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    base_summary = dict(base_report)
    base_tel = {"status": {"runtime": "DISABLED"}}
    base_launcher = {"runtime_enabled": False, "scheduler_enabled": False, "order_submission_allowed": False}
    cases: dict[str, dict[str, Any]] = {
        "missing_p32_report": {"p32_report": {}, "p32_summary": base_summary, "p32_contract": base_contract, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher},
        "p32_blocked": {"p32_report": {**base_report, "blocked": True}, "p32_summary": base_summary, "p32_contract": base_contract, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher},
        "missing_command_contract": {"p32_report": base_report, "p32_summary": base_summary, "p32_contract": {}, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher},
        "unsafe_runtime_flag": {"p32_report": {**base_report, "live_scaled_execution_enabled": True}, "p32_summary": base_summary, "p32_contract": base_contract, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher},
        "endpoint_called": {"p32_report": {**base_report, "order_endpoint_called": True}, "p32_summary": base_summary, "p32_contract": base_contract, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher},
        "secret_pattern_found": {"p32_report": base_report, "p32_summary": base_summary, "p32_contract": base_contract, "p32_telegram_responses": {"status": "BINANCE_API_SECRET=leaked"}, "p32_launcher_payload": base_launcher},
        "router_executes_runtime": {"p32_report": base_report, "p32_summary": base_summary, "p32_contract": base_contract, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher, "extra_payloads_for_scan": [("bad_router", {"router_command_executes_runtime": True})]},
        "launcher_allows_order_submission": {"p32_report": base_report, "p32_summary": base_summary, "p32_contract": base_contract, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher, "extra_payloads_for_scan": [("bad_launcher", {"router_command_allows_order_submission": True})]},
        "telegram_router_mutated": {"p32_report": base_report, "p32_summary": base_summary, "p32_contract": base_contract, "p32_telegram_responses": base_tel, "p32_launcher_payload": base_launcher, "extra_payloads_for_scan": [("bad_telegram", {"telegram_router_mutated_by_this_module": True})]},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_telegram_launcher_command_router_fixture_validator_report(root=root, **kwargs)
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
        "p33_telegram_launcher_command_router_fixture_validator_version": P33_TELEGRAM_LAUNCHER_COMMAND_ROUTER_FIXTURE_VALIDATOR_VERSION,
        "status": "P33_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_telegram_launcher_command_router_fixture_validator(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p33_telegram_launcher_command_router_fixture_validator")
    report = build_telegram_launcher_command_router_fixture_validator_report(root=cfg.root)
    negative_results = build_p33_negative_fixture_results(root=cfg.root)

    atomic_write_json(latest / "p33_telegram_launcher_command_router_fixture_validator_report.json", report)
    atomic_write_json(storage / "p33_telegram_launcher_command_router_fixture_validator_report.json", report)
    atomic_write_json(latest / "p33_telegram_launcher_command_router_contract.json", report["router_contract"])
    atomic_write_json(latest / "p33_telegram_command_router_fixture.json", report["telegram_router_fixture"])
    atomic_write_json(latest / "p33_launcher_command_router_fixture.json", report["launcher_router_fixture"])
    atomic_write_json(latest / "p33_command_router_fixture_validation_results.json", report["fixture_validation_results"])
    atomic_write_json(latest / "p33_telegram_launcher_command_router_fixture_validator_negative_fixture_results.json", negative_results)
    _atomic_write_text(
        latest / "p33_command_router_read_only_routes.txt",
        "Allowed read-only commands: " + ", ".join(_ALLOWED_COMMANDS) + "\nBlocked unsafe examples: " + ", ".join(_UNSAFE_COMMANDS),
    )
    atomic_write_json(storage / "p33_telegram_launcher_command_router_contract.json", report["router_contract"])
    atomic_write_json(storage / "p33_telegram_command_router_fixture.json", report["telegram_router_fixture"])
    atomic_write_json(storage / "p33_launcher_command_router_fixture.json", report["launcher_router_fixture"])

    summary = {
        "status": report["status"],
        "p33_telegram_launcher_command_router_fixture_validator_sha256": report["p33_telegram_launcher_command_router_fixture_validator_sha256"],
        "router_contract_generated_review_only": report["router_contract_generated_review_only"],
        "telegram_router_fixture_generated_review_only": report["telegram_router_fixture_generated_review_only"],
        "launcher_router_fixture_generated_review_only": report["launcher_router_fixture_generated_review_only"],
        "all_surfaces_valid_review_only": report["all_surfaces_valid_review_only"],
        "allowed_command_count": report["allowed_command_count"],
        "surface_count": report["surface_count"],
        "unsafe_command_fixture_count": report["unsafe_command_fixture_count"],
        "block_reasons": report["block_reasons"],
        "waiting_reasons": report["waiting_reasons"],
        "runtime_authority": False,
        "router_command_executes_runtime": False,
        "router_command_allows_order_submission": False,
        "router_command_mutates_runtime": False,
        "router_command_enables_scheduler": False,
        "router_command_calls_endpoint": False,
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
    summary["p33_telegram_launcher_command_router_fixture_validator_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p33_telegram_launcher_command_router_fixture_validator_summary.json", summary)
    registry_record = append_registry_record(
        registry_path(cfg, P33_TELEGRAM_LAUNCHER_COMMAND_ROUTER_FIXTURE_VALIDATOR_REGISTRY_NAME),
        report,
        registry_name=P33_TELEGRAM_LAUNCHER_COMMAND_ROUTER_FIXTURE_VALIDATOR_REGISTRY_NAME,
        id_field="p33_telegram_launcher_command_router_fixture_validator_registry_id",
        hash_field="p33_telegram_launcher_command_router_fixture_validator_registry_sha256",
        id_prefix="p33_telegram_launcher_command_router_fixture_validator",
    )
    atomic_write_json(latest / "p33_telegram_launcher_command_router_fixture_validator_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_telegram_launcher_command_router_fixture_validator()
    print(result["status"])
    print(result["p33_telegram_launcher_command_router_fixture_validator_sha256"])
