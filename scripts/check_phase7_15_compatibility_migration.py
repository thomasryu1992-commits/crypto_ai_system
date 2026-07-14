#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "src/crypto_ai_system/validation/phase7_15_operator_decision_intake_template.py"
SEMANTIC = ROOT / "src/crypto_ai_system/governance/pre_executor_compat/operator_decision_intake.py"
PHASE7_16_LEGACY = ROOT / "src/crypto_ai_system/validation/phase7_16_operator_decision_intake_validator.py"
PHASE7_16_SEMANTIC = ROOT / "src/crypto_ai_system/governance/pre_executor_compat/operator_decision_validation.py"
MANIFEST = ROOT / "config/lean/phase7_15_public_surface.json"
CLOSURE = ROOT / "config/lean/phase7_lean_closure.json"
FULL_CYCLE = ROOT / "run_full_cycle.py"

SEMANTIC_IMPORT = (
    "crypto_ai_system.governance.pre_executor_compat."
    "operator_decision_intake"
)
FORBIDDEN_NUMBERED_IMPORT = (
    "crypto_ai_system.validation."
    "phase7_15_operator_decision_intake_template"
)
FORBIDDEN_PHASE7_14_IMPORT = (
    "crypto_ai_system.validation."
    "phase7_14_future_executor_operator_decision_packet"
)
CRITICAL_PUBLIC_SYMBOLS = {
    "ALLOWED_DECISION_OPTIONS",
    "OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS",
    "persist_phase7_15_operator_decision_intake_template_report",
    "validate_operator_decision_intake_template",
}


def _module_all(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
                value = node.value
                try:
                    result = ast.literal_eval(value)
                except (ValueError, SyntaxError) as exc:
                    raise RuntimeError(f"Invalid __all__ in {path}: {exc}") from exc
                if not isinstance(result, (list, tuple)) or not all(isinstance(item, str) for item in result):
                    raise RuntimeError(f"__all__ must be a string list in {path}")
                return list(result)
    raise RuntimeError(f"__all__ missing in {path}")


def main() -> int:
    blockers: list[str] = []

    for path, code in (
        (LEGACY, "PHASE7_15_LEGACY_WRAPPER_MISSING"),
        (SEMANTIC, "PHASE7_15_SEMANTIC_COMPAT_MODULE_MISSING"),
        (MANIFEST, "PHASE7_15_PUBLIC_SURFACE_MANIFEST_MISSING"),
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
    meaningful_legacy_lines = [line for line in legacy_text.splitlines() if line.strip()]

    if len(meaningful_legacy_lines) > 12:
        blockers.append("PHASE7_15_LEGACY_WRAPPER_TOO_LARGE")
    if SEMANTIC_IMPORT not in legacy_text:
        blockers.append("PHASE7_15_LEGACY_WRAPPER_TARGET_INVALID")
    if FORBIDDEN_PHASE7_14_IMPORT in semantic_text:
        blockers.append("PHASE7_15_SEMANTIC_COMPAT_IMPORTS_NUMBERED_PHASE7_14")

    phase7_16_path = PHASE7_16_SEMANTIC if PHASE7_16_SEMANTIC.exists() else PHASE7_16_LEGACY
    if not phase7_16_path.exists():
        blockers.append("PHASE7_16_CONSUMER_MISSING")
    else:
        phase7_16_text = phase7_16_path.read_text(encoding="utf-8")
        if FORBIDDEN_NUMBERED_IMPORT in phase7_16_text:
            blockers.append("PHASE7_16_STILL_IMPORTS_NUMBERED_PHASE7_15")
        if SEMANTIC_IMPORT not in phase7_16_text:
            blockers.append("PHASE7_16_SEMANTIC_PHASE7_15_IMPORT_MISSING")

    full_cycle_text = FULL_CYCLE.read_text(encoding="utf-8") if FULL_CYCLE.exists() else ""
    if "crypto_ai_system.governance.pre_executor_compat" in full_cycle_text:
        blockers.append("ACTIVE_FULL_CYCLE_IMPORTS_PRE_EXECUTOR_COMPAT")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    exported = _module_all(SEMANTIC)
    expected = manifest.get("exported_public_symbols") or []

    if exported != expected:
        blockers.append("PHASE7_15_EXPORTED_PUBLIC_SURFACE_DRIFT")
    if not CRITICAL_PUBLIC_SYMBOLS <= set(exported):
        blockers.append(
            "PHASE7_15_CRITICAL_PUBLIC_SYMBOLS_MISSING:"
            + ",".join(sorted(CRITICAL_PUBLIC_SYMBOLS - set(exported)))
        )

    if manifest.get("runtime_authority") is not False:
        blockers.append("PHASE7_15_PUBLIC_SURFACE_RUNTIME_AUTHORITY_INVALID")
    if manifest.get("execution_permissions_changed") is not False:
        blockers.append("PHASE7_15_PUBLIC_SURFACE_EXECUTION_PERMISSION_CHANGE_INVALID")
    if manifest.get("legacy_numbered_module_is_thin_wrapper") is not True:
        blockers.append("PHASE7_15_THIN_WRAPPER_MANIFEST_INVALID")
    if manifest.get("active_orchestration_uses_compat_module") is not False:
        blockers.append("PHASE7_15_ACTIVE_COMPAT_IMPORT_POLICY_INVALID")

    closure = json.loads(CLOSURE.read_text(encoding="utf-8"))
    policy = closure.get("phase7_15_17_policy") or {}
    for field in (
        "phase7_15_numbered_module_is_thin_wrapper",
        "phase7_15_business_logic_relocated_without_contract_change",
    ):
        if policy.get(field) is not True:
            blockers.append(f"PHASE7_15_POLICY_INVALID:{field}")

    safety = closure.get("safety") or {}
    unsafe = sorted(name for name, value in safety.items() if value is True)
    if unsafe:
        blockers.append("PHASE7_15_MIGRATION_UNSAFE_FLAGS:" + ",".join(unsafe))

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)
        return 2

    print("PHASE7_15_COMPATIBILITY_MIGRATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
