# 검수 하네스 구현 계획

> 검수 루프 단계 0. 사용자가 자리에 없어 루프가 직접 실행한다(인라인 실행, `docs/review/loop-prompt.md`).

**목표:** 두뇌를 실제(또는 가짜) Jev·Gemini와 가상 시계로 돌려 시나리오를 실행하고, 기록·상태 분석표·커버리지를 남긴다.

**구조:** `brain/review/` 파이썬 패키지. `harness.py`(실행기), `analysis.py`(분석표·커버리지), `__main__.py`(CLI), `scenarios/*.json`(기본 세트), `README.md`(사용법). 테스트는 `brain/tests/test_review.py`(가짜 클라이언트).

**스펙:** [검수 루프 스펙](../specs/2026-10-15-review-loop-design.md) 2·3절.

## 전역 제약

- 두뇌 코드(`brain/brain/`)는 바꾸지 않는다. 공개 메서드(`handle_event`, `drain`, `clock_tick`, `connected`, `set_keys`, `reset`, `state_snapshot`, `log_snapshot`, `aclose`)와 생성자 인자만 쓴다. 성격 지정만 `brain._dog`를 바꾼다(하네스 전용).
- 키는 `config.read_keys()`로만 읽는다. 키·대화를 로그에 쓰지 않는다. 기록 파일은 `brain/review/out/`(git 제외).
- 화면 흉내: 대사가 나오면 `dog_spoke`를 보낸다. `wait` 동안 화면처럼 조용함(`quiet`)을 보낸다(자리 있음 10분, 비움 30분, `events.ts`와 같은 값).

## 시나리오 형식

```json
{"name": "first-meeting", "description": "...", "personality": "평균|과묵·차분|예민·성마름|활발·변덕쟁이|random|all",
 "seed": 1, "start": "2026-10-19T09:00",
 "steps": [
   {"say": "안녕 강아지야"},                       // 10글자마다 typing, 끝에 message
   {"event": "poke"}, {"event": "throw", "context": {"impact": 0.9, "bounces": 2, "flight_seconds": 1.2}},
   {"event": "message", "context": {"text": "..."}, "nowait": true},   // 판단을 기다리지 않음(묶음·말 버리기)
   {"wait": 600, "away": false, "quiet": true},     // 가상 시계를 넘긴다. 30초마다 기분 시계
   {"restart": true}, {"keys": "none|bad|fail|ok"}, {"disconnect": true}, {"connect": true},
   {"reset": true}, {"get_state": true}, {"get_log": true}, {"note": "검수자용 메모"}
 ]}
```

## 작업

### 1. 실행기 (`harness.py`)
- `FlakyJev/FlakyTalker`: 실제·가짜 클라이언트를 감싸 `fail` 플래그면 `CallError`, `bad`면 `AuthError`.
- `FakeJev/FakeTalker`(가짜 모드·테스트): 결정적 분포(시드).
- `Runner(scenario, mode, out_dir)`: 임시 sqlite 저장소, 가상 시계, 성격 지정, 단계 실행, 기록(JSONL) — 단계, 보낸 이벤트와 그때의 두뇌 단계(`idle/judging/speaking`), 두뇌 메시지, 판단 로그 새 항목, 기분·친밀도·말수·습관화·움직임 스냅샷, 가상 시각. 기분 시계 틱마다 기분 시계열 한 줄.
- 테스트: say가 typing+message로 펼쳐짐, wait가 시계를 넘기고 quiet를 보냄, 대사 뒤 dog_spoke, restart가 기록을 이어 감, keys fail/bad/none, reset, nowait 묶음, personality all이 4번 돈다.

### 2. 분석 (`analysis.py`)
- `analyze(records) -> str` 분석표: 기분 시간 흐름(단계마다 9개 값), 이벤트 뒤 반쯤 회복 시간(오른 기분의 기준값 초과분이 절반이 되는 가상 시간), 반대 기분 쌍이 함께 0.5 이상인 시간·최대값, 인과 사슬(이벤트 → 기분 변화 상위 → 반응 → 동작 → 대사), 반응·동작·대사 분포, 두드러진 기분별 움직임 경향, 시작·끝 성격(기준값)·친밀도. `all`이면 성격 유형 비교표.
- `coverage(all_records) -> (표, 빈 칸)`: 스펙 3절 칸.
- 테스트: 손으로 만든 기록으로 반쯤 회복 시간, 반대 기분 시간, 커버리지 빈 칸.

### 3. CLI·시나리오·README
- `uv run python -m review run [이름...] [--all] [--fake]`: `out/<이름>.jsonl`, `out/<이름>.analysis.md`, `out/coverage.md`.
- 기본 시나리오 세트(스펙 2절 목록).
- 실제 키로 짧은 시나리오 1개 실행, 호출 수 기록.
