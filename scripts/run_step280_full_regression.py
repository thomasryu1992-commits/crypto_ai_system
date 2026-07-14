#!/usr/bin/env python3
"""Step280 chunked full regression runner.

The historical single `pytest -q tests` command can be hard to observe in
short-lived CI/sandbox sessions because many review-only tests generate reports
and several canonical-port report tests scan the repository. This runner keeps
full regression semantics while emitting progress per suite, recording timings,
and preserving the safety posture: it only runs tests and never enables
execution/testnet/live paths.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "reports" / "step280_full_regression_runtime_hygiene_report.json"

STEP280_FULL_REGRESSION_SUITES: list[dict[str, object]] = [
    {
        "name": "base_safety_data_research",
        "patterns": [
            "tests/test_step130_*.py",
            "tests/test_step150_*.py",
            "tests/test_step158_*.py",
            "tests/test_step159_*.py",
            "tests/test_step161_*.py",
            "tests/test_step162_*.py",
            "tests/test_step163_*.py",
            "tests/test_step164_*.py",
            "tests/test_step209_237_*.py",
            "tests/test_step209_v5_*.py",
            "tests/test_step210_*.py",
        ],
    },
    {
        "name": "paper_lifecycle_feedback_chain_211_220",
        "patterns": [
            "tests/test_step211_*.py",
            "tests/test_step212_*.py",
            "tests/test_step213_*.py",
            "tests/test_step214_*.py",
            "tests/test_step215_*.py",
            "tests/test_step216_*.py",
            "tests/test_step217_*.py",
            "tests/test_step218_*.py",
            "tests/test_step219_*.py",
            "tests/test_step220_*.py",
        ],
    },
    {
        "name": "paper_enablement_chain_221_230",
        "patterns": [
            "tests/test_step221_*.py",
            "tests/test_step222_*.py",
            "tests/test_step223_*.py",
            "tests/test_step224_*.py",
            "tests/test_step225_*.py",
            "tests/test_step226_*.py",
            "tests/test_step227_*.py",
            "tests/test_step228_*.py",
            "tests/test_step229_*.py",
            "tests/test_step230_*.py",
        ],
    },
    {
        "name": "approval_enablement_and_legacy_boundary_231_240",
        "patterns": [
            "tests/test_step231_*.py",
            "tests/test_step232_*.py",
            "tests/test_step233_*.py",
            "tests/test_step234_*.py",
            "tests/test_step235_*.py",
            "tests/test_step236_*.py",
            "tests/test_step237_*.py",
            "tests/test_step239_*.py",
            "tests/test_step240_*.py",
        ],
    },
    {
        "name": "canonical_port_reports_241_250",
        "patterns": [
            "tests/test_step241_*.py",
            "tests/test_step242_*.py",
            "tests/test_step243_*.py",
            "tests/test_step244_*.py",
            "tests/test_step245_*.py",
            "tests/test_step246_*.py",
            "tests/test_step247_*.py",
            "tests/test_step248_*.py",
            "tests/test_step249_*.py",
            "tests/test_step250_*.py",
        ],
    },
    {
        "name": "canonical_port_and_profile_chain_251_260",
        "patterns": [
            "tests/test_step251_*.py",
            "tests/test_step252_*.py",
            "tests/test_step253_*.py",
            "tests/test_step254_*.py",
            "tests/test_step255_*.py",
            "tests/test_step256_*.py",
            "tests/test_step257_*.py",
            "tests/test_step258_*.py",
            "tests/test_step259_*.py",
            "tests/test_step260_*.py",
        ],
    },
    {
        "name": "approval_settings_audit_chain_261_269",
        "patterns": [
            "tests/test_step261_*.py",
            "tests/test_step262_*.py",
            "tests/test_step263_*.py",
            "tests/test_step264_*.py",
            "tests/test_step265_*.py",
            "tests/test_step266_*.py",
            "tests/test_step267_*.py",
            "tests/test_step268_*.py",
            "tests/test_step269_*.py",
        ],
    },
    {
        "name": "data_id_reconciliation_testnet_prep_status_lineage_270_286",
        "patterns": [
            "tests/test_step270_*.py",
            "tests/test_step271_*.py",
            "tests/test_step272_*.py",
            "tests/test_step273_*.py",
            "tests/test_step274_*.py",
            "tests/test_step275_*.py",
            "tests/test_step276_*.py",
            "tests/test_step277_*.py",
            "tests/test_step278_*.py",
            "tests/test_step279_*.py",
            "tests/test_step280_*.py",
            "tests/test_step281_*.py",
            "tests/test_step282_*.py",
            "tests/test_step283_*.py",
            "tests/test_step284_*.py",
            "tests/test_step285_*.py",
            "tests/test_step286_*.py",
            "tests/test_step287_*.py",
            "tests/test_step288_*.py",
            "tests/test_step289_*.py",
            "tests/test_step290_*.py",
            "tests/test_step291_*.py",
            "tests/test_step292_*.py",
            "tests/test_step293_*.py",
            "tests/test_step294_*.py",
            "tests/test_step295_*.py",
            "tests/test_step296_*.py",
            "tests/test_step297_*.py",
            "tests/test_step298_*.py",
            "tests/test_step299_*.py",
            "tests/test_step300_*.py",
            "tests/test_step301_*.py",
            "tests/test_step302_*.py",
            "tests/test_step303_*.py",
            "tests/test_step304_*.py",
            "tests/test_step305_*.py",
            "tests/test_step306_*.py",
            "tests/test_step307_*.py",
            "tests/test_step308_*.py",
            "tests/test_step309_*.py",
            "tests/test_step310_*.py",
            "tests/test_step311_*.py",
            "tests/test_step312_*.py",
            "tests/test_step313_*.py",
            "tests/test_step314_*.py",
            "tests/test_step315_*.py",
            "tests/test_step316_*.py",
            "tests/test_step317_*.py",
            "tests/test_step318_*.py",
            "tests/test_step319_*.py",
        ],
    },
]


def _expand_patterns(patterns: Iterable[str]) -> list[str]:
    files: list[str] = []
    for pattern in patterns:
        files.extend(path.relative_to(ROOT).as_posix() for path in sorted(ROOT.glob(pattern)))
    return sorted(dict.fromkeys(files))


def build_suite_plan() -> list[dict[str, object]]:
    plan: list[dict[str, object]] = []
    assigned: set[str] = set()
    for suite in STEP280_FULL_REGRESSION_SUITES:
        files = _expand_patterns(suite["patterns"])  # type: ignore[arg-type]
        assigned.update(files)
        plan.append({"name": suite["name"], "patterns": suite["patterns"], "files": files})
    all_root_tests = _expand_patterns(["tests/test_*.py"])
    unassigned = [path for path in all_root_tests if path not in assigned]
    if unassigned:
        plan.append({
            "name": "non_step_regressions",
            "patterns": ["tests/test_*.py"],
            "files": unassigned,
        })
    return plan


def _run_command(cmd: list[str]) -> tuple[int, float]:
    started = time.perf_counter()
    env = {**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "src")}
    completed = subprocess.run(cmd, cwd=ROOT, env=env)
    return completed.returncode, time.perf_counter() - started


def run_regression(*, durations: int = 10, compile_first: bool = True, report_path: Path = REPORT_PATH) -> int:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    suite_plan = build_suite_plan()
    records: list[dict[str, object]] = []
    overall_start = time.perf_counter()

    if compile_first:
        print("[step280] compileall: src config tests", flush=True)
        rc, elapsed = _run_command([sys.executable, "-m", "compileall", "-q", "src", "config", "tests"])
        records.append({"name": "compileall", "returncode": rc, "elapsed_sec": round(elapsed, 3)})
        if rc != 0:
            _write_report(report_path, records, suite_plan, overall_start, status="failed")
            return rc

    for index, suite in enumerate(suite_plan, start=1):
        files = list(suite["files"])  # type: ignore[arg-type]
        if not files:
            records.append({"name": suite["name"], "returncode": 0, "elapsed_sec": 0.0, "files": []})
            continue
        print(f"[step280] suite {index}/{len(suite_plan)} {suite['name']} ({len(files)} files)", flush=True)
        cmd = [sys.executable, "-m", "pytest", "-q", *files, f"--durations={durations}"]
        rc, elapsed = _run_command(cmd)
        records.append({
            "name": suite["name"],
            "returncode": rc,
            "elapsed_sec": round(elapsed, 3),
            "file_count": len(files),
            "files": files,
        })
        _write_report(report_path, records, suite_plan, overall_start, status="running")
        if rc != 0:
            _write_report(report_path, records, suite_plan, overall_start, status="failed")
            return rc

    _write_report(report_path, records, suite_plan, overall_start, status="passed")
    return 0


def _write_report(report_path: Path, records: list[dict[str, object]], suite_plan: list[dict[str, object]], started: float, *, status: str) -> None:
    payload = {
        "step": "step280_full_regression_runtime_hygiene",
        "status": status,
        "full_regression_strategy": "chunked_pytest_suites_with_progress_and_runtime_report",
        "single_pytest_tests_command_replaced_in_ci": True,
        "live_trading_enabled": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "settings_write_enabled": False,
        "score_weights_mutation_allowed": False,
        "total_elapsed_sec": round(time.perf_counter() - started, 3),
        "suite_count": len(suite_plan),
        "records": records,
        "suite_plan": suite_plan,
    }
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Step280 chunked full regression.")
    parser.add_argument("--list", action="store_true", help="Print the suite plan without running tests.")
    parser.add_argument("--no-compile", action="store_true", help="Skip compileall before pytest suites.")
    parser.add_argument("--durations", type=int, default=10, help="pytest --durations value for each suite.")
    parser.add_argument("--report-path", default=str(REPORT_PATH), help="JSON report output path.")
    args = parser.parse_args()

    if args.list:
        print(json.dumps(build_suite_plan(), indent=2), flush=True)
        return 0
    return run_regression(durations=args.durations, compile_first=not args.no_compile, report_path=Path(args.report_path))


if __name__ == "__main__":
    raise SystemExit(main())
