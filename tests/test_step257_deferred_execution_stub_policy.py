from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_step257_live_executor_is_disabled_compatibility_surface():
    live_executor = importlib.import_module("execution.live_executor")

    status = live_executor.compatibility_status()
    assert status["module"] == "execution.live_executor"
    assert status["compatibility_surface"] == "DISABLED_EXECUTION_COMPATIBILITY_SURFACE"
    assert status["disposition"] == "KEEP_EXPLICIT_LEGACY_COMPATIBILITY"
    assert status["port_to_canonical_allowed"] is False
    assert status["canonical_live_execution_port_allowed"] is False
    assert status["root_package_deletion_allowed"] is False
    assert status["live_trading_allowed_by_this_module"] is False
    assert status["order_routing_enabled_by_this_module"] is False
    assert status["external_order_submission_performed"] is False
    assert status["not_implemented_behavior_locked"] is True

    with pytest.raises(NotImplementedError, match="disabled compatibility surface"):
        live_executor.LiveExecutor().place_order({"intent_id": "live-intent-1"})


def test_step257_testnet_executor_default_skips_and_enabled_path_is_not_implemented(tmp_path, monkeypatch):
    testnet_executor = importlib.import_module("execution.testnet_executor")

    monkeypatch.setattr(testnet_executor, "TESTNET_ORDER_LOG_PATH", tmp_path / "testnet_order_log.jsonl")
    monkeypatch.setattr(testnet_executor, "ENABLE_TESTNET_ORDERS", False)

    status = testnet_executor.compatibility_status()
    assert status["module"] == "execution.testnet_executor"
    assert status["compatibility_surface"] == "DISABLED_EXECUTION_COMPATIBILITY_SURFACE"
    assert status["disposition"] == "KEEP_EXPLICIT_LEGACY_COMPATIBILITY"
    assert status["port_to_canonical_allowed"] is False
    assert status["canonical_testnet_execution_port_allowed"] is False
    assert status["root_package_deletion_allowed"] is False
    assert status["live_trading_allowed_by_this_module"] is False
    assert status["order_routing_enabled_by_this_module"] is False
    assert status["external_order_submission_performed"] is False
    assert status["skipped_behavior_supported"] is True
    assert status["not_implemented_behavior_locked"] is True

    skipped = testnet_executor.TestnetExecutor().place_order({"intent_id": "testnet-intent-1", "client_order_id": "cid-1"})
    assert skipped["status"] == "TESTNET_ORDER_SKIPPED"
    assert skipped["reason"] == "ENABLE_TESTNET_ORDERS_false"
    assert skipped["compatibility_surface"] == "DISABLED_EXECUTION_COMPATIBILITY_SURFACE"
    assert skipped["external_order_submission_performed"] is False
    assert (tmp_path / "testnet_order_log.jsonl").exists()

    monkeypatch.setattr(testnet_executor, "ENABLE_TESTNET_ORDERS", True)
    with pytest.raises(NotImplementedError, match="disabled compatibility surface"):
        testnet_executor.TestnetExecutor().place_order({"intent_id": "testnet-intent-2"})

    recovery = testnet_executor.TestnetExecutor().recover_unknown_order("cid-2")
    assert recovery["status"] == "RECOVERY_QUERY_NOT_IMPLEMENTED"
    assert recovery["external_order_submission_performed"] is False


def test_step257_never_ports_live_or_testnet_to_canonical_and_missing_count_stays_two():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "src" / "crypto_ai_system" / "execution" / "live_executor.py").exists()
    assert not (root / "src" / "crypto_ai_system" / "execution" / "testnet_executor.py").exists()

    sys.path.insert(0, str(root / "scripts"))
    from plan_thin_wrapper_conversion import build_thin_wrapper_conversion_plan

    plan = build_thin_wrapper_conversion_plan(root)
    missing_modules = sorted(
        row["legacy_module"]
        for row in plan["rows"]
        if row["recommended_action"] == "CANONICAL_MODULE_MISSING"
    )
    assert plan["canonical_module_missing_count"] == 2
    assert missing_modules == ["execution.live_executor", "execution.testnet_executor"]
    assert plan["root_package_deletion_performed"] is False


