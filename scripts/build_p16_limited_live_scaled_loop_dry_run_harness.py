from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.limited_live_scaled_loop_dry_run_harness import (
    persist_limited_live_scaled_loop_dry_run_harness,
)


def main() -> None:
    cfg = load_config(Path.cwd())
    report = persist_limited_live_scaled_loop_dry_run_harness(cfg=cfg)
    print(report["status"])
    print(report["p16_limited_live_scaled_loop_dry_run_harness_sha256"])


if __name__ == "__main__":
    main()
