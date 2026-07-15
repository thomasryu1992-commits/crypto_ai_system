# P36 Non-Developer Onboarding Wizard / ZIP Drop-in Guide Report

Status: `P36_NON_DEVELOPER_ONBOARDING_WIZARD_GENERATED_REVIEW_ONLY`

This phase adds a review-only onboarding wizard for non-developer operators. It explains where to place the ZIP, which read-only commands to run, which unsafe command families to avoid, and how to interpret common waiting/failure messages.

This phase does not enable runtime, scheduler, live/testnet order submission, endpoint calls, signature creation, secret access, settings mutation, score weight mutation, or auto-promotion.

Generated artifacts:

- `storage/latest/p36_non_developer_onboarding_wizard_report.json`
- `storage/latest/p36_non_developer_onboarding_wizard_summary.json`
- `storage/latest/p36_non_developer_onboarding_wizard_pack.json`
- `storage/latest/p36_onboarding_wizard_steps.json`
- `storage/latest/p36_zip_drop_in_wizard.md`
- `storage/latest/p36_zip_drop_in_checklist.md`
- `storage/latest/p36_failure_message_lookup.md`
- `storage/latest/p36_operator_onboarding_card.json`
- `storage/latest/p36_non_developer_onboarding_wizard_negative_fixture_results.json`

Allowed commands remain limited to `status`, `matrix`, `waiting`, `no_go`, and `export_paths`.
