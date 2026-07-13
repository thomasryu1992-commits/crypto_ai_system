from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_file, sha256_json, stable_id, utc_now_canonical

BASELINE_INTEGRITY_FREEZE_VERSION = "phase1_baseline_integrity_freeze_v1"
BASELINE_INTEGRITY_FREEZE_REGISTRY_NAME = "baseline_integrity_freeze_registry"
STATUS_BASELINE_INTEGRITY_FROZEN_REVIEW_ONLY = "BASELINE_INTEGRITY_FROZEN_REVIEW_ONLY"
STATUS_BASELINE_INTEGRITY_FREEZE_BLOCKED = "BASELINE_INTEGRITY_FREEZE_BLOCKED"

REQUIRED_LATEST_EVIDENCE_FILES: tuple[str, ...] = (
    "agent_lint_report.json",
    "agent_contract_validation_report.json",
    "agent_contract_index.json",
    "agent_contract_registry_record.json",
    "agent_output_schema_validation_report.json",
    "agent_eval_report.json",
    "agent_library_contract_review_report.json",
    "agent_permission_policy_report.json",
    "agent_prohibited_action_scan.json",
    "review_only_export_packet_manifest.json",
    "review_only_export_packet_registry_record.json",
    "live_scaled_readiness_gate.json",
    "live_scaled_readiness_gate_registry_record.json",
    "canary_outcome_report.json",
    "data_health_report.json",
)

REQUIRED_SOURCE_FILES: tuple[str, ...] = (
    "README.md",
    "CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md",
    "LIVE_EXECUTION_ROADMAP_REVIEW_ONLY.md",
    "agents/risk/preorder_risk_gate_auditor.md",
    "scripts/status_consistency_checker.py",
    "scripts/build_source_package.py",
    "scripts/build_audit_bundle.py",
    "scripts/lint_agents.py",
    "scripts/validate_agent_contracts.py",
    "scripts/validate_agent_outputs.py",
    "scripts/run_agent_evals.py",
    "scripts/generate_agent_index.py",
    "scripts/build_agent_library_contract_review.py",
    "tests/agents/test_step328_preorder_risk_gate_auditor_completion.py",
)

from crypto_ai_system.execution.runtime_disabled_flags import DISABLED_RUNTIME_FLAG_PATHS

DISABLED_RUNTIME_FLAGS = DISABLED_RUNTIME_FLAG_PATHS


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _baseline_dir(cfg: AppConfig) -> Path:
    path = cfg.root / "storage" / "baseline_freeze"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _get_nested(mapping: Mapping[str, Any], dotted_path: str) -> Any:
    value: Any = mapping
    for part in dotted_path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _load_settings(root: Path) -> dict[str, Any]:
    path = root / "config" / "settings.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _file_hash_or_none(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return sha256_file(path)


def _artifact_record(base: Path, rel_path: str) -> dict[str, Any]:
    path = base / rel_path
    return {
        "path": rel_path,
        "exists": path.exists() and path.is_file(),
        "sha256": _file_hash_or_none(path),
        "bytes": path.stat().st_size if path.exists() and path.is_file() else None,
    }


def _extract_review_packet_status(latest: Path) -> dict[str, Any]:
    manifest = read_json(latest / "review_only_export_packet_manifest.json", default={}) or {}
    return {
        "status": manifest.get("status"),
        "review_only": manifest.get("review_only"),
        "packet_id": manifest.get("review_only_export_packet_id"),
        "packet_dir": manifest.get("packet_dir"),
        "agent_library_evidence_status": manifest.get("agent_library_evidence_status"),
        "missing_agent_library_artifacts": manifest.get("missing_agent_library_artifacts", []),
        "runtime_settings_mutated": manifest.get("runtime_settings_mutated"),
        "score_weights_mutated": manifest.get("score_weights_mutated"),
        "auto_promotion_allowed": manifest.get("auto_promotion_allowed"),
        "external_order_submission_performed": manifest.get("external_order_submission_performed"),
        "live_trading_allowed_by_this_module": manifest.get("live_trading_allowed_by_this_module"),
    }


