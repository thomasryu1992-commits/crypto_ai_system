from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.agents.agent_output_validator import (
    build_agent_output_schema_validation_report,
    persist_agent_output_schema_validation_report,
    validate_agent_output,
)
from crypto_ai_system.config import load_config
from crypto_ai_system.registry.base_registry import load_registry_records


def _valid_output() -> dict:
    case = json.loads((Path.cwd() / "agent_contracts" / "eval_cases" / "approval" / "valid_approval_intake.json").read_text(encoding="utf-8"))
    return case["agent_output"]


def test_step323_valid_agent_output_passes_review_only() -> None:
    result = validate_agent_output(_valid_output())

    assert result.status == "PASS_REVIEW_ONLY"
    assert result.passed is True
    assert result.blocked is False
    assert result.fail_closed is False
    assert result.block_reasons == []


def test_step323_runtime_mutation_output_is_forced_fail_closed() -> None:
    output = _valid_output()
    output["runtime_mutation_performed"] = True
    output["passed"] = True
    output["blocked"] = False
    output["fail_closed"] = False

    result = validate_agent_output(output)

    assert result.status == "BLOCK_FAIL_CLOSED"
    assert result.passed is False
    assert result.blocked is True
    assert result.fail_closed is True
    assert "prohibited_runtime_mutation_performed" in result.block_reasons


def test_step323_order_submission_output_is_forced_fail_closed() -> None:
    output = _valid_output()
    output["order_submission_performed"] = True

    result = validate_agent_output(output)

    assert result.blocked is True
    assert result.fail_closed is True
    assert "prohibited_order_submission_performed" in result.block_reasons


def test_step323_missing_evidence_hash_blocks() -> None:
    output = _valid_output()
    output["evidence_hash"] = ""

    result = validate_agent_output(output)

    assert result.blocked is True
    assert result.fail_closed is True
    assert "missing_evidence_hash" in result.block_reasons


def test_step323_broken_canonical_id_chain_blocks() -> None:
    output = _valid_output()
    output["canonical_id_chain"].pop("risk_gate_id")

    result = validate_agent_output(output)

    assert result.blocked is True
    assert result.fail_closed is True
    assert any(reason.startswith("broken_canonical_id_chain") for reason in result.block_reasons)


def test_step323_schema_validation_report_persists_review_only_registry(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  version: step286_researchsignal_feature_lineage_fix\nstorage:\n  registry_dir: storage/registries\n  latest_dir: storage/latest\n",
        encoding="utf-8",
    )
    cfg = load_config(root)
    report = build_agent_output_schema_validation_report([_valid_output()])
    appended = persist_agent_output_schema_validation_report(cfg, report)

    assert report["review_only"] is True
    assert report["runtime_permission_source"] is False
    assert report["order_submission_performed"] is False
    assert appended["registry_name"] == "agent_output_schema_validation_registry"
    assert (root / "storage" / "latest" / "agent_output_schema_validation_report.json").exists()
    rows = load_registry_records(root / "storage" / "registries" / "agent_output_schema_validation_registry.jsonl")
    assert len(rows) == 1
