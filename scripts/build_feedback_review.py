from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.feedback.review import run_feedback_review_chain


def main() -> int:
    bundle = run_feedback_review_chain()
    report = bundle["report"]
    print(
        "feedback_review "
        f"status={report.get('status')} "
        f"blocked={report.get('blocked')} "
        f"components={report.get('component_count')}"
    )
    return 0 if report.get("blocked") is False else 2


if __name__ == "__main__":
    raise SystemExit(main())
