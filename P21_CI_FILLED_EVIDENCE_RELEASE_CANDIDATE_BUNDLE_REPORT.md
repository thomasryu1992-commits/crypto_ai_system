# P21 CI Filled Evidence Release Candidate Bundle - Review Only

This package adds a release-candidate bundle validator for externally filled Docker / Launcher evidence.

Scope:

- Validate P19 filled external Docker build / Docker run / Launcher import evidence.
- Verify evidence hashes against the P19 intake report.
- Verify the P20 artifact manifest and P18 hash chain.
- Export a review-only release candidate bundle only when all CI evidence is valid.
- Keep all execution flags disabled.

This module does not run Docker, mutate Launcher state, submit orders, start schedulers, read secrets, or grant runtime authority.
