# Design: TradingAgent decomposition + PipelineContext as a load-bearing contract

_Status: IMPLEMENTED (2026-07-20, branch `refactor/trading-agent-split-context`,
commits P1..P3 + M1..M5). Deviations from the proposal are noted inline as
**[as-built]** paragraphs._

**[as-built] summary.** All P and M steps landed as designed, with three
deliberate deviations: (1) `settle_live_before_refusal` stayed in the agent —
it runs before `CycleInputs` exists and its tests patch the agent's module
surface; (2) the counterfactual wrappers stayed in the agent for the same
monkeypatch-surface reason (`record_blocked_signal`/`settle_counterfactuals`
are patched on the agent module); (3) the `resolve_execution_stage` re-export
is kept permanently as the module's stable public surface rather than removed —
tests and operator tooling call `trading_agent.resolve_execution_stage`.
`positions.py` additionally absorbed the open-position count. The agent went
from ~660 to ~320 lines; `execute()` is the sequencer.

## Why

The QA audit's structural finding: the pipeline's in-memory contract is
decorative. `PipelineContext.data` is a grab-bag dict merged from every stage's
outputs, but only three keys are ever read (`allow_new_position`,
`strategy_routing`, `trade_executed`); `stage_ok` has zero callers. The real
dataflow is `storage/latest/*.json` re-read at every layer, and the no-trade
gate is re-derived independently per path. That is exactly how the
strategy-drive path shipped without consulting the validation verdict (audit
H1) and how the freshness gate went dead end-to-end (H2): nothing in the code's
*shape* forces a new entry path to consume the gates.

Meanwhile `TradingAgent.execute` has absorbed stage routing, three settlement
variants, S8 attribution, counterfactuals, the strategy drive, the multibook
entry walk, reconciliation selection, lifecycle derivation, and position
opening (~660 lines). Every recent bug of the H1 class was born here, and every
fix lands here. The other four agents are ~50-line wrappers.

Two changes, one goal: **make "which gates does this entry path consume" a
question the code cannot leave unanswered, and make the trading stage readable
enough that the next reviewer can answer it by looking.**

## Goals

1. The validation verdict becomes a **required, typed input** to every decision
   builder — omitting it is a `TypeError` at call time, not a silent pass.
2. `TradingAgent.execute` shrinks to a ~60-line sequencer whose step order is
   the documentation.
3. **Byte-identical behavior.** Same outputs keys, same file writes in the same
   order, same event logs, same fail-closed semantics. This is a refactor, not
   a redesign.

## Non-goals

- No gate logic changes, no file schema changes, no stage renames.
- `storage/latest/` files remain the persistence/audit layer and the contract
  for core modules and cross-process consumers (dashboard, operator scripts).
- The strategy factory is untouched.

---

## Part 1 — PipelineContext: typed, minimal, mandatory

### Rejected alternative

*Remove the context entirely, files only.* Honest about today's reality, but it
entrenches the root cause: every new path must **remember** to re-read the
right files. The bug class survives.

### Chosen design

The context carries a small set of **typed artifacts produced once per cycle**;
downstream code takes them as required parameters. Files keep being written for
audit, but intra-cycle flow is explicit in signatures.

```python
@dataclass(frozen=True)
class ValidationVerdict:
    """The validation stage's complete verdict for ONE cycle."""
    allow_new_position: bool
    data_health: Mapping[str, Any]   # full report (allow_trading, problems, ...)
    risk_status: Mapping[str, Any]   # full report (daily_pnl_r, consecutive_losses, ...)

    @classmethod
    def fail_closed(cls) -> "ValidationVerdict":
        return cls(False, {}, {})

    @classmethod
    def from_latest_files(cls) -> "ValidationVerdict":
        """EXPLICIT file-based loader for standalone entry points (module
        __main__, operator scripts). Never a hidden default."""
```

`PipelineContext` becomes:

```python
@dataclass
class PipelineContext:
    cycle: CycleEnvelope | None = None
    results: dict[str, StageResult] = field(default_factory=dict)
    verdict: ValidationVerdict | None = None       # set by ValidationAgent
    strategy_routing: dict | None = None           # set by StrategyRoutingAgent
```

