from __future__ import annotations

import ast
import importlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

STEP_BOOTSTRAP_STATUS_OK = "STEP209_237_V5_CHAIN_BOOTSTRAP_OK"
STEP_BOOTSTRAP_STATUS_FAILED = "STEP209_237_V5_CHAIN_BOOTSTRAP_FAILED"
STEP_BOOTSTRAP_VALIDATION_OK = "STEP209_237_V5_CHAIN_BOOTSTRAP_VALIDATION_OK"
BOOTSTRAP_SCOPE = "STEP209_237_CHAIN_ARTIFACT_GENERATION_VALIDATION"
EXPECTED_RUNNER_COUNT = 29


@dataclass(frozen=True)
class StepRunnerSpec:
    step: int
    script: str
    success_token: str


STEP209_237_RUNNERS: List[StepRunnerSpec] = [
    StepRunnerSpec(209, "run_step209_v5_paper_observation_queue.py", "STEP209_V5_PAPER_OBSERVATION_QUEUE_OK"),
    StepRunnerSpec(210, "run_step210_v5_paper_signal_replay.py", "STEP210_V5_PAPER_SIGNAL_REPLAY_OK"),
    StepRunnerSpec(211, "run_step211_v5_paper_execution_dry_run_bridge.py", "STEP211_V5_PAPER_EXECUTION_DRY_RUN_BRIDGE_OK"),
    StepRunnerSpec(212, "run_step212_v5_simulated_paper_order_lifecycle.py", "STEP212_V5_SIMULATED_PAPER_ORDER_LIFECYCLE_OK"),
    StepRunnerSpec(213, "run_step213_v5_paper_lifecycle_outcome_store.py", "STEP213_V5_PAPER_LIFECYCLE_OUTCOME_STORE_OK"),
    StepRunnerSpec(214, "run_step214_v5_paper_feedback_integration_report.py", "STEP214_V5_PAPER_FEEDBACK_INTEGRATION_REPORT_OK"),
    StepRunnerSpec(215, "run_step215_v5_promotion_gate_v2_review_only.py", "STEP215_V5_PROMOTION_GATE_V2_REVIEW_ONLY_OK"),
    StepRunnerSpec(216, "run_step216_v5_paper_execution_upgrade_readiness_review.py", "STEP216_V5_PAPER_EXECUTION_UPGRADE_READINESS_REVIEW_ONLY_OK"),
    StepRunnerSpec(217, "run_step217_v5_operator_approval_packet_review.py", "STEP217_V5_OPERATOR_APPROVAL_PACKET_REVIEW_ONLY_OK"),
    StepRunnerSpec(218, "run_step218_v5_operator_approval_intake_stub.py", "STEP218_V5_OPERATOR_APPROVAL_INTAKE_STUB_OK"),
    StepRunnerSpec(219, "run_step219_v5_operator_approval_intake_validator.py", "STEP219_V5_OPERATOR_APPROVAL_INTAKE_VALIDATOR_OK"),
    StepRunnerSpec(220, "run_step220_v5_paper_execution_enablement_plan_review_only.py", "STEP220_V5_PAPER_EXECUTION_ENABLEMENT_PLAN_REVIEW_ONLY_OK"),
    StepRunnerSpec(221, "run_step221_v5_dry_run_paper_execution_config_review.py", "STEP221_V5_DRY_RUN_PAPER_EXECUTION_CONFIG_REVIEW_ONLY_OK"),
    StepRunnerSpec(222, "run_step222_v5_dry_run_config_apply_validator_review_only.py", "STEP222_V5_DRY_RUN_CONFIG_APPLY_VALIDATOR_REVIEW_ONLY_OK"),
    StepRunnerSpec(223, "run_step223_v5_controlled_config_activation_review_only.py", "STEP223_V5_CONTROLLED_CONFIG_ACTIVATION_REVIEW_ONLY_OK"),
    StepRunnerSpec(224, "run_step224_v5_config_activation_apply_stub_review_only.py", "STEP224_V5_CONFIG_ACTIVATION_APPLY_STUB_REVIEW_ONLY_OK"),
    StepRunnerSpec(225, "run_step225_v5_final_config_apply_gate_review_only.py", "STEP225_V5_FINAL_CONFIG_APPLY_GATE_REVIEW_ONLY_OK"),
    StepRunnerSpec(226, "run_step226_v5_paper_execution_mode_shadow_ready_review.py", "STEP226_V5_PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW_ONLY_OK"),
    StepRunnerSpec(227, "run_step227_v5_paper_execution_mode_pre_enablement_audit_review.py", "STEP227_V5_PAPER_EXECUTION_MODE_PRE_ENABLEMENT_AUDIT_REVIEW_ONLY_OK"),
    StepRunnerSpec(228, "run_step228_v5_paper_execution_enablement_request_stub_review.py", "STEP228_V5_PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB_REVIEW_ONLY_OK"),
    StepRunnerSpec(229, "run_step229_v5_paper_execution_enablement_request_final_validator_review.py", "STEP229_V5_PAPER_EXECUTION_ENABLEMENT_REQUEST_FINAL_VALIDATOR_REVIEW_ONLY_OK"),
    StepRunnerSpec(230, "run_step230_v5_operator_final_enablement_approval_stub_review.py", "STEP230_V5_OPERATOR_FINAL_ENABLEMENT_APPROVAL_STUB_REVIEW_ONLY_OK"),
    StepRunnerSpec(231, "run_step231_v5_operator_final_approval_intake_validator_review.py", "STEP231_V5_OPERATOR_FINAL_APPROVAL_INTAKE_VALIDATOR_REVIEW_ONLY_OK"),
    StepRunnerSpec(232, "run_step232_v5_approval_to_enablement_bridge_review.py", "STEP232_V5_APPROVAL_TO_ENABLEMENT_BRIDGE_REVIEW_ONLY_OK"),
    StepRunnerSpec(233, "run_step233_v5_enablement_pre_submit_review.py", "STEP233_V5_ENABLEMENT_PRE_SUBMIT_REVIEW_ONLY_OK"),
    StepRunnerSpec(234, "run_step234_v5_enablement_submit_decision_stub_review.py", "STEP234_V5_ENABLEMENT_SUBMIT_DECISION_STUB_REVIEW_ONLY_OK"),
    StepRunnerSpec(235, "run_step235_v5_enablement_submit_decision_intake_validator_review.py", "STEP235_V5_ENABLEMENT_SUBMIT_DECISION_INTAKE_VALIDATOR_REVIEW_ONLY_OK"),
    StepRunnerSpec(236, "run_step236_v5_enablement_submit_gate_review.py", "STEP236_V5_ENABLEMENT_SUBMIT_GATE_REVIEW_ONLY_OK"),
    StepRunnerSpec(237, "run_step237_v5_enablement_submit_dry_run_review.py", "STEP237_V5_ENABLEMENT_SUBMIT_DRY_RUN_REVIEW_ONLY_OK"),
]


