from __future__ import annotations

from pathlib import Path
from typing import Any

from core.json_io import atomic_write_json
from crypto_ai_system.execution.external_adapter_review_contracts import (
    STATUS_P65_VALIDATED_DISABLED,
    build_p65_negative_fixture_results,
    build_p65_operator_installed_sender_executable_report,
)

STATUS_VALIDATED_REVIEW_ONLY_DISABLED = STATUS_P65_VALIDATED_DISABLED


def persist_p65_operator_installed_testnet_sender_executable(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    latest = root / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    report = build_p65_operator_installed_sender_executable_report()
    negative = build_p65_negative_fixture_results()
    atomic_write_json(latest / "p65_operator_installed_testnet_sender_executable_report.json", report)
    atomic_write_json(latest / "p65_operator_installed_testnet_sender_executable_negative_fixture_results.json", negative)
    atomic_write_json(root / "P65_OPERATOR_INSTALLED_TESTNET_SENDER_EXECUTABLE_REPORT.md", _markdown_report(report))
    return report


def _markdown_report(report: dict[str, Any]) -> str:
    return "\n".join([
        "# P65 Operator-installed Testnet Sender Executable Package",
        "",
        f"Status: `{report['status']}`",
        "",
        "Review-only / disabled. No real /order/test call, no HTTP request, no signature, no secret access.",
        "",
        f"Report SHA256: `{report['p65_operator_installed_testnet_sender_executable_sha256']}`",
        "",
    ])
