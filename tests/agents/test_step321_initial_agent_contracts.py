from __future__ import annotations

from pathlib import Path

from crypto_ai_system.agents.contract_loader import load_agent_contracts, validate_agent_contracts, validate_permission_policies

EXPECTED_INITIAL_AGENTS = {
    "approval_intake_validator",
    "signed_testnet_unlock_preview_agent",
    "kill_switch_auditor",
    "hard_cap_reviewer",
    "artifact_integrity_auditor",
}


def test_step321_initial_agent_contract_files_exist() -> None:
    root = Path.cwd()
    contracts = load_agent_contracts(root)
    agent_ids = {contract.agent_id for contract in contracts}

    assert EXPECTED_INITIAL_AGENTS.issubset(agent_ids)
    assert (root / "agents" / "approval" / "approval_intake_validator.md").exists()
    assert (root / "agents" / "approval" / "signed_testnet_unlock_preview_agent.md").exists()
    assert (root / "agents" / "risk" / "kill_switch_auditor.md").exists()
    assert (root / "agents" / "risk" / "hard_cap_reviewer.md").exists()
    assert (root / "agents" / "qa" / "artifact_integrity_auditor.md").exists()


def test_step321_initial_agent_contract_frontmatter_is_safe() -> None:
    contracts = load_agent_contracts(Path.cwd())
    selected = [contract for contract in contracts if contract.agent_id in EXPECTED_INITIAL_AGENTS]

    assert len(selected) == len(EXPECTED_INITIAL_AGENTS)
    for contract in selected:
        assert contract.frontmatter["requires_evidence"] is True
        assert contract.frontmatter["can_modify_runtime"] is False
        assert contract.frontmatter["can_submit_orders"] is False
        assert contract.frontmatter["output_schema"].endswith(".schema.json")
        assert contract.frontmatter["permission_tier"] in {"read_only", "approval_required"}


def test_step321_initial_agent_contracts_pass_lint_rules() -> None:
    contracts, errors = validate_agent_contracts(Path.cwd())

    assert {contract.agent_id for contract in contracts}.issuperset(EXPECTED_INITIAL_AGENTS)
    assert errors == []


def test_step321_permission_policy_files_exist_and_block_runtime_actions() -> None:
    errors = validate_permission_policies(Path.cwd())

    assert errors == []
    for name in ["read_only", "paper_only", "approval_required", "prohibited_actions"]:
        assert (Path.cwd() / "agent_contracts" / "permissions" / f"{name}.yaml").exists()


def test_step321_signed_testnet_preview_contract_keeps_execution_flags_disabled() -> None:
    contract = next(contract for contract in load_agent_contracts(Path.cwd()) if contract.agent_id == "signed_testnet_unlock_preview_agent")
    body = contract.body

    assert "ready_for_signed_testnet_execution=false" in body
    assert "testnet_order_submission_allowed=false" in body
    assert "place_order_enabled=false" in body
    assert "cancel_order_enabled=false" in body
    assert "signed_order_executor_enabled=false" in body
    assert "cannot unlock execution" in body.lower()
