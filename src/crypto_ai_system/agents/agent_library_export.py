from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import read_json
from crypto_ai_system.config import AppConfig
from crypto_ai_system.utils.audit import sha256_json, utc_now_canonical

AGENT_LIBRARY_EXPORT_VERSION = "step326_agent_library_export_v1"

AGENT_LIBRARY_EXPORT_FILE_MAP: dict[str, str] = {
    "agent_contract_index.json": "agent_contract_index.json",
    "agent_lint_report.json": "agent_lint_report.json",
    "agent_eval_report.json": "agent_eval_report.json",
    "agent_contract_review_report.json": "agent_library_contract_review_report.json",
    "agent_permission_policy_report.json": "agent_permission_policy_report.json",
    "agent_prohibited_action_scan.json": "agent_prohibited_action_scan.json",
}

AGENT_LIBRARY_EXPORT_FILE_NAMES: tuple[str, ...] = tuple(AGENT_LIBRARY_EXPORT_FILE_MAP.keys())


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def missing_agent_library_artifact_payload(export_name: str, source_name: str) -> dict[str, Any]:
    payload = {
        "agent_library_export_version": AGENT_LIBRARY_EXPORT_VERSION,
        "export_name": export_name,
        "source_artifact": source_name,
        "missing": True,
        "status": "AGENT_LIBRARY_EXPORT_ARTIFACT_MISSING",
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "runtime_mutation_performed": False,
        "order_submission_performed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    payload["agent_library_missing_artifact_sha256"] = sha256_json(payload)
    return payload


def collect_agent_library_export_artifacts(cfg: AppConfig) -> tuple[dict[str, dict[str, Any]], list[str]]:
    latest = _latest_dir(cfg)
    artifacts: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for export_name, source_name in AGENT_LIBRARY_EXPORT_FILE_MAP.items():
        source_path = latest / source_name
        if not source_path.exists():
            artifacts[export_name] = missing_agent_library_artifact_payload(export_name, source_name)
            missing.append(export_name)
            continue
        payload = _as_mapping(read_json(source_path, default={}))
        if not payload:
            artifacts[export_name] = missing_agent_library_artifact_payload(export_name, source_name)
            missing.append(export_name)
        else:
            artifacts[export_name] = payload
    return artifacts, missing
