from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml


def test_step280_versions_and_config_safety_flags():
    root = Path(__file__).resolve().parents[1]
    pyproject = root / "pyproject.toml"
    settings = yaml.safe_load((root / "config" / "settings.yaml").read_text(encoding="utf-8"))

    assert 'version = "0.286.2"' in pyproject.read_text(encoding="utf-8")
    assert settings["project"]["version"] == "p70_venue_neutral_execution_contract"

    hygiene = settings["validation"]["full_regression_runtime_hygiene"]
    assert hygiene["step"] == 280
    assert hygiene["single_pytest_tests_command_replaced_in_ci"] is True
    assert hygiene["full_pytest_completed_green_required_before_signed_testnet_execution"] is True
    assert hygiene["live_trading_enabled"] is False
    assert hygiene["testnet_order_submission_allowed"] is False
    assert hygiene["external_order_submission_allowed"] is False
    assert hygiene["settings_write_enabled"] is False
    assert hygiene["score_weights_mutation_allowed"] is False


def test_step280_chunked_regression_runner_lists_all_test_files():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/run_step280_full_regression.py", "--list"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    suites = json.loads(result.stdout)
    files = {file for suite in suites for file in suite["files"]}
    expected = {path.relative_to(root).as_posix() for path in sorted((root / "tests").glob("test_*.py"))}
    assert expected <= files
    assert "tests/test_step286_researchsignal_lineage_fix.py" in files
    assert "tests/test_step290_legacy_signal_fallback_blocker.py" in files
    assert any(suite["name"] == "data_id_reconciliation_testnet_prep_status_lineage_270_286" for suite in suites)


def test_step280_workflow_uses_chunked_runner_instead_of_single_pytest_tests():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "review_only_chain_validation.yml").read_text(encoding="utf-8")
    assert "python scripts/run_step280_full_regression.py --durations 10" in workflow
    assert "python -m pytest -q tests\n" not in workflow
    assert "Step258-282 and Step286 focused regression" in workflow
    assert "tests/test_step280_*.py tests/test_step281_*.py tests/test_step282_*.py tests/test_step286_*.py" in workflow
    assert "tests/test_step290_*.py" in workflow


def test_step280_research_decision_ignores_unrelated_latest_signal_permission(tmp_path, monkeypatch):
    import crypto_ai_system.research.decision_engine as decision_engine

    research_path = tmp_path / "research_result.json"
    signal_path = tmp_path / "latest_research_signal.json"
    decision_path = tmp_path / "research_decision.json"

    research_path.write_text(
        json.dumps(
            {
                "scenario": "Constructive",
                "signal_quality": "B",
                "signal_timing": "Early",
                "scores": {"final_score": 62, "positives": ["constructive"], "risks": []},
            }
        ),
        encoding="utf-8",
    )
    signal_path.write_text(
        json.dumps(
            {
                "research_signal_id": "unrelated_latest_signal",
                "trade_permission": {
                    "allow_long": False,
                    "allow_short": False,
                    "allow_new_position": False,
                    "risk_level": "blocked",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(decision_engine, "RESEARCH_RESULT_PATH", research_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_SIGNAL_PATH", signal_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_DECISION_PATH", decision_path)

    decision = decision_engine.run_research_decision()
    assert decision["allow_long"] is False
    assert decision["allow_new_position"] is False
    assert decision["risk_level"] == "blocked"
    assert decision["signal_permission_authoritative"] is False
    assert decision["legacy_signal_fallback_blocker_blocks_decision"] is True


def test_step280_research_decision_uses_matching_signal_permission(tmp_path, monkeypatch):
    import crypto_ai_system.research.decision_engine as decision_engine

    research_path = tmp_path / "research_result.json"
    signal_path = tmp_path / "matching_research_signal.json"
    qa_path = tmp_path / "matching_signal_qa.json"
    decision_path = tmp_path / "research_decision.json"

    research_path.write_text(
        json.dumps(
            {
                "research_signal_id": "matching_signal",
                "scenario": "Constructive",
                "signal_timing": "Early",
                "scores": {"final_score": 62},
            }
        ),
        encoding="utf-8",
    )
    signal_path.write_text(
        json.dumps(
            {
                "research_signal_id": "matching_signal",
                "profile_id": "profile_a",
                "trade_permission": {
                    "allow_long": False,
                    "allow_short": False,
                    "allow_new_position": False,
                    "risk_level": "blocked",
                },
            }
        ),
        encoding="utf-8",
    )
    qa_path.write_text(
        json.dumps(
            {
                "signal_qa_report_id": "matching_qa",
                "research_signal_id": "matching_signal",
                "signal_qa_result": "PASS_REVIEW_ONLY",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(decision_engine, "RESEARCH_RESULT_PATH", research_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_SIGNAL_PATH", signal_path)
    monkeypatch.setattr(decision_engine, "SIGNAL_QA_REPORT_PATH", qa_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_DECISION_PATH", decision_path)

    decision = decision_engine.run_research_decision()
    assert decision["allow_long"] is False
    assert decision["allow_new_position"] is False
    assert decision["profile_id"] == "profile_a"
    assert decision["signal_permission_authoritative"] is True
