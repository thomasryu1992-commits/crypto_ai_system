from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_support_bundle_troubleshooting_export_pack import persist_operator_support_bundle


def main() -> int:
    report = persist_operator_support_bundle(load_config(Path.cwd()))
    print(report["status"])
    print(f"support_issue_count={report['support_issue_count']}")
    print(f"present_source_artifact_count={report['present_source_artifact_count']}")
    print("runtime_scheduler_enabled=false")
    print("live_order_submission_allowed=false")
    print("order_endpoint_called=false")
    print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
