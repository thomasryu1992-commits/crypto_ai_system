# P52 - P7 Accepted Evidence Import Packet Staging

Status: `P52_P7_ACCEPTED_EVIDENCE_IMPORT_PACKET_STAGING_READY_REVIEW_ONLY_NO_SUBMIT`

P52 stages a P7 import packet only after P51 proves, by dry-run, that a P50-validated external-runtime signed-testnet evidence candidate would be accepted by P7. P52 does not persist P7 status, does not write a real P7 report, and does not grant runtime authority.

## Boundary

P52 is a staging layer only:

- No order submission
- No order/status/cancel endpoint calls
- No HTTP request creation
- No signature creation
- No secret access
- No P7 valid status write
- No P8 repeated clean session promotion
- No P9/P10/P15/P16 enablement

## Staged packet contents

The staged packet contains safe metadata and hashes:

- Source P51 dry-run id/hash
- Candidate hash and hash-match evidence
- P7 input preview metadata
- Evidence section hashes
- External evidence reference paths
- ID chain metadata required for later P7 import

It does not embed raw exchange responses, raw signed payloads, raw request bodies, or secret values.

## Next step

A separate operator-controlled P7 import action must review the staged packet and explicitly persist the real P7 post-submit evidence. Until that happens, P7 remains waiting/review-only and P8 remains waiting.
