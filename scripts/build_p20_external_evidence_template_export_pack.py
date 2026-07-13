from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.external_evidence_template_export_pack import persist_external_evidence_template_export_pack


def main() -> int:
    cfg = load_config(Path.cwd())
    report = persist_external_evidence_template_export_pack(cfg=cfg)
    print(report["status"])
    print(report["p20_external_evidence_template_export_pack_sha256"])
    print("limited_live_scaled_auto_trading_allowed=false")
    print("live_scaled_execution_enabled=false")
    print("runtime_scheduler_enabled=false")
    return 1 if report["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
