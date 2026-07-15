# STEP301 Review-only Export Packet v2 Report

## Goal
Create a review-only export packet that gives an operator one directory containing the human review summary, lineage evidence, signal debug evidence, market thesis note, paper decision preview, risk gate report, approval packet candidate preview, and disabled settings-write preview.

## Implemented
- Added `src/crypto_ai_system/reports/review_only_export_packet.py`.
- Added append-only `review_only_export_packet_registry.jsonl` support.
- Connected `run_full_cycle.py` and `run_operational_dry_run.py` to generate review-only export packet evidence.
- Added Step301 tests for required files, lineage preservation, approval packet candidate safety, registry append, latest mirrors, and missing-artifact fail-safe behavior.

## Output files
The module writes a packet directory under `storage/review_packets/<review_only_export_packet_id>/` containing:

- `human_review_summary.md`
- `feature_lineage.json`
- `research_signal_debug.json`
- `market_thesis_note.json`
- `paper_decision_preview.json`
- `risk_gate_report.json`
- `approval_packet_candidate.json`
- `disabled_settings_write_preview.diff`
- `review_only_export_packet_manifest.json`

Latest mirrors:

- `storage/latest/review_only_export_packet_manifest.json`
- `storage/latest/review_only_export_packet_registry_record.json`

Registry:

- `storage/registries/review_only_export_packet_registry.jsonl`

## Safety
This module does not:

- mutate `settings.yaml`
- mutate runtime `score_weights`
- apply candidate profiles
- create valid approval packets or approval intakes
- submit signed testnet orders
- submit live orders
- enable automatic promotion

## Roadmap progress check
The previously created Phase1~7 roadmap is now complete through Step301.

- Phase 1 Step282~285: complete
- Phase 2 Step286~290: complete
- Phase 3 Step291~296: complete
- Phase 4 Step297~301: complete through review-only export packet; Step302 remains
- Phase 5 Step303~310: not started
- Phase 6 Step311~318: not started
- Phase 7 Step319: not started

Current roadmap count: 20 of 38 roadmap steps complete: Step282~301.
Remaining: 18 steps: Step302~319.

## Validation commands
- `PYTHONPATH=src python -m compileall -q src config tests`
- `PYTHONPATH=src python scripts/status_consistency_checker.py .`
- `PYTHONPATH=src pytest -q tests/test_step301_*.py tests/test_step282_*.py`
- `PYTHONPATH=src pytest -q tests/test_step294_*.py tests/test_step295_*.py tests/test_step296_*.py tests/test_step297_*.py tests/test_step298_*.py tests/test_step299_*.py tests/test_step300_*.py tests/test_step301_*.py`
- `PYTHONPATH=src python run_operational_dry_run.py`
- `PYTHONPATH=src python run_full_cycle.py`
