# P27 Operator Runtime Activation Request Intake Validator

Status: review-only / disabled-by-default.

This phase validates a human-filled operator runtime activation request intake created from the P26 template. It checks operator identity, ticket/signature evidence, exact request phrase, P26/P25 hash-chain continuity, no-runtime-authority acknowledgement, no-secret/no-endpoint/no-scheduler acknowledgements, cap acknowledgements, kill switch acknowledgements, rollback/full-shutdown acknowledgements, monitoring/reporting acknowledgements, idempotency, post-submit relock, and canonical ID chain acknowledgements.

This packet does not enable runtime, does not start a scheduler, does not submit orders, does not create signatures, does not call endpoints, and does not access secret values.
