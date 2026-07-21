---
name: verify
description: 이 리포의 변경을 CI와 동일한 기준으로 검증한다 — 컴파일, 테스트, 파이프라인 스모크, fail-closed 안전 플래그 가드.
---

# 이 리포에서 변경을 검증하는 법

`.github/workflows/ci.yml`이 도는 4단계를 로컬에서 그대로 재현한다.
**이 4개가 통과해야 "검증됨"이다.** 일부만 돌리고 완료라고 보고하지 않는다.

Windows 기준. CI는 Python 3.11이므로 3.11 시맨틱을 목표로 한다.

## 전제

- `python`이 아니라 **`py` 런처**를 쓴다 (이 PC의 `python`은 Store 스텁일 수 있음).
- **`PYTHONPATH`를 손으로 설정할 필요 없다.** `pytest.ini`의 `pythonpath = src, .`가
  테스트 경로를 잡고, `run_pipeline.py`는 스스로 부트스트랩한다.
  (`$env:PYTHONPATH='src;.'`를 앞에 붙이던 습관은 이제 불필요하다.)
- **`--basetemp`/`-p no:cacheprovider`도 붙일 필요 없다.** `pytest.ini`의 `addopts`에
  이미 들어 있다 (Windows 샌드박스가 기본 `%TEMP%\pytest-of-*`를 WinError 5로 막기 때문).
  즉 `py -m pytest -q`만 치면 된다.

## 검증 4단계 (CI 패리티)

```powershell
# 1. 유지 대상 트리 컴파일 — import 깨짐/구문 오류를 먼저 잡는다
py -m compileall -q src config core collectors builders risk bridge data_health run_pipeline.py

# 2. 유닛 + 통합 테스트
py -m pytest -q

# 3. 파이프라인 스모크 — 한 사이클 실제 실행
py run_pipeline.py
echo "exit=$LASTEXITCODE"

# 4. fail-closed 안전 플래그 가드 (반드시 통과해야 함)
py scripts/check_safety_defaults.py
```

### 3번 종료 코드를 오독하지 말 것

`run_pipeline.py`는 **0이 아니어도 정상일 수 있다.** CI 기준 그대로:

| 코드 | 의미 | 판정 |
|---|---|---|
| `0` | 거래 실행됨 | ✅ 정상 |
| `2` | 노트레이드 사이클 | ✅ 정상 (P0-6) |
| `10` / `20` / `30` / `50` | 안전 정지 / 에러 | ❌ 실패 |

**exit 2를 실패로 보고하지 않는다.** 진입 조건이 없어서 거래를 안 한 것은
파이프라인이 정상 동작한 결과다.

### 4번은 타협 대상이 아니다

`check_safety_defaults.py`는 `config/settings.py`의 live/testnet 주문 플래그가
전부 False인지 검사한다. 실패하면 **테스트를 고치지 말고 플래그를 되돌린다.**
CLAUDE.md의 non-negotiable 규칙 1번("어떤 주문 경로도 기본 활성화되지 않는다")을
코드로 강제하는 가드다.

## 상황별 추가 게이트 (CI에는 없음)

해당 작업을 할 때만 돌린다.

```powershell
py scripts/check_testnet_readiness.py       # 테스트넷 주문 경로를 건드렸을 때
py scripts/check_live_canary_readiness.py   # 라이브 카나리 준비 상태 점검
```

## 좁게 돌리기 (개발 중 반복 루프)

전체가 느리면 작업 중인 파일만:

```powershell
py -m pytest tests/test_pipeline.py -q          # 파이프라인만
py -m pytest tests/test_<대상>.py -q            # 특정 파일
py -m pytest -q -m "not integration"            # 네트워크/실파이프라인 제외
```

**단, 보고 직전에는 반드시 4단계 전체를 한 번 돌린다.** 좁은 실행만으로 완료 보고 금지.

## 상태 초기화 (필요할 때만)

```powershell
py reset_paper_state.py                          # 페이퍼 트레이딩 상태 초기화
py scripts/reset_paper_outcomes.py --confirm     # 리스크/성과 이력까지 0에서 시작 (백업 후 삭제)
```

주의: 청산된 페이퍼 결과는 `outcome_feedback_registry`가 단일 출처이고
`risk/risk_guard.py`가 거기서 리스크 이력을 읽는다. `storage/latest/paper_trades.json`을
지워도 리스크 이력은 초기화되지 않는다.

## 알려진 함정

- 한국어 출력이 섞이면 `$env:PYTHONUTF8='1'`을 설정한다.
- 콘솔에 나가는 문자열은 ASCII로 유지한다 — Windows cp949가 em-dash 같은 문자를
  인코딩하지 못해 죽는다. (`run_pipeline.py`는 stdout을 UTF-8로 재설정한다.)
- 새 모듈은 `src/crypto_ai_system/` 아래에 만든다. 루트 패키지
  (`core/`, `config/`, `collectors/`, `builders/`, `risk/`, `bridge/`, `data_health/`)는
  **동결**이며 이름으로 import된다 — `src/`로 옮기는 "정리"를 하지 않는다.

## 보고 형식

검증 결과는 **실제 출력을 인용해서** 보고한다. 4단계 각각의 통과/실패와,
3번의 경우 종료 코드와 그 의미를 함께 적는다. 실패를 요약으로 덮지 않는다.
