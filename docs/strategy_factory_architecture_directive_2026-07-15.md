# Crypto_AI_System 독립 에이전트 기반 지속형 전략 생산·선발·운영·퇴출 구조 설계 및 GitHub 적용 지시서

- **문서 버전:** v1.0
- **작성 기준일:** 2026-07-15
- **대상 저장소:** `thomasryu1992-commits/crypto_ai_system`
- **검토 기준:** 현재 `main` 브랜치 및 최근 통합된 Phase A / Phase B+E 구조
- **문서 목적:** 현재 5-Agent 파이프라인을 유지하면서, 전략을 지속 생성하고 Batch 단위 백테스트를 통해 우수 전략을 선발하며, 여러 선발 전략을 동시에 운영하고, 실운영 성과가 기준 이하로 하락한 전략을 자동 중지·퇴출하는 독립 에이전트 구조를 정의한다.

---

# 1. 목표 정의

본 시스템은 하나의 고정 진입 전략만 사용하는 시스템이 아니다.

또한 여러 전략을 한 번 생성한 뒤 영구적으로 유지하는 시스템도 아니다.

최종 목표는 다음과 같다.

```text
전략 후보를 지속 생성
        ↓
4개 단위 Generation Batch 구성
        ↓
각 전략 독립 백테스트
        ↓
Batch 내 최상위 전략 선발
        ↓
절대 성과 기준 검증
        ↓
기존 Active Strategy Pool에 추가
        ↓
여러 활성 전략을 OR 조건으로 동시 운영
        ↓
전략별 Paper/Testnet/Live 성과 독립 추적
        ↓
성과 저하 전략 자동 Warning / Probation / Suspend
        ↓
장기 실패 전략 Archive
        ↓
새로운 전략이 지속적으로 Pool을 보충
```

예:

```text
Generation Batch 001

Strategy 001
Strategy 002
Strategy 003
Strategy 004

→ Backtest

→ Strategy 001 선발


Generation Batch 002

Strategy 005
Strategy 006
Strategy 007
Strategy 008

→ Backtest

→ Strategy 006 선발


Active Strategy Pool

Strategy 001
OR
Strategy 006
```

실제 거래 조건:

```text
(
    Strategy 001 Entry Match
    OR
    Strategy 006 Entry Match
)

AND

Data Health PASS

AND

ResearchSignal Permission PASS

AND

Signal QA PASS

AND

PreOrderRiskGate PASS

AND

Execution Stage Permission PASS
```

---

# 2. 핵심 설계 원칙

## 2.1 전략은 거래 기회를 만들고 RiskGate는 거래 권한을 결정한다

전략이 조건을 충족했다고 즉시 주문하면 안 된다.

```text
Strategy Match
    ↓
Entry Candidate
    ↓
Research Permission
    ↓
PreOrderRiskGate
    ↓
OrderIntent
    ↓
Execution
```

전략의 역할:

- 시장 조건 평가
- 방향 판단
- Entry 후보 생성
- Stop Loss 후보 생성
- Take Profit 후보 생성
- Invalidation 조건 생성
- 해당 전략 ID와 버전 기록

전략이 하면 안 되는 역할:

- RiskGate 우회
- 주문 직접 제출
- 포지션 한도 변경
- 손실 한도 변경
- Runtime Stage 변경
- Live 승격
- 다른 전략 자동 삭제

---

## 2.2 활성 전략은 OR, 안전 조건은 AND

활성 전략:

```text
S001
OR
S006
OR
S011
OR
S019
```

공통 안전 조건:

```text
Data Health
AND
ResearchSignal
AND
Signal QA
AND
PreOrderRiskGate
AND
Position Limit
AND
Daily Loss Limit
AND
Kill Switch
AND
Venue Readiness
```

최종 거래 허용식:

```text
ENTRY_ALLOWED
=
(
  S001_MATCH
  OR S006_MATCH
  OR S011_MATCH
)

AND COMMON_RESEARCH_PERMISSION

AND COMMON_RISK_PERMISSION
```

---

## 2.3 독립 에이전트는 별도 서버를 의미하지 않는다

현재 단계에서 독립 에이전트는 Microservice를 의미하지 않는다.

각 에이전트는 동일 프로세스 안에서 실행할 수 있다.

독립성은 다음으로 정의한다.

- 독립 Input Contract
- 독립 Output Contract
- 독립 상태 소유권
- 독립 Registry
- 독립 테스트
- 명확한 권한 제한
- 다른 Agent 내부 구현에 대한 직접 의존 금지

현재 단계에서는 다음을 추가하지 않는다.

- Kafka
- Redis
- Kubernetes
- Agent별 별도 서버
- Agent별 별도 Database
- 분산 이벤트 버스

권장:

```text
Single Process
+
Typed Agent Contracts
+
SQLite Transaction
+
Append-only Audit Registry
```

---

# 3. 현재 GitHub 구조

