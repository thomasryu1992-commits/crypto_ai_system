from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.onboarding_wizard_failure_doctor import persist_onboarding_wizard_failure_doctor


if __name__ == "__main__":
    report = persist_onboarding_wizard_failure_doctor(load_config(Path.cwd()))
    print(report["status"])
