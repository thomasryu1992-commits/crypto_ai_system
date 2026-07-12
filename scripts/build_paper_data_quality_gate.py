from __future__ import annotations

from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report


if __name__ == "__main__":
    report = persist_paper_data_quality_gate_report()
    print(report["status"])
    if report.get("block_reasons"):
        print("block_reasons=" + ",".join(report["block_reasons"]))
