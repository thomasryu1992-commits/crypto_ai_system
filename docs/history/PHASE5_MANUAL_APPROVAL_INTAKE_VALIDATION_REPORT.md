# Phase 5 Manual Approval Intake Validation Report

Phase 5 adds a review-only manual approval intake validation layer after Phase 4.4 candidate profile review packet generation.

The validator reads `approval_packet_draft_review_only.json`, `candidate_profile_review_packet.json`, the Phase 4.3 source report, and the drift-reduced candidate profile draft. It validates hash-chain continuity and then requires a separate manual approval submission containing approver information, ticket/signature evidence, approval packet ID, approval intake ID, source report hash, approval packet hash, feature matrix hash, profile candidate hash, and canonical UTC timestamp.

In the packaged baseline there is no manual approval submission, so Phase 5 must fail closed with `PHASE5_MANUAL_APPROVAL_INTAKE_BLOCKED_REVIEW_ONLY` and `MANUAL_APPROVAL_SUBMISSION_MISSING`.

This phase does not create an approved approval packet, does not validate an approval intake, does not mutate `settings.yaml`, does not mutate runtime `score_weights`, does not apply the candidate profile, does not read API key values, does not read or create secret files, does not submit signed testnet/live orders, and does not unlock signed testnet or live execution.
