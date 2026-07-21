# Design: Venue-Keyed Cost Calibration + Extended (USDC) Integration

Status: **decided, not implemented**. Recorded 2026-07-21. Two coupled
concerns: (e) calibrating the paper cost model from measured venue fills, and
adding Extended (USDC-quoted perps) as a second execution venue next to the
Binance-verified path.

Historical note: the pre-lean codebase (P69 / Step157E era, see
`docs/VENUE_ALIGNMENT_DECISION.md`, `docs/EXTENDED_README.md`) had Extended as
the primary venue. That work is frozen at `archive/pre-lean-2026-07-15` and is
REFERENCE ONLY. The current lean pipeline's verified order path (signed
testnet, live canary, reconciliation) is Binance. Extended integration is a
NEW second venue on the lean system, not a restoration.

## (e) Cost calibration from measured fills

**Trigger: when signed-testnet session data exists** (the operator runs
`run_testnet_session.py`, producing
`storage/latest/signed_testnet_session_report.json` with fill/slippage/latency
stats), calibrate the paper cost model from those measurements.

- Today the paper engine assumes constant `slippage_bps=2.0` / `fee_bps=4.0`
  ("paper_execution_config_or_default"). If real costs are higher, every paper
  expectancy is inflated and the paper->live gap surfaces only after live
  money is at risk.
- Calibration = derive per-venue `{maker_fee_bps, taker_fee_bps,
  slippage_bps_p50, slippage_bps_p95, latency_ms_p50}` from measured fills and
  feed the paper execution config from the calibrated file. Prefer p95
  slippage for gate math and p50 for expectancy math (pessimistic where it
  guards, realistic where it estimates).
- Calibration is an artifact + operator apply, not an automatic runtime
  mutation (same boundary as everything else in feedback).

## Extended (USDC) integration — the price-basis problem

Extended quotes USD/USDC-margined perps; the research feed is Binance USDT
klines. The two prices differ by a small basis (USDT/USDC deviation + venue
microstructure). Decisions:

### V1. Research feed and execution feed are separate roles, never mixed silently

- **Research/signals stay on Binance USDT klines.** The validated 1d regime,
  the strategy pool's backtests, and the accumulated paper history are all on
  this feed; switching the research substrate would invalidate them.
- **Everything execution-critical uses the venue's own prices**: entry
  reference, fill accounting, settlement/reconciliation, and cost modeling for
  Extended orders use Extended prices only.

### V2. SL/TP anchor to the venue fill, not to feed prices

Strategy exits are derived (entry +/- ATR multiples, R:R ratios), not absolute
price levels. Anchoring them to the **Extended fill price** makes the whole
trade plan venue-consistent automatically; no cross-feed conversion is needed
in the exit math.

### V3. Pre-order basis guard (fail-closed)

Before any Extended order intent: measure `basis_bps = |binance_ref -
extended_quote| / extended_quote * 1e4`. If it exceeds a threshold, REFUSE the
intent (extends the PreOrderRiskGate's existing spread/slippage family with a
`venue_basis_ok` check). This also covers USDT/USDC depeg stress: a depeg
shows up as basis and the gate closes.

### V4. Measure before trusting: read-only dual-feed probe first

Before any Extended order authority, run a read-only probe collecting
(binance_ref, extended_quote) pairs for several days -> basis stats (mean /
std / p99 / max). The V3 threshold is set from these measurements, not
guessed. This mirrors the live read-only probe pattern already in the
canary preparation gate.

### V5. Per-venue cost model keys

The (e) calibration file is keyed by venue: `binance_testnet`,
`binance_live`, `extended`. Extended's fees/slippage are measured on Extended
(V4 probe + its own testnet path), never copied from Binance numbers.

### V6. Accounting currency is explicit

Extended P&L is computed and recorded in USDC and tagged as such
(`quote_asset: "USDC"` on venue-scoped artifacts). Aggregation across venues
converts explicitly; no silent USDT==USDC assumption in the ledgers.

## Order of work (when picked up)

1. (e) Binance testnet cost calibration — needs only operator session data.
2. V4 Extended read-only dual-feed probe + basis stats artifact.
3. V3 basis guard in the gate (fail-closed, threshold from V4).
4. Extended adapter behind the existing venue-neutral contracts (endpoint
   allowlist, hard caps, final guard) — same promotion gates as the Binance
   path: read-only -> testnet -> canary; no evidence cross-credit between
   venues (consistent with the P69 rule).
