from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent))

import yaml

from crypto_ai_system.execution.exchange_adapter_contract import DisabledExchangeAdapter
from crypto_ai_system.execution.signed_testnet_read_only_venue_probe_session import (
    build_signed_testnet_read_only_venue_probe_session,
)
from crypto_ai_system.execution.signed_testnet_probe_result_validator import (
    SIGNED_TESTNET_PROBE_RESULT_VALIDATOR_VERSION,
    build_read_only_venue_probe_result_summary,
    validate_read_only_venue_probe_result_summary,
)
from test_step277_signed_testnet_dry_run_session_recorder import _operator_ack, _order_intent, _readiness_packet  # type: ignore
from test_step278_signed_testnet_read_only_venue_probe_session import _operator_probe_ack  # type: ignore
from crypto_ai_system.execution.signed_testnet_dry_run_session_recorder import build_signed_testnet_dry_run_session_recorder


def _dry_run_recorder() -> dict:
    packet = _readiness_packet()
    return build_signed_testnet_dry_run_session_recorder(
        execution_readiness_packet=packet,
        operator_acknowledgement=_operator_ack(packet),
        order_intent=_order_intent(),
    )


def _step278_session() -> dict:
    recorder = _dry_run_recorder()
    return build_signed_testnet_read_only_venue_probe_session(
        dry_run_session_recorder=recorder,
        operator_acknowledgement=_operator_probe_ack(recorder),
        order_intent={**_order_intent(), "min_notional_usdt": 1},
        adapter=DisabledExchangeAdapter(),
    )


def test_step279_probe_result_summary_validates_step278_and_blocks_promotion(tmp_path: Path) -> None:
    session = _step278_session()
    summary = build_read_only_venue_probe_result_summary(
        read_only_probe_session=session,
        output_path=tmp_path / "step279_probe_result_summary.json",
    )
    assert summary["version"] == SIGNED_TESTNET_PROBE_RESULT_VALIDATOR_VERSION
    assert summary["probe_result_summary_review_ready"] is True
    assert summary["all_read_probes_valid"] is True
    assert summary["operator_acknowledgement_valid"] is True
    assert summary["place_cancel_disabled_evidence_valid"] is True
    assert summary["probe_close_report_hash_valid"] is True
    assert summary["probe_evidence_fresh"] is True
    assert summary["signed_testnet_execution_allowed"] is False
    assert summary["testnet_order_submission_allowed"] is False
    assert summary["signed_testnet_promotion_allowed"] is False
    assert summary["promotion_remains_blocked"] is True
    blocker = summary["signed_testnet_promotion_blocker"]
    assert blocker["promotion_status"] == "BLOCKED_BY_DESIGN_STEP279"
    assert "STEP279_SIGNED_TESTNET_PROMOTION_BLOCKED_PENDING_EXPLICIT_EXECUTION_STEP" in blocker["promotion_block_reasons"]
    assert Path(summary["probe_result_summary_path"]).exists()
    assert validate_read_only_venue_probe_result_summary(summary)["valid"] is True


def test_step279_blocks_tampered_step278_session_hash() -> None:
    session = _step278_session()
    session["read_only_venue_probe_session_sha256"] = "bad-hash"
    summary = build_read_only_venue_probe_result_summary(read_only_probe_session=session)
    assert summary["probe_result_summary_review_ready"] is False
    assert "STEP279_STEP278_READ_ONLY_PROBE_SESSION_INVALID" in summary["block_reasons"]


def test_step279_blocks_stale_probe_evidence() -> None:
    session = _step278_session()
    summary = build_read_only_venue_probe_result_summary(read_only_probe_session=session, max_probe_age_sec=-1)
    assert summary["probe_result_summary_review_ready"] is False
    assert summary["probe_evidence_fresh"] is False
    assert "STEP279_PROBE_EVIDENCE_STALE_BLOCKED" in summary["block_reasons"]


def test_step279_detects_place_cancel_disabled_evidence_tampering() -> None:
    session = _step278_session()
    session["read_only_venue_probe_evidence"]["place_order_block_probe"]["adapter_method_called"] = True
    summary = build_read_only_venue_probe_result_summary(read_only_probe_session=session)
    assert summary["probe_result_summary_review_ready"] is False
    assert summary["place_cancel_disabled_evidence_valid"] is False
    assert "STEP279_PLACE_ORDER_ADAPTER_METHOD_CALLED_BLOCKED" in summary["block_reasons"]


def test_step279_validation_blocks_promotion_flag_tampering() -> None:
    session = _step278_session()
    summary = build_read_only_venue_probe_result_summary(read_only_probe_session=session)
    assert validate_read_only_venue_probe_result_summary(summary)["valid"] is True
    summary["testnet_order_submission_allowed"] = True
    validation = validate_read_only_venue_probe_result_summary(summary)
    assert validation["valid"] is False
    assert "STEP279_TESTNET_ORDER_SUBMISSION_ALLOWED_INVARIANT_FAILED" in validation["block_reasons"]


def test_step279_detects_promotion_blocker_hash_tampering() -> None:
    session = _step278_session()
    summary = build_read_only_venue_probe_result_summary(read_only_probe_session=session)
    summary["signed_testnet_promotion_blocker"]["promotion_status"] = "ALLOWED"
    validation = validate_read_only_venue_probe_result_summary(summary)
    assert validation["valid"] is False
    assert "STEP279_PROMOTION_BLOCKER_STATUS_INVALID" in validation["block_reasons"]
    assert "STEP279_PROMOTION_BLOCKER_HASH_INVALID" in validation["block_reasons"]


def test_step279_detects_summary_hash_tampering() -> None:
    session = _step278_session()
    summary = build_read_only_venue_probe_result_summary(read_only_probe_session=session)
    summary["all_read_probes_valid"] = False
    validation = validate_read_only_venue_probe_result_summary(summary)
    assert validation["valid"] is False
    assert "STEP279_ALL_READ_PROBES_NOT_VALID" in validation["block_reasons"]
    assert "STEP279_PROBE_RESULT_SUMMARY_HASH_INVALID" in validation["block_reasons"]


def test_step279_config_version_and_safety_flags() -> None:
    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    assert settings["project"]["version"] == "p70_venue_neutral_execution_contract"
    cfg = settings["execution"]["signed_testnet_probe_result_validator"]
    assert cfg["enabled"] is False
    assert cfg["review_only"] is True
    assert cfg["require_step278_read_only_venue_probe_session"] is True
    assert cfg["require_probe_evidence_freshness"] is True
    assert cfg["require_all_read_probes_valid"] is True
    assert cfg["require_place_cancel_disabled_evidence"] is True
    assert cfg["require_probe_close_report_hash_valid"] is True
    assert cfg["require_operator_acknowledgement_valid"] is True
    assert cfg["signed_testnet_promotion_allowed"] is False
    assert cfg["testnet_order_submission_allowed"] is False
    assert cfg["place_order_enabled"] is False
    assert cfg["cancel_order_enabled"] is False
    assert settings["safety"]["live_trading_enabled"] is False
    assert settings["safety"]["testnet_signed_order_enabled"] is False