최근 구조는 다음 5단계 파이프라인을 사용한다.

```text
DataAgent
    ↓
ResearchAgent
    ↓
ValidationAgent
    ↓
TradingAgent
    ↓
FeedbackAgent
```

최근 Phase A 및 Phase B+E를 통해 다음 기반이 추가되었다.

- Cycle ID 기반 실행 계보
- Active ResearchSignal v2
- 동일 Cycle Signal QA
- 실제 PreOrderRiskGate 연결
- Canonical OrderIntent
- Paper/Testnet ExecutionPort
- Paper Position Lifecycle
- Reconciliation
- Outcome Analytics
- Performance Report
- Candidate Profile

현재 상위 실행 경로는 이전보다 크게 개선되었다.

그러나 전략 운영 관점에서는 아직 다음 구조다.

```text
Market Data
    ↓
하나의 공통 Feature Set
    ↓
하나의 Scoring Model
    ↓
하나의 Scenario
    ↓
하나의 ResearchSignal
    ↓
하나의 Default Paper Profile
    ↓
하나의 Entry Decision
```

현재 진입 구조는 복수 전략 Pool이 아니다.

---

# 4. 현재 GitHub와 목표 구조의 차이

| 영역 | 현재 GitHub | 목표 구조 | 필요 조치 |
|---|---|---|---|
| 전략 생성 | 없음 | 지속형 Strategy Generator | 신규 Agent 필요 |
| 전략 Batch | 없음 | 4개 단위 Generation Batch | 신규 Registry 필요 |
| 전략 Schema | 단일 Profile 중심 | StrategySpec 표준 | 신규 Contract 필요 |
| 백테스트 | 과거 도구 및 일부 검증 존재 | 전략별 통합 Backtest Engine | 활성 경로 신규 통합 |
| Batch 선발 | 없음 | 상대 순위 + 절대 기준 | Champion Selector 필요 |
| 활성 전략 | `paper_default_v1` 중심 | 다중 Champion Pool | Active Strategy Registry 필요 |
| 진입 판정 | 단일 Research/Scenario 기반 | 여러 Strategy Evaluator | Entry Strategy Router 필요 |
| 진입 결합 | 단일 Signal | `S001 OR S006 OR ...` | OR Router 필요 |
| 전략별 ID | 충분하지 않음 | 모든 Chain에 Strategy ID | ID Chain 확장 필요 |
| 전략별 성과 | Profile/Signal 기준 일부 가능 | Strategy ID 기준 완전 분리 | Outcome Schema 확장 |
| 성과 악화 처리 | Candidate Drop 추천 | Warning → Probation → Suspend → Archive | Lifecycle Manager 필요 |
| 자동 퇴출 | 없음 | 안전 방향 자동 Suspend | 신규 Policy 필요 |
| 자동 재활성 | 없음 | 금지, 승인 필요 | Fail-closed 유지 |
| 전략 자동 적용 | 금지 | Paper 한정 자동 등록 가능 | Stage별 권한 분리 |
| Testnet/Live 승격 | 수동 승인 | 계속 수동 승인 | 기존 원칙 유지 |

---

# 5. 목표 독립 에이전트 구조

```text
┌──────────────────────────────────────┐
│ 1. DataAgent                         │
│ Market Data / Source Health          │
└──────────────────┬───────────────────┘
                   ↓
┌──────────────────────────────────────┐
│ 2. FeatureAgent                      │
│ FeatureSnapshot / Regime             │
└──────────────────┬───────────────────┘
                   ↓
┌──────────────────────────────────────┐
│ 3. ResearchAgent                     │
│ ResearchSignal / Signal QA           │
└──────────────────┬───────────────────┘
                   ↓
        ┌──────────┴───────────┐
        │                      │
        ↓                      ↓
┌───────────────────┐  ┌──────────────────────────┐
│ Runtime Trading   │  │ Strategy Factory Domain  │
│ Path              │  │                          │
└─────────┬─────────┘  └────────────┬─────────────┘
          │                         │
          ↓                         ↓
┌───────────────────┐  ┌──────────────────────────┐
│ Active Strategy   │  │ 4. StrategyGeneration   │
│ Pool              │  │ Agent                    │
└─────────┬─────────┘  └────────────┬─────────────┘
          │                         ↓
          │              ┌──────────────────────────┐
          │              │ 5. StrategyValidation   │
          │              │ Agent                    │
          │              └────────────┬─────────────┘
          │                           ↓
          │              ┌──────────────────────────┐
          │              │ 6. BacktestAgent         │
          │              └────────────┬─────────────┘
          │                           ↓
          │              ┌──────────────────────────┐
          │              │ 7. ChampionSelection     │
          │              │ Agent                    │
          │              └────────────┬─────────────┘
          │                           ↓
          │              ┌──────────────────────────┐
          │              │ Strategy Champion        │
          │              │ Registry                 │
          │              └────────────┬─────────────┘
          │                           │
          └──────────────┬────────────┘
                         ↓
┌──────────────────────────────────────┐
│ 8. EntryStrategyRouterAgent          │
│ S001 OR S006 OR S011                 │
└──────────────────┬───────────────────┘
                   ↓
┌──────────────────────────────────────┐
│ 9. DecisionAgent                     │
│ Direction / Entry / SL / TP / RR     │
└──────────────────┬───────────────────┘
                   ↓
┌──────────────────────────────────────┐
│ 10. PreOrderRiskGateAgent            │
└──────────────────┬───────────────────┘
                   ↓
┌──────────────────────────────────────┐
│ 11. ExecutionAgent                   │
│ Paper / Testnet Adapter              │
└──────────────────┬───────────────────┘
                   ↓
┌──────────────────────────────────────┐
│ 12. ReconciliationAgent              │
└──────────────────┬───────────────────┘
                   ↓
┌──────────────────────────────────────┐
│ 13. OutcomeAgent                     │
└──────────────────┬───────────────────┘
                   ↓
┌──────────────────────────────────────┐
│ 14. StrategyPerformanceAgent         │
└──────────────────┬───────────────────┘
                   ↓
┌──────────────────────────────────────┐
│ 15. StrategyLifecycleAgent           │
│ ACTIVE / WARNING / PROBATION         │
│ SUSPENDED / ARCHIVED                 │
└──────────────────────────────────────┘
```

