from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.feedback.common import (
    bool_value,
    float_value,
    json_safe,
    seal_payload,
    text_value,
)


def test_common_value_coercion_is_fail_closed_and_deterministic() -> None:
    assert bool_value(True) is True
    assert bool_value("yes") is True
    assert bool_value("no") is False
    assert bool_value(None) is False

    assert text_value("  BTC-USD  ") == "BTC-USD"
    assert text_value("nan", "unknown") == "unknown"
    assert text_value(None, "missing") == "missing"

    assert float_value("3.5") == 3.5
    assert float_value(float("nan"), 7.0) == 7.0
    assert float_value("invalid", 9.0) == 9.0


def test_json_safe_normalizes_nested_nan_values() -> None:
    payload = {
        "a": float("nan"),
        "b": [1, float("inf"), {"c": "ok"}],
    }
    assert json_safe(payload) == {
        "a": None,
        "b": [1, None, {"c": "ok"}],
    }


def test_seal_payload_replaces_existing_hash_and_is_stable() -> None:
    source = {"status": "REVIEW_ONLY", "report_sha256": "old"}
    first = seal_payload(source, "report_sha256")
    second = seal_payload(first, "report_sha256")

    assert len(first["report_sha256"]) == 64
    assert first == second
    assert source["report_sha256"] == "old"
