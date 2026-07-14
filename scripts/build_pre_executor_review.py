from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.governance.pre_executor_review import (
    run_pre_executor_review_chain,
)


def main() -> int:
    bundle = (
        run_pre_executor_review_chain()
    )

    report = bundle["report"]

    print(
        "pre_executor_review "
        f"status={report.get('status')} "
        f"state={report.get('pre_executor_review_state')} "
        f"blocked={report.get('blocked')} "
        f"waiting={report.get('waiting_for_operator_decision')} "
        f"phase8_preparation_review="
        f"{report.get('phase8_preparation_design_review_allowed')}"
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
