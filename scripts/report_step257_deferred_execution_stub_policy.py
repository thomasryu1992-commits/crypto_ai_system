from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from plan_legacy_root_import_retirement import build_import_retirement_plan
from plan_thin_wrapper_conversion import build_thin_wrapper_conversion_plan


DEFERRED_MODULES = ["execution.live_executor", "execution.testnet_executor"]


def _canonical_file_for(root: Path, legacy_module: str) -> Path:
    _, module_name = legacy_module.split(".", 1)
    return root / "src" / "crypto_ai_system" / "execution" / f"{module_name}.py"


def _root_file_for(root: Path, legacy_module: str) -> Path:
    return root / Path(*legacy_module.split(".")).with_suffix(".py")


def _module_status(module_name: str) -> dict:
    module = importlib.import_module(module_name)
    status_fn = getattr(module, "compatibility_status")
    return status_fn()


def _runtime_requirements(root: Path) -> list[str]:
    requirements_path = root / "requirements.txt"
    if not requirements_path.exists():
        return []
    return [
        line.strip()
        for line in requirements_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _dependency_policy(root: Path) -> dict:
    pyproject_text = (root / "pyproject.toml").read_text(encoding="utf-8")
    runtime_requirements = _runtime_requirements(root)
    runtime_names = [req.split(">=")[0].split("<")[0].split("=")[0].strip() for req in runtime_requirements]
    return {
        "runtime_dependencies_declared_in_pyproject": all(name in pyproject_text for name in runtime_names),
        "runtime_requirements": runtime_requirements,
        "pytest_removed_from_runtime_requirements": "pytest" not in runtime_names,
        "pytest_declared_as_dev_optional_dependency": "pytest>=8.0,<9.0" in pyproject_text
        and "[project.optional-dependencies]" in pyproject_text
        and "dev = [" in pyproject_text,
    }


def _packaging_policy(root: Path) -> dict:
    source_script = (root / "scripts" / "build_source_package.py").read_text(encoding="utf-8")
    validation_script = (root / "scripts" / "build_audit_bundle.py").read_text(encoding="utf-8")
    return {
        "source_handoff_root": "crypto_ai_system_source",
        "validation_bundle_root": "crypto_ai_system_validation",
        "source_handoff_excludes_runtime_outputs": (
            "data/reports" in source_script
            and ("storage/latest" in source_script or '"storage"' in source_script)
            and ("storage/logs" in source_script or '"storage"' in source_script)
        ),
        "validation_bundle_uses_distinct_root": "crypto_ai_system_validation" in validation_script,
        "validation_bundle_default_output": "dist/crypto_ai_system_validation_bundle.zip",
    }


def _plain_checkout_policy(root: Path) -> dict:
    testnet_source = (root / "execution" / "testnet_executor.py").read_text(encoding="utf-8")
    return {
        "testnet_executor_self_contained_disabled_stub": "from execution.retry_policy import" not in testnet_source
        and "from crypto_ai_system" not in testnet_source,
        "testnet_executor_uses_local_disabled_recovery_policy": "_classify_disabled_stub_recovery_policy" in testnet_source,
        "plain_checkout_subprocess_import_test_added": (root / "tests" / "test_step257_deferred_execution_stub_policy.py").read_text(encoding="utf-8").find("plain_checkout_without_src_pythonpath") >= 0,
    }


def build_step257_deferred_execution_stub_policy_report(root: Path) -> dict:
    for import_root in [root, root / "src"]:
        import_root_text = str(import_root)
        if import_root_text not in sys.path:
            sys.path.insert(0, import_root_text)

    import_plan = build_import_retirement_plan(root)
    wrapper_plan = build_thin_wrapper_conversion_plan(root)
    wrapper_rows = {row["legacy_module"]: row for row in wrapper_plan["rows"]}

    statuses = [_module_status(module_name) for module_name in DEFERRED_MODULES]
    dependency_policy = _dependency_policy(root)
    packaging_policy = _packaging_policy(root)
    plain_checkout_policy = _plain_checkout_policy(root)
    canonical_files = {module_name: _canonical_file_for(root, module_name) for module_name in DEFERRED_MODULES}
    root_files = {module_name: _root_file_for(root, module_name) for module_name in DEFERRED_MODULES}

    canonical_files_absent = all(not path.exists() for path in canonical_files.values())
    root_files_present = all(path.exists() for path in root_files.values())
    missing_rows_are_exactly_deferred = sorted(
        row["legacy_module"]
        for row in wrapper_plan["rows"]
        if row["recommended_action"] == "CANONICAL_MODULE_MISSING"
    ) == DEFERRED_MODULES

    policy_locked = all(
        status.get("compatibility_surface") == "DISABLED_EXECUTION_COMPATIBILITY_SURFACE"
        and status.get("disposition") == "KEEP_EXPLICIT_LEGACY_COMPATIBILITY"
        and status.get("port_to_canonical_allowed") is False
        and status.get("canonical_live_execution_port_allowed") is False
        and status.get("root_package_deletion_allowed") is False
        and status.get("live_trading_allowed_by_this_module") is False
        and status.get("order_routing_enabled_by_this_module") is False
        and status.get("external_order_submission_performed") is False
        and status.get("not_implemented_behavior_locked") is True
        for status in statuses
    )

    missing_count_is_locked = wrapper_plan["canonical_module_missing_count"] == 2
    status = (
        "DEFERRED_EXECUTION_STUB_POLICY_LOCKED"
        if canonical_files_absent
        and root_files_present
        and missing_rows_are_exactly_deferred
        and policy_locked
        and missing_count_is_locked
        and dependency_policy["runtime_dependencies_declared_in_pyproject"]
        and dependency_policy["pytest_removed_from_runtime_requirements"]
        and dependency_policy["pytest_declared_as_dev_optional_dependency"]
        and packaging_policy["source_handoff_excludes_runtime_outputs"]
        and packaging_policy["validation_bundle_uses_distinct_root"]
        and plain_checkout_policy["testnet_executor_self_contained_disabled_stub"]
        and plain_checkout_policy["plain_checkout_subprocess_import_test_added"]
        else "DEFERRED_EXECUTION_STUB_POLICY_REVIEW_REQUIRED"
    )

    return {
        "report_type": "step257_deferred_execution_stub_policy_report",
        "status": status,
        "deferred_modules": DEFERRED_MODULES,
        "direct_root_import_finding_count": import_plan["direct_root_import_finding_count"],
        "root_direct_imports_retired": import_plan["direct_root_import_finding_count"] == 0,
        "missing_canonical_module_count_after": wrapper_plan["canonical_module_missing_count"],
        "missing_canonical_module_count_locked": missing_count_is_locked,
        "missing_canonical_modules_after": sorted(
            row["legacy_module"]
            for row in wrapper_plan["rows"]
            if row["recommended_action"] == "CANONICAL_MODULE_MISSING"
        ),
        "missing_rows_are_exactly_deferred_execution_surfaces": missing_rows_are_exactly_deferred,
        "canonical_live_execution_port_performed": False,
        "canonical_testnet_execution_port_performed": False,
        "canonical_files_absent": canonical_files_absent,
        "canonical_files": {module: str(path.relative_to(root)) for module, path in canonical_files.items()},
        "root_files_present": root_files_present,
        "root_files": {module: str(path.relative_to(root)) for module, path in root_files.items()},
        "root_package_deletion_performed": False,
        "root_package_deletion_deferred": True,
        "wrapper_conversion_performed": False,
        "port_performed": False,
        "trading_execution_enabled": False,
        "order_routing_enabled": False,
        "live_trading_allowed": False,
        "external_order_submission_performed": False,
        "plain_checkout_policy": plain_checkout_policy,
        "dependency_policy": dependency_policy,
        "packaging_policy": packaging_policy,
        "compatibility_statuses": statuses,
        "wrapper_rows_for_deferred_modules": {module: wrapper_rows.get(module) for module in DEFERRED_MODULES},
        "locked_behaviors": {
            "execution.live_executor.place_order": "raises NotImplementedError",
            "execution.testnet_executor.place_order_default": "returns TESTNET_ORDER_SKIPPED and appends local audit JSONL",
            "execution.testnet_executor.place_order_when_enabled": "raises NotImplementedError",
            "execution.testnet_executor.recover_unknown_order": "returns RECOVERY_QUERY_NOT_IMPLEMENTED and appends local audit JSONL",
        },
        "next_step": {
            "name": "Step258 v5 Feature Store / ResearchSignal v2 Integration",
            "goal": "Continue live-readiness work by connecting additional data features and ResearchSignal v2 gates while root execution package deletion remains postponed.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step257 deferred execution stub policy report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default="data/reports/step257_deferred_execution_stub_policy_report.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    report = build_step257_deferred_execution_stub_policy_report(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "missing_canonical_module_count_after": report["missing_canonical_module_count_after"],
        "missing_canonical_module_count_locked": report["missing_canonical_module_count_locked"],
        "deferred_modules": report["deferred_modules"],
        "canonical_files_absent": report["canonical_files_absent"],
        "root_package_deletion_deferred": report["root_package_deletion_deferred"],
        "external_order_submission_performed": report["external_order_submission_performed"],
        "testnet_plain_checkout_safe": report["plain_checkout_policy"]["testnet_executor_self_contained_disabled_stub"],
        "runtime_dependencies_declared_in_pyproject": report["dependency_policy"]["runtime_dependencies_declared_in_pyproject"],
        "validation_bundle_uses_distinct_root": report["packaging_policy"]["validation_bundle_uses_distinct_root"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
