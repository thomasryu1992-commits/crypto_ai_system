from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase7_15_17_retirement_closure_checker() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_phase7_15_17_retirement_closure.py",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        "PHASE7_15_17_NUMBERED_BUSINESS_LOGIC_RETIREMENT_VALID"
        in result.stdout
    )


def test_phase7_15_17_retirement_manifest_keeps_execution_disabled() -> None:
    payload = json.loads(
        (
            ROOT
            / "config"
            / "lean"
            / "phase7_15_17_retirement_closure.json"
        ).read_text(encoding="utf-8")
    )

    assert payload["all_numbered_modules_are_thin_wrappers"] is True
    assert payload["numbered_business_logic_still_present"] is False
    assert payload["numbered_business_logic_retirement_complete"] is True
    assert payload["runtime_authority"] is False
    assert payload["execution_permissions_changed"] is False
    assert all(value is False for value in payload["safety"].values())
