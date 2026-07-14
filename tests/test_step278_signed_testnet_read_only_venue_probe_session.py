from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent))

import yaml

from crypto_ai_system.execution.exchange_adapter_contract import DisabledExchangeAdapter
from crypto_ai_system.execution.signed_testnet_read_only_venue_probe_session import (
    SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_VERSION,
    build_signed_testnet_read_only_venue_probe_session,
    validate_signed_testnet_read_only_venue_probe_session,
)
from crypto_ai_system.utils.audit import utc_now_canonical
from test_step277_signed_testnet_dry_run_session_recorder import (  # type: ignore
    _operator_ack,
    _order_intent,
    _readiness_packet,
)
from crypto_ai_system.execution.signed_testnet_dry_run_session_recorder import build_signed_testnet_dry_run_session_recorder


def _dry_run_recorder() -> dict:
    packet = _readiness_packet()
    return build_signed_testnet_dry_run_session_recorder(
        execution_readiness_packet=packet,
        operator_acknowledgement=_operator_ack(packet),
        order_intent=_order_intent(),
    )


def _operator_probe_ack(recorder: dict) -> dict:
    return {
        "operator_id": "operator_thomas_step278_review_only",
        "operator_role": "operator",
        "probe_ticket_id": "TICKET-STEP278-READ-ONLY-PROBE",
        "operator_signature": "operator-acknowledged-read-only-venue-probe-review-only",
        "timestamp_utc": utc_now_canonical(),
        "signed_testnet_dry_run_session_recorder_id": recorder["signed_testnet_dry_run_session_recorder_id"],
        "dry_run_session_sha256": recorder["dry_run_session_sha256"],
        "testnet_execution_session_id": recorder["testnet_execution_session_id"],
        "operator_acknowledges_read_only_probe_only": True,
        "operator_acknowledges_no_order_submission": True,
        "operator_acknowledges_place_order_disabled": True,
        "operator_acknowledges_cancel_order_disabled": True,
        "operator_confirms_order_submission_enabled": False,
        "operator_confirms_place_order_enabled": False,
        "operator_confirms_cancel_order_enabled": False,
    }


def test_step278_read_only_venue_probe_session_links_step277_and_remains_disabled(tmp_path: Path) -> None:
    recorder = _dry_run_recorder()
    session = build_signed_testnet_read_only_venue_probe_session(
        dry_run_session_recorder=recorder,
        operator_acknowledgement=_operator_probe_ack(recorder),
        order_intent={**_order_intent(), "min_notional_usdt": 1},
        adapter=DisabledExchangeAdapter(),
        symbol="BTCUSDT",
        output_path=tmp_path / "step278_read_only_probe_session.json",
    )
    assert session["version"] == SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_VERSION
    assert session["probe_session_review_ready"] is True
    assert session["testnet_execution_session_id"] == recorder["testnet_execution_session_id"]
    evidence = session["read_only_venue_probe_evidence"]
    assert evidence["valid"] is True
    for section in [
        "balance_read_probe",
        "positions_read_probe",
        "open_orders_read_probe",
        "orderbook_read_probe",
        "fee_estimate_probe",
        "slippage_estimate_probe",
        "min_order_size_probe",
        "fetch_order_probe",
    ]:
        assert evidence[section]["valid"] is True
    assert evidence["place_order_block_probe"]["adapter_method_called"] is False
    assert evidence["cancel_order_block_probe"]["adapter_method_called"] is False
    assert session["ready_for_signed_testnet_execution"] is False
    assert session["testnet_order_submission_allowed"] is False
    assert session["external_order_submission_performed"] is False
    assert session["place_order_enabled"] is False
    assert session["cancel_order_enabled"] is False
    assert session["signed_order_executor_enabled"] is False
    assert session["adapter_place_order_called"] is False
    assert session["adapter_cancel_order_called"] is False
    assert Path(session["probe_session_path"]).exists()
    assert validate_signed_testnet_read_only_venue_probe_session(session)["valid"] is True


