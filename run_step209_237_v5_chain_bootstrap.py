from __future__ import annotations

from scripts.common import bootstrap

bootstrap()


import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crypto_ai_system.runner.step209_237_chain_bootstrap import (
    STEP_BOOTSTRAP_STATUS_OK,
    STEP_BOOTSTRAP_VALIDATION_OK,
    execute_step209_237_chain_bootstrap,
    validate_step209_237_chain_bootstrap,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Step209~237 review-only chain/artifact-generation bootstrap.")
    parser.add_argument("--continue-on-error", action="store_true", help="Run all step runners even if one runner fails.")
    parser.add_argument("--timeout-seconds", type=int, default=120, help="Per-runner timeout in seconds.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    result = execute_step209_237_chain_bootstrap(
        root,
        write_output=True,
        fail_fast=not args.continue_on_error,
        timeout_seconds=args.timeout_seconds,
    )
    validation = validate_step209_237_chain_bootstrap(root)

    print(result.status)
    print("validation_wording: 체인/산출물 생성 검증 통과" if result.chain_artifact_generation_validation_passed else "validation_wording: 체인/산출물 생성 검증 실패")
    print(f"bootstrap_scope: {result.bootstrap_scope}")
    print(f"runner_count_expected: {result.runner_count_expected}")
    print(f"runner_count_executed: {result.runner_count_executed}")
    print(f"runner_count_passed: {result.runner_count_passed}")
    print(f"runner_count_failed: {result.runner_count_failed}")
    print(f"operating_validation_passed: {result.operating_validation_passed}")
    print(f"production_live_trading_validation_performed: {result.production_live_trading_validation_performed}")
    print(f"live_trading_allowed: {result.live_trading_allowed}")
    print(f"result_path: {result.result_path}")
    print(f"markdown_report_path: {result.markdown_report_path}")
    if validation.blocking_failures:
        print(f"blocking_failures: {validation.blocking_failures}")
    if result.status != STEP_BOOTSTRAP_STATUS_OK or validation.status != STEP_BOOTSTRAP_VALIDATION_OK:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
