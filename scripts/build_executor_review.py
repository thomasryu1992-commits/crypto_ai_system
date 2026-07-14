from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.governance.executor_review import (
    run_executor_review_chain,
)


def main() -> int:
    bundle = run_executor_review_chain()
    report = bundle["report"]

    print(
        "executor_review "
        f"status={report.get('status')} "
        f"state={report.get('executor_review_state')} "
        f"blocked={report.get('blocked')} "
        f"endpoint_call_count={report.get('endpoint_call_count')}"
    )

    return (
        0
        if report.get("blocked") is False
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
