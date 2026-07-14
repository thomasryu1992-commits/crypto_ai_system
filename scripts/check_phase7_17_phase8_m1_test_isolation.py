from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
TARGET_TESTS: tuple[str, ...] = (
    "tests/test_pre_executor_review_merge.py",
    "tests/test_phase8_execution_preparation_m1.py",
)
RANDOM_SEEDS: tuple[int, ...] = (7142026, 7142027, 7142028)
FORBIDDEN_SHARED_ARTIFACT_MARKERS: tuple[str, ...] = (
    "storage/latest",
    "data/reports",
    "read_latest_json(",
    "_read_latest_json(",
    "load_config(",
    "persist_",
)


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(ROOT / "src"), str(ROOT), env.get("PYTHONPATH", "")) if part
    )
    return env


def _existing_target_paths() -> list[Path]:
    missing = [relative for relative in TARGET_TESTS if not (ROOT / relative).is_file()]
    if missing:
        raise SystemExit(
            "P0_TEST_ISOLATION_TARGET_MISSING:" + ",".join(sorted(missing))
        )
    return [ROOT / relative for relative in TARGET_TESTS]


def _static_dependency_check(paths: Iterable[Path]) -> None:
    violations: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_SHARED_ARTIFACT_MARKERS:
            if marker in text:
                violations.append(f"{path.relative_to(ROOT).as_posix()}:{marker}")
    if violations:
        raise SystemExit(
            "P0_TEST_ISOLATION_SHARED_ARTIFACT_DEPENDENCY:" + ",".join(violations)
        )


def _collect_node_ids() -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--disable-warnings",
            *TARGET_TESTS,
        ],
        cwd=ROOT,
        env=_base_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        raise RuntimeError(f"test collection failed with exit code {result.returncode}\n{output}")

    nodes = [
        line.strip()
        for line in result.stdout.splitlines()
        if "::" in line and line.strip().startswith("tests/")
    ]
    if not nodes:
        raise RuntimeError("P0_TEST_ISOLATION_NO_TEST_NODES_COLLECTED")
    return nodes


def _pytest_command(nodes: Sequence[str], basetemp: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--disable-warnings",
        "--maxfail=1",
        f"--basetemp={basetemp}",
        *nodes,
    ]


def _run_pytest(label: str, nodes: Sequence[str], basetemp: Path) -> None:
    result = subprocess.run(
        _pytest_command(nodes, basetemp),
        cwd=ROOT,
        env=_base_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        raise RuntimeError(f"{label} failed with exit code {result.returncode}\n{output}")
    print(f"PASS {label}: {len(nodes)} node(s)")


def _run_single(nodes: Sequence[str]) -> None:
    for index, node in enumerate(nodes, start=1):
        with tempfile.TemporaryDirectory(prefix=f"p0_single_{index}_") as temp_dir:
            _run_pytest(
                f"single[{index}] {node}",
                [node],
                Path(temp_dir) / "pytest",
            )


def _run_reverse(nodes: Sequence[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="p0_reverse_") as temp_dir:
        _run_pytest(
            "reverse",
            list(reversed(nodes)),
            Path(temp_dir) / "pytest",
        )


def _run_random(nodes: Sequence[str]) -> None:
    for seed in RANDOM_SEEDS:
        randomized = list(nodes)
        random.Random(seed).shuffle(randomized)
        with tempfile.TemporaryDirectory(prefix=f"p0_random_{seed}_") as temp_dir:
            _run_pytest(
                f"random[{seed}]",
                randomized,
                Path(temp_dir) / "pytest",
            )


def _parallel_worker(index: int, node: str, temp_root: Path) -> str:
    _run_pytest(
        f"parallel[{index}] {node}",
        [node],
        temp_root / f"pytest_{index}",
    )
    return node


def _run_parallel(nodes: Sequence[str]) -> None:
    worker_count = min(4, len(nodes))
    with tempfile.TemporaryDirectory(prefix="p0_parallel_") as temp_dir:
        temp_root = Path(temp_dir)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(_parallel_worker, index, node, temp_root): node
                for index, node in enumerate(nodes, start=1)
            }
            failures: list[str] = []
            for future in as_completed(futures):
                node = futures[future]
                try:
                    future.result()
                except Exception as exc:  # pragma: no cover - exercised in CI failures
                    failures.append(f"{node}: {exc}")
            if failures:
                raise RuntimeError("parallel isolation failed\n" + "\n".join(failures))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that Phase 7.15-7.17 and Phase 8-M1 focused tests remain "
            "independent from shared generated artifacts and test order."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("all", "static", "single", "reverse", "random", "parallel"),
        default="all",
    )
    parser.add_argument("--list", action="store_true", help="List collected test node IDs and exit.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    paths = _existing_target_paths()
    _static_dependency_check(paths)
    print("PASS static: no direct shared generated-artifact dependency")

    if args.mode == "static":
        return 0

    nodes = _collect_node_ids()
    print(f"COLLECTED {len(nodes)} focused test node(s)")
    if args.list:
        for node in nodes:
            print(node)
        return 0

    if args.mode in {"all", "single"}:
        _run_single(nodes)
    if args.mode in {"all", "reverse"}:
        _run_reverse(nodes)
    if args.mode in {"all", "random"}:
        _run_random(nodes)
    if args.mode in {"all", "parallel"}:
        _run_parallel(nodes)

    print("P0_PHASE7_17_PHASE8_M1_TEST_ISOLATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
