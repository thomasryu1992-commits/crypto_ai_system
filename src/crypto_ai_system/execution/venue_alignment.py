from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

PRIMARY_EXECUTION_VENUE = "extended"
EXTENDED_TESTNET_VENUE = "extended_starknet_sepolia"
BINANCE_REFERENCE_VENUE = "binance_futures_testnet"


@dataclass(frozen=True)
class VenueAlignmentPolicy:
    primary_execution_venue: str = PRIMARY_EXECUTION_VENUE
    primary_testnet_venue: str = EXTENDED_TESTNET_VENUE
    binance_branch_status: str = "REFERENCE_ONLY_BINANCE_BRANCH"
    binance_reference_branch_runtime_enabled: bool = False
    cross_venue_evidence_import_allowed: bool = False
    runtime_auto_route_allowed: bool = False
    execution_frozen_until_extended_alignment_validated: bool = True
    extended_alignment_validated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_venue_alignment(policy: Mapping[str, Any] | VenueAlignmentPolicy) -> dict[str, Any]:
    data = policy.to_dict() if isinstance(policy, VenueAlignmentPolicy) else dict(policy or {})
    blockers: list[str] = []
    if data.get("primary_execution_venue") != PRIMARY_EXECUTION_VENUE:
        blockers.append("PRIMARY_EXECUTION_VENUE_MUST_BE_EXTENDED")
    if data.get("primary_testnet_venue") != EXTENDED_TESTNET_VENUE:
        blockers.append("PRIMARY_TESTNET_VENUE_MUST_BE_EXTENDED_STARKNET_SEPOLIA")
    if data.get("binance_branch_status") != "REFERENCE_ONLY_BINANCE_BRANCH":
        blockers.append("BINANCE_BRANCH_MUST_BE_REFERENCE_ONLY")
    for field in ("binance_reference_branch_runtime_enabled", "cross_venue_evidence_import_allowed", "runtime_auto_route_allowed"):
        if data.get(field) is not False:
            blockers.append(f"{field.upper()}_MUST_BE_FALSE")
    return {"valid": not blockers, "block_reasons": sorted(blockers), "policy": data}


def validate_evidence_venue_for_primary_execution(evidence_venue: str | None, *, target_venue: str = EXTENDED_TESTNET_VENUE) -> dict[str, Any]:
    evidence = str(evidence_venue or "").strip().lower()
    target = str(target_venue or "").strip().lower()
    blockers: list[str] = []
    if not evidence:
        blockers.append("EVIDENCE_VENUE_MISSING")
    if target != EXTENDED_TESTNET_VENUE:
        blockers.append("PRIMARY_TARGET_VENUE_NOT_EXTENDED")
    if evidence and evidence != target:
        blockers.append("CROSS_VENUE_EVIDENCE_IMPORT_BLOCKED")
    if evidence == BINANCE_REFERENCE_VENUE:
        blockers.append("BINANCE_REFERENCE_EVIDENCE_NOT_RUNTIME_ELIGIBLE")
    return {"valid": not blockers, "evidence_venue": evidence or None, "target_venue": target or None, "cross_venue_evidence_import_allowed": False, "block_reasons": sorted(set(blockers))}