Deleted: the generic `data` dict, `get()`, `stage_ok()` (zero callers), and the
implicit "outputs merge into a shared namespace" behavior of `record()`.
`record()` keeps only `results[stage] = result`.

`trade_executed` leaves the context entirely: the orchestrator already holds
the trading `StageResult` and reads `trade_result.outputs.get("trade_executed")`
directly. One less shared-namespace key.

### The kill-shot rule

The two decision builders change signature (required keyword-only params, no
defaults):

```python
# bridge/research_trading_bridge.py
def run_research_trading_bridge(execution_stage="paper", *, open_positions=None,
                                data_health: Mapping, risk: Mapping) -> dict: ...

# strategy_execution_bridge.build_strategy_decision_for_cycle — already takes
# data_health/risk since the QA fix via build_strategy_trade_decision; lift the
# same requirement to the cycle-level function so IT stops reading the files.
def build_strategy_decision_for_cycle(strategy_routing, *, execution_stage,
                                      open_positions, data_health: Mapping,
                                      risk: Mapping, cycle_id=None, now=None): ...
```

The agent passes `ctx.verdict.data_health` / `ctx.verdict.risk_status`. A
`None` verdict maps to `ValidationVerdict.fail_closed()` (the trading agent
should never run without validation, but if an embedder wires it wrong, the
result is *blocked*, not *ungated*).

Standalone invocation (`py -m bridge.research_trading_bridge`, tests) must name
its verdict source: `ValidationVerdict.from_latest_files()`. Explicitness is
the point — "where does your gate come from" appears at every call site.

Two second-order wins:

- **Same-cycle consistency.** Today `build_trading_decision` re-reads
  `data_health.json`/`risk_status.json` from disk; under an overlapping or
  crashed run those can be another cycle's files. In-memory verdicts are
  cycle-bound by construction (the run lock already prevents overlap; this
  removes the residual same-process window).
- **One read per cycle.** `market_snapshot` and the latest candle are read once
  into the cycle inputs (Part 2) instead of 5+ scattered `read_json` calls.

### Migration (each step lands with a green suite)

- **P1** — Add `ValidationVerdict` + typed context fields. ValidationAgent and
  StrategyRoutingAgent populate them *alongside* the legacy dict. No consumer
  changes. (Small; zero risk.)
- **P2** — Thread `data_health`/`risk` into `run_research_trading_bridge` and
  `build_strategy_decision_for_cycle` as required kwargs; update the trading
  agent, `main()` entry points (via `from_latest_files()`), and tests.
  `build_trading_decision`'s own re-reads are replaced by the passed mappings.
- **P3** — Delete `ctx.data`/`get`/`stage_ok`; orchestrator reads
  `trade_executed` from the trading StageResult. Grep-verify zero `ctx.get(`
  remains under `src/crypto_ai_system/pipeline/`.

---

## Part 2 — TradingAgent decomposition

### Shape

`TradingAgent` stays the only `Agent`; the steps move to a package of
narrow modules with explicit inputs and small result dataclasses:

```
src/crypto_ai_system/pipeline/trading_steps/
    context.py      CycleInputs: cfg, cycle_id, now, stage, snapshot,
                    latest_candle, verdict, routing  (built ONCE per cycle)
    stage_router.py resolve_execution_stage + the flag/confirmation helpers
    settlement.py   settle_positions(inputs) -> SettlementOutcome
                    {settlement, book_settlements, closed_attributions}
                    + settle_live_before_refusal(inputs)
                    (3 variants: multibook books / paper single / live;
                     S8 attribution recording lives here — it is a
                     settlement concern)
    entry.py        run_single_entry(inputs, open_positions) -> EntryOutcome
                    {trade_decision, strategy_drive, order, reconciliation,
                     externally_submitted}
                    (research bridge -> drive override -> executor ->
                     reconciliation selection)
    multibook.py    run_multibook_entries(inputs, research_decision, open_count)
                    -> MultibookOutcome {entries, strategy_drive, representative}
                    (the walk + representative selection + executed-decision
                     re-persist)
    lifecycle.py    derive_lifecycle(order, entries, multibook) -> Lifecycle
                    {order_status, order_intent_created, order_submitted,
                     order_filled, trade_executed}   # PURE — unit-testable
    positions.py    open_position_if_filled(inputs, lifecycle, order,
                    reconciliation) -> opened        (paper / live open)
    counterfactual.py  the two flag+try/except wrappers around
                    feedback.counterfactual_tracker
```