def _extract_live_scaled_status(latest: Path) -> dict[str, Any]:
    gate = read_json(latest / "live_scaled_readiness_gate.json", default={}) or {}
    return {
        "status": gate.get("status"),
        "gate_decision": gate.get("gate_decision"),
        "blocked_reasons": gate.get("blocked_reasons", []),
        "live_scaled_execution_enabled_by_this_module": gate.get("live_scaled_execution_enabled_by_this_module"),
        "live_scaled_promotion_allowed_by_this_module": gate.get("live_scaled_promotion_allowed_by_this_module"),
        "live_trading_allowed_by_this_module": gate.get("live_trading_allowed_by_this_module"),
        "live_order_submission_allowed": gate.get("live_order_submission_allowed"),
        "api_key_value_access_allowed": gate.get("api_key_value_access_allowed"),
        "runtime_settings_mutated": gate.get("runtime_settings_mutated"),
        "score_weights_mutated": gate.get("score_weights_mutated"),
        "auto_promotion_allowed": gate.get("auto_promotion_allowed"),
    }


def build_baseline_integrity_freeze_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    root = Path(project_root or cfg.root).resolve()
    latest = _latest_dir(cfg)
    settings = _load_settings(root)

    latest_artifacts = [_artifact_record(latest, name) for name in REQUIRED_LATEST_EVIDENCE_FILES]
    source_artifacts = [_artifact_record(root, name) for name in REQUIRED_SOURCE_FILES]
    missing_latest = [item["path"] for item in latest_artifacts if not item["exists"]]
    missing_source = [item["path"] for item in source_artifacts if not item["exists"]]

    runtime_flag_values: dict[str, Any] = {}
    unsafe_runtime_flags: list[dict[str, Any]] = []
    for dotted_path, expected_bool in DISABLED_RUNTIME_FLAGS:
        value = _get_nested(settings, dotted_path)
        runtime_flag_values[dotted_path] = value
        if value is not expected_bool:
            unsafe_runtime_flags.append({"flag": dotted_path, "expected": expected_bool, "actual": value})

    agent_index = read_json(latest / "agent_contract_index.json", default={}) or {}
    agent_review = read_json(latest / "agent_library_contract_review_report.json", default={}) or {}
    agent_eval = read_json(latest / "agent_eval_report.json", default={}) or {}
    data_health = read_json(latest / "data_health_report.json", default={}) or {}
    review_packet = _extract_review_packet_status(latest)
    live_scaled = _extract_live_scaled_status(latest)

    checks = {
        "required_latest_evidence_present": not missing_latest,
        "required_source_files_present": not missing_source,
        "agent_library_contract_review_passed": agent_review.get("passed") is True,
        "agent_contract_index_review_only_recorded": agent_index.get("status") == "AGENT_CONTRACT_INDEX_REVIEW_ONLY_RECORDED",
        "agent_count_at_least_21": int(agent_index.get("agent_count") or 0) >= 21,
        "agent_eval_passed": agent_eval.get("passed") is True,
        "review_packet_agent_library_evidence_included": review_packet.get("agent_library_evidence_status") == "AGENT_LIBRARY_EVIDENCE_INCLUDED",
        "review_packet_runtime_safe": review_packet.get("runtime_settings_mutated") is False and review_packet.get("auto_promotion_allowed") is False and review_packet.get("external_order_submission_performed") is False,
        "live_scaled_readiness_blocked": str(live_scaled.get("gate_decision") or "").lower().startswith("block") or str(live_scaled.get("status") or "").upper().endswith("BLOCKED"),
        "live_scaled_runtime_safe": live_scaled.get("live_scaled_execution_enabled_by_this_module") is False and live_scaled.get("live_trading_allowed_by_this_module") is False and live_scaled.get("live_order_submission_allowed") is False,
        "runtime_disabled_flags_false": not unsafe_runtime_flags,
    }
    block_reasons: list[str] = []
    for key, ok in checks.items():
        if not ok:
            block_reasons.append(f"failed_baseline_check:{key}")
    for name in missing_latest:
        block_reasons.append(f"missing_latest_evidence:{name}")
    for name in missing_source:
        block_reasons.append(f"missing_source_file:{name}")
    for item in unsafe_runtime_flags:
        block_reasons.append(f"unsafe_runtime_flag:{item['flag']}")

    blocked = bool(block_reasons)
    evidence_hashes = {
        "latest": {item["path"]: item["sha256"] for item in latest_artifacts},
        "source": {item["path"]: item["sha256"] for item in source_artifacts},
    }
    report = {
        "baseline_integrity_freeze_version": BASELINE_INTEGRITY_FREEZE_VERSION,
        "baseline_integrity_freeze_id": stable_id("baseline_freeze", {"evidence_hashes": evidence_hashes, "checks": checks}, 24),
        "created_at_utc": utc_now_canonical(),
        "status": STATUS_BASELINE_INTEGRITY_FREEZE_BLOCKED if blocked else STATUS_BASELINE_INTEGRITY_FROZEN_REVIEW_ONLY,
        "passed": not blocked,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "current_allowed_stage": "review-only / shadow / paper-preparation",
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "runtime_mutation_performed": False,
        "order_submission_performed": False,
        "external_order_submission_performed": False,
        "auto_promotion_allowed": False,
        "signed_testnet_unlock_authority": False,
        "live_execution_unlock_authority": False,
        "checks": checks,
        "block_reasons": block_reasons,
        "required_latest_evidence_files": list(REQUIRED_LATEST_EVIDENCE_FILES),
        "missing_latest_evidence_files": missing_latest,
        "required_source_files": list(REQUIRED_SOURCE_FILES),
        "missing_source_files": missing_source,
        "evidence_sha256": evidence_hashes,
        "runtime_flag_values": runtime_flag_values,
        "unsafe_runtime_flags": unsafe_runtime_flags,
        "agent_library_summary": {
            "agent_count": agent_index.get("agent_count"),
            "division_count": len(agent_index.get("divisions") or {}),
            "can_modify_runtime_all_false": agent_index.get("can_modify_runtime_all_false"),
            "can_submit_orders_all_false": agent_index.get("can_submit_orders_all_false"),
            "agent_library_contract_review_status": agent_review.get("status"),
            "agent_eval_case_count": agent_eval.get("eval_case_count"),
            "agent_blocked_eval_case_count": agent_eval.get("blocked_case_count"),
        },
        "review_packet_summary": review_packet,
        "live_scaled_readiness_summary": live_scaled,
        "data_health_summary": {
            "status": data_health.get("status"),
            "decision": data_health.get("decision"),
            "data_health_status": data_health.get("data_health_status"),
            "blocked_reasons": data_health.get("blocked_reasons", []),
        },
        "next_phase": "Phase 2 Paper Data Quality Hardening",
    }
    report["baseline_integrity_freeze_sha256"] = sha256_json(report)
    return report


