from __future__ import annotations

from pathlib import Path
from typing import Any

import json
import os
import tempfile
from crypto_ai_system.agents.contract_loader import validate_agent_contracts
from crypto_ai_system.config import AppConfig
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

AGENT_CONTRACT_REGISTRY_NAME = "agent_contract_registry"
AGENT_CONTRACT_INDEX_VERSION = "step322_agent_contract_index_v1"
AGENT_CONTRACT_REGISTRY_VERSION = "step322_agent_contract_registry_v1"


def _atomic_write_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True, default=str)
            handle.write("\n")
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def build_agent_contract_index(*, project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root).resolve()
    contracts, errors = validate_agent_contracts(root)
    contract_records = [contract.to_index_record() for contract in contracts]
    divisions: dict[str, list[str]] = {}
    for record in contract_records:
        divisions.setdefault(str(record["division"]), []).append(str(record["agent_id"]))
    for values in divisions.values():
        values.sort()
    index_payload = {
        "agent_contract_index_version": AGENT_CONTRACT_INDEX_VERSION,
        "created_at_utc": utc_now_canonical(),
        "status": "AGENT_CONTRACT_INDEX_REVIEW_ONLY_RECORDED" if not errors else "AGENT_CONTRACT_INDEX_BLOCKED",
        "review_only": True,
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "order_submission_performed": False,
        "auto_promotion_allowed": False,
        "can_modify_runtime_all_false": all(record.get("can_modify_runtime") is False for record in contract_records),
        "can_submit_orders_all_false": all(record.get("can_submit_orders") is False for record in contract_records),
        "agent_count": len(contract_records),
        "divisions": divisions,
        "contracts": contract_records,
        "validation_errors": errors,
    }
    index_payload["agent_contract_index_id"] = stable_id("agent_contract_index", index_payload, 24)
    index_payload["agent_contract_index_sha256"] = sha256_json(index_payload)
    return index_payload


def build_agent_contract_registry_record(index: dict[str, Any]) -> dict[str, Any]:
    contracts = index.get("contracts") or []
    record = {
        "agent_contract_registry_version": AGENT_CONTRACT_REGISTRY_VERSION,
        "agent_contract_index_id": index.get("agent_contract_index_id"),
        "agent_contract_index_sha256": index.get("agent_contract_index_sha256"),
        "status": "AGENT_CONTRACT_REGISTRY_RECORDED" if not index.get("validation_errors") else "AGENT_CONTRACT_REGISTRY_BLOCKED",
        "review_only": True,
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "order_submission_performed": False,
        "auto_promotion_allowed": False,
        "agent_count": index.get("agent_count", 0),
        "agent_ids": [record.get("agent_id") for record in contracts],
        "contract_file_sha256_by_agent_id": {
            str(record.get("agent_id")): record.get("contract_file_sha256") for record in contracts
        },
        "agent_hash_by_agent_id": {str(record.get("agent_id")): record.get("agent_hash") for record in contracts},
        "validation_errors": index.get("validation_errors", []),
        "created_at_utc": utc_now_canonical(),
    }
    record["agent_contract_registry_record_id"] = stable_id("agent_contract_registry", record, 24)
    record["agent_contract_registry_record_sha256"] = sha256_json(record)
    return record


def persist_agent_contract_index(cfg: AppConfig, index: dict[str, Any], registry_record: dict[str, Any] | None = None) -> dict[str, Any]:
    latest = _latest_dir(cfg)
    _atomic_write_json(latest / "agent_contract_index.json", index)
    if registry_record is not None:
        _atomic_write_json(latest / "agent_contract_registry_record.json", registry_record)
    return index


def persist_agent_contract_registry_record(cfg: AppConfig, registry_record: dict[str, Any]) -> dict[str, Any]:
    path = registry_path(cfg, AGENT_CONTRACT_REGISTRY_NAME)
    appended = append_registry_record(
        path,
        registry_record,
        registry_name=AGENT_CONTRACT_REGISTRY_NAME,
        id_field="agent_contract_registry_append_id",
        hash_field="agent_contract_registry_append_sha256",
        id_prefix="agent_contract_registry_append",
    )
    latest = _latest_dir(cfg)
    _atomic_write_json(latest / "agent_contract_registry_record.json", appended)
    return appended


def generate_and_persist_agent_contract_registry(cfg: AppConfig) -> dict[str, Any]:
    index = build_agent_contract_index(project_root=cfg.root)
    registry_record = build_agent_contract_registry_record(index)
    persist_agent_contract_index(cfg, index, registry_record)
    appended = persist_agent_contract_registry_record(cfg, registry_record)
    return {"index": index, "registry_record": appended}
