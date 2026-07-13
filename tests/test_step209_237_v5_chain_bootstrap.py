from pathlib import Path

from crypto_ai_system.runner.step209_237_chain_bootstrap import (
    BOOTSTRAP_SCOPE,
    EXPECTED_RUNNER_COUNT,
    STEP209_237_RUNNERS,
    STEP_BOOTSTRAP_STATUS_OK,
    STEP_BOOTSTRAP_VALIDATION_OK,
    execute_step209_237_chain_bootstrap,
    validate_runner_inventory,
    validate_step209_237_chain_bootstrap,
)


def test_step209_237_bootstrap_inventory_is_complete(isolated_project_root):
    root = isolated_project_root
    inventory = validate_runner_inventory(root)
    assert len(STEP209_237_RUNNERS) == EXPECTED_RUNNER_COUNT
    assert inventory["expected_runner_count"] == EXPECTED_RUNNER_COUNT
    assert inventory["actual_runner_count"] == EXPECTED_RUNNER_COUNT
    assert inventory["all_runners_present"] is True
    assert inventory["missing_runners"] == []
    assert inventory["steps"] == list(range(209, 238))


def test_step209_237_bootstrap_executes_review_only_chain(isolated_project_root):
    root = isolated_project_root
    result = execute_step209_237_chain_bootstrap(root, write_output=True, fail_fast=True, timeout_seconds=120)
    assert result.status == STEP_BOOTSTRAP_STATUS_OK
    assert result.bootstrap_scope == BOOTSTRAP_SCOPE
    assert result.runner_count_expected == EXPECTED_RUNNER_COUNT
    assert result.runner_count_executed == EXPECTED_RUNNER_COUNT
    assert result.runner_count_passed == EXPECTED_RUNNER_COUNT
    assert result.runner_count_failed == 0
    assert result.all_runners_present is True
    assert result.all_runners_passed is True
    assert result.chain_artifact_generation_validation_passed is True
    assert result.operating_validation_passed is False
    assert result.production_live_trading_validation_performed is False
    assert result.live_trading_allowed is False
    assert result.external_api_call_required is False
    assert all(row["status"] == "PASS" for row in result.runner_results)


def test_step209_237_bootstrap_validation_wording_and_scope(isolated_project_root):
    root = isolated_project_root
    execute_step209_237_chain_bootstrap(root, write_output=True, fail_fast=True, timeout_seconds=120)
    validation = validate_step209_237_chain_bootstrap(root)
    assert validation.status == STEP_BOOTSTRAP_VALIDATION_OK
    assert validation.expected_runner_count == EXPECTED_RUNNER_COUNT
    assert validation.actual_runner_count == EXPECTED_RUNNER_COUNT
    assert validation.all_runners_present is True
    assert validation.all_runners_passed is True
    assert validation.chain_artifact_generation_validation_passed is True
    assert validation.operating_validation_passed is False
    assert validation.production_live_trading_validation_performed is False
    assert validation.live_trading_allowed is False
    assert validation.blocking_failure_count == 0
