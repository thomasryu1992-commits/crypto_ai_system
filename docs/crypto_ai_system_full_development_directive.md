# Crypto_AI_System 전체 개발 지시 문서 - P45 현재 업데이트본

작성일: 2026-07-09
업데이트 기준 패키지: `crypto_ai_system_v0.286.0-agent.14-feature-snapshot_p45_external_review_packet_round_trip_closure.zip`
이전 기준: Step328.1 review-only / signed-testnet-preparation / blocked-design
최종 목표: 실제 자동거래가 가능한 BTC 중심 Crypto AI System

## 1. 현재 판정

현재 ZIP은 Step328.1 이후 P0~P45까지 확장된 외부 검토/운영자 증거 패킷 중심 패키지다. 개발 문서의 단계형 안전 아키텍처에는 대체로 맞게 진행되고 있으나, 실제 자동거래 시스템으로 라이브된 상태는 아니다.

현재 정확한 상태는 다음과 같이 고정한다.

```text
Current package posture: review-only / signed-testnet-preparation / live-boundary-preparation / external-review-packet
Actual auto trading: not live
Signed testnet real order submitted: no
Live canary real order submitted: no
Live scaled execution: no
Runtime scheduler enabled: no
Order endpoint called: no
HTTP request sent for private order: no
Signature created for real order: no
Secret value accessed: no
P45 reviewer decision: PENDING_REVIEW
```

분석 기준 ZIP에서 확인된 규모는 다음과 같다.

```text
ZIP entries: 4089
Python files: 1008
Test files: 273
storage files: 2446
storage size: about 166 MB
src files: 326
Agent contract validation: passed, 59 agents
Agent lint: passed, 59 agents
Agent evals: passed
Operator dashboard execution_flags_all_disabled: true
Operator dashboard blocker count: 50
```

따라서 현재 패키지는 다음처럼 표현해야 한다.

```text
Crypto_AI_System is an auditable research, paper, approval, signed-testnet-boundary, live-boundary, operator-handoff, and external-review evidence package. It is not yet an operating live auto-trading system.
```

## 2. 현재까지의 주요 진척

P0~P45 기준으로 다음 진척은 인정한다.

- P0 Baseline Hygiene: Step328.1 baseline을 review-only 상태로 정리했고, 실행 플래그 중앙화가 들어갔다.
- P1 Live Candidate Data Foundation: live candidate data foundation 검사가 추가되었다. 다만 최신 evidence는 아직 live-candidate eligible이 아니다.
- P2 Paper Operation Validation: paper operation validation이 review-only 완료 상태로 기록되었다.
- P3 Candidate Manual Approval Chain: candidate/manual approval chain이 review-only valid 상태로 기록되었다.
- P4 Signed Testnet One-Order Runtime Package: 단일 signed testnet order runtime package 경계가 준비되었으나 disabled/no-submit이다.
- P5 Action-Time Submit Approval Boundary: action-time approval boundary가 valid review-only no-submit 상태다.
- P6 Single Signed Testnet Submit Runtime Action: 별도 local runtime에서 조건이 맞을 경우를 위한 boundary가 생겼으나 기본 상태는 ready-disabled-no-submit이다.
- P7 Post-Submit Evidence Intake: 실제 외부 submit evidence를 기다리는 상태다.
- P8 Repeated Clean Signed Testnet Sessions: 반복 signed testnet session evidence를 기다리는 상태다.
- P9 Live Read-only Canary Preparation: P8 clean sessions와 live read-only/key-scope/monitoring evidence가 없어 waiting 상태다.
- P10 Live Canary One-Order Execution Boundary: live canary order intent와 P9 준비가 없어 waiting 상태다.
- P11~P14: live canary post-submit, repeated canary, live scaled readiness, live scaled approval intake가 모두 waiting/review-only다.
- P15 Limited Live Scaled Runtime Enablement Boundary: live scaled runtime enablement는 waiting/review-only이며 실행을 열지 않는다.
- P16 Limited Live Scaled Loop Dry-run Harness: scheduler tick과 would-submit chain을 dry-run으로 검증하되 실제 루프를 시작하지 않는다.
- P17~P18: release handoff 및 CI release gate가 review-only로 정리되었다.
- P19~P45: Docker/launcher/evidence/archive/external-review/operator UX 계층이 추가되었다.
- P43~P45: external review packet round-trip seal, intake validator, closure template이 생성되었다.

