# P66 Operator Activation Intake for Real `/fapi/v1/order/test`

P66 implements the operator activation intake validator for exactly one future Binance Futures testnet `POST /fapi/v1/order/test` call. It validates the P65 source chain, exact P65 operator phrase, metadata-only credential reference, key fingerprint SHA256, one-shot nonce SHA256, a maximum 15-minute validity window, testnet-only endpoint scope, BTCUSDT-only scope, one-request-only scope, and no-secret/no-raw-field boundaries.

P66 produces a validation receipt only. It does not enable the P65 sender executable, consume the nonce, create a signature, send HTTP, call `/fapi/v1/order/test`, call `/fapi/v1/order`, submit a testnet order, import P7 evidence, mutate runtime settings, or promote any stage.

Generated package artifacts include a fillable review-only intake template and an accepted fixture used only to prove validator behavior. The fixture is never eligible for actual execution.

An actual operator intake must use the exact P65 phrase, set `approval_granted=true`, set `actual_operator_supplied=true`, set `fixture_only=false`, use execution scope `p65_approved_testnet_order_test_only`, provide a metadata-only credential reference, provide nonzero key-fingerprint and nonce SHA256 values, remain within the validity window, and pass duplicate-nonce checks.
