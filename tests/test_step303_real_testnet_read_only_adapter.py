from __future__ import annotations

from pathlib import Path
import yaml

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.real_testnet_read_only_adapter import (
    BinanceFuturesTestnetReadOnlyAdapter,
    ExtendedTestnetReadOnlyAdapter,
    ReadOnlyAdapterPolicyError,
    build_real_testnet_read_only_adapter_evidence,
    build_read_only_testnet_adapter,
    persist_real_testnet_read_only_adapter_evidence,
    run_real_testnet_read_only_adapter_latest,
    validate_real_testnet_read_only_capabilities,
)


def _order_intent() -> dict:
    return {
        "order_intent_id": "order_intent_step303_unit",
        "symbol": "BTCUSDT",
        "notional_usdt": 5,
        "min_notional_usdt": 1,
        "fee_bps": 2.5,
        "slippage_bps": 3.0,
    }


def test_step303_binance_read_only_adapter_capabilities_are_testnet_only_and_no_write() -> None:
    adapter = BinanceFuturesTestnetReadOnlyAdapter()
    capabilities = adapter.get_capabilities()
    validation = validate_real_testnet_read_only_capabilities(capabilities)
    assert validation["valid"] is True
    assert capabilities["venue"] == "binance_futures_testnet"
    assert capabilities["testnet_only"] is True
    assert capabilities["read_only"] is True
    assert capabilities["supports_balance_read"] is True
    assert capabilities["supports_positions_read"] is True
    assert capabilities["supports_open_orders_read"] is True
    assert capabilities["supports_orderbook_read"] is True
    assert capabilities["supports_fee_estimate"] is True
    assert capabilities["supports_slippage_estimate"] is True
    assert capabilities["supports_min_order_validation"] is True
    assert capabilities["supports_fetch_order"] is True
    assert capabilities["supports_place_order"] is False
    assert capabilities["supports_cancel_order"] is False
    assert capabilities["testnet_order_submission_allowed"] is False
    assert capabilities["api_key_value_access_allowed"] is False
    assert capabilities["api_secret_value_access_allowed"] is False
    assert capabilities["secret_file_access_allowed"] is False
    assert capabilities["secret_file_creation_allowed"] is False


def test_step303_blocks_mainnet_or_live_base_url() -> None:
    try:
        BinanceFuturesTestnetReadOnlyAdapter(base_url="https://fapi.binance.com")
    except ReadOnlyAdapterPolicyError as exc:
        assert "testnet" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("mainnet base URL must be blocked")


def test_step303_read_methods_may_use_injected_read_transport_but_never_submit_orders() -> None:
    calls: list[tuple[str, str, dict]] = []

    def transport(method: str, path: str, params: dict) -> dict:
        calls.append((method, path, dict(params)))
        return {"ok": True, "path": path, "params": dict(params)}

    adapter = ExtendedTestnetReadOnlyAdapter(read_transport=transport)
    balance = adapter.get_balance()
    orderbook = adapter.get_orderbook("BTCUSDT")
    fee = adapter.estimate_fee(_order_intent())
    assert balance["read_transport_called"] is True
    assert orderbook["external_order_submission_performed"] is False
    assert fee["estimated_fee_usdt"] > 0
    assert calls and all(call[0] == "GET" for call in calls)

    placed = adapter.place_order(_order_intent())
    cancelled = adapter.cancel_order("abc123")
    assert placed["submitted"] is False
    assert cancelled["submitted"] is False
    assert placed["read_transport_called"] is False
    assert cancelled["read_transport_called"] is False
    assert placed["external_order_submission_performed"] is False
    assert placed["testnet_order_submission_allowed"] is False


