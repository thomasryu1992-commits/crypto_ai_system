from __future__ import annotations

import sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_ai_system.execution.venue_alignment import validate_venue_alignment


def main() -> int:
    root = ROOT
    settings = yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8")) or {}
    result = validate_venue_alignment(settings.get("venue_alignment") or {})
    failures = list(result["block_reasons"])
    decision = (root / "docs/VENUE_ALIGNMENT_DECISION.md").read_text(encoding="utf-8")
    for marker in ("primary_execution_venue=extended", "REFERENCE_ONLY_BINANCE_BRANCH", "cross_venue_evidence_import_allowed=false"):
        if marker not in decision:
            failures.append(f"VENUE_DECISION_MARKER_MISSING:{marker}")
    forbidden_import = "external_runtime_packages.binance_futures_testnet_adapter"
    reference_bridge_modules = {
        "concrete_external_order_test_executor_integration.py",
        "external_signer_http_transport_injection_harness.py",
        "opaque_sender_subprocess_bridge.py",
        "operator_installed_testnet_sender_executable.py",
        "operator_side_external_order_test_execution_kit.py",
        "real_testnet_order_test_dry_validation_adapter.py",
        "separate_testnet_external_adapter_package.py",
    }
    for path in (root / "src/crypto_ai_system").rglob("*.py"):
        if forbidden_import in path.read_text(encoding="utf-8") and path.name not in reference_bridge_modules:
            failures.append(f"BINANCE_REFERENCE_ADAPTER_IMPORTED_BY_CORE:{path.relative_to(root)}")
    if failures:
        print("P69 venue alignment: BLOCKED")
        for failure in sorted(set(failures)):
            print(f"- {failure}")
        return 1
    print("P69 venue alignment: VALID; execution remains frozen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