def persist_baseline_integrity_freeze_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    baseline_dir = _baseline_dir(cfg)
    report = build_baseline_integrity_freeze_report(cfg=cfg, project_root=project_root or cfg.root)
    atomic_write_json(latest / "baseline_integrity_freeze_report.json", report)
    atomic_write_json(baseline_dir / "baseline_integrity_freeze_report.json", report)
    record = append_registry_record(
        registry_path(cfg, BASELINE_INTEGRITY_FREEZE_REGISTRY_NAME),
        {
            "baseline_integrity_freeze_id": report["baseline_integrity_freeze_id"],
            "status": report["status"],
            "passed": report["passed"],
            "blocked": report["blocked"],
            "fail_closed": report["fail_closed"],
            "review_only": True,
            "runtime_permission_source": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "order_submission_performed": False,
            "auto_promotion_allowed": False,
            "baseline_integrity_freeze_sha256": report["baseline_integrity_freeze_sha256"],
            "required_latest_evidence_files": report["required_latest_evidence_files"],
            "missing_latest_evidence_files": report["missing_latest_evidence_files"],
            "checks": report["checks"],
            "block_reasons": report["block_reasons"],
        },
        registry_name=BASELINE_INTEGRITY_FREEZE_REGISTRY_NAME,
        id_field="baseline_integrity_freeze_registry_record_id",
        hash_field="baseline_integrity_freeze_registry_record_sha256",
        id_prefix="baseline_freeze_registry",
    )
    atomic_write_json(latest / "baseline_integrity_freeze_registry_record.json", record)
    return report
