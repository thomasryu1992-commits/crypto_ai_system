from __future__ import annotations

from pathlib import Path

REQUIRED_FILES = [
    "config/settings.py",
    "data_collector_bot/main.py",
    "knowledge_engine/raw_store.py",
    "knowledge_engine/kb_linter.py",
    "knowledge_engine/research_decision_builder.py",
    "research_bot/main.py",
    "trading_bot/main.py",
    "execution/order_executor.py",
    "execution/execution_reconciler.py",
    "risk/risk_manager.py",
    "run_research_cycle.py",
    "run_trading_cycle.py",
    "run_full_cycle.py",
]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    missing = [item for item in REQUIRED_FILES if not (root / item).exists()]
    print("[PROJECT FILE CHECK]")
    if missing:
        print("Missing files:")
        for item in missing:
            print(f"- {item}")
        raise SystemExit(1)
    print("All required files exist.")


if __name__ == "__main__":
    main()
