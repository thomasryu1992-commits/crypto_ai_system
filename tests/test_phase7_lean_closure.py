from __future__ import annotations

import ast
import json
from pathlib import Path


STEP_MAPPINGS = {
    "phase7_signed_testnet_validation_design_guard.py": (
        "validation_design.py"
    ),
    "phase7_1_signed_testnet_pre_submit_payload_guard.py": (
        "pre_submit_guard.py"
    ),
    "review_chain_state_doctor.py": (
        "review_chain_doctor.py"
    ),
    "phase7_2_executor_enablement_review_packet.py": (
        "executor_enablement_review.py"
    ),
    "phase7_3_disabled_signed_testnet_executor_review.py": (
        "disabled_executor_review.py"
    ),
    "phase7_4_disabled_execution_reconciliation_session_close.py": (
        "disabled_session_reconciliation.py"
    ),
    "phase7_5_reconciliation_session_close_review_packet.py": (
        "session_close_review.py"
    ),
    "phase7_6_disabled_signed_testnet_session_operator_handoff.py": (
        "session_operator_handoff.py"
    ),
    "phase7_7_future_executor_review_prerequisite_design.py": (
        "executor_prerequisite.py"
    ),
    "phase7_8_future_executor_approval_packet_template.py": (
        "executor_approval_template.py"
    ),
    "phase7_9_future_executor_approval_intake_validator.py": (
        "executor_approval_intake.py"
    ),
    "phase7_10_future_executor_approval_review_packet.py": (
        "executor_approval_packet_review.py"
    ),
    "phase7_11_future_executor_enablement_design_review.py": (
        "enablement_design.py"
    ),
    "phase7_12_future_executor_enablement_guard_fixture.py": (
        "enablement_guard_fixtures.py"
    ),
    "phase7_13_future_executor_enablement_review_packet.py": (
        "enablement_review.py"
    ),
    "phase7_14_future_executor_operator_decision_packet.py": (
        "operator_decision_packet.py"
    ),
}


def _root() -> Path:
    return (
        Path(__file__)
        .resolve()
        .parents[1]
    )


def _load_json(
    relative: str,
) -> dict:
    payload = json.loads(
        (
            _root()
            / relative
        ).read_text(
            encoding="utf-8"
        )
    )

    assert isinstance(
        payload,
        dict,
    )

    return payload


def test_phase7_semantic_step_mapping_is_complete() -> None:
    root = _root()

    steps = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
        / "phase7_steps"
    )

    validation = (
        root
        / "src"
        / "crypto_ai_system"
        / "validation"
    )

    assert len(
        STEP_MAPPINGS
    ) == 16

    for (
        legacy_name,
        semantic_name,
    ) in STEP_MAPPINGS.items():
        semantic_path = (
            steps
            / semantic_name
        )

        wrapper_path = (
            validation
            / legacy_name
        )

        assert semantic_path.exists()
        assert wrapper_path.exists()

        semantic_text = (
            semantic_path.read_text(
                encoding="utf-8"
            )
        )

        assert (
            "crypto_ai_system.validation.phase7"
            not in semantic_text
        )

        assert (
            "crypto_ai_system.validation."
            "review_chain_state_doctor"
            not in semantic_text
        )

        wrapper_text = (
            wrapper_path.read_text(
                encoding="utf-8"
            )
        )

        meaningful = [
            line
            for line in (
                wrapper_text.splitlines()
            )
            if line.strip()
        ]

        assert len(
            meaningful
        ) <= 12

        assert (
            "crypto_ai_system.governance.phase7_steps."
            + Path(
                semantic_name
            ).stem
            in wrapper_text
        )


def test_phase7_aggregate_modules_use_common_and_semantic_steps() -> None:
    root = _root()

    governance = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
    )

    for name in (
        "executor_review.py",
        "session_review.py",
        "executor_approval.py",
        "stage_transition.py",
        "pre_executor_review.py",
    ):
        text = (
            governance
            / name
        ).read_text(
            encoding="utf-8"
        )

        assert (
            "crypto_ai_system.governance.common"
            in text
        )

        assert (
            "crypto_ai_system.validation.phase7"
            not in text
        )

        assert (
            "crypto_ai_system.validation."
            "review_chain_state_doctor"
            not in text
        )


