from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.governance.readiness import (
    run_readiness_review_chain,
)


def main() -> int:
    bundle = run_readiness_review_chain()
    report = bundle["report"]

    print(
        "readiness_review "
        f"status={report.get('status')} "
        f"state={report.get('readiness_state')} "
        f"blocked={report.get('blocked')}"
    )

    return 0 if report.get("blocked") is False else 2


if __name__ == "__main__":
    raise SystemExit(main())