---

# 6. Agent별 상세 역할

## 6.1 DataAgent

### 역할

- Price Data 수집
- Derivatives Data 수집
- Source Health 생성
- Freshness 생성
- Synthetic/Fallback 여부 생성

### Input

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "cycle_id": "cycle_xxx"
}
```

### Output

```json
{
  "data_snapshot_id": "data_snapshot_xxx",
  "cycle_id": "cycle_xxx",
  "source_health": {},
  "candles": [],
  "derivatives": {}
}
```

### 권한

```text
can_modify_strategy = false
can_activate_strategy = false
can_submit_order = false
```

### 현재 GitHub 적용

현재 DataAgent와 Market Snapshot 구조를 유지한다.

추가 필요:

- Strategy Backtest용 Historical Data Adapter
- 기간별 데이터 Slice
- 거래 비용 데이터
- Spread/Slippage 추정 데이터

---

## 6.2 FeatureAgent

### 역할

모든 전략이 공통으로 사용하는 Feature를 생성한다.

예:

```text
SMA20
SMA50
EMA20
EMA50
RSI
ATR
ADX
Volume Ratio
OI Change
Funding Z-score
Breakout Distance
Pullback Depth
Candle Body Ratio
Upper/Lower Wick Ratio
Market Regime
Volatility Regime
```

### 원칙

각 전략이 Feature를 직접 계산하지 않는다.

모든 전략은 동일 FeatureSnapshot을 사용한다.

### 이유

- 계산 중복 제거
- 백테스트와 실시간 결과 일치
- 전략 간 비교 가능
- Feature Hash 유지
- Look-ahead Bias 방지

### Output

```json
{
  "feature_snapshot_id": "feature_snapshot_xxx",
  "data_snapshot_id": "data_snapshot_xxx",
  "feature_matrix_sha256": "...",
  "features": {}
}
```

### 현재 GitHub 적용

현재 Market Snapshot과 Active ResearchSignal의 Feature 부분을 별도 FeatureAgent로 승격한다.

---

## 6.3 ResearchAgent

### 역할

- 시장 상태 해석
- ResearchSignal 생성
- Signal QA
- 공통 방향 허용

### 중요한 역할 분리

ResearchAgent는 특정 전략을 선발하지 않는다.

ResearchAgent는 공통 시장 Permission을 제공한다.

예:

```json
{
  "allow_long": true,
  "allow_short": false,
  "allow_new_position": true,
  "risk_level": "normal"
}
```

### 현재 GitHub 적용

현재 Active ResearchSignal v2 구조를 유지한다.

단 다음을 추가한다.

```text
market_regime
volatility_regime
liquidity_regime
research_permission_id
```

---

## 6.4 StrategyGenerationAgent

### 역할

전략 후보를 지속 생성한다.

### 생성 단위

기본:

```text
4 strategies per generation batch
```

예:

```text
GEN-001

S001
S002
S003
S004
```

### 전략 생성 방식

초기에는 Code Generation을 금지한다.

허용된 Strategy Template과 Parameter 조합만 사용한다.

```json
{
  "strategy_id": "S006",
  "strategy_family": "trend_pullback",
  "strategy_version": "1.0",
  "timeframe": "1h",
  "direction": "long_short",
  "entry_rules": {
    "fast_ma": 20,
    "slow_ma": 50,
    "pullback_distance_pct": 0.5,
    "volume_ratio_min": 1.15,
    "oi_change_min": 0.3
  },
  "exit_rules": {
    "stop_atr": 1.2,
    "target_atr": 2.4,
    "max_holding_bars": 24
  }
}
```

### 생성 전략 비율 권장

```text
70%
기존 우수 전략 Parameter 변형

