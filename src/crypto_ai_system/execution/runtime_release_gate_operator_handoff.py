from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P17_RUNTIME_RELEASE_GATE_VERSION = "p17_runtime_release_gate_operator_handoff_v1"
P17_RUNTIME_RELEASE_GATE_REGISTRY_NAME = "p17_runtime_release_gate_operator_handoff_registry"

STATUS_GENERATED_REVIEW_ONLY = "P17_RUNTIME_RELEASE_GATE_OPERATOR_HANDOFF_GENERATED_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P17_RUNTIME_RELEASE_GATE_OPERATOR_HANDOFF_BLOCKED_FAIL_CLOSED"

_HIGH_RISK_TRUE_FIELDS = {
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "live_execution_unlock_authority",
    "live_trading_allowed_by_this_module",
    "live_order_submission_allowed",
    "live_order_submission_allowed_by_this_module",
    "live_scaled_readiness_allowed",
    "live_scaled_promotion_allowed",
    "live_scaled_promotion_allowed_by_this_module",
    "live_scaled_auto_trading_allowed",
    "limited_live_scaled_auto_trading_allowed",
    "limited_live_scaled_auto_trading_allowed_by_this_module",
    "limited_live_scaled_auto_trading_allowed_this_module",
    "live_scaled_runtime_enablement_allowed",
    "live_scaled_runtime_enablement_performed",
    "runtime_scheduler_enabled",
    "runtime_loop_started",
    "actual_order_submission_performed",
    "actual_testnet_order_submitted",
    "actual_live_order_submitted",
    "actual_live_order_submitted_by_this_module",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "live_order_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "auto_promotion_allowed",
    "secret_value_accessed",
    "secret_value_logged",
    "api_key_value_logged",
    "api_secret_value_logged",
    "private_key_logged",
    "passphrase_logged",
    "secret_file_accessed",
    "secret_file_created",
    "mainnet_key_scope_allowed",
    "withdrawal_permission_allowed",
    "transfer_permission_allowed",
    "admin_permission_allowed",
}

_ENDPOINT_EVIDENCE_TRUE_FIELDS = {
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "live_order_endpoint_called",
    "http_request_sent",
    "actual_order_submission_performed",
    "actual_testnet_order_submitted",
    "actual_live_order_submitted",
    "external_order_submission_performed",
    "signature_created",
    "signed_request_created",
}

_SECRET_VALUE_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ASIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{20,}"),
    re.compile(r"(?i)(api[_-]?secret|private[_-]?key|passphrase)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
]

# The gate intentionally uses latest summary/report artifacts rather than runtime
# authority. Missing latest artifacts block the handoff pack because the operator
# should not receive a partial readiness surface.
_REQUIRED_PHASE_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("P0", "p0_baseline_hygiene_completion_summary.json"),
    ("P1", "p1_live_candidate_data_foundation_summary.json"),
    ("P2", "p2_paper_operation_validation_summary.json"),
    ("P3", "p3_candidate_manual_approval_chain_summary.json"),
    ("P4", "p4_signed_testnet_one_order_runtime_package_summary.json"),
    ("P5", "p5_action_time_submit_approval_boundary_summary.json"),
    ("P6", "p6_single_signed_testnet_submit_runtime_action_summary.json"),
    ("P7", "p7_post_submit_evidence_intake_summary.json"),
    ("P8", "p8_repeated_clean_signed_testnet_sessions_summary.json"),
    ("P9", "p9_live_read_only_canary_preparation_summary.json"),
    ("P10", "p10_live_canary_one_order_execution_boundary_summary.json"),
    ("P11", "p11_live_canary_post_submit_evidence_review_summary.json"),
    ("P12", "p12_repeated_clean_live_canary_sessions_summary.json"),
    ("P13", "p13_live_scaled_readiness_review_summary.json"),
    ("P14", "p14_live_scaled_approval_intake_validation_summary.json"),
    ("P15", "p15_limited_live_scaled_runtime_enablement_boundary_summary.json"),
    ("P16", "p16_limited_live_scaled_loop_dry_run_harness_summary.json"),
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


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _status_from(payload: Mapping[str, Any]) -> str:
    for key in ("status", "baseline_status", "phase_status", "validation_status"):
        value = payload.get(key)
        if value:
            return str(value)
    return "UNKNOWN_STATUS"


def _walk_json(payload: Any, *, path: str = "$") -> Iterable[tuple[str, str, Any]]:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            child_path = f"{path}.{key}"
            yield child_path, str(key), value
            yield from _walk_json(value, path=child_path)
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            yield from _walk_json(value, path=f"{path}[{index}]")