`TradingAgent.execute` becomes the sequencer (~60 lines):

```
build CycleInputs                     (one snapshot read, one candle read)
stage = resolve_execution_stage()     -> refusal? settle_live_before_refusal, BLOCKED
settlement = settle_positions(...)    (S8 attribution inside)
settle_counterfactuals(...)
open_positions = count_open(...)
entry = multibook ? run_multibook_entries(...) : run_single_entry(...)
lifecycle = derive_lifecycle(...)
if not lifecycle.trade_executed: record_counterfactual(...)
opened = open_position_if_filled(...)
assemble outputs (key-for-key identical) -> DEGRADED / OK
```

### Behavior-preservation invariants (the PR's review checklist)

1. Settle-first, always — including on a refused live stage (kill switch).
2. The kernel remains the arbiter of book/global/direction caps inside the walk.
3. The multibook walk re-persists the FILLED entry's decision (consumption
   marker preserved); order/reconciliation describe that same trade.
4. Reconciliation selection: venue reconciliation only when
   `external_order_submission_performed`, else the paper reconciler.
5. Best-effort isolation unchanged: S8 attribution, counterfactuals, and the
   strategy drive can fail without touching the trade path (same log events).
6. Outputs dict identical key-for-key (scheduler/dashboard compat).
7. File writes happen in the same order (crash-window compatibility).
8. `no-new-position` still returns DEGRADED with full outputs.

Verification per step: full suite + `py scripts/check_safety_defaults.py` +
one real cycle, then diff `storage/latest/` key sets against a pre-refactor
cycle.

### Test-compat plan

Tests monkeypatch `trading_agent.resolve_execution_stage`,
`trading_agent.read_json`, `trading_agent._latest_candle`, and kernel functions
at their own modules. Kernel-module patches keep working (steps import kernels
at call time). For the agent-module surface, `trading_agent` keeps thin
re-exports (`resolve_execution_stage = stage_router.resolve_execution_stage`,
etc.) until the affected tests are migrated to patch the step modules; the
re-exports are removed in the final step. Known affected tests:
`test_signed_testnet_guard`, `test_live_strategy_wiring`, `test_multibook_m3`,
`test_strategy_drive_wiring`, `test_live_strategy_integration`,
`test_multi_symbol_routing`.

### Migration order

**P-series first, then M-series** — P2 changes the bridge signatures that M4
would otherwise move twice.

- **M1** — Create `trading_steps/` + `CycleInputs`; move `stage_router`;
  re-export aliases. No behavior change.
- **M2** — Extract `derive_lifecycle` (pure) + direct unit tests for the
  single-book/multibook matrix (this logic has never been unit-tested alone).
- **M3** — Extract `settlement.py` (3 variants + refusal settle + S8).
- **M4** — Extract `entry.py` + `multibook.py`.
- **M5** — Slim `execute()` to the sequencer; delete dead agent helpers;
  remove re-exports after migrating the monkeypatch call sites.

Estimated effort: P-series one session; M-series one to two sessions. Every
commit lands green; any step can stop and ship without leaving the tree in an
intermediate state.

### Risks

- **Hidden monkeypatch surfaces** in tests beyond the list above — mitigated by
  re-export aliases and running the full suite per commit (the CI lesson from
  the QA PR: local storage can mask missing-file behavior; the suite must pass
  on a clean checkout, so CI is the gate, not the local run).
- **Side-effect ordering** — file writes and `log_event` calls are asserted
  order-identical (invariant 7); the diff-a-real-cycle check catches drift the
  unit tests cannot.
- **Bridge signature ripple** — `run_research_trading_bridge` is called from
  the agent, its `main()`, and tests; P2 must sweep all call sites in one
  commit (grep `run_research_trading_bridge(`).

## What this deliberately does NOT fix

- The dual-config system (flat settings + AppConfig) stays as-is — parsing was
  unified in the QA follow-up; full consolidation is a separate decision.
- `run_order_executor` still reads `TRADE_DECISION_PATH` from disk. That file
  is the executor's consumption-guarded contract (one decision -> at most one
  intent) and operator scripts depend on it; moving it in-memory would break
  the standalone executor without a safety gain.
