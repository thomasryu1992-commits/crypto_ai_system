# Crypto_AI_System P45 이후 실제 자동거래 개발 지시서

작성일: 2026-07-09
기준 패키지: `crypto_ai_system_v0.286.0-agent.14-feature-snapshot_p45_external_review_packet_round_trip_closure.zip`
현재 상태: P45 external review packet round-trip closure template ready, reviewer decision pending
목표: P45 이후 실제 signed testnet evidence를 만들고, 단계적으로 live canary 및 제한적 live scaled 자동거래로 이동

## 1. 핵심 목표

현재 시스템은 P45까지 외부 리뷰/운영자 승인/증거 archive 계층이 확장되어 있다. 하지만 실제 자동거래로 가기 위해 필요한 핵심 증거는 아직 비어 있다.

즉시 목표는 live가 아니다. 즉시 목표는 다음이다.

```text
P6 operator-armed single signed testnet submit
-> P7 real post-submit evidence intake
-> P8 repeated clean signed testnet sessions
```

P8이 실제 evidence로 valid가 되기 전까지 P9~P16은 모두 review-only/waiting/dry-run 상태를 유지한다.

## 2. 현재 출발 상태

```text
P45 status: P45_EXTERNAL_REVIEW_PACKET_ROUND_TRIP_CLOSURE_TEMPLATE_READY_REVIEW_ONLY
P45 reviewer decision: PENDING_REVIEW
P30 final activation decision: WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE
P7 status: WAITING_FOR_EXTERNAL_SUBMIT_REVIEW_ONLY
P8 status: WAITING_REVIEW_ONLY
P9 status: WAITING_REVIEW_ONLY
P10 status: WAITING_REVIEW_ONLY
P15 status: WAITING_REVIEW_ONLY
P16 status: WAITING_REVIEW_ONLY
actual_testnet_order_submitted=false
actual_live_order_submitted=false
order_endpoint_called=false
http_request_sent=false
signature_created=false
secret_value_accessed=false
runtime_scheduler_enabled=false
```

## 3. 개발 금지 사항

- P7/P8 실제 signed testnet evidence 없이 P9 live canary 준비를 ready로 만들지 않는다.
- P9 valid 없이 P10 live canary execution boundary를 ready로 만들지 않는다.
- P10/P11/P12 clean evidence 없이 P13~P15를 ready로 만들지 않는다.
- P15 ready 없이 P16을 runtime enablement로 해석하지 않는다.
- P16 dry-run을 실제 scheduler start로 해석하지 않는다.
- P45 reviewer acceptance를 runtime authority로 해석하지 않는다.
- mock, synthetic, fixture, review-only evidence를 real exchange evidence로 승격하지 않는다.
- secret 값은 파일, 로그, registry, report, exception에 절대 남기지 않는다.
- 플래그 true 변경만으로 실행 권한을 만들지 않는다.

## 4. Phase 1 - 문서/패키지 정합성 정리

### 작업

1. 최신 전체 개발 지시서와 이 P45 이후 개발 지시서를 `docs/`에 포함한다.
2. README와 master context에 P45 현재 상태를 추가한다.
3. P0~P45 status matrix를 생성한다.
4. P45는 review closure template이며 runtime authority가 아니라는 문구를 모든 dashboard/export 문서에 반영한다.
5. P30 waiting phase 20개를 운영자에게 보이는 형태로 정리한다.

### 완료 기준

- 외부 리뷰어가 ZIP만 봐도 현재 상태를 오해하지 않는다.
- `Step328.1` 문구와 `P45` 문구가 충돌하지 않는다.
- P7/P8 미완료가 명확히 표시된다.

## 5. Phase 2 - Agent 계약명/산출물명 정합성

### 작업

1. 아래 9개 계약명을 alias contract 또는 mapping table로 처리한다.

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

2. 유사 기존 계약과의 매핑을 명시한다.
3. `agent_output_validation_report.json`, `agent_contract_review_report.json` 누락 문제를 해결한다.
4. Agent lint/contract/eval/prohibited action scan을 다시 실행한다.

### 완료 기준

- Agent Library 요구사항이 파일명 기준으로도 추적 가능하다.
- 문서에서 기대하는 latest artifact와 실제 latest artifact가 일치한다.

## 6. Phase 3 - 패키지 분리

### 목적

