from __future__ import annotations

import json
from pathlib import Path


MODULE_MAP = {
    "phase4_outcome_candidate_feedback.py": "outcome_candidate_feedback.py",
    "phase4_1_paper_outcome_sample_accumulation.py": "paper_sample_accumulation.py",
    "phase4_2_signal_drift_candidate_readiness.py": "signal_drift_readiness.py",
    "phase4_3_research_signal_score_bucket_replay.py": "signal_score_replay.py",
    "phase4_4_candidate_profile_review_packet.py": "candidate_review.py",
}

SCRIPT_IMPORTS = {
    "build_phase4_outcome_candidate_feedback.py":
        "crypto_ai_system.feedback.outcome_candidate_feedback",
    "build_phase4_1_paper_outcome_sample_accumulation.py":
        "crypto_ai_system.feedback.paper_sample_accumulation",
    "build_phase4_2_signal_drift_candidate_readiness.py":
        "crypto_ai_system.feedback.signal_drift_readiness",
    "build_phase4_3_research_signal_score_bucket_replay.py":
        "crypto_ai_system.feedback.signal_score_replay",
    "build_phase4_4_candidate_profile_review_packet.py":
        "crypto_ai_system.feedback.candidate_review",
}

FORBIDDEN_RUNTIME_TRUE = {
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "approval_packet_created",
    "auto_promotion_allowed",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    feedback = root / "src" / "crypto_ai_system" / "feedback"
    validation = root / "src" / "crypto_ai_system" / "validation"
    scripts = root / "scripts"
    blockers: list[str] = []

    required = {
        "review.py",
        "common.py",
        "paper_sample_accumulation.py",
        "outcome_candidate_feedback.py",
        "signal_drift_readiness.py",
        "signal_score_replay.py",
        "candidate_review.py",
    }
    for name in sorted(required):
        if not (feedback / name).exists():
            blockers.append(f"PHASE4_CANONICAL_MODULE_MISSING:{name}")

    for legacy_name, canonical_name in MODULE_MAP.items():
        legacy = validation / legacy_name
        canonical = feedback / canonical_name
        if not canonical.exists():
            blockers.append(f"PHASE4_CANONICAL_MODULE_MISSING:{canonical_name}")
        if not legacy.exists():
            blockers.append(f"PHASE4_LEGACY_WRAPPER_MISSING:{legacy_name}")
            continue
        text = legacy.read_text(encoding="utf-8")
        if "thin compatibility wrapper" not in text.lower():
            blockers.append(f"PHASE4_LEGACY_MODULE_NOT_WRAPPER:{legacy_name}")
        if len(text.splitlines()) > 12:
            blockers.append(f"PHASE4_LEGACY_WRAPPER_TOO_LARGE:{legacy_name}")

    for script_name, semantic_import in SCRIPT_IMPORTS.items():
        path = scripts / script_name
        if not path.exists():
            blockers.append(f"PHASE4_COMPAT_SCRIPT_MISSING:{script_name}")
            continue
        text = path.read_text(encoding="utf-8")
        if semantic_import not in text:
            blockers.append(f"PHASE4_SCRIPT_SEMANTIC_IMPORT_MISSING:{script_name}")
        if "crypto_ai_system.validation.phase4_" in text:
            blockers.append(f"PHASE4_SCRIPT_STILL_IMPORTS_LEGACY_PATH:{script_name}")

    # Active implementation and operational scripts must no longer import the old
    # Phase-number package paths. The five validation wrappers are excluded.
    excluded = {validation / name for name in MODULE_MAP}
    for base in (root / "src" / "crypto_ai_system", scripts):
        for path in base.rglob("*.py"):
            if path in excluded or path.name.startswith(("test_", "check_")):
                continue
            text = path.read_text(encoding="utf-8")
            if "crypto_ai_system.validation.phase4_" in text:
                blockers.append(
                    "PHASE4_ACTIVE_LEGACY_IMPORT:"
                    + str(path.relative_to(root)).replace("\\", "/")
                )

    full_cycle = (root / "run_full_cycle.py").read_text(encoding="utf-8")
    if "from crypto_ai_system.feedback.review import run_feedback_review_chain" not in full_cycle:
        blockers.append("PHASE4_UNIFIED_FEEDBACK_ENTRY_MISSING")
    if "from crypto_ai_system.validation.phase4_" in full_cycle:
        blockers.append("PHASE4_FULL_CYCLE_STILL_IMPORTS_LEGACY_PATH")

    closure_path = root / "config" / "lean" / "phase4_lean_closure.json"
    if not closure_path.exists():
        blockers.append("PHASE4_CLOSURE_MANIFEST_MISSING")
    else:
        payload = json.loads(closure_path.read_text(encoding="utf-8"))
        if payload.get("status") != "PHASE4_LEAN_MERGE_CLOSED":
            blockers.append("PHASE4_CLOSURE_STATUS_INVALID")
        if payload.get("runtime_authority") is not False:
            blockers.append("PHASE4_RUNTIME_AUTHORITY_MUST_BE_FALSE")
        safety = payload.get("safety") or {}
        for flag in sorted(FORBIDDEN_RUNTIME_TRUE):
            if safety.get(flag) is not False:
                blockers.append(f"PHASE4_UNSAFE_CLOSURE_FLAG:{flag}")

    history = root / "docs" / "history" / "PHASE4_FEEDBACK_DEVELOPMENT_SUMMARY.md"
    if not history.exists():
        blockers.append("PHASE4_CONSOLIDATED_HISTORY_MISSING")

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)
        return 2

    print("PHASE4_LEAN_CLOSURE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
