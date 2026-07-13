from __future__ import annotations

import json

from crypto_ai_system.validation.phase_d_candidate_manual_approval_chain import persist_phase_d_candidate_manual_approval_chain_report


if __name__ == "__main__":
    report = persist_phase_d_candidate_manual_approval_chain_report(create_manual_fixture=True)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
