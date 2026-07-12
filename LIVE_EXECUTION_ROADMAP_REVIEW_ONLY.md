# Crypto_AI_System Live Execution Roadmap — Review-First Plan

Current state: Step328.1 review-only Agent Library completion. The system is not a live auto-trading system. Signed testnet, live canary, and live scaled execution remain disabled until manual approval and staged validation are completed.

## Phase 1 — Baseline Integrity Freeze

Goal: freeze the current Step328.1 package as a trusted review baseline.

Required actions:
- Run compile, Agent Library lint, contract validation, output validation, evals, index generation, contract review, status consistency, and focused Step319 regression.
- Store source handoff ZIP, audit bundle, and generated review artifacts.
- Confirm all execution flags remain disabled.

Exit criteria:
- `tests/agents/` passes.
- Step301 export packet includes Agent Library evidence.
- Step319 live scaled readiness remains blocked.
- No runtime mutation or order submission is performed.

## Phase 2 — Paper Data Quality Hardening

Goal: make paper validation meaningful by improving data reliability.

Required actions:
- Confirm price data ingestion is complete, fresh, non-fallback, non-synthetic, and non-sample.
- Mark optional source health explicitly for derivatives, exchange flow, ETF flow, and stablecoin liquidity.
- Ensure missing optional data is `neutral_due_to_missing` and not live eligible.
- Preserve source bundle hash, data snapshot ID, feature snapshot ID, and feature matrix hash.

Exit criteria:
- Source registry and data snapshot registry pass.
- Feature lineage is reproducible.
- No hidden fallback, stale, synthetic, mock, or sample data enters candidate eligibility.

## Phase 3 — Paper Strategy Validation

Goal: validate trading logic in paper mode only.

Required actions:
- Generate ResearchSignal v2 with complete lineage.
- Run Signal QA.
- Generate trading decisions from price structure.
- Run PreOrderRiskGate in paper stage.
- Execute paper orders only through the paper execution engine.
- Reconcile order intent, simulated fill, position delta, fees, and slippage.

Exit criteria:
- Paper execution never calls real exchange order endpoints.
- Reconciliation mismatch blocks promotion.
- Outcome records include R-multiple, drawdown, slippage, latency, stale data rate, and signal-to-outcome drift.

## Phase 4 — Outcome Analytics and Candidate Profile Review

Goal: convert paper results into review-only improvement candidates.

Required actions:
- Build performance reports by profile, signal, regime, timeframe, risk level, and data quality.
- Create candidate profile drafts only when evidence supports them.
- Keep candidate profiles disabled until manual approval.
- Create approval packet drafts with source report hash, feature matrix hash, and profile candidate hash.

Exit criteria:
- Candidate profile is not applied to runtime settings.
- Disabled settings-write preview remains disabled.
- Approval packet draft is review-only.

## Phase 5 — Manual Approval Intake

Goal: validate whether a candidate can enter signed testnet preparation.

Required actions:
- Create a manual approval packet.
- Validate approver information, ticket/signature, source report path, source report hash, feature matrix hash, profile candidate hash, and canonical UTC timestamp.
- Run approval intake validation and Agent Library review.

Exit criteria:
- Missing or damaged approval files fail closed.
- Hash mismatch fails closed.
- Approval validation does not mutate settings.
- Approval validation does not enable order submission.

## Phase 6 — Signed Testnet Preparation

Goal: prepare signed testnet evidence without submitting orders.

Required actions:
- Run read-only venue probes.
- Validate metadata-only key references and fingerprints.
- Validate venue readiness, min/max notional, fee, slippage, rate limit, and API error-rate evidence.
- Generate signed testnet unlock preview artifacts.
- Keep signed executor disabled.

Exit criteria:
- `ready_for_signed_testnet_execution=false` remains false until a later explicit approved stage.
- `testnet_order_submission_allowed=false` remains false.
- `signed_order_executor_enabled=false` remains false.
- No API secret value or secret file is read.

## Phase 7 — Signed Testnet Validation

Goal: only after explicit approval, validate signed testnet order lifecycle in a controlled environment.

Required actions:
- Create separate manual approval for signed testnet execution.
- Enable only the minimum testnet order permissions required for the testnet stage.
- Submit tightly capped testnet orders only after approval.
- Validate order submit, cancel, fill, position sync, balance/margin/leverage checks, fee/slippage, rejection handling, and reconciliation.
- Close the session and produce a session close report.

Exit criteria:
- Testnet reconciliation passes.
- No mainnet/live key scope is used.
- Any mismatch disables progression.
- Promotion is manual, never automatic.

## Phase 8 — Live Canary Preparation

Goal: prepare live canary without enabling scaled live execution.

Required actions:
- Run live read-only probe.
- Validate live key scope metadata without reading key values.
- Confirm withdrawal, transfer, admin, leverage mutation, and broad write scopes are absent or fail-closed.
- Prepare live canary approval packet, deployment runbook, monitoring, alerting, and kill-switch procedure.

Exit criteria:
- Live canary executor remains disabled until explicit approval.
- Live scaled execution remains disabled.
- Monitoring and manual kill switch are verified.

## Phase 9 — Live Canary Execution

Goal: execute minimal-size live canary only after separate approval.

Required actions:
- Use strict notional caps.
- Enforce manual kill switch.
- Monitor spread, slippage, latency, rejection rate, API error rate, reconciliation mismatch, and paper/live gap.
- Produce live canary reconciliation and canary outcome report.

Exit criteria:
- Canary outcome is reviewed manually.
- Any mismatch or abnormal risk blocks live scaled readiness.
- No automatic promotion occurs.

## Phase 10 — Live Scaled Readiness Review

Goal: decide whether scaled live execution can even be considered.

Required actions:
- Review signed testnet and live canary outcomes.
- Confirm data, feature, signal, decision, risk, execution, reconciliation, outcome, feedback, and approval ID chain completeness.
- Confirm monitoring, alerting, deployment runbook, rollback procedure, and manual control readiness.

Exit criteria:
- Live scaled readiness is reviewed separately.
- Live scaled execution remains disabled until a distinct manual approval.
- Agent contracts remain governance artifacts and never become runtime permission sources.