def test_step278_blocks_operator_ack_hash_mismatch() -> None:
    recorder = _dry_run_recorder()
    ack = _operator_probe_ack(recorder)
    ack["dry_run_session_sha256"] = "bad-hash"
    session = build_signed_testnet_read_only_venue_probe_session(
        dry_run_session_recorder=recorder,
        operator_acknowledgement=ack,
        order_intent={**_order_intent(), "min_notional_usdt": 1},
        adapter=DisabledExchangeAdapter(),
    )
    assert session["probe_session_review_ready"] is False
    assert "STEP278_OPERATOR_PROBE_ACK_DRY_RUN_HASH_MISMATCH" in session["block_reasons"]


def test_step278_blocks_any_submission_enabled_flags() -> None:
    recorder = _dry_run_recorder()
    ack = _operator_probe_ack(recorder)
    ack["operator_confirms_place_order_enabled"] = True
    session = build_signed_testnet_read_only_venue_probe_session(
        dry_run_session_recorder=recorder,
        operator_acknowledgement=ack,
        order_intent={**_order_intent(), "min_notional_usdt": 1},
        adapter=DisabledExchangeAdapter(),
    )
    assert session["probe_session_review_ready"] is False
    assert "STEP278_OPERATOR_CONFIRMS_PLACE_ORDER_ENABLED_BLOCKED" in session["block_reasons"]


def test_step278_blocks_min_order_invalid() -> None:
    recorder = _dry_run_recorder()
    session = build_signed_testnet_read_only_venue_probe_session(
        dry_run_session_recorder=recorder,
        operator_acknowledgement=_operator_probe_ack(recorder),
        order_intent={**_order_intent(), "min_notional_usdt": 10},
        adapter=DisabledExchangeAdapter(),
    )
    assert session["probe_session_review_ready"] is False
    assert "STEP278_MIN_ORDER_SIZE_PROBE_INVALID" in session["block_reasons"]


def test_step278_detects_probe_hash_tampering() -> None:
    recorder = _dry_run_recorder()
    session = build_signed_testnet_read_only_venue_probe_session(
        dry_run_session_recorder=recorder,
        operator_acknowledgement=_operator_probe_ack(recorder),
        order_intent={**_order_intent(), "min_notional_usdt": 1},
        adapter=DisabledExchangeAdapter(),
    )
    assert validate_signed_testnet_read_only_venue_probe_session(session)["valid"] is True
    session["read_only_venue_probe_evidence"]["balance_read_probe"]["adapter_response"]["status"] = "TAMPERED"
    validation = validate_signed_testnet_read_only_venue_probe_session(session)
    assert validation["valid"] is False
    assert "STEP278_BALANCE_READ_PROBE_HASH_INVALID" in validation["block_reasons"]


def test_step278_detects_session_event_hash_tampering() -> None:
    recorder = _dry_run_recorder()
    session = build_signed_testnet_read_only_venue_probe_session(
        dry_run_session_recorder=recorder,
        operator_acknowledgement=_operator_probe_ack(recorder),
        order_intent={**_order_intent(), "min_notional_usdt": 1},
        adapter=DisabledExchangeAdapter(),
    )
    session["probe_event_log"][0]["event_type"] = "TAMPERED"
    validation = validate_signed_testnet_read_only_venue_probe_session(session)
    assert validation["valid"] is False
    assert "STEP278_PROBE_EVENT_HASH_INVALID" in validation["block_reasons"]


def test_step278_config_version_and_safety_flags() -> None:
    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    assert settings["project"]["version"] == "p70_venue_neutral_execution_contract"
    probe_cfg = settings["execution"]["signed_testnet_read_only_venue_probe_session"]
    assert probe_cfg["enabled"] is False
    assert probe_cfg["review_only"] is True
    assert probe_cfg["require_step277_dry_run_session_recorder"] is True
    assert probe_cfg["require_balance_read_probe"] is True
    assert probe_cfg["require_position_read_probe"] is True
    assert probe_cfg["require_orderbook_read_probe"] is True
    assert probe_cfg["require_fee_estimate_probe"] is True
    assert probe_cfg["require_slippage_estimate_probe"] is True
    assert probe_cfg["require_min_order_validation_probe"] is True
    assert probe_cfg["require_fetch_order_probe"] is True
    assert probe_cfg["place_order_enabled"] is False
    assert probe_cfg["cancel_order_enabled"] is False
    assert probe_cfg["testnet_order_submission_allowed"] is False
    assert probe_cfg["external_order_submission_allowed"] is False
    assert settings["safety"]["live_trading_enabled"] is False
    assert settings["safety"]["testnet_signed_order_enabled"] is False