20%
기존 전략 조건 조합 변형

10%
새로운 Strategy Family
```

### 권한

```text
can_create_candidate_spec = true

can_create_runtime_code = false

can_activate_strategy = false

can_modify_risk_gate = false

can_submit_order = false
```

---

## 6.5 StrategyValidationAgent

### 역할

생성 전략의 구조와 안전성을 검증한다.

### 검사 항목

- 허용 Indicator만 사용
- 존재하지 않는 Feature 사용 금지
- Future Data 참조 금지
- Look-ahead Bias 금지
- Entry/Exit Rule 완전성
- Stop Loss 필수
- Max Holding 필수
- Parameter 범위
- Timeframe 허용 범위
- Strategy Hash
- Schema Version

### 차단 예

```text
BLOCK_LOOKAHEAD_BIAS

BLOCK_UNKNOWN_FEATURE

BLOCK_MISSING_STOP_LOSS

BLOCK_UNBOUNDED_HOLDING

BLOCK_INVALID_PARAMETER_RANGE
```

### Output

```json
{
  "strategy_validation_id": "...",
  "strategy_id": "S006",
  "approved_for_backtest": true,
  "block_reasons": []
}
```

---

## 6.6 BacktestAgent

### 역할

각 StrategySpec을 독립적으로 평가한다.

### 필수 백테스트 요소

- 동일 Historical Data
- 동일 거래 비용
- 동일 Slippage
- 동일 Position Sizing
- 동일 Risk Model
- 동일 Execution Model
- 동일 Benchmark 기간

### 평가 방식

단순 전체 기간 Backtest만 사용하지 않는다.

```text
In-sample
+
Out-of-sample
+
Walk-forward
+
Regime Split
```

### 필수 Metrics

```text
trade_count
win_rate
expectancy_R
profit_factor
average_R
max_drawdown_R
sharpe_like_score
sortino_like_score
fee_cost_R
slippage_cost_R
long_expectancy
short_expectancy
regime_consistency
walk_forward_pass_rate
parameter_stability
```

### Output

```json
{
  "backtest_run_id": "...",
  "strategy_id": "S006",
  "generation_id": "GEN-002",
  "metrics": {},
  "qualified": true
}
```

---

## 6.7 ChampionSelectionAgent

### 역할

각 Batch에서 최상위 전략을 선발한다.

### 중요 원칙

Batch 1위라고 자동 선발하지 않는다.

다음 두 조건을 모두 통과해야 한다.

```text
Relative Ranking PASS

AND

Absolute Performance Gate PASS
```

### 상대 평가

```text
1~4 중 종합 점수 1위
```

### 절대 평가 예

```text
trade_count >= 100

expectancy_R >= +0.10

profit_factor >= 1.15

walk_forward_pass_rate >= 0.70

max_drawdown_R <= 10

fee_adjusted_expectancy > 0

parameter_stability PASS
```

### 결과

```text
Champion = S001
```

또는:

```text
Champion = NONE
```

### Output

```json
{
  "generation_id": "GEN-001",
  "selected_strategy_id": "S001",
  "selection_status": "BATCH_CHAMPION",
  "activation_permission": "PAPER_ONLY"
}
```

### 권한

```text
can_add_to_paper_pool = true

can_add_to_testnet_pool = false

can_add_to_live_pool = false
```

---

## 6.8 ActiveStrategyPoolAgent

### 역할

현재 활성 전략 목록을 관리한다.

### 예

```json
{
  "pool_version": "active_strategy_pool.v1",
  "stage": "paper",
  "active_strategies": [
    {
      "strategy_id": "S001",
      "status": "ACTIVE"
    },
    {
      "strategy_id": "S006",
      "status": "ACTIVE"
    }
  ]
}
```

### 상태

```text
PAPER_ACTIVE

SIGNED_TESTNET_CANDIDATE

SIGNED_TESTNET_ACTIVE

LIVE_CANARY_CANDIDATE

LIVE_ACTIVE

WARNING

PROBATION

SUSPENDED

ARCHIVED
```

### 현재 GitHub 적용

현재 `paper_default_v1` 단일 Profile을 다중 Strategy Profile Registry로 확장한다.

---

## 6.9 EntryStrategyRouterAgent

### 역할

모든 활성 전략을 동일 FeatureSnapshot에서 평가한다.

### 예

```json
{
  "evaluations": [
    {
      "strategy_id": "S001",
      "matched": true,
      "direction": "LONG"
    },
    {
      "strategy_id": "S006",
      "matched": false,
      "direction": "NONE"
    }
  ]
}
```

### OR 정책

```text
S001_MATCH
OR
S006_MATCH
```

이면 Entry Candidate 생성.

### 같은 방향 복수 Match

```text
S001 → LONG