def test_step257_report_locks_deferred_execution_stub_policy(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "step257_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_step257_deferred_execution_stub_policy.py",
            "--output",
            str(output),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "DEFERRED_EXECUTION_STUB_POLICY_LOCKED"
    assert payload["deferred_modules"] == ["execution.live_executor", "execution.testnet_executor"]
    assert payload["missing_canonical_module_count_after"] == 2
    assert payload["missing_canonical_module_count_locked"] is True
    assert payload["missing_rows_are_exactly_deferred_execution_surfaces"] is True
    assert payload["canonical_live_execution_port_performed"] is False
    assert payload["canonical_testnet_execution_port_performed"] is False
    assert payload["canonical_files_absent"] is True
    assert payload["root_files_present"] is True
    assert payload["root_package_deletion_performed"] is False
    assert payload["root_package_deletion_deferred"] is True
    assert payload["wrapper_conversion_performed"] is False
    assert payload["port_performed"] is False
    assert payload["trading_execution_enabled"] is False
    assert payload["order_routing_enabled"] is False
    assert payload["live_trading_allowed"] is False
    assert payload["external_order_submission_performed"] is False
    assert payload["plain_checkout_policy"]["testnet_executor_self_contained_disabled_stub"] is True
    assert payload["plain_checkout_policy"]["plain_checkout_subprocess_import_test_added"] is True
    assert payload["dependency_policy"]["runtime_dependencies_declared_in_pyproject"] is True
    assert payload["dependency_policy"]["pytest_removed_from_runtime_requirements"] is True
    assert payload["dependency_policy"]["pytest_declared_as_dev_optional_dependency"] is True
    assert payload["packaging_policy"]["source_handoff_excludes_runtime_outputs"] is True
    assert payload["packaging_policy"]["validation_bundle_uses_distinct_root"] is True


def test_step257_testnet_executor_imports_from_plain_checkout_without_src_pythonpath(tmp_path):
    root = Path(__file__).resolve().parents[1]
    log_path = tmp_path / "plain_checkout_testnet_order_log.jsonl"
    env = dict(__import__("os").environ)
    env.pop("PYTHONPATH", None)

    script = f"""
import json
import sys
from pathlib import Path
assert not any(str(p).endswith('/src') or str(p).endswith('\\\\src') for p in sys.path if p)
import execution.testnet_executor as testnet_executor
testnet_executor.TESTNET_ORDER_LOG_PATH = Path({str(log_path)!r})
status = testnet_executor.compatibility_status()
result = testnet_executor.TestnetExecutor().recover_unknown_order('cid-plain-checkout')
print(json.dumps({{'module': status['module'], 'status': result['status'], 'policy_source': result['policy'].get('source')}}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload == {
        "module": "execution.testnet_executor",
        "status": "RECOVERY_QUERY_NOT_IMPLEMENTED",
        "policy_source": "local_disabled_testnet_stub_policy",
    }
    assert log_path.exists()


def test_step257_runtime_dependencies_are_declared_in_pyproject_and_pytest_is_dev_only():
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    requirements = (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
    requirements_dev = (root / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()

    runtime_requirement_names = [line.split(">=")[0].strip() for line in requirements if line.strip() and not line.startswith("#")]
    assert "pytest" not in runtime_requirement_names
    assert "pytest>=8.0,<9.0" in requirements_dev

    for package_name in runtime_requirement_names:
        assert package_name in pyproject
    assert "pytest>=8.0,<9.0" in pyproject
    assert "[project.optional-dependencies]" in pyproject
    assert "dev = [" in pyproject


def test_step257_source_and_validation_package_roots_are_separated(tmp_path):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    from build_source_package import build_source_package
    from build_audit_bundle import build_audit_bundle

    source_zip = tmp_path / "source.zip"
    validation_zip = tmp_path / "validation.zip"
    build_source_package(root, source_zip)
    build_audit_bundle(root, validation_zip)

    import zipfile

    with zipfile.ZipFile(source_zip) as zf:
        names = zf.namelist()
    assert names
    assert all(name.startswith("crypto_ai_system_source/") for name in names)
    assert not any(name.startswith("crypto_ai_system_source/data/reports/") for name in names)
    assert not any(name.startswith("crypto_ai_system_source/storage/latest/") for name in names)
    assert not any(name.startswith("crypto_ai_system_source/storage/logs/") for name in names)

    with zipfile.ZipFile(validation_zip) as zf:
        names = zf.namelist()
    assert names
    assert all(name.startswith("crypto_ai_system_validation/") for name in names)
    assert any(name.startswith("crypto_ai_system_validation/data/reports/") for name in names)
