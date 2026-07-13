from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LATEST_DIR = ROOT / "storage" / "latest"
EPHEMERAL_OPERATOR_INPUTS = {
    "operator_unlock_request.json",
    "manual_approval_intake_submission.json",
    "single_signed_testnet_enablement_intake_REVIEW_ONLY.json",
}
EPHEMERAL_OPERATOR_INPUT_PATHS = (
    ROOT / "storage" / "latest" / "operator_unlock_request.json",
    ROOT / "storage" / "signed_testnet" / "operator_unlock_request.json",
    ROOT / "storage" / "manual_approval" / "approval_intake_submission.json",
    ROOT / "storage" / "latest" / "manual_approval_intake_submission.json",
)


def remove_ephemeral_operator_inputs() -> None:
    for path in EPHEMERAL_OPERATOR_INPUT_PATHS:
        if path.exists():
            path.unlink()


@pytest.fixture(autouse=True)
def isolate_latest_json_reports() -> Generator[None, None, None]:
    remove_ephemeral_operator_inputs()
    before = (
        {
            path.name: path.read_bytes()
            for path in LATEST_DIR.glob("*.json")
            if path.is_file() and path.name not in EPHEMERAL_OPERATOR_INPUTS
        }
        if LATEST_DIR.exists()
        else {}
    )

    yield

    remove_ephemeral_operator_inputs()
    LATEST_DIR.mkdir(parents=True, exist_ok=True)

    for name, content in before.items():
        path = LATEST_DIR / name
        if not path.exists() or path.read_bytes() != content:
            path.write_bytes(content)
