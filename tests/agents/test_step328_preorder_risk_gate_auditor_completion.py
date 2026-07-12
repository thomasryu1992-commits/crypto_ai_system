from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.agents.contract_loader import validate_agent_contracts
from crypto_ai_system.registry.agent_contract_registry import build_agent_contract_index
from scripts.run_agent_evals import build_agent_eval_report


def test_preorder_risk_gate_auditor_contract_exists_and_is_review_only() -> None:
    root = Path.cwd()
    path = root / "agents" / "risk" / "preorder_risk_gate_auditor.md"
    assert path.exists()
    contracts, errors = validate_agent_contracts(root)
    assert not errors
    by_id = {contract.agent_id: contract for contract in contracts}
    contract = by_id["preorder_risk_gate_auditor"]

    assert contract.division == "risk"
    assert contract.permission_tier == "read_only"
    assert contract.frontmatter["requires_evidence"] is True
    assert contract.frontmatter["can_modify_runtime"] is False
    assert contract.frontmatter["can_submit_orders"] is False
    assert contract.frontmatter["eval_case_path"] == "agent_contracts/eval_cases/risk/valid_preorder_risk_gate_auditor.json"
    assert (root / contract.frontmatter["eval_case_path"]).exists()
    assert "runtime_mutation_performed=false" in contract.body
    assert "order_submission_performed=false" in contract.body
    assert "blocked=true" in contract.body
    assert "fail_closed=true" in contract.body


def test_preorder_risk_gate_auditor_required_checks_cover_full_gate_policy() -> None:
    body = (Path.cwd() / "agents" / "risk" / "preorder_risk_gate_auditor.md").read_text(encoding="utf-8")
    required_terms = [
        "Approved profile",
        "Profile hash",
        "Price data",
        "Optional data health",
        "Fallback, synthetic, mock, sample, stale, or hidden-missing",
        "Position limits",
        "daily loss limits",
        "max consecutive loss limits",
        "Spread, slippage, fee model, and min/max notional",
        "API error rate",
        "venue readiness",
        "Reconciliation mismatch",
        "manual kill switch",
        "Canonical ID chain",
    ]
    for term in required_terms:
        assert term in body


def test_preorder_risk_gate_auditor_is_indexed_and_eval_covered() -> None:
    root = Path.cwd()
    index = build_agent_contract_index(project_root=root)
    indexed_ids = {record["agent_id"] for record in index["contracts"]}
    assert "preorder_risk_gate_auditor" in indexed_ids
    assert "preorder_risk_gate_auditor" in set(index["divisions"]["risk"])
    assert index["can_modify_runtime_all_false"] is True
    assert index["can_submit_orders_all_false"] is True

    valid_case = json.loads((root / "agent_contracts/eval_cases/risk/valid_preorder_risk_gate_auditor.json").read_text(encoding="utf-8"))
    blocked_case = json.loads((root / "agent_contracts/eval_cases/risk/preorder_risk_gate_missing_profile_hash.json").read_text(encoding="utf-8"))
    assert valid_case["agent_output"]["agent_id"] == "preorder_risk_gate_auditor"
    assert blocked_case["agent_output"]["agent_id"] == "preorder_risk_gate_auditor"

    report = build_agent_eval_report(root)
    assert report["passed"] is True
    case_ids = {record["eval_case_id"] for record in report["records"]}
    assert "valid_preorder_risk_gate_auditor" in case_ids
    assert "preorder_risk_gate_missing_profile_hash" in case_ids
