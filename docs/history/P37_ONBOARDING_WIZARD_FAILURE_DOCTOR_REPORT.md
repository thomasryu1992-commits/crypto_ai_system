# P37 Onboarding Wizard Failure Doctor / Self-Diagnosis Pack Report

P37 adds a review-only self-diagnosis layer for non-developer onboarding issues.

It detects common ZIP drop-in and dashboard lookup failures such as:

- no_zip_found
- bad_zip_structure
- missing_scripts
- missing_src_package
- missing_storage_latest
- missing_p36_artifacts
- blocked_command_attempt
- secret_detected
- runtime_flag_truthy
- scheduler_enabled
- endpoint_called
- p36_waiting
- p36_blocked

This package does not enable runtime, scheduler, order submission, endpoint calls, secret access, settings mutation, score-weight mutation, or auto-promotion.
