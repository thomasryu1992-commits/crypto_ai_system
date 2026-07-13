from __future__ import annotations

import json
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.agents.agent_library_contract_review import (
    STATUS_AGENT_LIBRARY_CONTRACT_REVIEW_BLOCKED,
    STATUS_AGENT_LIBRARY_CONTRACT_REVIEW_RECORDED,
    build_agent_library_contract_review_report,
    persist_agent_library_contract_review_report,
)
from crypto_ai_system.config import load_config
from crypto_ai_system.registry.base_registry import load_registry_records


def _cfg(tmp_path: Path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    return cfg


def _seed_agent_evidence(tmp_path: Path) -> None:
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    payloads = {
        "agent_lint_report.json": {
            "status": "AGENT_LINT_PASSED",
            "passed": True,
            "review_only": True,
            "runtime_permission_source": False,
            "agent_count": 5,
        },
        "agent_contract_validation_report.json": {
            "status": "AGENT_CONTRACT_VALIDATION_PASSED",
            "passed": True,
            "review_only": True,
            "runtime_permission_source": False,
            "agent_count": 5,
        },
        "agent_contract_index.json": {
            "status": "AGENT_CONTRACT_INDEX_REVIEW_ONLY_RECORDED",
            "review_only": True,
            "runtime_permission_source": False,
            "agent_count": 5,
            "can_modify_runtime_all_false": True,
            "can_submit_orders_all_false": True,
            "agent_contract_index_id": "agent_contract_index_test",
            "agent_contract_index_sha256": "agent_contract_index_hash_test",
        },
        "agent_contract_registry_record.json": {
            "status": "AGENT_CONTRACT_REGISTRY_RECORDED",
            "review_only": True,
            "runtime_permission_source": False,
            "agent_contract_registry_record_id": "agent_contract_registry_record_test",
        },
        "agent_output_schema_validation_report.json": {
            "status": "AGENT_OUTPUT_SCHEMA_VALIDATION_RECORDED",
            "passed": True,
            "review_only": True,
            "runtime_permission_source": False,
        },
        "agent_eval_report.json": {
            "status": "AGENT_EVALS_PASSED",
            "passed": True,
            "review_only": True,
            "runtime_permission_source": False,
            "eval_case_count": 9,
        },
    }
    for filename, payload in payloads.items():
        atomic_write_json(latest / filename, payload)


def test_step325_builds_contract_review_artifact_from_agent_evidence(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _seed_agent_evidence(tmp_path)

    report = build_agent_library_contract_review_report(cfg=cfg, project_root=Path.cwd())

    assert report["status"] == STATUS_AGENT_LIBRARY_CONTRACT_REVIEW_RECORDED
    assert report["passed"] is True
    assert report["blocked"] is False
    assert report["review_only"] is True
    assert report["runtime_permission_source"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["order_submission_performed"] is False
    assert report["signed_testnet_unlock_authority"] is False
    assert report["live_execution_unlock_authority"] is False
    assert report["missing_evidence_files"] == []
    assert report["checks"]["permission_policy_passed"] is True
    assert report["checks"]["prohibited_action_scan_passed"] is True


def test_step325_missing_evidence_fails_closed(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    atomic_write_json(latest / "agent_lint_report.json", {"status": "AGENT_LINT_PASSED", "passed": True})

    report = build_agent_library_contract_review_report(cfg=cfg, project_root=Path.cwd())

    assert report["status"] == STATUS_AGENT_LIBRARY_CONTRACT_REVIEW_BLOCKED
    assert report["passed"] is False
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert any(reason.startswith("missing_agent_library_evidence:") for reason in report["block_reasons"])
    assert report["runtime_settings_mutated"] is False
    assert report["auto_promotion_allowed"] is False


def test_step325_persists_review_artifact_and_append_only_registry(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _seed_agent_evidence(tmp_path)
    report = build_agent_library_contract_review_report(cfg=cfg, project_root=Path.cwd())

    registry_record = persist_agent_library_contract_review_report(cfg, report)

    latest = tmp_path / "storage" / "latest"
    assert (latest / "agent_library_contract_review_report.json").exists()
    assert (latest / "agent_permission_policy_report.json").exists()
    assert (latest / "agent_prohibited_action_scan.json").exists()
    assert registry_record["runtime_permission_source"] is False
    rows = load_registry_records(tmp_path / "storage" / "registries" / "agent_library_contract_review_registry.jsonl")
    assert len(rows) == 1
    assert rows[0]["status"] == STATUS_AGENT_LIBRARY_CONTRACT_REVIEW_RECORDED
    assert rows[0]["order_submission_performed"] is False
