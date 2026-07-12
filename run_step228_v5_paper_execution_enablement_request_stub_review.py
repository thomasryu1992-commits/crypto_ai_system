
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.paper_execution_enablement_request_stub_review import (
    STEP228_STATUS_OK,
    STEP228_VALIDATION_OK,
    execute_paper_execution_enablement_request_stub_review,
    validate_paper_execution_enablement_request_stub_review,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_paper_execution_enablement_request_stub_review(root, write_output=True)
    validation = validate_paper_execution_enablement_request_stub_review(root)
    if result.status != STEP228_STATUS_OK or validation.status != STEP228_VALIDATION_OK:
        print("STEP228_V5_PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP228_V5_PAPER_EXECUTION_ENABLEMENT_REQUEST_STUB_REVIEW_ONLY_OK")
    print(f"source_audit_record_count: {result.source_audit_record_count}")
    print(f"source_audit_review_ready_count: {result.source_audit_review_ready_count}")
    print(f"request_stub_count: {result.request_stub_count}")
    print(f"request_stub_review_ready_count: {result.request_stub_review_ready_count}")
    print(f"request_stub_blocked_count: {result.request_stub_blocked_count}")
    print(f"paper_execution_enablement_request_stub_review_created: {result.paper_execution_enablement_request_stub_review_created}")
    print(f"request_stub_mode: {result.request_stub_mode}")
    print(f"request_stub_only: {result.request_stub_only}")
    print(f"enablement_request_created: {result.enablement_request_created}")
    print(f"enablement_request_submitted: {result.enablement_request_submitted}")
    print(f"paper_execution_enablement_allowed: {result.paper_execution_enablement_allowed}")
    print(f"paper_execution_enabled: {result.paper_execution_enabled}")
    print(f"paper_order_execution_enabled: {result.paper_order_execution_enabled}")
    print(f"paper_trade_execution_enabled: {result.paper_trade_execution_enabled}")
    print(f"adapter_routing_enabled: {result.adapter_routing_enabled}")
    print(f"shadow_execution_enabled: {result.shadow_execution_enabled}")
    print(f"live_trading_allowed: {result.live_trading_allowed}")
    print(f"strategy_registry_write_allowed: {result.strategy_registry_write_allowed}")
    print(f"live_order_executed: {result.live_order_executed}")
    print(f"telegram_real_send: {result.telegram_real_send}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
