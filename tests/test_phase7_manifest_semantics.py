from __future__ import annotations

import json
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_phase7_15_17_manifest_records_canonical_path_and_pending_legacy_retirement() -> None:
    closure = json.loads(
        (_root() / "config/lean/phase7_lean_closure.json").read_text(
            encoding="utf-8"
        )
    )
    policy = closure["phase7_15_17_policy"]

    assert policy["semantic_implementation_is_canonical"] is True
    assert policy["new_numbered_business_logic_created"] is False
    assert policy["legacy_numbered_compatibility_paths_preserved"] is True
    assert policy["active_orchestration_uses_legacy_numbered_paths"] is False

    # Current repository truth: the historical 7.15-7.17 modules still carry
    # business logic and must be retired one at a time after call-surface tests.
    assert policy["legacy_numbered_business_logic_still_present"] is False
    assert policy["legacy_numbered_business_logic_retirement_pending"] is False
    assert policy["legacy_numbered_business_logic_retirement_complete"] is True
    assert policy["legacy_numbered_business_logic_files"] == [
        "phase7_15_operator_decision_intake_template.py",
        "phase7_16_operator_decision_intake_validator.py",
        "phase7_17_final_pre_executor_review_packet.py",
    ]

    wrapper_policy = closure["legacy_wrapper_policy"]
    assert wrapper_policy["thin_wrapper_scope"] == (
        "semantic_step_mappings_phase7_through_phase7_14"
    )
    assert wrapper_policy["phase7_15_17_excluded_pending_retirement"] is True

    # Ambiguous wording must not return.
    assert "semantic_only_implementation" not in policy
    assert "numbered_implementation_files_created" not in policy

    # Documentation clarity must never change runtime authority.
    assert closure["runtime_authority"] is False
    assert not any(closure["safety"].values())