@dataclass
class StepBootstrapResult:
    status: str
    root: str
    bootstrap_scope: str
    runner_count_expected: int
    runner_count_found: int
    runner_count_executed: int
    runner_count_passed: int
    runner_count_failed: int
    all_runners_present: bool
    all_runners_passed: bool
    chain_artifact_generation_validation_passed: bool
    operating_validation_passed: bool
    production_live_trading_validation_performed: bool
    live_trading_allowed: bool
    external_api_call_required: bool
    fail_fast: bool
    result_path: str
    jsonl_path: str
    markdown_report_path: str
    missing_runners: List[str]
    failed_steps: List[int]
    runner_results: List[Dict[str, object]]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class StepBootstrapValidationResult:
    status: str
    result_path: str
    expected_runner_count: int
    actual_runner_count: int
    all_runners_present: bool
    all_runners_passed: bool
    chain_artifact_generation_validation_passed: bool
    operating_validation_passed: bool
    production_live_trading_validation_performed: bool
    live_trading_allowed: bool
    blocking_failure_count: int
    blocking_failures: List[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf-8")


def _tail(text: str, limit: int = 4000) -> str:
    return text[-limit:] if len(text) > limit else text


def _discover_runner_callables(root: Path, spec: StepRunnerSpec) -> Dict[str, str]:
    script_path = root / spec.script
    tree = ast.parse(script_path.read_text(encoding="utf-8"))
    discovered: Dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module or not node.module.startswith("crypto_ai_system."):
            continue
        imported_names = [alias.name for alias in node.names]
        execute_names = [name for name in imported_names if name.startswith("execute_")]
        validate_names = [name for name in imported_names if name.startswith("validate_")]
        status_names = [name for name in imported_names if name.startswith("STEP") and name.endswith("STATUS_OK")]
        validation_names = [name for name in imported_names if name.startswith("STEP") and name.endswith("VALIDATION_OK")]
        if execute_names and validate_names and status_names and validation_names:
            discovered = {
                "module": node.module,
                "execute_function": execute_names[0],
                "validate_function": validate_names[0],
                "status_constant": status_names[0],
                "validation_constant": validation_names[0],
            }
            break
    if not discovered:
        raise RuntimeError(f"Could not discover runner callables from {spec.script}")
    return discovered


def _execute_runner_in_process(root: Path, spec: StepRunnerSpec) -> Dict[str, object]:
    started = time.monotonic()
    discovered = _discover_runner_callables(root, spec)
    module = importlib.import_module(discovered["module"])
    execute_fn = getattr(module, discovered["execute_function"])
    validate_fn = getattr(module, discovered["validate_function"])
    expected_status = getattr(module, discovered["status_constant"])
    expected_validation_status = getattr(module, discovered["validation_constant"])

    result = execute_fn(root, write_output=True)
    validation = validate_fn(root)
    result_status = getattr(result, "status", None)
    validation_status = getattr(validation, "status", None)
    passed = result_status == expected_status and validation_status == expected_validation_status
    elapsed = round(time.monotonic() - started, 4)
    return {
        "step": spec.step,
        "script": spec.script,
        "module": discovered["module"],
        "execute_function": discovered["execute_function"],
        "validate_function": discovered["validate_function"],
        "expected_status": expected_status,
        "actual_status": result_status,
        "expected_validation_status": expected_validation_status,
        "actual_validation_status": validation_status,
        "success_token": spec.success_token,
        "success_token_found": passed,
        "returncode": 0 if passed else 1,
        "status": "PASS" if passed else "FAIL",
        "elapsed_seconds": elapsed,
        "stdout_tail": f"{spec.success_token}\nresult_status: {result_status}\nvalidation_status: {validation_status}",
        "stderr_tail": "",
    }


def validate_runner_inventory(root: Path) -> Dict[str, object]:
    missing = [spec.script for spec in STEP209_237_RUNNERS if not (root / spec.script).exists()]
    return {
        "expected_runner_count": EXPECTED_RUNNER_COUNT,
        "actual_runner_count": len(STEP209_237_RUNNERS),
        "all_runners_present": not missing and len(STEP209_237_RUNNERS) == EXPECTED_RUNNER_COUNT,
        "missing_runners": missing,
        "steps": [spec.step for spec in STEP209_237_RUNNERS],
    }


def _write_markdown_report(path: Path, result: StepBootstrapResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Step209~237 Runner Bootstrap Report",
        "",
        f"- Status: `{result.status}`",
        f"- Scope: `{result.bootstrap_scope}`",
        "- Validation wording: `체인/산출물 생성 검증 통과`" if result.chain_artifact_generation_validation_passed else "- Validation wording: `체인/산출물 생성 검증 실패`",
        f"- Operating validation passed: `{result.operating_validation_passed}`",
        f"- Production/live trading validation performed: `{result.production_live_trading_validation_performed}`",
        f"- Live trading allowed: `{result.live_trading_allowed}`",
        f"- Runner files expected: `{result.runner_count_expected}`",
        f"- Runner files found: `{result.runner_count_found}`",
        f"- Runner files executed: `{result.runner_count_executed}`",
        f"- Runner files passed: `{result.runner_count_passed}`",
        f"- Runner files failed: `{result.runner_count_failed}`",
        "",
        "## Runner Results",
        "",
        "| Step | Script | Return code | Success token found | Status |",
        "|---:|---|---:|---|---|",
    ]
    for row in result.runner_results:
        lines.append(
            f"| {row['step']} | `{row['script']}` | `{row['returncode']}` | `{row['success_token_found']}` | `{row['status']}` |"
        )
    lines.extend([
        "",
        "## Scope Note",
        "",
        "This bootstrap validates the Step209~Step237 review-only chain and confirms that expected artifacts are generated by the runners. It does not validate live trading, exchange adapter routing, external API execution, production cutover, or real Telegram sends.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def execute_step209_237_chain_bootstrap(root: Path, write_output: bool = True, fail_fast: bool = True, timeout_seconds: int = 120) -> StepBootstrapResult:
    root = root.resolve()
    inventory = validate_runner_inventory(root)
    result_path = root / "storage/latest/step209_237_chain_bootstrap_latest.json"
    jsonl_path = root / "storage/logs/step209_237_chain_bootstrap_runs.jsonl"
    markdown_report_path = root / "reports/step209_237_chain_bootstrap_report.md"

    runner_results: List[Dict[str, object]] = []
    if not inventory["all_runners_present"]:
        failed_steps: List[int] = []
        result = StepBootstrapResult(
            status=STEP_BOOTSTRAP_STATUS_FAILED,
            root=str(root),
            bootstrap_scope=BOOTSTRAP_SCOPE,
            runner_count_expected=EXPECTED_RUNNER_COUNT,
            runner_count_found=len(STEP209_237_RUNNERS) - len(inventory["missing_runners"]),
            runner_count_executed=0,
            runner_count_passed=0,
            runner_count_failed=len(inventory["missing_runners"]),
            all_runners_present=False,
            all_runners_passed=False,
            chain_artifact_generation_validation_passed=False,
            operating_validation_passed=False,
            production_live_trading_validation_performed=False,
            live_trading_allowed=False,
            external_api_call_required=False,
            fail_fast=fail_fast,
            result_path=str(result_path),
            jsonl_path=str(jsonl_path),
            markdown_report_path=str(markdown_report_path),
            missing_runners=list(inventory["missing_runners"]),
            failed_steps=failed_steps,
            runner_results=runner_results,
        )
        if write_output:
            _write_json(result_path, result.to_dict())
            _write_jsonl(jsonl_path, runner_results)
            _write_markdown_report(markdown_report_path, result)
        return result

    for spec in STEP209_237_RUNNERS:
        try:
            row = _execute_runner_in_process(root, spec)
        except Exception as exc:  # noqa: BLE001 - bootstrap must record the failed step instead of hiding it.
            row = {
                "step": spec.step,
                "script": spec.script,
                "success_token": spec.success_token,
                "success_token_found": False,
                "returncode": 1,
                "status": "FAIL",
                "elapsed_seconds": 0.0,
                "stdout_tail": "",
                "stderr_tail": repr(exc),
            }
        runner_results.append(row)
        if fail_fast and row["status"] != "PASS":
            break

    failed_steps = [int(row["step"]) for row in runner_results if row["status"] != "PASS"]
    runner_count_passed = sum(1 for row in runner_results if row["status"] == "PASS")
    runner_count_failed = len(runner_results) - runner_count_passed
    all_passed = len(runner_results) == EXPECTED_RUNNER_COUNT and runner_count_failed == 0
    result = StepBootstrapResult(
        status=STEP_BOOTSTRAP_STATUS_OK if all_passed else STEP_BOOTSTRAP_STATUS_FAILED,
        root=str(root),
        bootstrap_scope=BOOTSTRAP_SCOPE,
        runner_count_expected=EXPECTED_RUNNER_COUNT,
        runner_count_found=len(STEP209_237_RUNNERS),
        runner_count_executed=len(runner_results),
        runner_count_passed=runner_count_passed,
        runner_count_failed=runner_count_failed,
        all_runners_present=True,
        all_runners_passed=all_passed,
        chain_artifact_generation_validation_passed=all_passed,
        operating_validation_passed=False,
        production_live_trading_validation_performed=False,
        live_trading_allowed=False,
        external_api_call_required=False,
        fail_fast=fail_fast,
        result_path=str(result_path),
        jsonl_path=str(jsonl_path),
        markdown_report_path=str(markdown_report_path),
        missing_runners=[],
        failed_steps=failed_steps,
        runner_results=runner_results,
    )
    if write_output:
        _write_json(result_path, result.to_dict())
        _write_jsonl(jsonl_path, runner_results)
        _write_markdown_report(markdown_report_path, result)
    return result


def validate_step209_237_chain_bootstrap(root: Path) -> StepBootstrapValidationResult:
    root = root.resolve()
    result_path = root / "storage/latest/step209_237_chain_bootstrap_latest.json"
    failures: List[str] = []
    if not result_path.exists():
        failures.append("STEP209_237_CHAIN_BOOTSTRAP_RESULT_MISSING")
        data: Dict[str, object] = {}
    else:
        data = json.loads(result_path.read_text(encoding="utf-8"))

    expected = EXPECTED_RUNNER_COUNT
    actual = int(data.get("runner_count_found", 0) or 0)
    if actual != expected:
        failures.append("STEP209_237_RUNNER_COUNT_MISMATCH")
    if data.get("all_runners_present") is not True:
        failures.append("STEP209_237_RUNNERS_NOT_ALL_PRESENT")
    if data.get("all_runners_passed") is not True:
        failures.append("STEP209_237_RUNNERS_NOT_ALL_PASSED")
    if data.get("chain_artifact_generation_validation_passed") is not True:
        failures.append("STEP209_237_CHAIN_ARTIFACT_GENERATION_VALIDATION_NOT_PASSED")
    if data.get("operating_validation_passed") is not False:
        failures.append("OPERATING_VALIDATION_SHOULD_NOT_BE_MARKED_PASSED")
    if data.get("production_live_trading_validation_performed") is not False:
        failures.append("PRODUCTION_LIVE_VALIDATION_SHOULD_NOT_BE_MARKED_PERFORMED")
    if data.get("live_trading_allowed") is not False:
        failures.append("LIVE_TRADING_SHOULD_REMAIN_DISABLED")

    return StepBootstrapValidationResult(
        status=STEP_BOOTSTRAP_VALIDATION_OK if not failures else STEP_BOOTSTRAP_STATUS_FAILED,
        result_path=str(result_path),
        expected_runner_count=expected,
        actual_runner_count=actual,
        all_runners_present=data.get("all_runners_present") is True,
        all_runners_passed=data.get("all_runners_passed") is True,
        chain_artifact_generation_validation_passed=data.get("chain_artifact_generation_validation_passed") is True,
        operating_validation_passed=data.get("operating_validation_passed") is True,
        production_live_trading_validation_performed=data.get("production_live_trading_validation_performed") is True,
        live_trading_allowed=data.get("live_trading_allowed") is True,
        blocking_failure_count=len(failures),
        blocking_failures=failures,
    )