## 3. 개발 문서 대비 아키텍처 적합성 검증

### 3.1 적합한 부분

현재 ZIP은 다음 개발 원칙을 유지하고 있다.

- review-only evidence와 runtime authority를 분리한다.
- signed testnet/live/live scaled 실행 플래그는 기본적으로 false다.
- `runtime_disabled_flags.py`로 실행 차단 플래그를 중앙화했다.
- `live_guard.py`는 Binance API key/secret 직접 import를 제거하고 metadata-only secret boundary로 바뀌었다.
- P6 submit runtime action은 adapter protocol과 disabled-by-default adapter를 제공하지만 기본 실행은 하지 않는다.
- P7 이후의 실제 post-submit evidence가 없으면 repeated clean signed testnet, live canary, live scaled로 진행하지 않는다.
- P30 go/no-go matrix는 runtime authority가 아니며, 현재 final activation은 waiting이다.
- P45 external review closure도 runtime authority가 아니며 reviewer decision은 pending이다.

### 3.2 아직 부족한 부분

다음은 개발 문서 기준으로 아직 부족하다.

- 실제 signed testnet order endpoint call evidence가 없다.
- 실제 exchange order id가 없다.
- 실제 status polling/cancel endpoint evidence가 없다.
- 실제 exchange response 기반 signed testnet reconciliation이 없다.
- repeated clean signed testnet sessions가 없다.
- live read-only probe/key scope validation/monitoring/runbook이 실제 live venue 기준으로 통과하지 않았다.
- live canary order가 없다.
- live scaled readiness는 P30 기준 30개 phase 중 20개 waiting 상태다.
- P45 reviewer acceptance는 아직 `PENDING_REVIEW`다.

## 4. 현재 주요 산출물 상태

```text
operator_dashboard_status.project_stage = review_only / signed-testnet-preparation / blocked-design
operator_dashboard_status.execution_flags_all_disabled = true
p1_live_candidate_data_foundation.status = P1_LIVE_CANDIDATE_DATA_FOUNDATION_COMPLETED_REVIEW_ONLY
p2_paper_operation_validation.status = P2_PAPER_OPERATION_VALIDATION_COMPLETED_REVIEW_ONLY
p3_candidate_manual_approval_chain.status = PHASE_D_CANDIDATE_MANUAL_APPROVAL_CHAIN_VALID_REVIEW_ONLY
p4_signed_testnet_one_order_runtime_package.status = READY_REVIEW_ONLY_DISABLED
p5_action_time_submit_approval_boundary.status = VALID_REVIEW_ONLY_NO_SUBMIT
p6_single_signed_testnet_submit_runtime_action.status = READY_DISABLED_NO_SUBMIT
p7_post_submit_evidence_intake.status = WAITING_FOR_EXTERNAL_SUBMIT_REVIEW_ONLY
p8_repeated_clean_signed_testnet_sessions.status = WAITING_REVIEW_ONLY
p9_live_read_only_canary_preparation.status = WAITING_REVIEW_ONLY
p10_live_canary_one_order_execution_boundary.status = WAITING_REVIEW_ONLY
p15_limited_live_scaled_runtime_enablement_boundary.status = WAITING_REVIEW_ONLY
p16_limited_live_scaled_loop_dry_run_harness.status = WAITING_REVIEW_ONLY
p18_full_regression_ci_release_gate.status = HARDENED_REVIEW_ONLY
p30 final activation decision = WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE
p45 reviewer decision = PENDING_REVIEW
```

## 5. 현재 발견된 문제점 및 불필요한 요소

### 5.1 문서/패키지 불일치

