from __future__ import annotations

import json

from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts


def main() -> int:
    report = persist_valid_price_lineage_artifacts()
    print(report.get("status"))
    print(json.dumps({
        "passed": report.get("passed"),
        "data_snapshot_id": report.get("data_snapshot_id"),
        "feature_snapshot_id": report.get("feature_snapshot_id"),
        "feature_matrix_sha256": report.get("feature_matrix_sha256"),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