S006 → LONG
```

결과:

```json
{
  "direction": "LONG",
  "matched_strategy_ids": [
    "S001",
    "S006"
  ],
  "matched_strategy_count": 2,
  "order_candidate_count": 1
}
```

기본 정책:

```text
주문 1개
```

전략 두 개가 일치했다고 자동으로 Position Size를 두 배로 늘리지 않는다.

---

## 6.10 StrategyConflictResolver

### 반대 방향 Match

```text
S001 → LONG

S006 → SHORT
```

초기 정책:

```text
BLOCK_STRATEGY_DIRECTION_CONFLICT
```

향후 충분한 성과가 쌓인 뒤에만 다음을 고려한다.

```text
현재 Regime에서 성과가 높은 전략 우선
```

초기에는 Fail-closed가 권장된다.

---

## 6.11 DecisionAgent

### 역할

Router 결과를 Canonical TradePlan으로 변환한다.

```json
{
  "trade_plan_id": "...",
  "primary_strategy_id": "S001",
  "matched_strategy_ids": [
    "S001",
    "S006"
  ],
  "direction": "LONG",
  "entry": 100000,
  "stop_loss": 99000,
  "take_profit": 102500,
  "risk_reward": 2.5
}
```

### 현재 GitHub 적용

현재 Trading Decision Agent에 다음 필드를 추가한다.

```text
strategy_id

strategy_version

strategy_generation_id

matched_strategy_ids

strategy_rule_hash

strategy_pool_version
```

---

## 6.12 PreOrderRiskGateAgent

### 역할

기존 PreOrderRiskGate를 그대로 유지한다.

추가 검사:

```text
Active Strategy Registry 존재

Strategy 상태 ACTIVE

Strategy Hash 일치

Strategy Stage 허용

Strategy가 Suspend 상태가 아님

Strategy Backtest Approval 존재

Strategy Runtime Version 일치
```

### 추가 Block

```text
BLOCK_STRATEGY_NOT_ACTIVE

BLOCK_STRATEGY_HASH_MISMATCH

BLOCK_STRATEGY_STAGE_NOT_APPROVED

BLOCK_STRATEGY_SUSPENDED

BLOCK_STRATEGY_BACKTEST_EVIDENCE_MISSING
```

---

## 6.13 ExecutionAgent

### 역할

기존 Canonical ExecutionPort를 유지한다.

```text
OrderIntent
    ↓
PaperExecutionAdapter

or

SignedTestnetAdapter
```

전략마다 별도 Executor를 만들지 않는다.

모든 전략이 동일 Execution Kernel을 사용해야 한다.

---

## 6.14 OutcomeAgent

### 역할

모든 Outcome에 Strategy ID를 유지한다.

### 필수 Chain

```text
strategy_id

strategy_version

strategy_generation_id

strategy_rule_hash

trade_plan_id

risk_gate_id

order_intent_id

execution_id

reconciliation_id

outcome_id
```

### 이유

전략별 독립 성과 측정.

---

## 6.15 StrategyPerformanceAgent

### 역할

전략별 성과를 독립 집계한다.

예:

```json
{
  "strategy_id": "S006",
  "lifetime": {
    "trade_count": 185,
    "win_rate": 0.47,
    "expectancy_R": 0.18
  },
  "rolling_20": {
    "win_rate": 0.35,
    "expectancy_R": -0.12
  },
  "rolling_50": {
    "win_rate": 0.39,
    "expectancy_R": -0.05
  }
}
```

### 평가 Window

```text
Rolling 20 trades

Rolling 50 trades

Rolling 100 trades

Recent 7 days

Recent 30 days

Lifetime
```

---

## 6.16 StrategyLifecycleAgent

### 역할

성과 저하 전략을 중지·퇴출한다.

### 권장 상태 전이

```text
ACTIVE

↓

WARNING

↓

PROBATION

↓

SUSPENDED

↓

ARCHIVED
```

### Warning 예

```text
Rolling 20 Expectancy < 0

OR

Profit Factor < 1.0
```

### Probation 예

```text
Rolling 30 Expectancy <= -0.05R

OR

Profit Factor < 0.9

OR

실운영 승률이 Backtest 승률보다 15%p 이상 하락
```

### Suspend 예

```text
Rolling 50 Expectancy < 0

AND

Profit Factor < 0.9

AND

2개 연속 평가 구간 실패
```

### Archive 예

```text
실운영 거래 수 >= 100

AND

장기 Expectancy < 0

AND

3개 연속 평가 구간 실패
```

### 중요

승률만으로 폐기하지 않는다.

최소 평가 항목:

```text
Win Rate

Expectancy

Profit Factor

Average R

Drawdown

Fee

Slippage

Sample Size
```

---

# 7. 자동화 권한 정책

## 자동 허용

```text
Strategy Candidate 생성

Backtest 실행

Backtest 결과 기록

Batch Champion 선정

Paper Pool 등록

