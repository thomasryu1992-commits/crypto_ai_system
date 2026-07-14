#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "src/crypto_ai_system/validation"
COMPAT = ROOT / "src/crypto_ai_system/governance/pre_executor_compat"
FULL_CYCLE = ROOT / "run_full_cycle.py"
CLOSURE = ROOT / "config/lean/phase7_lean_closure.json"
RETIREMENT = ROOT / "config/lean/phase7_15_17_retirement_closure.json"

MAPPINGS = {
    "phase7_15_operator_decision_intake_template.py": (
        "operator_decision_intake.py",
        "crypto_ai_system.governance.pre_executor_compat.operator_decision_intake",
    ),
    "phase7_16_operator_decision_intake_validator.py": (
        "operator_decision_validation.py",
        "crypto_ai_system.governance.pre_executor_compat.operator_decision_validation",
    ),
    "phase7_17_final_pre_executor_review_packet.py": (
        "final_pre_executor_review.py",
        "crypto_ai_system.governance.pre_executor_compat.final_pre_executor_review",
    ),
}

FORBIDDEN_NUMBERED_IMPORTS = (
    "crypto_ai_system.validation.phase7_15_",
    "crypto_ai_system.validation.phase7_16_",
    "crypto_ai_system.validation.phase7_17_",
)


def _module_all(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
                result = ast.literal_eval(node.value)
                if (
                    not isinstance(result, (list, tuple))
                    or not all(isinstance(item, str) for item in result)
                ):
                    raise RuntimeError(f"Invalid __all__ in {path}")
                return list(result)
    raise RuntimeError(f"__all__ missing in {path}")


def main() -> int:
    blockers: list[str] = []

    for legacy_name, (semantic_name, semantic_import) in MAPPINGS.items():
        legacy = VALIDATION / legacy_name
        semantic = COMPAT / semantic_name

        if not legacy.exists():
            blockers.append("PRE_EXECUTOR_LEGACY_WRAPPER_MISSING:" + legacy_name)
            continue
        if not semantic.exists():
            blockers.append("PRE_EXECUTOR_SEMANTIC_COMPAT_MISSING:" + semantic_name)
            continue

        legacy_text = legacy.read_text(encoding="utf-8")
        semantic_text = semantic.read_text(encoding="utf-8")
        meaningful = [line for line in legacy_text.splitlines() if line.strip()]

        if len(meaningful) > 12:
            blockers.append("PRE_EXECUTOR_LEGACY_WRAPPER_TOO_LARGE:" + legacy_name)
        if semantic_import not in legacy_text:
            blockers.append("PRE_EXECUTOR_LEGACY_WRAPPER_TARGET_INVALID:" + legacy_name)
        if "import *" not in legacy_text:
            blockers.append("PRE_EXECUTOR_LEGACY_WRAPPER_REEXPORT_MISSING:" + legacy_name)

        for forbidden in FORBIDDEN_NUMBERED_IMPORTS:
            if forbidden in semantic_text:
                blockers.append(
                    "PRE_EXECUTOR_SEMANTIC_COMPAT_NUMBERED_IMPORT:"
                    + semantic_name
                    + ":"
                    + forbidden
                )

        if not _module_all(semantic):
            blockers.append("PRE_EXECUTOR_SEMANTIC_COMPAT_EXPORT_EMPTY:" + semantic_name)

    if FULL_CYCLE.exists():
        full_cycle = FULL_CYCLE.read_text(encoding="utf-8")
        if "crypto_ai_system.governance.pre_executor_compat" in full_cycle:
            blockers.append("ACTIVE_ORCHESTRATION_IMPORTS_PRE_EXECUTOR_COMPAT")
        for forbidden in FORBIDDEN_NUMBERED_IMPORTS:
            if forbidden in full_cycle:
                blockers.append("ACTIVE_ORCHESTRATION_IMPORTS_NUMBERED_PRE_EXECUTOR:" + forbidden)
    else:
        blockers.append("RUN_FULL_CYCLE_MISSING")

    if not RETIREMENT.exists():
        blockers.append("PHASE7_15_17_RETIREMENT_CLOSURE_MANIFEST_MISSING")
    else:
        retirement = json.loads(RETIREMENT.read_text(encoding="utf-8"))
        expected = {
            "status": "PHASE7_15_17_NUMBERED_BUSINESS_LOGIC_RETIRED",
            "all_numbered_modules_are_thin_wrappers": True,
            "numbered_business_logic_still_present": False,
            "numbered_business_logic_retirement_complete": True,
            "runtime_authority": False,
            "execution_permissions_changed": False,
        }
        for field, value in expected.items():
            if retirement.get(field) != value:
                blockers.append("PHASE7_15_17_RETIREMENT_MANIFEST_INVALID:" + field)

        safety = retirement.get("safety") or {}
        unsafe = sorted(name for name, value in safety.items() if value is True)
        if unsafe:
            blockers.append("PHASE7_15_17_RETIREMENT_UNSAFE_FLAGS:" + ",".join(unsafe))

    if not CLOSURE.exists():
        blockers.append("PHASE7_LEAN_CLOSURE_MANIFEST_MISSING")
    else:
        closure = json.loads(CLOSURE.read_text(encoding="utf-8"))
        policy = closure.get("phase7_15_17_policy") or {}
        expected_policy = {
            "all_phase7_15_17_numbered_modules_are_thin_wrappers": True,
            "legacy_numbered_business_logic_still_present": False,
            "legacy_numbered_business_logic_retirement_pending": False,
            "legacy_numbered_business_logic_retirement_complete": True,
        }
        for field, value in expected_policy.items():
            if policy.get(field) is not value:
                blockers.append("PHASE7_LEAN_CLOSURE_RETIREMENT_POLICY_INVALID:" + field)

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)
        return 2

    print("PHASE7_15_17_NUMBERED_BUSINESS_LOGIC_RETIREMENT_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
