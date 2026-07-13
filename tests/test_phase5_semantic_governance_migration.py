from __future__ import annotations

from pathlib import Path


MAPPINGS = {
    "phase5_manual_approval_intake_validation.py": "approval_intake.py",
    "phase5_1_manual_approval_operator_handoff.py": "operator_handoff.py",
    "phase5_2_manual_approval_submission_fixture_validator.py":
        "approval_fixtures.py",
}


def test_phase5_legacy_modules_are_thin_compatibility_wrappers() -> None:
    root = Path(__file__).resolve().parents[1]
    validation = root / "src" / "crypto_ai_system" / "validation"
    governance = root / "src" / "crypto_ai_system" / "governance"

    for legacy_name, semantic_name in MAPPINGS.items():
        legacy = validation / legacy_name
        semantic = governance / semantic_name

        assert semantic.exists(), semantic
        assert legacy.exists(), legacy

        text = legacy.read_text(encoding="utf-8")
        assert "Thin compatibility wrapper" in text
        assert "from crypto_ai_system.governance." in text
        assert len(text.splitlines()) <= 12


def test_approval_aggregator_uses_semantic_governance_modules() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
        / "approval.py"
    ).read_text(encoding="utf-8")

    assert "crypto_ai_system.governance.approval_intake" in text
    assert "crypto_ai_system.governance.operator_handoff" in text
    assert "crypto_ai_system.governance.approval_fixtures" in text
    assert "crypto_ai_system.validation.phase5_" not in text


def test_phase5_build_scripts_use_semantic_governance_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    scripts = root / "scripts"

    for name in (
        "build_phase5_manual_approval_intake_validation.py",
        "build_phase5_1_manual_approval_operator_handoff.py",
        "build_phase5_2_manual_approval_submission_fixture_validator.py",
    ):
        text = (scripts / name).read_text(encoding="utf-8")
        assert "crypto_ai_system.validation.phase5_" not in text
        assert "crypto_ai_system.governance." in text


def test_active_source_does_not_import_legacy_phase5_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    excluded = {
        root / "src" / "crypto_ai_system" / "validation" / name
        for name in MAPPINGS
    }

    for base in (
        root / "src" / "crypto_ai_system",
        root / "scripts",
        root / "run_full_cycle.py",
    ):
        paths = [base] if base.is_file() else list(base.rglob("*.py"))
        for path in paths:
            if path in excluded:
                continue
            text = path.read_text(encoding="utf-8")
            assert "crypto_ai_system.validation.phase5_" not in text, path
