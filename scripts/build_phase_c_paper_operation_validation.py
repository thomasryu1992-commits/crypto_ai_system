from __future__ import annotations

import json

from crypto_ai_system.validation.phase_c_paper_operation_validation import persist_phase_c_paper_operation_validation_report


if __name__ == "__main__":
    report = persist_phase_c_paper_operation_validation_report(run_upstream=True, min_closed_sample_size=30)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
