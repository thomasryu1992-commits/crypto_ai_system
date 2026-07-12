from __future__ import annotations

from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report


if __name__ == "__main__":
    report = persist_paper_strategy_validation_report()
    print(report["status"])
    if report.get("block_reasons"):
        print("block_reasons=" + ",".join(report["block_reasons"]))