Paper 전략 Warning

Paper 전략 Probation

Paper 전략 자동 Suspend
```

## 자동 금지

```text
Signed Testnet 자동 승격

Live Canary 자동 승격

Live 자동 재활성화

Risk Limit 변경

Position Size 상한 변경

Executor 변경

Secret 접근

Runtime 코드 자동 수정
```

---

# 8. 전략 재활성 정책

자동 Suspend는 허용한다.

```text
성과 악화
→ 자동 Suspend
→ 신규 Entry 차단
```

자동 재활성은 금지한다.

재활성:

```text
Suspended Strategy

↓

재백테스트

↓

Paper 재검증

↓

Manual Approval

↓

Stage 재등록
```

---

# 9. 권장 StrategySpec Schema

```json
{
  "schema_version": "strategy_spec.v1",
  "strategy_id": "S006",
  "strategy_version": "1.0",
  "generation_id": "GEN-002",
  "strategy_family": "trend_pullback",
  "status": "GENERATED",
  "symbol_scope": [
    "BTCUSDT"
  ],
  "timeframe": "1h",
  "direction": "long_short",
  "entry_rules": {
    "operator": "AND",
    "conditions": [
      {
        "feature": "sma20",
        "comparison": ">",
        "value_from": "sma50"
      },
      {
        "feature": "pullback_distance_pct",
        "comparison": "<=",
        "value": 0.5
      },
      {
        "feature": "volume_ratio",
        "comparison": ">=",
        "value": 1.15
      }
    ]
  },
  "exit_rules": {
    "stop_model": "atr",
    "stop_atr": 1.2,
    "target_atr": 2.4,
    "max_holding_bars": 24
  },
  "risk_constraints": {
    "max_risk_per_trade_R": 1.0
  },
  "created_by": "StrategyGenerationAgent",
  "can_submit_orders": false,
  "can_modify_runtime": false,
  "strategy_rule_hash": "sha256..."
}
```

---

# 10. 신규 Registry 구조

```text
strategy_generation_registry

strategy_candidate_registry

strategy_validation_registry

strategy_backtest_registry

strategy_champion_registry

active_strategy_registry

strategy_entry_evaluation_registry

strategy_trade_plan_registry

strategy_performance_registry

strategy_lifecycle_registry

strategy_retirement_registry
```

---

# 11. 현재 ID Chain 확장

현재 Canonical ID Chain:

```text
data_snapshot_id

→ feature_snapshot_id

→ research_signal_id

→ profile_id

→ decision_id

→ risk_gate_id

→ order_intent_id

→ execution_id

→ reconciliation_id

→ outcome_id

→ feedback_cycle_id
```

확장:

```text
strategy_generation_id

→ strategy_id

→ strategy_validation_id

→ backtest_run_id

→ champion_selection_id

→ active_strategy_registration_id

→ strategy_entry_evaluation_id

→ trade_plan_id

→ decision_id

→ risk_gate_id

→ order_intent_id

→ execution_id

→ reconciliation_id

→ outcome_id

→ strategy_performance_report_id

→ strategy_lifecycle_decision_id
```

---

# 12. 권장 디렉터리 구조

```text
src/crypto_ai_system/

├── strategy_factory/
│
│   ├── contracts.py
│   ├── strategy_spec.py
│   ├── strategy_template_library.py
│   ├── strategy_generator_agent.py
│   ├── strategy_validator_agent.py
│   ├── generation_batch.py
│   ├── strategy_hash.py
│   └── allowed_feature_registry.py
│
├── backtesting/
│
│   ├── backtest_agent.py
│   ├── backtest_engine.py
│   ├── execution_simulator.py
│   ├── cost_model.py
│   ├── walk_forward.py
│   ├── regime_evaluator.py
│   ├── performance_metrics.py
│   └── champion_selector_agent.py
│
├── strategies/
│
│   ├── active_strategy_pool.py
│   ├── strategy_evaluator.py
│   ├── entry_strategy_router_agent.py
│   ├── strategy_conflict_resolver.py
│   └── strategy_runtime_contract.py
│
├── feedback/
│
│   ├── strategy_performance_agent.py
│   ├── strategy_lifecycle_agent.py
│   ├── strategy_probation_policy.py
│   └── strategy_retirement_policy.py
│
└── registry/
    ├── strategy_generation_registry.py
    ├── strategy_backtest_registry.py
    ├── strategy_champion_registry.py
    ├── active_strategy_registry.py
    ├── strategy_performance_registry.py
    └── strategy_lifecycle_registry.py
```

---

# 13. 현재 GitHub 파일별 적용 방향

## 유지

```text
src/crypto_ai_system/pipeline/orchestrator.py

src/crypto_ai_system/pipeline/data_agent.py

src/crypto_ai_system/pipeline/research_agent.py

src/crypto_ai_system/pipeline/validation_agent.py

src/crypto_ai_system/pipeline/trading_agent.py

