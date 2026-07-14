from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.governance.signed_testnet_execution_preparation import (
    run_signed_testnet_execution_preparation_chain,
)


def main() -> int:
    bundle = (
        run_signed_testnet_execution_preparation_chain()
    )

    report = bundle["report"]

    print(
        "phase8_execution_preparation "
        f"status={report.get('status')} "
        f"state={report.get('phase8_execution_preparation_state')} "
        f"blocked={report.get('blocked')} "
        f"design_complete={report.get('phase8_m1_design_complete')} "
        f"execution_ready="
        f"{report.get('phase8_execution_preparation_ready')}"
    )

    return (
        0
        if report.get("blocked") is False
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