현재 ZIP 안에는 최신 `crypto_ai_system_full_development_directive.md`와 라이브 자동거래 개발 지시서가 포함되어 있지 않다. 외부 검토용 패키지라면 `docs/` 아래에 현재 기준 문서를 포함해야 한다.

### 5.2 Agent 계약명 불일치

이전 개발 지시서에서 요구한 Phase 7.15~7.17 Agent 계약 파일명 9개가 정확한 이름으로는 존재하지 않는다.

누락된 정확한 파일명:

```text
operator_decision_intake_template_agent.md
operator_decision_intake_validator_agent.md
final_pre_executor_review_agent.md
disabled_executor_evidence_reviewer.md
disabled_reconciliation_session_close_reviewer.md
future_executor_approval_reviewer.md
enablement_design_reviewer.md
enablement_guard_fixture_reviewer.md
operator_decision_packet_reviewer.md
```

유사 역할의 계약은 존재하지만, 정확한 요구사항 충족을 위해 alias contract 또는 mapping table이 필요하다.

### 5.3 최신 Agent 산출물명 일부 불일치

다음 파일은 `storage/latest`에서 확인되지 않았다.

```text
agent_output_validation_report.json
agent_contract_review_report.json
```

반면 다음은 존재한다.

```text
agent_contract_validation_report.json
agent_eval_report.json
agent_contract_index.json
agent_lint_report.json
agent_permission_policy_report.json
agent_prohibited_action_scan.json
```

README/Step326 계열 문구와 실제 최신 산출물명을 맞춰야 한다.

### 5.4 패키지 크기와 storage 과다 포함

현재 ZIP은 `storage/`가 약 166MB이며, 검증/외부 리뷰 번들 성격이 강하다.

특히 큰 파일:

```text
storage/registries/performance_report_registry.jsonl ~87MB
storage/registries/outcome_feedback_registry.jsonl ~18MB
storage/registries/valid_price_lineage_artifacts_registry.jsonl ~5MB
storage/registries/source_registry.jsonl ~3.5MB
storage/registries/agent_eval_registry.jsonl ~3.4MB
```

소스 핸드오프, 운영 런타임 패키지, 외부 리뷰 evidence bundle을 분리해야 한다.

### 5.5 P19~P45 부가 계층 과확장 위험

운영자 UX, Telegram/launcher/dashboard, support bundle, evidence archive, external review packet 계층이 많이 추가되었다. 이는 감사/운영 보조에는 유용하지만, 실제 자동거래의 핵심 blocker인 P7/P8을 해결하지 않는다.

향후 개발 우선순위는 P45 이후 추가 패킷이 아니라 다음이다.

```text
P6 실제 operator-armed signed testnet submit
-> P7 실제 post-submit evidence intake
-> P8 repeated clean signed testnet sessions
```

### 5.6 Secret 문자열 스캔 결과 해석

여러 release/activation/launcher 모듈에 `BINANCE_API_KEY`, `BINANCE_API_SECRET` 문자열이 남아 있다. 대부분은 secret value가 들어오면 차단하기 위한 패턴 또는 외부 입력명으로 보인다. 그러나 CI에서 secret value scan은 계속 강제해야 한다.

실제 secret 값은 패키지에 포함되어서는 안 되며, evidence에는 fingerprint/reference만 남겨야 한다.

## 6. 현재 실행 안전성 판정

최신 산출물 기준으로 다음은 유지된다.

```text
actual_order_submission_performed=false
actual_testnet_order_submitted=false
actual_live_order_submitted=false
order_endpoint_called=false
http_request_sent=false
signature_created=false
signed_request_created=false
secret_value_accessed=false
live_canary_execution_enabled=false
live_scaled_execution_enabled=false
runtime_scheduler_enabled=false
runtime_loop_started=false
```

따라서 현재 ZIP은 실행 안전성 측면에서 문서 원칙을 유지한다. 다만 실제 자동거래 준비가 완료된 것은 아니다.

## 7. 다음 개발 우선순위

### P0 - 문서와 패키지 정합성

