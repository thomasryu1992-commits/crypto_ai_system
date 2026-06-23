from __future__ import annotations

from research_bot.decision_engine import run_decision_engine


def main() -> None:
    result = run_decision_engine()
    print("[RESEARCH BOT]")
    print(f"Status: {result.get('status')}")
    print(f"Path: {result.get('path')}")


if __name__ == "__main__":
    main()