현재 ZIP은 source package와 evidence archive가 섞여 있다. 자동거래 개발과 외부 리뷰를 위해 분리한다.

### 출력물

```text
source_handoff.zip
validation_evidence_bundle.zip
full_audit_archive.zip
runtime_candidate_package.zip
```

### 포함 기준

- `source_handoff.zip`: src, scripts, tests, config templates, docs, agents, requirements.
- `validation_evidence_bundle.zip`: storage/latest, selected recent registry rows, validation reports.
- `full_audit_archive.zip`: full storage/registries 포함.
- `runtime_candidate_package.zip`: 실제 runtime 후보 코드만 포함, generated storage 제외.

### 완료 기준

- source handoff가 166MB storage registry를 포함하지 않는다.
- runtime package가 review-only generated artifacts에 의존하지 않는다.
- audit archive는 별도 보관된다.

## 7. Phase 4 - P6 실제 signed testnet submit 준비

### 목적

P6 boundary를 실제 local runtime에서 한 번 사용할 수 있게 준비한다.

### 필수 조건

- operator arming phrase.
- testnet-only environment.
- BTCUSDT-only.
- max order count 1.
- low notional cap.
- fresh hot-path PreOrderRiskGate.
- endpoint time sync fresh.
- duplicate submit lock acquired.
- idempotency key present.
- post-submit relock ready.
- runtime network call explicitly allowed by operator.
- real signed-testnet adapter attached.
- secret value logging blocked.

### 작업

1. P6 runtime action에 실제 adapter를 주입할 interface를 명확히 한다.
2. disabled adapter와 real adapter를 코드상 분리한다.
3. real adapter는 별도 local runtime package 또는 별도 branch에서만 활성화한다.
4. secret binding은 process memory에서만 이루어지고 evidence에는 fingerprint/reference만 저장한다.
5. submit 전 최종 preflight report를 생성한다.

### 완료 기준

- P6 default package는 여전히 no-submit이다.
- 별도 local runtime에서만 단일 testnet submit이 가능하다.
- submit 전 조건 하나라도 실패하면 endpoint call 전에 fail closed 된다.

## 8. Phase 5 - P7 실제 post-submit evidence intake

### 목적

실제 signed testnet order 1건의 post-submit evidence를 P7에서 검증한다.

### 입력 evidence

```text
redacted exchange submit response
exchange order id
client order id
idempotency key
request hash
response hash
endpoint type
HTTP status
server time/timestamp evidence
status polling evidence
cancel boundary evidence, if applicable
hot-path risk gate id/hash
secret reference id
key fingerprint sha256
no secret logged evidence
post-submit relock evidence
```

### 검증 조건

- order id가 mock이 아니어야 한다.
- request/response hash가 일치해야 한다.
- order intent id와 risk gate id가 canonical chain에 연결되어야 한다.
- status polling evidence가 있어야 한다.
- cancel boundary가 필요한 경우 cancel evidence가 있어야 한다.
- reconciliation input이 완성되어야 한다.
- secret value가 어디에도 남지 않아야 한다.

### 완료 기준

- P7 status가 waiting이 아니라 valid real post-submit evidence 상태가 된다.
- P7은 P8 repeated sessions의 입력으로 사용 가능해야 한다.

## 9. Phase 6 - P8 repeated clean signed testnet sessions

### 목적

단일 testnet order가 아니라 반복 가능한 운영 안정성을 입증한다.

### 최소 기준

```text
minimum clean session count: 5
minimum symbols: BTCUSDT only at first
allowed environments: testnet only
max order count per session: 1 initially
required cases: filled, rejected or canceled, status polling, no duplicate submit, no secret leak
```

### 작업

1. P7 valid evidence를 최소 5개 누적한다.
2. 각 session의 reconciliation을 수행한다.
3. mismatch, slippage, latency, rejection, API error, timeout, retry count를 기록한다.
4. kill switch와 duplicate submit lock negative cases를 검증한다.
5. P8 validator가 fixture가 아니라 real session evidence를 인식하도록 한다.

### 완료 기준

- `repeated_clean_signed_testnet_sessions_validated=true`.
- live canary preparation candidate evidence가 생성된다.
- live canary execution은 아직 false다.

## 10. Phase 7 - P9 live read-only canary preparation

### 목적

testnet 반복 검증 이후 live venue를 read-only로 확인한다.