src/crypto_ai_system/pipeline/feedback_agent.py

src/crypto_ai_system/research/active_research_signal.py

src/crypto_ai_system/trading/pre_order_risk_gate.py

src/crypto_ai_system/execution/execution_port.py

src/crypto_ai_system/execution/order_executor.py

src/crypto_ai_system/execution/paper_position_kernel.py
```

## 확장

```text
TradingAgent

→ ActiveStrategyPool 호출

→ EntryStrategyRouter 호출

→ Strategy Evaluation 결과를 DecisionAgent에 전달
```

```text
FeedbackAgent

→ StrategyPerformanceAgent 호출

→ StrategyLifecycleAgent 호출
```

## 신규

```text
StrategyGenerationAgent

StrategyValidationAgent

BacktestAgent

ChampionSelectionAgent

ActiveStrategyPoolAgent

EntryStrategyRouterAgent

StrategyPerformanceAgent

StrategyLifecycleAgent
```

---

# 14. Runtime Pipeline 적용안

현재:

```text
DataAgent

→ ResearchAgent

→ ValidationAgent

→ TradingAgent

→ FeedbackAgent
```

목표:

```text
DataAgent

→ FeatureAgent

→ ResearchAgent

→ ActiveStrategyPoolAgent

→ EntryStrategyRouterAgent

→ DecisionAgent

→ ValidationAgent

→ PreOrderRiskGate

→ TradingAgent

→ ReconciliationAgent

→ FeedbackAgent

→ StrategyPerformanceAgent

→ StrategyLifecycleAgent
```

Strategy Factory는 Runtime Hot Path와 분리한다.

```text
Scheduled Research Loop

StrategyGenerationAgent

→ StrategyValidationAgent

→ BacktestAgent

→ ChampionSelectionAgent

→ Paper Active Pool
```

---

# 15. 전략 생성 스케줄 권장

초기:

```text
Weekly

1 Generation Batch

4 Candidate Strategies
```

데이터가 충분해진 뒤:

```text
Daily

1 Generation Batch

단 동일 Family 과다 생성 방지
```

전략 생성이 Runtime Trading보다 우선하면 안 된다.

다음 우선순위:

```text
1. Trading Runtime 안정성

2. Position/Reconciliation

3. Feedback 기록

4. Strategy Factory

5. Backtest

6. Champion 선발
```

---

# 16. 전략 수 상한

전략을 무한히 Active 상태로 쌓으면 안 된다.

권장 초기 상한:

```text
Maximum Paper Active Strategies = 5

Maximum Signed Testnet Active Strategies = 2

Maximum Live Canary Active Strategies = 1

Maximum Live Active Strategies = 별도 승인
```

Pool이 가득 찬 경우:

```text
새 Champion 생성

↓

기존 Active 중 성과 최하위와 비교

↓

새 전략이 충분히 우수하면

기존 전략 → Probation 또는 Suspend

새 전략 → Paper Active
```

자동 Live 교체는 금지한다.

---

# 17. Backtest 선발 점수 예시

```text
Champion Score

=

Expectancy Score × 0.30

+

Profit Factor Score × 0.20

+

Walk-forward Stability × 0.20

+

Regime Consistency × 0.10

+

Sample Quality × 0.10

-

Drawdown Penalty × 0.10
```

승률은 독립 보조 지표로 사용한다.

---

# 18. 테스트 요구사항

## Unit Tests

```text
StrategySpec Schema

Strategy Hash

Allowed Feature

Parameter Range

Look-ahead Block

Generation Batch

Backtest Metrics

Champion Selection

Active Pool

OR Routing

Direction Conflict

Strategy Status

Performance Window

Probation

Suspend

Archive
```

## Integration Tests

```text
S001 Match

→ Decision

→ RiskGate

→ Paper Order

→ Outcome

→ S001 Performance
```

```text
S001 Match

S006 Match

Same Direction

→ One Order

→ matched_strategy_ids = [S001, S006]
```

```text
S001 LONG

S006 SHORT

→ BLOCK_STRATEGY_DIRECTION_CONFLICT
```

```text
S006 Performance Degrades

→ WARNING

→ PROBATION

→ SUSPENDED

→ New Entry Block
```

---

# 19. 안전 회귀 테스트

반드시 유지:

```text
Strategy Agent cannot submit order

Strategy Agent cannot modify runtime

Strategy Agent cannot change risk limit

Strategy Agent cannot read secrets

Backtest result cannot enable testnet

Champion result cannot enable live

Suspended strategy cannot create OrderIntent

Archived strategy cannot enter Active Pool without review

Missing Strategy Hash blocks