def _hash_if_present(payload: Mapping[str, Any]) -> str | None:
    if not payload:
        return None
    for key in ("sha256", "report_sha256", "summary_sha256", "p16_limited_live_scaled_loop_dry_run_harness_sha256"):
        if payload.get(key):
            return str(payload[key])
    return sha256_json(dict(payload))


def _scan_truthy_fields(named_payloads: Sequence[tuple[str, Mapping[str, Any]]], fields: set[str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for source_name, payload in named_payloads:
        for path, key, value in _walk_json(payload):
            if key in fields and _bool(value):
                hits.append(
                    {
                        "source": source_name,
                        "path": path,
                        "field": key,
                        "value": bool(_bool(value)),
                    }
                )
    return hits


def _scan_secret_values(named_payloads: Sequence[tuple[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for source_name, payload in named_payloads:
        for path, _key, value in _walk_json(payload):
            if not isinstance(value, str):
                continue
            text = value.strip()
            if not text:
                continue
            for pattern in _SECRET_VALUE_PATTERNS:
                if pattern.search(text):
                    hits.append(
                        {
                            "source": source_name,
                            "path": path,
                            "pattern": pattern.pattern,
                            "redacted_value_preview": f"{text[:4]}...{text[-4:]}" if len(text) > 8 else "<redacted>",
                        }
                    )
    return hits


def build_latest_status_matrix(
    *,
    latest_payloads: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    latest_payloads = latest_payloads or {}
    matrix: list[dict[str, Any]] = []
    for phase_id, filename in _REQUIRED_PHASE_ARTIFACTS:
        payload = dict(latest_payloads.get(filename) or {})
        exists = bool(payload)
        status = _status_from(payload) if exists else "MISSING"
        matrix.append(
            {
                "phase_id": phase_id,
                "artifact_filename": filename,
                "artifact_present": exists,
                "status": status,
                "waiting": bool(_bool(payload.get("waiting"))) or "WAITING" in status,
                "blocked": bool(_bool(payload.get("blocked"))) or "BLOCKED" in status,
                "review_only": "REVIEW_ONLY" in status or bool(_bool(payload.get("review_only"))),
                "sha256": _hash_if_present(payload),
                "live_order_submission_allowed": bool(_bool(payload.get("live_order_submission_allowed"))),
                "live_scaled_execution_enabled": bool(_bool(payload.get("live_scaled_execution_enabled"))),
                "runtime_scheduler_enabled": bool(_bool(payload.get("runtime_scheduler_enabled"))),
                "secret_value_accessed": bool(_bool(payload.get("secret_value_accessed"))),
            }
        )
    return matrix


def build_operator_handoff_checklist(status_matrix: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    waiting = [row["phase_id"] for row in status_matrix if row.get("waiting")]
    blocked = [row["phase_id"] for row in status_matrix if row.get("blocked")]
    return [
        {
            "step": "Confirm package posture",
            "required_outcome": "review_only / preparation / no runtime execution authority",
            "current_evidence": "P17 release gate keeps all execution flags disabled",
        },
        {
            "step": "Review waiting stages",
            "required_outcome": "No stage is interpreted as live-ready while waiting evidence exists",
            "current_evidence": {"waiting_phase_ids": waiting, "blocked_phase_ids": blocked},
        },
        {
            "step": "Run one-command release gate before handoff",
            "required_command": "PYTHONPATH=src:. python scripts/run_release_gate.py",
            "required_outcome": "P17_RUNTIME_RELEASE_GATE_OPERATOR_HANDOFF_GENERATED_REVIEW_ONLY",
        },
        {
            "step": "Do not enable runtime flags from this pack",
            "required_outcome": "limited_live_scaled_auto_trading_allowed=false and live_scaled_execution_enabled=false",
        },
        {
            "step": "Collect missing real evidence outside this pack",
            "required_outcome": "Actual signed testnet/live evidence must be externally supplied and validated by the relevant P7/P8/P11/P12/P13/P14/P15 gates",
        },
    ]


def build_runtime_release_gate_operator_handoff_report(
    *,
    latest_payloads: Mapping[str, Mapping[str, Any]],
    extra_payloads_for_scan: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    latest_status_matrix = build_latest_status_matrix(latest_payloads=latest_payloads)
    missing = [row["artifact_filename"] for row in latest_status_matrix if not row["artifact_present"]]
    named_payloads = [(filename, dict(payload)) for filename, payload in latest_payloads.items()]
    named_payloads.extend(extra_payloads_for_scan or [])

    unsafe_hits = _scan_truthy_fields(named_payloads, _HIGH_RISK_TRUE_FIELDS)
    endpoint_hits = _scan_truthy_fields(named_payloads, _ENDPOINT_EVIDENCE_TRUE_FIELDS)
    secret_hits = _scan_secret_values(named_payloads)
    disabled_state = default_execution_flag_state()
    disabled_state.update(
        {
            "p17_runtime_release_gate_operator_handoff_valid_review_only": False,
            "p17_operator_handoff_pack_created": False,
            "limited_live_scaled_auto_trading_allowed": False,
            "live_scaled_runtime_enablement_allowed": False,
            "live_scaled_execution_enabled": False,
            "live_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "runtime_scheduler_enabled": False,
            "runtime_loop_started": False,
            "actual_live_order_submitted": False,
            "live_order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "secret_value_logged": False,
            "api_key_value_logged": False,
            "api_secret_value_logged": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "auto_promotion_allowed": False,
        }
    )
    truthy_disabled = truthy_execution_flags(disabled_state)
    block_reasons: list[str] = []
    if missing:
        block_reasons.append("P17_REQUIRED_PHASE_ARTIFACT_MISSING")
    if unsafe_hits:
        block_reasons.append("P17_UNSAFE_TRUTHY_FLAG_FOUND")
    if endpoint_hits:
        block_reasons.append("P17_ENDPOINT_CALL_EVIDENCE_FOUND")
    if secret_hits:
        block_reasons.append("P17_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P17_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    status = STATUS_BLOCKED_FAIL_CLOSED if blocked else STATUS_GENERATED_REVIEW_ONLY
    waiting_phase_ids = [str(row["phase_id"]) for row in latest_status_matrix if row.get("waiting")]
    blocked_phase_ids = [str(row["phase_id"]) for row in latest_status_matrix if row.get("blocked")]

    report: dict[str, Any] = {
        "p17_runtime_release_gate_version": P17_RUNTIME_RELEASE_GATE_VERSION,
        "status": status,
        "blocked": blocked,
        "block_reasons": sorted(set(block_reasons)),
        "created_at_utc": utc_now_canonical(),
        "required_phase_artifact_count": len(_REQUIRED_PHASE_ARTIFACTS),
        "present_phase_artifact_count": len(_REQUIRED_PHASE_ARTIFACTS) - len(missing),
        "missing_required_phase_artifacts": missing,
        "latest_status_matrix": latest_status_matrix,
        "waiting_phase_ids": waiting_phase_ids,
        "blocked_phase_ids": blocked_phase_ids,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "endpoint_call_evidence_hits": endpoint_hits,
        "secret_value_scan_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "p17_runtime_release_gate_operator_handoff_valid_review_only": not blocked,
        "p17_operator_handoff_pack_created": not blocked,
        "one_command_release_gate_command": "PYTHONPATH=src:. python scripts/run_release_gate.py",
        "operator_handoff_checklist": build_operator_handoff_checklist(latest_status_matrix),
        "operator_release_decision": {
            "release_pack_generated": not blocked,
            "live_scaled_runtime_ready": False,
            "limited_live_scaled_auto_trading_allowed": False,
            "live_scaled_runtime_enablement_allowed": False,
            "live_scaled_execution_enabled": False,
            "live_order_submission_allowed": False,
            "runtime_scheduler_enabled": False,
            "runtime_loop_started": False,
            "must_not_submit_orders_from_this_pack": True,
            "separate_real_evidence_and_manual_approval_still_required": True,
        },
        "scan_scope": {
            "phase_artifacts": [filename for _, filename in _REQUIRED_PHASE_ARTIFACTS],
            "high_risk_truthy_fields": sorted(_HIGH_RISK_TRUE_FIELDS),
            "endpoint_evidence_fields": sorted(_ENDPOINT_EVIDENCE_TRUE_FIELDS),
            "secret_scan_mode": "latest_artifact_string_values_redacted_preview_only",
        },
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "actual_live_order_submitted": False,
        "live_order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    report["p17_runtime_release_gate_operator_handoff_id"] = stable_id("p17_runtime_release_gate_operator_handoff", report, 24)
    report["p17_runtime_release_gate_operator_handoff_sha256"] = sha256_json(report)
    return report


def build_p17_negative_fixture_results() -> dict[str, Any]:
    base_payloads: dict[str, dict[str, Any]] = {
        filename: {
            "status": f"{phase_id}_FIXTURE_REVIEW_ONLY",
            "review_only": True,
            "live_scaled_execution_enabled": False,
            "live_order_submission_allowed": False,
            "secret_value_accessed": False,
        }
        for phase_id, filename in _REQUIRED_PHASE_ARTIFACTS
    }
    cases: dict[str, dict[str, Mapping[str, Any] | dict[str, dict[str, Any]]]] = {
        "missing_required_artifact": {
            "payloads": {k: v for k, v in base_payloads.items() if k != "p16_limited_live_scaled_loop_dry_run_harness_summary.json"},
        },
        "unsafe_live_scaled_enabled": {
            "payloads": {
                **base_payloads,
                "p16_limited_live_scaled_loop_dry_run_harness_summary.json": {
                    **base_payloads["p16_limited_live_scaled_loop_dry_run_harness_summary.json"],
                    "live_scaled_execution_enabled": True,
                },
            }
        },
        "endpoint_call_evidence_found": {
            "payloads": {
                **base_payloads,
                "p15_limited_live_scaled_runtime_enablement_boundary_summary.json": {
                    **base_payloads["p15_limited_live_scaled_runtime_enablement_boundary_summary.json"],
                    "http_request_sent": True,
                },
            }
        },
        "secret_pattern_found": {
            "payloads": {
                **base_payloads,
                "p14_live_scaled_approval_intake_validation_summary.json": {
                    **base_payloads["p14_live_scaled_approval_intake_validation_summary.json"],
                    "operator_note": "sk-thisIsAFakeSecretPatternForScannerOnly123456",
                },
            }
        },
        "runtime_scheduler_enabled": {
            "payloads": {
                **base_payloads,
                "p16_limited_live_scaled_loop_dry_run_harness_summary.json": {
                    **base_payloads["p16_limited_live_scaled_loop_dry_run_harness_summary.json"],
                    "runtime_scheduler_enabled": True,
                },
            }
        },
    }
    results: dict[str, Any] = {}
    for name, case in cases.items():
        report = build_runtime_release_gate_operator_handoff_report(
            latest_payloads=dict(case["payloads"]),
        )
        results[name] = {
            "blocked": report["blocked"],
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "limited_live_scaled_auto_trading_allowed": report["limited_live_scaled_auto_trading_allowed"],
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
            "live_order_submission_allowed": report["live_order_submission_allowed"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    return {
        "p17_runtime_release_gate_version": P17_RUNTIME_RELEASE_GATE_VERSION,
        "status": "P17_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_runtime_release_gate_operator_handoff(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    latest_payloads = {filename: _read_latest_json(cfg, filename) for _, filename in _REQUIRED_PHASE_ARTIFACTS}
    report = build_runtime_release_gate_operator_handoff_report(latest_payloads=latest_payloads)
    negative_results = build_p17_negative_fixture_results()
    storage = _storage_dir(cfg, "storage/p17_runtime_release_gate_operator_handoff")

    atomic_write_json(latest / "p17_runtime_release_gate_operator_handoff_report.json", report)
    atomic_write_json(storage / "p17_runtime_release_gate_operator_handoff_report.json", report)
    atomic_write_json(latest / "p17_runtime_release_gate_operator_handoff_negative_fixture_results.json", negative_results)

    summary = {
        "status": report["status"],
        "p17_runtime_release_gate_operator_handoff_sha256": report["p17_runtime_release_gate_operator_handoff_sha256"],
        "p17_runtime_release_gate_operator_handoff_valid_review_only": report[
            "p17_runtime_release_gate_operator_handoff_valid_review_only"
        ],
        "p17_operator_handoff_pack_created": report["p17_operator_handoff_pack_created"],
        "present_phase_artifact_count": report["present_phase_artifact_count"],
        "required_phase_artifact_count": report["required_phase_artifact_count"],
        "missing_required_phase_artifacts": report["missing_required_phase_artifacts"],
        "waiting_phase_ids": report["waiting_phase_ids"],
        "blocked_phase_ids": report["blocked_phase_ids"],
        "unsafe_truthy_execution_flag_hit_count": len(report["unsafe_truthy_execution_flag_hits"]),
        "endpoint_call_evidence_hit_count": len(report["endpoint_call_evidence_hits"]),
        "secret_value_scan_hit_count": len(report["secret_value_scan_hits"]),
        "one_command_release_gate_command": report["one_command_release_gate_command"],
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "actual_live_order_submitted": False,
        "live_order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    summary["p17_runtime_release_gate_operator_handoff_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p17_runtime_release_gate_operator_handoff_summary.json", summary)

    registry_record = append_registry_record(
        registry_path(cfg, P17_RUNTIME_RELEASE_GATE_REGISTRY_NAME),
        report,
        registry_name=P17_RUNTIME_RELEASE_GATE_REGISTRY_NAME,
        id_field="p17_runtime_release_gate_operator_handoff_registry_id",
        hash_field="p17_runtime_release_gate_operator_handoff_registry_sha256",
        id_prefix="p17_release_gate",
    )
    atomic_write_json(latest / "p17_runtime_release_gate_operator_handoff_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_runtime_release_gate_operator_handoff()
    print(result["status"])
    print(result["p17_runtime_release_gate_operator_handoff_sha256"])
