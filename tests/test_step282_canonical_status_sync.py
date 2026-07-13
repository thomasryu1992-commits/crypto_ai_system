from __future__ import annotations

from pathlib import Path

import yaml

from scripts.status_consistency_checker import validate_status_consistency


def test_step282_status_consistency_checker_passes() -> None:
    result = validate_status_consistency(Path("."))

    assert result.passed is True, result.failed_checks
    assert result.details["settings_project_version"] == "p70_venue_neutral_execution_contract"
    assert result.details["pyproject_version"] == "0.286.2"


def test_step282_readme_current_title_and_status_are_not_stale() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    first_line = readme.splitlines()[0]

    assert "P70 Venue-neutral Execution Contract" in first_line
    assert "Step273 Signed Testnet Adapter Contract Preflight" not in first_line
    assert "Current project version: `p70_venue_neutral_execution_contract`" in readme
    assert "Signed testnet execution: disabled" in readme
    assert "Live order execution: disabled" in readme
    assert "Runtime settings mutation: disabled" in readme


def test_step282_settings_safety_invariants_remain_disabled() -> None:
    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    execution = settings["execution"]
    explicit = execution["explicit_signed_testnet_execution_approval_packet"]

    assert settings["project"]["version"] == "p70_venue_neutral_execution_contract"
    assert settings["safety"]["live_trading_enabled"] is False
    assert settings["safety"]["testnet_signed_order_enabled"] is False
    assert explicit["ready_for_signed_testnet_execution"] is False
    assert explicit["testnet_order_submission_allowed"] is False
    assert explicit["external_order_submission_allowed"] is False
    assert explicit["external_order_submission_performed"] is False
    assert explicit["place_order_enabled"] is False
    assert explicit["cancel_order_enabled"] is False
    assert explicit["signed_order_executor_enabled"] is False