Missing Backtest Evidence blocks
```

---

# 20. 단계별 개발 로드맵

## Phase S1 — Strategy Contract Foundation

### 작업

- StrategySpec
- StrategyStatus
- Strategy Hash
- Allowed Feature Registry
- Strategy Registry

### 완료 기준

- 전략 정의가 Python 코드가 아니라 검증 가능한 Spec
- Runtime 코드 자동 생성 없음

---

## Phase S2 — Strategy Generation Batch

### 작업

- StrategyGenerationAgent
- 4개 Batch
- Template Library
- Parameter Mutation

### 완료 기준

- GEN-001 생성
- S001~S004 생성
- 각 전략 Hash 생성

---

## Phase S3 — Strategy Validation

### 작업

- Schema Validator
- Feature Validator
- Look-ahead Validator
- Risk Rule Validator

### 완료 기준

- 비정상 전략 Backtest 진입 차단

---

## Phase S4 — Unified Backtest Engine

### 작업

- Historical Data Adapter
- Cost Model
- Slippage Model
- Walk-forward
- Regime Split

### 완료 기준

- S001~S004 동일 조건 평가
- 결과 재현 가능

---

## Phase S5 — Batch Champion Selection

### 작업

- Relative Ranking
- Absolute Performance Gate
- Champion Registry

### 완료 기준

```text
GEN-001

S001 selected
```

또는:

```text
GEN-001

Champion NONE
```

---

## Phase S6 — Active Strategy Pool

### 작업

- Paper Pool
- Pool Limit
- Strategy Status
- Runtime Load

### 완료 기준

```text
S001 ACTIVE
```

---

## Phase S7 — Multi-Strategy Entry Router

### 작업

- S001 OR S006
- Same Direction Merge
- Opposite Direction Block
- Strategy ID Chain

### 완료 기준

복수 전략이 독립적으로 Entry 생성.

---

## Phase S8 — Strategy Outcome Attribution

### 작업

- 모든 거래에 Strategy ID
- 복수 Match Attribution
- Primary Strategy
- Supporting Strategy

### 완료 기준

전략별 성과 독립 계산.

---

## Phase S9 — Strategy Performance Monitoring

### 작업

- Rolling 20
- Rolling 50
- Rolling 100
- Lifetime

### 완료 기준

전략별 성과 Dashboard.

---

## Phase S10 — Strategy Lifecycle

### 작업

- Warning
- Probation
- Suspend
- Archive

### 완료 기준

성과 악화 전략 신규 진입 자동 차단.

---

## Phase S11 — Continuous Strategy Factory

### 작업

- 주기 생성
- 다음 Generation
- Pool 보충
- Diversity Guard

### 완료 기준

```text
GEN-001

→ S001

GEN-002

→ S006

GEN-003

→ NONE

GEN-004

→ S014
```

---

# 21. 최종 목표 상태

```text
Active Strategy Pool

S001
S006
S014


Runtime

S001 Match

OR

S006 Match

OR

S014 Match


Common Gate

ResearchSignal PASS

AND

Signal QA PASS

AND

PreOrderRiskGate PASS


Execution

Canonical OrderIntent

→ Paper/Testnet/Live Adapter


Feedback

Outcome

→ Strategy Performance

→ Warning

→ Probation

→ Suspend

→ Archive


Factory

새 전략 지속 생성

→ Backtest

→ Champion

→ Active Pool
```

---

# 22. 최종 결론

현재 GitHub는 다음 기반까지는 이미 보유하고 있다.

```text
Data

→ ResearchSignal

→ Signal QA

→ Decision

→ PreOrderRiskGate

→ OrderIntent

→ Execution

→ Reconciliation

→ Outcome

→ Performance

→ Candidate
```

따라서 전체 시스템을 다시 만들 필요는 없다.

다음 계층을 추가하면 된다.

```text
StrategyGeneration

→ StrategyValidation

→ Backtest

→ ChampionSelection

→ ActiveStrategyPool

→ MultiStrategyEntryRouter

→ StrategyPerformance

→ StrategyLifecycle
```

핵심 원칙:

> 전략은 지속 생성된다.  
> 각 Generation은 독립 백테스트를 거친다.  
> Batch 1위라도 절대 기준을 통과하지 못하면 채택하지 않는다.  
> 채택된 전략은 기존 전략과 함께 OR 방식으로 거래 기회를 만든다.  
> 모든 전략은 동일 ResearchSignal과 PreOrderRiskGate를 통과한다.  
> 모든 거래 결과는 전략별로 귀속된다.  
> 성과가 악화된 전략은 자동 중지할 수 있다.  
> 자동 중지는 허용하지만 자동 Testnet·Live 승격과 자동 재활성은 금지한다.  
> Feedback은 전략 후보와 중지 결정을 만들 수 있지만 RiskGate와 Runtime 권한을 변경하지 않는다.  

최종적으로 구축해야 하는 것은 하나의 고정 전략 봇이 아니다.

> **새로운 전략을 지속적으로 생산하고, 백테스트로 선발하며, 여러 우수 전략을 동시에 운영하고, 성과가 무너진 전략을 자동 퇴출하는 독립 에이전트 기반 전략 생태계다.**
