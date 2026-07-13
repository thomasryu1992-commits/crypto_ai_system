from __future__ import annotations

import argparse
import json
from pathlib import Path

from .probe import ExtendedPrivateReadOnlyProbe, PrivateReadOnlyProbePolicy
from .windows_credential_provider import read_generic_credential_secret


def main() -> int:
    parser = argparse.ArgumentParser(
        description="External GET-only REST + authenticated account-stream P71 probe using Windows Credential Manager"
    )
    parser.add_argument("--credential-target", required=True, help="Windows Generic Credential target name; never the secret value")
    parser.add_argument("--credential-reference-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--network-enabled", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--stream-url-override",
        help="Optional wss:// Extended Starknet Sepolia stream base URL override; never the credential value",
    )
    args = parser.parse_args()

    api_key = read_generic_credential_secret(args.credential_target)
    probe = ExtendedPrivateReadOnlyProbe(
        api_key=api_key,
        policy=PrivateReadOnlyProbePolicy(
            credential_reference_id=args.credential_reference_id,
            network_enabled=args.network_enabled,
            timeout_seconds=args.timeout_seconds,
            stream_url_override=args.stream_url_override,
            source_is_fixture=False,
        ),
    )
    receipt = probe.run()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt_sha256": receipt.get("receipt_sha256"),
                "read_session_id": receipt.get("read_session_id"),
                "actual_network_read_performed": receipt.get("actual_network_read_performed"),
                "private_account_stream_valid": (receipt.get("account_stream_receipt") or {}).get("initial_snapshot_valid") is True,
                "private_account_stream_failure_reason": (receipt.get("account_stream_receipt") or {}).get("stream_failure_reason"),
                "private_account_stream_endpoint_source": (receipt.get("account_stream_receipt") or {}).get("stream_url_source"),
                "private_account_stream_host": (receipt.get("account_stream_receipt") or {}).get("stream_host"),
                "rest_ws_consistency_valid": receipt.get("rest_ws_consistency_valid"),
                "write_call_performed": False,
                "signature_created": False,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt.get("actual_network_read_performed") and receipt.get("rest_ws_consistency_valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
