from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.final_activation_readiness_go_no_go_matrix import (
    OPERATOR_DECISION_GO_REVIEW_ONLY,
    OPERATOR_DECISION_NO_GO,
    OPERATOR_DECISION_WAITING,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P31_OPERATOR_DECISION_MATRIX_DASHBOARD_EXPORT_VERSION = "p31_operator_decision_matrix_dashboard_export_v1"
P31_OPERATOR_DECISION_MATRIX_DASHBOARD_EXPORT_REGISTRY_NAME = "p31_operator_decision_matrix_dashboard_export_registry"

STATUS_GENERATED_REVIEW_ONLY = "P31_OPERATOR_DECISION_MATRIX_DASHBOARD_EXPORT_GENERATED_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P31_OPERATOR_DECISION_MATRIX_DASHBOARD_EXPORT_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P31_OPERATOR_DECISION_MATRIX_DASHBOARD_EXPORT_BLOCKED_FAIL_CLOSED"

_EXECUTION_FIELDS_FOR_P31 = {
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
    "dashboard_is_runtime_authority",
    "operator_dashboard_executes_runtime",
    "operator_dashboard_allows_order_submission",
    "telegram_dashboard_allows_runtime",
    "launcher_dashboard_allows_runtime",
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

_DASHBOARD_HEADERS = (
    "phase",
    "label",
    "decision",
    "summary_status",
    "summary_present",
    "decision_reasons",
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
                if key in _EXECUTION_FIELDS_FOR_P31 and _bool(value):
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


def _normalise_matrix_rows(matrix: Any) -> list[dict[str, Any]]:
    if not isinstance(matrix, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in matrix:
        if not isinstance(item, Mapping):
            continue
        rows.append({
            "phase": str(item.get("phase", "")),
            "label": str(item.get("label", "")),
            "decision": str(item.get("decision", "")),
            "summary_status": item.get("summary_status"),
            "summary_present": bool(item.get("summary_present", False)),
            "decision_reasons": list(item.get("decision_reasons") or []),
            "summary_sha256": item.get("summary_sha256"),
            "runtime_authority": False,
            "order_submission_allowed_by_phase": False,
        })
    return rows


def _matrix_to_csv(matrix_rows: Sequence[Mapping[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(_DASHBOARD_HEADERS))
    writer.writeheader()
    for row in matrix_rows:
        writer.writerow({
            "phase": row.get("phase", ""),
            "label": row.get("label", ""),
            "decision": row.get("decision", ""),
            "summary_status": row.get("summary_status") or "",
            "summary_present": str(bool(row.get("summary_present", False))).lower(),
            "decision_reasons": ";".join(str(item) for item in row.get("decision_reasons", []) or []),
        })
    return buffer.getvalue()


def _matrix_to_markdown(*, compact_dashboard: Mapping[str, Any], matrix_rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# Crypto AI System Operator Decision Matrix Dashboard",
        "",
        "## Final decision",
        "",
        f"- Status: `{compact_dashboard['status']}`",
        f"- Operator decision: `{compact_dashboard['operator_final_activation_decision']}`",
        f"- Required phases: `{compact_dashboard['required_phase_count']}`",
        f"- Present phases: `{compact_dashboard['present_phase_count']}`",
        f"- Go-review-only phases: `{compact_dashboard['go_review_only_phase_count']}`",
        f"- Waiting phases: `{compact_dashboard['waiting_phase_count']}`",
        f"- No-Go phases: `{compact_dashboard['no_go_phase_count']}`",
        "- Runtime authority: `false`",
        "- Live scaled execution enabled: `false`",
        "- Runtime scheduler enabled: `false`",
        "- Order submission allowed: `false`",
        "",
        "## Next operator action",
        "",
        compact_dashboard["next_operator_action"],
        "",
        "## Waiting phases",
        "",
        ", ".join(compact_dashboard.get("waiting_phases") or ["none"]),
        "",
        "## No-Go phases",
        "",
        ", ".join(compact_dashboard.get("no_go_phases") or ["none"]),
        "",
        "## Phase matrix",
        "",
        "| Phase | Label | Decision | Summary status | Present | Reasons |",
        "|---|---|---|---|---|---|",
    ]
    for row in matrix_rows:
        reasons = ", ".join(str(item) for item in row.get("decision_reasons", []) or []) or "-"
        lines.append(
            "| {phase} | {label} | {decision} | {status} | {present} | {reasons} |".format(
                phase=str(row.get("phase", "")).replace("|", "/"),
                label=str(row.get("label", "")).replace("|", "/"),
                decision=str(row.get("decision", "")).replace("|", "/"),
                status=str(row.get("summary_status") or "").replace("|", "/"),
                present=str(bool(row.get("summary_present", False))).lower(),
                reasons=reasons.replace("|", "/"),
            )
        )
    lines.extend([
        "",
        "## Safety note",
        "",
        "This dashboard is review-only. It does not enable runtime, scheduler, endpoint calls, secret access, or order submission.",
        "",
    ])
    return "\n".join(lines)


def _telegram_summary(compact_dashboard: Mapping[str, Any]) -> str:
    waiting_preview = ", ".join(compact_dashboard.get("waiting_phases", [])[:8])
    if len(compact_dashboard.get("waiting_phases", [])) > 8:
        waiting_preview += ", ..."
    if not waiting_preview:
        waiting_preview = "none"
    return (
        "Crypto_AI_System P31 Dashboard\n"
        f"Decision: {compact_dashboard['operator_final_activation_decision']}\n"
        f"Go/Waiting/No-Go: {compact_dashboard['go_review_only_phase_count']} / {compact_dashboard['waiting_phase_count']} / {compact_dashboard['no_go_phase_count']}\n"
        f"Waiting: {waiting_preview}\n"
        "Runtime: DISABLED | Scheduler: DISABLED | Orders: DISABLED\n"
        "Authority: REVIEW_ONLY"
    )


def _next_operator_action(decision: str, waiting_count: int, no_go_count: int) -> str:
    if no_go_count:
        return "Resolve NO-GO blockers before creating any runtime activation request."
    if waiting_count:
        return "Collect the missing external/operator evidence listed in the waiting phases, then rerun P30 and P31."
    if decision == OPERATOR_DECISION_GO_REVIEW_ONLY:
        return "All phases are Go-review-only; proceed only to a separate operator runtime activation review, not execution."
    return "Keep the package in review-only mode and rerun upstream gates."


def _build_compact_dashboard(p30_report: Mapping[str, Any], matrix_rows: Sequence[Mapping[str, Any]], status: str) -> dict[str, Any]:
    waiting_phases = list(p30_report.get("waiting_phases") or [])
    no_go_phases = list(p30_report.get("no_go_phases") or [])
    decision = str(p30_report.get("operator_final_activation_decision") or OPERATOR_DECISION_WAITING)
    return {
        "p31_operator_decision_matrix_dashboard_export_version": P31_OPERATOR_DECISION_MATRIX_DASHBOARD_EXPORT_VERSION,
        "status": status,
        "created_at_utc": utc_now_canonical(),
        "operator_final_activation_decision": decision,
        "required_phase_count": int(p30_report.get("required_phase_count") or len(matrix_rows)),
        "present_phase_count": int(p30_report.get("present_phase_count") or 0),
        "go_review_only_phase_count": int(p30_report.get("go_review_only_phase_count") or 0),
        "waiting_phase_count": int(p30_report.get("waiting_phase_count") or len(waiting_phases)),
        "no_go_phase_count": int(p30_report.get("no_go_phase_count") or len(no_go_phases)),
        "waiting_phases": waiting_phases,
        "no_go_phases": no_go_phases,
        "go_review_only_phases": list(p30_report.get("go_review_only_phases") or []),
        "next_operator_action": _next_operator_action(decision, len(waiting_phases), len(no_go_phases)),
        "runtime_authority": False,
        "dashboard_is_runtime_authority": False,
        "operator_dashboard_executes_runtime": False,
        "telegram_dashboard_allows_runtime": False,
        "launcher_dashboard_allows_runtime": False,
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
    }


def build_operator_decision_matrix_dashboard_export_report(
    *,
    root: Path | None = None,
    p30_report: Mapping[str, Any] | None = None,
    p30_summary: Mapping[str, Any] | None = None,
    p30_matrix: Sequence[Mapping[str, Any]] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] | None = None,
) -> dict[str, Any]:
    root = root or Path.cwd()
    cfg = load_config(root)
    if p30_report is None:
        loaded_report = _read_latest_json(cfg, "p30_final_activation_readiness_go_no_go_matrix_report.json")
        p30_report = dict(loaded_report) if isinstance(loaded_report, Mapping) else {}
    if p30_summary is None:
        loaded_summary = _read_latest_json(cfg, "p30_final_activation_readiness_go_no_go_matrix_summary.json")
        p30_summary = dict(loaded_summary) if isinstance(loaded_summary, Mapping) else {}
    if p30_matrix is None:
        loaded_matrix = _read_latest_json(cfg, "p30_final_activation_readiness_go_no_go_matrix.json")
        p30_matrix = loaded_matrix if isinstance(loaded_matrix, list) else p30_report.get("go_no_go_matrix", [])

    matrix_rows = _normalise_matrix_rows(p30_matrix)
    missing_p30_report = not bool(p30_report)
    missing_p30_matrix = not bool(matrix_rows)
    upstream_blocked = bool(p30_report.get("blocked", False))

    status = STATUS_WAITING_REVIEW_ONLY if missing_p30_report or missing_p30_matrix else STATUS_GENERATED_REVIEW_ONLY
    compact_dashboard = _build_compact_dashboard(p30_report, matrix_rows, status)
    markdown = _matrix_to_markdown(compact_dashboard=compact_dashboard, matrix_rows=matrix_rows)
    csv_content = _matrix_to_csv(matrix_rows)
    telegram = _telegram_summary(compact_dashboard)
    launcher_card = {
        "card_type": "crypto_ai_system_operator_dashboard",
        "title": "Crypto AI System Activation Matrix",
        "decision": compact_dashboard["operator_final_activation_decision"],
        "status": status,
        "counts": {
            "go_review_only": compact_dashboard["go_review_only_phase_count"],
            "waiting": compact_dashboard["waiting_phase_count"],
            "no_go": compact_dashboard["no_go_phase_count"],
        },
        "runtime_enabled": False,
        "scheduler_enabled": False,
        "order_submission_allowed": False,
        "next_action": compact_dashboard["next_operator_action"],
    }

    scan_payloads: list[tuple[str, Any]] = [
        ("p30_report", p30_report),
        ("p30_summary", p30_summary),
        ("p30_matrix", list(matrix_rows)),
        ("compact_dashboard", compact_dashboard),
        ("launcher_card", launcher_card),
    ]
    scan_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(scan_payloads)
    secret_hits = _scan_secret_value_patterns(scan_payloads)
    endpoint_hits = [hit for hit in unsafe_hits if hit["field"] in {"order_endpoint_called", "live_order_endpoint_called", "order_status_endpoint_called", "cancel_endpoint_called", "http_request_sent"}]
    truthy_disabled = truthy_execution_flags(default_execution_flag_state())

    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if missing_p30_report:
        waiting_reasons.append("P31_SOURCE_P30_REPORT_MISSING")
    if missing_p30_matrix:
        waiting_reasons.append("P31_SOURCE_P30_MATRIX_MISSING")
    if upstream_blocked:
        block_reasons.append("P31_SOURCE_P30_BLOCKED_FAIL_CLOSED")
    if unsafe_hits:
        block_reasons.append("P31_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND")
    if endpoint_hits:
        block_reasons.append("P31_ENDPOINT_CALL_EVIDENCE_FOUND")
    if secret_hits:
        block_reasons.append("P31_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P31_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED
        compact_dashboard["status"] = status
    elif waiting_reasons:
        status = STATUS_WAITING_REVIEW_ONLY
        compact_dashboard["status"] = status

    report: dict[str, Any] = {
        "p31_operator_decision_matrix_dashboard_export_version": P31_OPERATOR_DECISION_MATRIX_DASHBOARD_EXPORT_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": not blocked,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "source_p30_report_present": not missing_p30_report,
        "source_p30_matrix_present": not missing_p30_matrix,
        "source_p30_report_sha256": sha256_json(p30_report) if p30_report else None,
        "source_p30_summary_sha256": sha256_json(p30_summary) if p30_summary else None,
        "source_p30_matrix_sha256": sha256_json(list(matrix_rows)) if matrix_rows else None,
        "operator_final_activation_decision": compact_dashboard["operator_final_activation_decision"],
        "dashboard_markdown_created_review_only": bool(matrix_rows) and not blocked,
        "dashboard_csv_created_review_only": bool(matrix_rows) and not blocked,
        "telegram_compact_summary_created_review_only": not blocked,
        "launcher_compact_dashboard_created_review_only": not blocked,
        "compact_dashboard": compact_dashboard,
        "launcher_dashboard_card": launcher_card,
        "telegram_summary_text": telegram,
        "markdown_preview_sha256": sha256_json({"markdown": markdown}),
        "csv_preview_sha256": sha256_json({"csv": csv_content}),
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "endpoint_call_evidence_hits": endpoint_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "runtime_authority": False,
        "dashboard_is_runtime_authority": False,
        "operator_dashboard_executes_runtime": False,
        "operator_dashboard_allows_order_submission": False,
        "telegram_dashboard_allows_runtime": False,
        "launcher_dashboard_allows_runtime": False,
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
    report["p31_operator_decision_matrix_dashboard_export_id"] = stable_id("p31_operator_decision_matrix_dashboard_export", report, 24)
    report["p31_operator_decision_matrix_dashboard_export_sha256"] = sha256_json(report)
    return report


def build_p31_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    valid_matrix = [
        {
            "phase": f"P{idx}",
            "label": f"Phase {idx}",
            "decision": "GO_REVIEW_ONLY",
            "summary_status": f"P{idx}_VALID_REVIEW_ONLY",
            "summary_present": True,
            "decision_reasons": [],
        }
        for idx in range(30)
    ]
    valid_report = {
        "status": "P30_FINAL_ACTIVATION_READINESS_GO_NO_GO_MATRIX_GENERATED_REVIEW_ONLY",
        "blocked": False,
        "operator_final_activation_decision": OPERATOR_DECISION_GO_REVIEW_ONLY,
        "required_phase_count": 30,
        "present_phase_count": 30,
        "go_review_only_phase_count": 30,
        "waiting_phase_count": 0,
        "no_go_phase_count": 0,
        "waiting_phases": [],
        "no_go_phases": [],
        "go_review_only_phases": [f"P{idx}" for idx in range(30)],
        "go_no_go_matrix": valid_matrix,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    cases: dict[str, dict[str, Any]] = {
        "missing_p30_report": {"p30_report": {}, "p30_matrix": valid_matrix},
        "missing_p30_matrix": {"p30_report": valid_report, "p30_matrix": []},
        "p30_blocked": {"p30_report": {**valid_report, "blocked": True}, "p30_matrix": valid_matrix},
        "unsafe_runtime_flag": {"p30_report": {**valid_report, "live_scaled_execution_enabled": True}, "p30_matrix": valid_matrix},
        "endpoint_call_evidence_found": {"p30_report": {**valid_report, "order_endpoint_called": True}, "p30_matrix": valid_matrix},
        "secret_pattern_found": {"p30_report": {**valid_report, "operator_note": "BINANCE_API_SECRET=leaked"}, "p30_matrix": valid_matrix},
        "launcher_dashboard_runtime_enabled": {"p30_report": valid_report, "p30_matrix": valid_matrix, "extra_payloads_for_scan": [("launcher_card", {"launcher_dashboard_allows_runtime": True})]},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_operator_decision_matrix_dashboard_export_report(root=root, **kwargs)
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
        "p31_operator_decision_matrix_dashboard_export_version": P31_OPERATOR_DECISION_MATRIX_DASHBOARD_EXPORT_VERSION,
        "status": "P31_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_operator_decision_matrix_dashboard_export(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p31_operator_decision_matrix_dashboard_export")
    report = build_operator_decision_matrix_dashboard_export_report(root=cfg.root)
    negative_results = build_p31_negative_fixture_results(root=cfg.root)

    compact = report["compact_dashboard"]
    matrix_payload = _read_latest_json(cfg, "p30_final_activation_readiness_go_no_go_matrix.json")
    matrix_rows = _normalise_matrix_rows(matrix_payload)
    markdown = _matrix_to_markdown(compact_dashboard=compact, matrix_rows=matrix_rows)
    csv_content = _matrix_to_csv(matrix_rows)
    telegram = report["telegram_summary_text"]
    launcher_card = report["launcher_dashboard_card"]

    atomic_write_json(latest / "p31_operator_decision_matrix_dashboard_export_report.json", report)
    atomic_write_json(storage / "p31_operator_decision_matrix_dashboard_export_report.json", report)
    atomic_write_json(latest / "p31_operator_decision_matrix_compact_dashboard.json", compact)
    atomic_write_json(latest / "p31_operator_decision_matrix_launcher_card.json", launcher_card)
    atomic_write_json(latest / "p31_operator_decision_matrix_dashboard_export_negative_fixture_results.json", negative_results)
    _atomic_write_text(latest / "p31_operator_decision_matrix_dashboard.md", markdown)
    _atomic_write_text(latest / "p31_operator_decision_matrix_dashboard.csv", csv_content)
    _atomic_write_text(latest / "p31_operator_decision_matrix_telegram_summary.txt", telegram)
    _atomic_write_text(storage / "p31_operator_decision_matrix_dashboard.md", markdown)
    _atomic_write_text(storage / "p31_operator_decision_matrix_dashboard.csv", csv_content)
    _atomic_write_text(storage / "p31_operator_decision_matrix_telegram_summary.txt", telegram)

    summary = {
        "status": report["status"],
        "p31_operator_decision_matrix_dashboard_export_sha256": report["p31_operator_decision_matrix_dashboard_export_sha256"],
        "operator_final_activation_decision": report["operator_final_activation_decision"],
        "dashboard_markdown_created_review_only": report["dashboard_markdown_created_review_only"],
        "dashboard_csv_created_review_only": report["dashboard_csv_created_review_only"],
        "telegram_compact_summary_created_review_only": report["telegram_compact_summary_created_review_only"],
        "launcher_compact_dashboard_created_review_only": report["launcher_compact_dashboard_created_review_only"],
        "source_p30_report_present": report["source_p30_report_present"],
        "source_p30_matrix_present": report["source_p30_matrix_present"],
        "block_reasons": report["block_reasons"],
        "waiting_reasons": report["waiting_reasons"],
        "runtime_authority": False,
        "dashboard_is_runtime_authority": False,
        "operator_dashboard_executes_runtime": False,
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
    summary["p31_operator_decision_matrix_dashboard_export_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p31_operator_decision_matrix_dashboard_export_summary.json", summary)
    registry_record = append_registry_record(
        registry_path(cfg, P31_OPERATOR_DECISION_MATRIX_DASHBOARD_EXPORT_REGISTRY_NAME),
        report,
        registry_name=P31_OPERATOR_DECISION_MATRIX_DASHBOARD_EXPORT_REGISTRY_NAME,
        id_field="p31_operator_decision_matrix_dashboard_export_registry_id",
        hash_field="p31_operator_decision_matrix_dashboard_export_registry_sha256",
        id_prefix="p31_operator_decision_matrix_dashboard_export",
    )
    atomic_write_json(latest / "p31_operator_decision_matrix_dashboard_export_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_operator_decision_matrix_dashboard_export()
    print(result["status"])
    print(result["p31_operator_decision_matrix_dashboard_export_sha256"])