### 작업

1. live read-only probe를 실제 venue에서 수행한다.
2. balance, position, open orders, symbol info, fee tier, min notional, rate limit을 확인한다.
3. live key scope metadata를 검증한다.
4. withdrawal, transfer, admin 권한이 차단되었는지 확인한다.
5. monitoring heartbeat, alerting, runbook readiness를 확인한다.
6. operator live canary preparation request를 별도 작성한다.

### 완료 기준

- P9 waiting blockers가 해소된다.
- live canary preparation allowed가 review-only evidence로만 true가 될 수 있다.
- live order submission은 여전히 false다.

## 11. Phase 8 - P10 live canary one-order boundary

### 목적

최소 금액 live canary 1건을 실행할 수 있는 boundary를 준비한다.

### 작업

1. 별도 live canary approval request를 작성한다.
2. fresh data snapshot, ResearchSignal, Signal QA를 생성한다.
3. live-canary-stage hot-path PreOrderRiskGate를 submit 직전에 실행한다.
4. max order count 1, low notional cap, idempotency, duplicate lock을 강제한다.
5. manual kill switch를 확인한다.
6. post-submit relock plan을 생성한다.
7. operator가 명시적으로 live canary network call을 승인한 별도 runtime에서만 실행한다.

### 완료 기준

- P10 ready review-only no-submit 상태가 먼저 된다.
- 실제 live canary submit은 별도 승인/runtime에서만 수행한다.
- submit evidence는 P11로 전달된다.

## 12. Phase 9 - P11/P12 live canary evidence

### 작업

1. P11에서 live canary post-submit evidence를 검증한다.
2. live order id, status polling, fill/reject/cancel, reconciliation을 검증한다.
3. P12에서 여러 clean live canary session을 요구한다.
4. slippage, latency, rejection, API error, mismatch 기준을 고정한다.

### 완료 기준

- repeated clean live canary sessions valid.
- live scaled readiness 검토로 이동 가능.
- live scaled execution은 아직 false다.

## 13. Phase 10 - P13~P16 제한적 live scaled 준비

### 작업

1. P13 live scaled readiness review를 실행한다.
2. P14 separate live scaled approval intake를 검증한다.
3. P15 runtime enablement boundary를 valid review-only로 만든다.
4. P16 dry-run harness를 실제 운영 tick과 동일한 구조로 검증한다.
5. daily report, incident report, rollback, full shutdown을 검증한다.

### 완료 기준

- P16 dry-run이 clean하다.
- live scaled runtime enablement는 별도 operator activation 전까지 false다.

## 14. Phase 11 - 실제 제한적 live scaled activation

이 단계는 현재 패키지 범위 밖이다. 다음 조건이 모두 충족될 때만 별도 runtime activation package에서 진행한다.

- P7 valid.
- P8 valid.
- P9 valid.
- P10/P11/P12 valid.
- P13/P14 valid.
- P15 valid.
- P16 clean.
- P30 go/no-go matrix가 go review-only 상태.
- P45 또는 이후 external reviewer acceptance가 approved.
- operator final runtime activation request가 별도 승인됨.

초기 live scaled는 다음 제한을 둔다.

```text
symbol: BTCUSDT only
max order count: very low
max notional: strict cap
daily loss cap: strict cap
max consecutive loss: strict cap
manual kill switch: required
automatic rollback: required
all orders reconciled: required
```

## 15. 필수 검증 명령

각 phase 후 다음을 실행한다.

```bash
PYTHONPATH=src:. python -m compileall -q src config tests scripts
PYTHONPATH=src:. pytest -q tests
PYTHONPATH=src:. python scripts/lint_agents.py
PYTHONPATH=src:. python scripts/validate_agent_contracts.py
PYTHONPATH=src:. python scripts/validate_agent_outputs.py
PYTHONPATH=src:. python scripts/run_agent_evals.py
PYTHONPATH=src:. python scripts/status_consistency_checker.py .
```

P6 이후 실제 runtime 관련 검증은 별도 local runtime package에서만 실행하고, source/evidence package에는 redacted evidence만 반영한다.

## 16. 다음 작업의 한 줄 지시

```text
Stop expanding external review wrappers for now; create the first real signed-testnet evidence chain and make P7/P8 validate it without weakening any disabled runtime defaults.
```