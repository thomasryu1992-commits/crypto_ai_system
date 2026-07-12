from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.limited_live_scaled_runtime_enablement_boundary import (
    persist_limited_live_scaled_runtime_enablement_boundary,
)


def main() -> None:
    cfg = load_config(Path.cwd())
    report = persist_limited_live_scaled_runtime_enablement_boundary(cfg=cfg)
    print(report["status"])
    print(report["p15_limited_live_scaled_runtime_enablement_boundary_sha256"])


if __name__ == "__main__":
    main()
