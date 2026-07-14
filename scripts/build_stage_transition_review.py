from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.governance.stage_transition import (
    run_stage_transition_chain,
)


def main() -> int:
    bundle = (
        run_stage_transition_chain()
    )

    report = bundle["report"]

    print(
        "stage_transition_review "
        f"status={report.get('status')} "
        f"state={report.get('stage_transition_review_state')} "
        f"blocked={report.get('blocked')} "
        f"operator_decision_packet_ready="
        f"{report.get('operator_decision_packet_ready')}"
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
