from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from crypto_ai_system.validation.p71_extended_readonly_closure import (  # noqa: E402
    build_p71_closure_report,
    load_registry_records,
    persist_p71_closure_outputs,
)


def _read_json(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and persist P71 Extended public/private read-only closure evidence. No write endpoint is available."
    )
    parser.add_argument("--public-evidence", required=True)
    parser.add_argument("--private-receipt", required=True)
    parser.add_argument("--project-root", default=str(ROOT))
    parser.add_argument("--operator-session-id")
    parser.add_argument("--registry")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output", help="Optional explicit JSON copy of the resulting closure report")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    public = _read_json(args.public_evidence)
    private = _read_json(args.private_receipt)
    registry_path = Path(args.registry).resolve() if args.registry else project_root / "storage" / "registries" / "p71_consumed_evidence_registry.jsonl"

    if args.validate_only:
        report = build_p71_closure_report(
            public_evidence=public,
            private_receipt=private,
            consumed_registry_records=load_registry_records(registry_path),
            operator_session_id=args.operator_session_id,
        )
    else:
        report = persist_p71_closure_outputs(
            project_root=project_root,
            public_evidence=public,
            private_receipt=private,
            operator_session_id=args.operator_session_id,
            registry_path=registry_path,
        )

    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "status": report.get("status"),
                "p71_complete": report.get("p71_complete"),
                "closure_report_id": report.get("closure_report_id"),
                "closure_report_sha256": report.get("closure_report_sha256"),
                "closure_evidence_consumed": report.get("closure_evidence_consumed"),
                "public_websocket_valid": report.get("public_websocket_valid"),
                "private_account_websocket_valid": report.get("private_account_websocket_valid"),
                "block_reasons": report.get("block_reasons"),
                "ready_for_signed_testnet_execution": False,
                "testnet_order_submission_allowed": False,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0 if report.get("p71_complete") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
