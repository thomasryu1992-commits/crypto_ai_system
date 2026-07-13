from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.runtime_release_gate_operator_handoff import (
    persist_runtime_release_gate_operator_handoff,
)


def main() -> None:
    cfg = load_config(Path.cwd())
    report = persist_runtime_release_gate_operator_handoff(cfg=cfg)
    print(report["status"])
    print(report["p17_runtime_release_gate_operator_handoff_sha256"])


if __name__ == "__main__":
    main()
