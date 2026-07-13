from __future__ import annotations

from pathlib import Path

from scripts.status_consistency_checker import (
    AGENT_LIBRARY_DOC_WORDING,
    AGENT_LIBRARY_REQUIRED_PATHS,
    AGENT_LIBRARY_WORKFLOW_COMMANDS,
    EXPECTED_STEP,
    validate_status_consistency,
)


def test_step327_status_checker_requires_agent_library_ci_and_docs() -> None:
    root = Path.cwd()
    workflow = (root / ".github/workflows/review_only_chain_validation.yml").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    master_context = (root / "CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md").read_text(encoding="utf-8")

    assert EXPECTED_STEP == "P70"
    assert "P70 Venue-neutral Execution Contract" in readme.splitlines()[0]
    for command in AGENT_LIBRARY_WORKFLOW_COMMANDS:
        assert command in workflow
    for wording in AGENT_LIBRARY_DOC_WORDING:
        assert wording in readme
        assert wording in master_context
    for rel_path in AGENT_LIBRARY_REQUIRED_PATHS:
        assert (root / rel_path).exists(), rel_path


def test_step327_status_consistency_checker_passes_with_agent_library_sync() -> None:
    result = validate_status_consistency(Path.cwd())

    assert result.passed, result.failed_checks
    assert not result.failed_checks
    assert result.details["readme_title"].startswith("# Crypto AI System — P70")
    assert result.details["settings_project_version"] == "p70_venue_neutral_execution_contract"
    assert all(value is False for value in result.details["runtime_flags"].values())
