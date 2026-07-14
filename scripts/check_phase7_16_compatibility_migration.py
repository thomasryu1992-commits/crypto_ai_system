#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "src/crypto_ai_system/validation/phase7_16_operator_decision_intake_validator.py"
SEMANTIC = ROOT / "src/crypto_ai_system/governance/pre_executor_compat/operator_decision_validation.py"
PHASE7_17 = ROOT / "src/crypto_ai_system/validation/phase7_17_final_pre_executor_review_packet.py"
PHASE7_17_SEMANTIC = ROOT / "src/crypto_ai_system/governance/pre_executor_compat/final_pre_executor_review.py"
MANIFEST = ROOT / "config/lean/phase7_16_public_surface.json"
CLOSURE = ROOT / "config/lean/phase7_lean_closure.json"
FULL_CYCLE = ROOT / "run_full_cycle.py"

SEMANTIC_IMPORT = (
    "crypto_ai_system.governance.pre_executor_compat."
    "operator_decision_validation"
)
PHASE7_15_SEMANTIC_IMPORT = (
    "crypto_ai_system.governance.pre_executor_compat."
    "operator_decision_intake"
)
FORBIDDEN_PHASE7_15_NUMBERED_IMPORT = (
    "crypto_ai_system.validation."
    "phase7_15_operator_decision_intake_template"
)
FORBIDDEN_PHASE7_16_NUMBERED_IMPORT = (
    "crypto_ai_system.validation."
    "phase7_16_operator_decision_intake_validator"
)

CRITICAL_PUBLIC_SYMBOLS = {
    "PHASE7_16_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_operator_decision_intake_submission_fixture",
    "validate_operator_decision_intake_submission",
    "validate_operator_decision_intake_validation_report",
    "build_phase7_16_operator_decision_intake_validator_report",
    "persist_phase7_16_operator_decision_intake_validator_report",
}


def _module_all(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
                result = ast.literal_eval(node.value)
                if not isinstance(result, (list, tuple)) or not all(isinstance(item, str) for item in result):
                    raise RuntimeError(f"__all__ must be a string list in {path}")
                return list(result)
    raise RuntimeError(f"__all__ missing in {path}")


def main() -> int:
    blockers: list[str] = []

    for path, code in (
        (LEGACY, "PHASE7_16_LEGACY_WRAPPER_MISSING"),
        (SEMANTIC, "PHASE7_16_SEMANTIC_COMPAT_MODULE_MISSING"),
        (PHASE7_17, "PHASE7_17_MODULE_MISSING"),
        (MANIFEST, "PHASE7_16_PUBLIC_SURFACE_MANIFEST_MISSING"),
        (CLOSURE, "PHASE7_LEAN_CLOSURE_MANIFEST_MISSING"),
    ):
        if not path.exists():
            blockers.append(code)

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)
        return 2

    legacy_text = LEGACY.read_text(encoding="utf-8")
    semantic_text = SEMANTIC.read_text(encoding="utf-8")
    phase7_17_text = PHASE7_17.read_text(encoding="utf-8")
    phase7_17_dependency_text = (
        PHASE7_17_SEMANTIC.read_text(encoding="utf-8")
        if PHASE7_17_SEMANTIC.exists()
        else phase7_17_text
    )
    meaningful = [line for line in legacy_text.splitlines() if line.strip()]

    if len(meaningful) > 12:
        blockers.append("PHASE7_16_LEGACY_WRAPPER_TOO_LARGE")
    if SEMANTIC_IMPORT not in legacy_text:
        blockers.append("PHASE7_16_LEGACY_WRAPPER_TARGET_INVALID")

    if FORBIDDEN_PHASE7_15_NUMBERED_IMPORT in semantic_text:
        blockers.append("PHASE7_16_SEMANTIC_IMPORTS_NUMBERED_PHASE7_15")
    if PHASE7_15_SEMANTIC_IMPORT not in semantic_text:
        blockers.append("PHASE7_16_PHASE7_15_SEMANTIC_IMPORT_MISSING")

    if FORBIDDEN_PHASE7_16_NUMBERED_IMPORT in phase7_17_dependency_text:
        blockers.append("PHASE7_17_STILL_IMPORTS_NUMBERED_PHASE7_16")
    if SEMANTIC_IMPORT not in phase7_17_dependency_text:
        blockers.append("PHASE7_17_SEMANTIC_PHASE7_16_IMPORT_MISSING")

    full_cycle_text = FULL_CYCLE.read_text(encoding="utf-8") if FULL_CYCLE.exists() else ""
    if "crypto_ai_system.governance.pre_executor_compat" in full_cycle_text:
        blockers.append("ACTIVE_FULL_CYCLE_IMPORTS_PRE_EXECUTOR_COMPAT")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    exported = _module_all(SEMANTIC)
    if exported != (manifest.get("exported_public_symbols") or []):
        blockers.append("PHASE7_16_EXPORTED_PUBLIC_SURFACE_DRIFT")
    if not CRITICAL_PUBLIC_SYMBOLS <= set(exported):
        blockers.append(
            "PHASE7_16_CRITICAL_PUBLIC_SYMBOLS_MISSING:"
            + ",".join(sorted(CRITICAL_PUBLIC_SYMBOLS - set(exported)))
        )

    for field, expected in (
        ("legacy_numbered_module_is_thin_wrapper", True),
        ("business_logic_relocated_without_contract_change", True),
        ("active_orchestration_uses_compat_module", False),
        ("runtime_authority", False),
        ("execution_permissions_changed", False),
    ):
        if manifest.get(field) is not expected:
            blockers.append(f"PHASE7_16_PUBLIC_SURFACE_POLICY_INVALID:{field}")

    closure = json.loads(CLOSURE.read_text(encoding="utf-8"))
    policy = closure.get("phase7_15_17_policy") or {}
    stable_policy = {
        "phase7_15_numbered_module_is_thin_wrapper": True,
        "phase7_16_numbered_module_is_thin_wrapper": True,
        "phase7_16_business_logic_relocated_without_contract_change": True,
    }
    for field, expected in stable_policy.items():
        if policy.get(field) is not expected:
            blockers.append(f"PHASE7_15_17_POLICY_INVALID:{field}")

    pending = (
        policy.get("phase7_17_numbered_business_logic_retirement_pending") is True
        and policy.get("legacy_numbered_business_logic_still_present") is True
        and policy.get("legacy_numbered_business_logic_retirement_pending") is True
    )
    complete = (
        policy.get("legacy_numbered_business_logic_still_present") is False
        and policy.get("legacy_numbered_business_logic_retirement_pending") is False
        and policy.get("legacy_numbered_business_logic_retirement_complete") is True
    )
    if not (pending or complete):
        blockers.append("PHASE7_15_17_POLICY_INVALID:retirement_state")

    safety = closure.get("safety") or {}
    unsafe = sorted(name for name, value in safety.items() if value is True)
    if unsafe:
        blockers.append("PHASE7_16_MIGRATION_UNSAFE_FLAGS:" + ",".join(unsafe))

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)
        return 2

    print("PHASE7_16_COMPATIBILITY_MIGRATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
