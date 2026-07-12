
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.paper_execution_mode_shadow_ready_review import (
    STEP226_STATUS_OK,
    STEP226_VALIDATION_OK,
    execute_paper_execution_mode_shadow_ready_review,
    validate_paper_execution_mode_shadow_ready_review,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_paper_execution_mode_shadow_ready_review(root, write_output=True)
    validation = validate_paper_execution_mode_shadow_ready_review(root)
    if result.status != STEP226_STATUS_OK or validation.status != STEP226_VALIDATION_OK:
        print("STEP226_V5_PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP226_V5_PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW_ONLY_OK")
    print(f"source_final_gate_decision_count: {result.source_final_gate_decision_count}")
    print(f"shadow_ready_decision_count: {result.shadow_ready_decision_count}")
    print(f"shadow_ready_review_ready_count: {result.shadow_ready_review_ready_count}")
    print(f"shadow_ready_blocked_count: {result.shadow_ready_blocked_count}")
    print(f"paper_execution_mode_shadow_ready_review_created: {result.paper_execution_mode_shadow_ready_review_created}")
    print(f"shadow_ready_mode: {result.shadow_ready_mode}")
    print(f"shadow_ready_review_only: {result.shadow_ready_review_only}")
    print(f"shadow_ready_mode_allowed: {result.shadow_ready_mode_allowed}")
    print(f"shadow_ready_mode_enabled: {result.shadow_ready_mode_enabled}")
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
