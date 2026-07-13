from __future__ import annotations

from pathlib import Path


MAPPINGS = {
    "phase6_signed_testnet_preparation_preview.py":
        "signed_testnet_preparation.py",
    "phase6_1_signed_testnet_operator_unlock_request_template.py":
        "operator_unlock_template.py",
    "phase6_2_operator_unlock_request_fixture_validator.py":
        "operator_unlock_fixtures.py",
    "phase6_3_signed_testnet_readiness_gate_review.py":
        "readiness_gate.py",
    "phase6_4_signed_testnet_readiness_review_packet.py":
        "readiness_packet.py",
    "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox.py":
        "actual_intake_sandbox.py",
    "phase6_6_actual_intake_validation_bridge.py":
        "actual_intake_bridge.py",
}

SEMANTIC_IMPORTS = {
    "signed_testnet_preparation.py":
        "crypto_ai_system.governance.signed_testnet_preparation",
    "operator_unlock_template.py":
        "crypto_ai_system.governance.operator_unlock_template",
    "operator_unlock_fixtures.py":
        "crypto_ai_system.governance.operator_unlock_fixtures",
    "readiness_gate.py":
        "crypto_ai_system.governance.readiness_gate",
    "readiness_packet.py":
        "crypto_ai_system.governance.readiness_packet",
    "actual_intake_sandbox.py":
        "crypto_ai_system.governance.actual_intake_sandbox",
    "actual_intake_bridge.py":
        "crypto_ai_system.governance.actual_intake_bridge",
}


def test_phase6_legacy_modules_are_thin_compatibility_wrappers() -> None:
    root = Path(__file__).resolve().parents[1]

    validation = (
        root
        / "src"
        / "crypto_ai_system"
        / "validation"
    )

    governance = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
    )

    for legacy_name, semantic_name in MAPPINGS.items():
        legacy = validation / legacy_name
        semantic = governance / semantic_name

        assert semantic.exists(), semantic
        assert legacy.exists(), legacy

        text = legacy.read_text(encoding="utf-8")

        assert "Thin compatibility wrapper" in text
        assert "from crypto_ai_system.governance." in text
        assert len(text.splitlines()) <= 12


def test_readiness_aggregator_uses_semantic_governance_modules() -> None:
    root = Path(__file__).resolve().parents[1]

    text = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
        / "readiness.py"
    ).read_text(encoding="utf-8")

    for semantic_import in SEMANTIC_IMPORTS.values():
        assert semantic_import in text

    assert "crypto_ai_system.validation.phase6_" not in text


def test_active_source_does_not_import_legacy_phase6_paths() -> None:
    root = Path(__file__).resolve().parents[1]

    validation = (
        root
        / "src"
        / "crypto_ai_system"
        / "validation"
    )

    excluded = {
        validation / name
        for name in MAPPINGS
    }

    for base in (
        root / "src" / "crypto_ai_system",
        root / "scripts",
        root / "run_full_cycle.py",
    ):
        paths = (
            [base]
            if base.is_file()
            else list(base.rglob("*.py"))
        )

        for path in paths:
            if path in excluded:
                continue

            text = path.read_text(encoding="utf-8")

            assert (
                "crypto_ai_system.validation.phase6_"
                not in text
            ), path


def test_historical_phase6_build_commands_use_semantic_modules() -> None:
    root = Path(__file__).resolve().parents[1]

    scripts = root / "scripts"

    expected = {
        "build_phase6_signed_testnet_preparation_preview.py":
            "crypto_ai_system.governance."
            "signed_testnet_preparation",
        "build_phase6_1_signed_testnet_operator_unlock_request_template.py":
            "crypto_ai_system.governance."
            "operator_unlock_template",
        "build_phase6_2_operator_unlock_request_fixture_validator.py":
            "crypto_ai_system.governance."
            "operator_unlock_fixtures",
        "build_phase6_3_signed_testnet_readiness_gate_review.py":
            "crypto_ai_system.governance."
            "readiness_gate",
        "build_phase6_4_signed_testnet_readiness_review_packet.py":
            "crypto_ai_system.governance."
            "readiness_packet",
        "build_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox.py":
            "crypto_ai_system.governance."
            "actual_intake_sandbox",
        "build_phase6_6_actual_intake_validation_bridge.py":
            "crypto_ai_system.governance."
            "actual_intake_bridge",
    }

    for name, semantic_import in expected.items():
        path = scripts / name

        if not path.exists():
            continue

        text = path.read_text(encoding="utf-8")

        assert semantic_import in text
        assert (
            "crypto_ai_system.validation.phase6_"
            not in text
        )