def test_step303_adapter_evidence_records_all_read_probes_and_blocked_write_probes() -> None:
    evidence = build_real_testnet_read_only_adapter_evidence(
        adapter=build_read_only_testnet_adapter("binance_futures_testnet"),
        order_intent=_order_intent(),
        symbol="BTCUSDT",
    )
    assert evidence["adapter_ready_for_read_only_testnet_probe"] is True
    assert evidence["all_read_probes_valid"] is True
    assert evidence["place_cancel_disabled_evidence_valid"] is True
    assert evidence["ready_for_signed_testnet_execution"] is False
    assert evidence["testnet_order_submission_allowed"] is False
    assert evidence["external_order_submission_performed"] is False
    assert evidence["place_order_enabled"] is False
    assert evidence["cancel_order_enabled"] is False
    assert evidence["signed_order_executor_enabled"] is False
    assert set(evidence["read_only_probes"]) == {
        "balance_read_probe",
        "positions_read_probe",
        "open_orders_read_probe",
        "orderbook_read_probe",
        "fee_estimate_probe",
        "slippage_estimate_probe",
        "min_order_size_probe",
        "fetch_order_probe",
    }
    assert set(evidence["blocked_write_probes"]) == {"place_order_block_probe", "cancel_order_block_probe"}


def test_step303_evidence_blocks_invalid_min_order_size() -> None:
    evidence = build_real_testnet_read_only_adapter_evidence(
        adapter=BinanceFuturesTestnetReadOnlyAdapter(),
        order_intent={**_order_intent(), "notional_usdt": 0.1, "min_notional_usdt": 1},
    )
    assert evidence["adapter_ready_for_read_only_testnet_probe"] is False
    assert "STEP303_MIN_ORDER_SIZE_PROBE_INVALID" in evidence["block_reasons"]


def test_step303_persists_registry_and_latest_evidence(tmp_path: Path) -> None:
    cfg = load_config(Path.cwd())
    object.__setattr__(cfg, "root", tmp_path)
    evidence = build_real_testnet_read_only_adapter_evidence(
        adapter=BinanceFuturesTestnetReadOnlyAdapter(),
        order_intent=_order_intent(),
    )
    persisted = persist_real_testnet_read_only_adapter_evidence(cfg, evidence)
    assert persisted["real_testnet_read_only_adapter_registry_record_id"]
    latest = tmp_path / "storage/latest/real_testnet_read_only_adapter_evidence.json"
    registry = tmp_path / "storage/registries/real_testnet_read_only_adapter_registry.jsonl"
    assert latest.exists()
    assert registry.exists()
    assert len(registry.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_step303_latest_runner_creates_review_only_adapter_evidence(tmp_path: Path) -> None:
    # Copy settings into a minimal temp project root so the runner can use AppConfig paths.
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    result = run_real_testnet_read_only_adapter_latest(project_root=root)
    assert result["adapter_ready_for_read_only_testnet_probe"] is True
    assert result["testnet_order_submission_allowed"] is False
    assert (root / "storage/latest/real_testnet_read_only_adapter_evidence.json").exists()


def test_step303_config_flags_remain_disabled() -> None:
    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    cfg = settings["execution"]["real_testnet_read_only_adapter"]
    assert cfg["enabled"] is False
    assert cfg["review_only"] is True
    assert cfg["read_only"] is True
    assert cfg["network_enabled"] is False
    assert cfg["api_key_value_access_allowed"] is False
    assert cfg["api_secret_value_access_allowed"] is False
    assert cfg["secret_file_access_allowed"] is False
    assert cfg["secret_file_creation_allowed"] is False
    assert cfg["place_order_enabled"] is False
    assert cfg["cancel_order_enabled"] is False
    assert cfg["signed_order_executor_enabled"] is False
    assert cfg["ready_for_signed_testnet_execution"] is False
    assert cfg["testnet_order_submission_allowed"] is False
    assert cfg["external_order_submission_allowed"] is False
    assert cfg["external_order_submission_performed"] is False
    assert settings["safety"]["live_trading_enabled"] is False
    assert settings["safety"]["testnet_signed_order_enabled"] is False