def test_governance_common_contains_phase7_shared_contracts() -> None:
    root = _root()

    path = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
        / "common.py"
    )

    tree = ast.parse(
        path.read_text(
            encoding="utf-8"
        ),
        filename=str(
            path
        ),
    )

    functions = {
        node.name
        for node in tree.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
    }

    required = {
        "read_optional_json",
        "number_value",
        "positive_number_within",
        "positive_integer_within",
        "is_zero_number",
        "placeholder_value",
        "canonical_utc_value",
        "hex_fingerprint_valid",
        "artifact_hash",
        "artifact_summary",
        "unsafe_flags_by_artifact",
        "forbidden_secret_fields",
        "review_only_permission_state",
    }

    assert (
        required
        <= functions
    )


def test_run_full_cycle_uses_only_phase7_semantic_entry_points() -> None:
    text = (
        _root()
        / "run_full_cycle.py"
    ).read_text(
        encoding="utf-8"
    )

    for marker in (
        "run_executor_review_chain",
        "run_session_review_chain",
        "run_executor_approval_chain",
        "run_stage_transition_chain",
        "run_pre_executor_review_chain",
    ):
        assert marker in text

    assert (
        "crypto_ai_system.validation.phase7"
        not in text
    )


def test_phase7_15_17_remain_semantic_only() -> None:
    full_cycle = (
        _root()
        / "run_full_cycle.py"
    ).read_text(encoding="utf-8")

    for numbered_import in (
        "crypto_ai_system.validation.phase7_15_",
        "crypto_ai_system.validation.phase7_16_",
        "crypto_ai_system.validation.phase7_17_",
    ):
        assert numbered_import not in full_cycle


def test_phase7_closure_manifest_is_fail_closed() -> None:
    closure = _load_json(
        "config/lean/phase7_lean_closure.json"
    )

    assert (
        closure["status"]
        == "PHASE7_LEAN_MERGE_CLOSED"
    )

    assert (
        closure["runtime_authority"]
        is False
    )

    assert (
        closure["next_work"]
        == (
            "PHASE8_SIGNED_TESTNET_"
            "EXECUTION_PREPARATION"
        )
    )

    assert not any(
        closure["safety"].values()
    )

    wrapper_policy = (
        closure[
            "legacy_wrapper_policy"
        ]
    )

    assert (
        wrapper_policy[
            "historical_imports_preserved"
        ]
        is True
    )

    assert (
        wrapper_policy[
            "legacy_files_are_thin_wrappers"
        ]
        is True
    )

    assert (
        wrapper_policy[
            "active_orchestration_uses_legacy_phase_imports"
        ]
        is False
    )


def test_phase7_migration_state_points_to_phase8_preparation() -> None:
    migration = _load_json(
        "config/lean/lean_migration_state.json"
    )

    assert (
        migration[
            "completed"
        ][
            "phase7_pre_executor"
        ][
            "status"
        ]
        == "CLOSED"
    )

    assert (
        migration[
            "current"
        ][
            "status"
        ]
        in {
            "PHASE7_LEAN_MERGE_CLOSED",
            (
                "PHASE8_M1_EXECUTION_PREPARATION_"
                "DESIGN_COMPLETE"
            ),
        }
    )

    assert (
        migration[
            "current"
        ][
            "next_step"
        ]
        in {
            (
                "PHASE8_SIGNED_TESTNET_"
                "EXECUTION_PREPARATION"
            ),
            (
                "PHASE8_M2_METADATA_KEY_SCOPE_"
                "AND_WRITE_PATH_DRY_VALIDATION"
            ),
        }
    )

    assert (
        migration[
            "execution_permissions_changed"
        ]
        is False
    )
