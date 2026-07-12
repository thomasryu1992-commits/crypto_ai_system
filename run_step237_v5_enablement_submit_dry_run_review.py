
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.enablement_submit_dry_run_review import (
    STEP237_STATUS_OK,
    STEP237_VALIDATION_OK,
    execute_enablement_submit_dry_run_review,
    validate_enablement_submit_dry_run_review,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_enablement_submit_dry_run_review(root, write_output=True)
    validation = validate_enablement_submit_dry_run_review(root)
    if result.status != STEP237_STATUS_OK or validation.status != STEP237_VALIDATION_OK:
        print("STEP237_V5_ENABLEMENT_SUBMIT_DRY_RUN_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP237_V5_ENABLEMENT_SUBMIT_DRY_RUN_REVIEW_ONLY_OK")
    print(f"source_submit_gate_record_count: {result.source_submit_gate_record_count}")
    print(f"source_submit_gate_review_ready_count: {result.source_submit_gate_review_ready_count}")
    print(f"dry_run_record_count: {result.dry_run_record_count}")
    print(f"dry_run_review_ready_count: {result.dry_run_review_ready_count}")
    print(f"dry_run_blocked_count: {result.dry_run_blocked_count}")
    print(f"enablement_submit_dry_run_review_created: {result.enablement_submit_dry_run_review_created}")
    print(f"dry_run_mode: {result.dry_run_mode}")
    print(f"dry_run_review_only: {result.dry_run_review_only}")
    print(f"dry_run_artifact_created: {result.dry_run_artifact_created}")
    print(f"dry_run_passed: {result.dry_run_passed}")
    print(f"submit_gate_passed: {result.submit_gate_passed}")
    print(f"submit_gate_opened: {result.submit_gate_opened}")
    print(f"enablement_request_submit_allowed: {result.enablement_request_submit_allowed}")
    print(f"enablement_request_submitted: {result.enablement_request_submitted}")
    print(f"paper_execution_enablement_allowed: {result.paper_execution_enablement_allowed}")
    print(f"paper_execution_enabled: {result.paper_execution_enabled}")
    print(f"paper_order_execution_enabled: {result.paper_order_execution_enabled}")
    print(f"adapter_routing_enabled: {result.adapter_routing_enabled}")
    print(f"shadow_execution_enabled: {result.shadow_execution_enabled}")
    print(f"external_api_call_performed: {result.external_api_call_performed}")
    print(f"live_trading_allowed: {result.live_trading_allowed}")
    print(f"strategy_registry_write_allowed: {result.strategy_registry_write_allowed}")
    print(f"live_order_executed: {result.live_order_executed}")
    print(f"telegram_real_send: {result.telegram_real_send}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
