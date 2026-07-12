from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.registry.agent_contract_registry import (
    AGENT_CONTRACT_REGISTRY_NAME,
    build_agent_contract_index,
    generate_and_persist_agent_contract_registry,
)
from crypto_ai_system.registry.base_registry import load_registry_records


def _minimal_project(tmp_path: Path) -> Path:
    source_root = Path.cwd()
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  version: step286_researchsignal_feature_lineage_fix\nstorage:\n  registry_dir: storage/registries\n  latest_dir: storage/latest\n",
        encoding="utf-8",
    )
    for directory in ["agents", "agent_contracts"]:
        src = source_root / directory
        dst = root / directory
        for path in src.rglob("*"):
            if path.is_file():
                target = dst / path.relative_to(src)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return root


def test_step322_builds_hash_tracked_agent_contract_index() -> None:
    index = build_agent_contract_index(project_root=Path.cwd())

    assert index["status"] == "AGENT_CONTRACT_INDEX_REVIEW_ONLY_RECORDED"
    assert index["review_only"] is True
    assert index["runtime_permission_source"] is False
    assert index["runtime_settings_mutated"] is False
    assert index["order_submission_performed"] is False
    assert index["agent_count"] >= 5
    assert index["can_modify_runtime_all_false"] is True
    assert index["can_submit_orders_all_false"] is True
    assert index["validation_errors"] == []
    for record in index["contracts"]:
        assert record["contract_file_sha256"]
        assert record["contract_body_sha256"]
        assert record["agent_hash"]


def test_step322_persists_index_latest_and_append_only_registry(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    cfg = load_config(root)

    result = generate_and_persist_agent_contract_registry(cfg)
    index = result["index"]
    registry_record = result["registry_record"]

    assert index["validation_errors"] == []
    assert registry_record["registry_name"] == AGENT_CONTRACT_REGISTRY_NAME
    assert registry_record["runtime_permission_source"] is False
    assert registry_record["runtime_settings_mutated"] is False
    assert registry_record["order_submission_performed"] is False
    assert (root / "storage" / "latest" / "agent_contract_index.json").exists()
    assert (root / "storage" / "latest" / "agent_contract_registry_record.json").exists()

    rows = load_registry_records(root / "storage" / "registries" / f"{AGENT_CONTRACT_REGISTRY_NAME}.jsonl")
    assert len(rows) == 1
    assert rows[0]["agent_contract_registry_append_sha256"]
    assert rows[0]["agent_count"] >= 5


def test_step322_duplicate_agent_id_fails_closed(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    duplicate = root / "agents" / "qa" / "duplicate_artifact_integrity_auditor.md"
    source = root / "agents" / "qa" / "artifact_integrity_auditor.md"
    duplicate.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    index = build_agent_contract_index(project_root=root)

    assert index["status"] == "AGENT_CONTRACT_INDEX_BLOCKED"
    assert index["runtime_permission_source"] is False
    assert any(error.startswith("duplicate_agent_id:artifact_integrity_auditor") for error in index["validation_errors"])


def test_step322_index_json_is_stable_and_contains_divisions() -> None:
    index = build_agent_contract_index(project_root=Path.cwd())
    encoded = json.dumps(index, ensure_ascii=False, sort_keys=True)

    assert "approval_intake_validator" in encoded
    assert "signed_testnet_unlock_preview_agent" in encoded
    assert "kill_switch_auditor" in encoded
    assert "hard_cap_reviewer" in encoded
    assert "artifact_integrity_auditor" in encoded
    assert set(index["divisions"]).issuperset({"approval", "risk", "qa"})
