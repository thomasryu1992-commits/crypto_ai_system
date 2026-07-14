from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.governance.session_review import (
    run_session_review_chain,
)


def main() -> int:
    bundle = run_session_review_chain()
    report = bundle["report"]

    print(
        "session_review "
        f"status={report.get('status')} "
        f"state={report.get('session_review_state')} "
        f"blocked={report.get('blocked')} "
        f"fills={report.get('observed_fill_count')} "
        f"position_delta={report.get('observed_position_delta')} "
        f"balance_delta={report.get('observed_balance_delta')}"
    )

    return (
        0
        if report.get("blocked") is False
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
