from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.agents.contract_loader import load_agent_contracts, validate_agent_contracts
from crypto_ai_system.registry.agent_contract_registry import build_agent_contract_index

EXPECTED_STEP328_AGENTS = {
    "preorder_risk_gate_auditor": "risk",
    "research_signal_builder": "research",
    "research_signal_qa_agent": "research",
    "signal_drift_detector": "research",
    "trading_decision_reviewer": "trading",
    "price_structure_reviewer": "trading",
    "permission_boundary_auditor": "trading",
    "paper_execution_auditor": "execution",
    "reconciliation_auditor": "execution",
    "order_intent_chain_validator": "execution",
    "outcome_feedback_analyst": "feedback",
    "performance_report_builder": "feedback",
    "candidate_profile_reviewer": "feedback",
    "evidence_collector": "qa",
    "regression_runtime_hygiene_agent": "qa",
    "export_packet_agent": "approval",
}

REQUIRED_DIVISIONS = {"approval", "risk", "qa", "research", "trading", "execution", "feedback"}


def test_step328_full_agent_contracts_exist_with_safe_permissions() -> None:
    root = Path.cwd()
    contracts, errors = validate_agent_contracts(root)
    assert not errors
    by_id = {contract.agent_id: contract for contract in contracts}

    for agent_id, division in EXPECTED_STEP328_AGENTS.items():
        assert agent_id in by_id
        contract = by_id[agent_id]
        assert contract.division == division
        assert contract.frontmatter["requires_evidence"] is True
        assert contract.frontmatter["can_modify_runtime"] is False
        assert contract.frontmatter["can_submit_orders"] is False
        eval_case_path = contract.frontmatter.get("eval_case_path")
        assert isinstance(eval_case_path, str) and eval_case_path.endswith(".json")
        assert (root / eval_case_path).exists()
        assert "runtime_mutation_performed=false" in contract.body
        assert "order_submission_performed=false" in contract.body
        assert "blocked=true" in contract.body
        assert "fail_closed=true" in contract.body


def test_step328_agent_index_has_required_divisions_and_review_only_flags() -> None:
    index = build_agent_contract_index(project_root=Path.cwd())

    assert index["status"] == "AGENT_CONTRACT_INDEX_REVIEW_ONLY_RECORDED"
    assert index["review_only"] is True
    assert index["runtime_permission_source"] is False
    assert index["runtime_settings_mutated"] is False
    assert index["score_weights_mutated"] is False
    assert index["order_submission_performed"] is False
    assert index["auto_promotion_allowed"] is False
    assert index["can_modify_runtime_all_false"] is True
    assert index["can_submit_orders_all_false"] is True
    assert REQUIRED_DIVISIONS.issubset(set(index["divisions"].keys()))

    indexed_ids = {record["agent_id"] for record in index["contracts"]}
    assert set(EXPECTED_STEP328_AGENTS).issubset(indexed_ids)


def test_step328_eval_cases_cover_new_role_separated_agents() -> None:
    root = Path.cwd()
    eval_case_paths = sorted((root / "agent_contracts" / "eval_cases").rglob("valid_*.json"))
    eval_agent_ids = set()
    for path in eval_case_paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        eval_agent_ids.add(data["agent_output"]["agent_id"])

    assert set(EXPECTED_STEP328_AGENTS).issubset(eval_agent_ids)
