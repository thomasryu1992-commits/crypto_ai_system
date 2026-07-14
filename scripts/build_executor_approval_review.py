from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.governance.executor_approval import (
    run_executor_approval_chain,
)


def main() -> int:
    bundle = (
        run_executor_approval_chain()
    )

    report = bundle["report"]

    print(
        "executor_approval_review "
        f"status={report.get('status')} "
        f"state={report.get('executor_approval_review_state')} "
        f"blocked={report.get('blocked')} "
        f"actual_operator_submission="
        f"{report.get('actual_operator_submission_present')} "
        f"source={report.get('validated_submission_source')}"
    )

    return (
        0
        if report.get(
            "blocked"
        )
        is False
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