1. 최신 전체 개발 지시서와 P45 이후 개발 지시서를 `docs/`에 포함한다.
2. README의 current package status를 P45 기준으로 갱신한다.
3. Step328 중심 문구와 P45 현황 문구가 충돌하지 않도록 정리한다.
4. P0~P45 phase status table을 하나의 문서로 생성한다.

### P1 - Agent 계약 정합성

1. 누락된 9개 Agent 계약명을 alias 파일로 추가하거나 mapping table을 만든다.
2. Agent validation report가 요구 산출물명과 실제 산출물명 모두를 명시하도록 한다.
3. `agent_output_validation_report.json`, `agent_contract_review_report.json`을 생성하거나 문서에서 기대 파일명을 수정한다.

### P2 - 패키지 분리

1. Source handoff ZIP: source, config template, tests, docs만 포함.
2. Validation evidence ZIP: storage/latest, selected registry tail, reports 포함.
3. Full audit archive ZIP: 대형 registry 전체 포함.
4. Runtime package ZIP: 실행에 필요한 최소 코드와 config만 포함, generated storage 제외.

### P3 - P7 실제 post-submit evidence 준비

1. P6 external runtime submit 조건을 명확히 한다.
2. testnet-only runtime secret binding을 실제 local process에서 구현한다.
3. 단일 BTCUSDT testnet order를 operator-armed 조건에서만 제출한다.
4. exchange response를 redacted evidence로 저장한다.
5. P7 post-submit evidence intake가 실제 exchange order id/status/cancel/reconciliation evidence를 검증하게 한다.

### P4 - P8 repeated clean signed testnet sessions

1. 최소 5회 clean signed testnet session evidence를 수집한다.
2. filled/rejected/cancel/timeout/rate-limit/duplicate-submit 사례를 포함한다.
3. secret leak, endpoint mismatch, reconciliation mismatch, stale risk gate를 모두 차단한다.
4. P8이 synthetic fixture가 아니라 real testnet evidence로 valid가 되도록 한다.

### P5 - Live canary 이후

1. P8 valid 이후 P9 live read-only probe와 live key-scope validation을 실제 venue 기준으로 실행한다.
2. P10 live canary one-order execution boundary를 실제 approval과 함께 사용한다.
3. P11/P12 live canary evidence가 clean할 때만 P13~P15로 이동한다.
4. P16 dry-run harness는 실제 live scaled 실행 전 마지막 simulation 검증으로 유지한다.

## 8. 완료 정의 업데이트

### 8.1 현재 P45 패키지 완료 정의

현재 P45 패키지는 다음 조건을 만족하면 review/external-evidence package로 완료된 것으로 본다.

- 실행 플래그 false 유지.
- P45 closure template ready.
- P44 external review intake valid.
- P43 evidence archive sealed.
- P30 final activation은 waiting으로 유지.
- 실제 endpoint/secret/signature/order 없음.
- 최신 문서와 패키지 status가 일치.

### 8.2 실제 자동거래 완료 정의

실제 자동거래 완료는 다음 이후에만 말할 수 있다.

- 실제 signed testnet order 1건 제출 evidence 존재.
- P7 post-submit evidence intake valid.
- P8 repeated clean signed testnet sessions valid.
- P9 live read-only/key-scope/monitoring/runbook valid.
- P10 live canary order 1건 실행 evidence 존재.
- P11/P12 live canary evidence clean.
- P13/P14 live scaled readiness/approval valid.
- P15 runtime enablement boundary valid.
- P16 dry-run harness clean.
- 별도 operator runtime activation 후 제한적 scheduler 실행.

## 9. 최종 지시

다음 개발자는 P45 이후 새 기능을 더 붙이기 전에 P7/P8 실제 signed testnet evidence를 확보해야 한다. 현재 패키지는 안전한 외부 검토/운영자 승인 패킷으로는 진척됐지만, 자동거래 라이브의 핵심 증거는 아직 없다.

가장 중요한 다음 목표는 다음 한 줄이다.

```text
Create one real, operator-armed, low-notional signed testnet order evidence chain, then validate it through P7 and repeat it through P8.
```