# 검수 하네스

두뇌를 실제 Jev·Gemini와 가상 시계로 돌려 시나리오를 실행하고, 기록·상태 분석표·커버리지를 남긴다. 설계는 [검수 루프 스펙](../../docs/superpowers/specs/2026-10-15-review-loop-design.md)에 있다.

## 실행 (`brain/`에서)

```
set PYTHONIOENCODING=utf-8        # Windows 콘솔 한글 (Git Bash: PYTHONIOENCODING=utf-8 uv run ...)
uv run python -m review run 03-conversation        # 시나리오 하나
uv run python -m review run --all                   # 전부 (probe-* 포함)
uv run python -m review coverage                    # out/*.jsonl 전체로 커버리지만 다시 계산
uv run python -m review run --all --fake            # 가짜 Jev·Gemini (하네스 시험용. 판정에 쓰지 않는다)
```

- 키는 앱 설정에서 넣은 키(자격 저장소)를 쓴다.
- 결과는 `review/out/`에 생긴다(git 제외).
  - `<이름>.jsonl`: 모든 기록. 줄마다 `run`(성격), `type`, `t`(가상 시각).
  - `<이름>.analysis.md`: 상태 분석표. 기분 흐름, 기다리는 동안 기분, 반쯤 회복 시간, 반대 기분이 함께 높음, 인과 사슬, 반응·동작·말하기 분포, 움직임 경향, 성격·친밀도 변화, 호출 수. 성격이 `all`이면 성격 유형 비교표.
  - `coverage.md`: 스펙 3절 칸마다 일어난 횟수와 빈 칸. `out/`에 있는 모든 기록을 합친다.
- 기본 세트 전체를 실제로 돌리면 Jev 약 400번, Gemini 약 150번이다(2026-10-16 가짜 실행 기준 추정). 시간은 대부분 가상 시계를 넘기는 데 들고(약 3~4분), 실제 호출이 더해진다.

## 시나리오 형식 (`scenarios/<이름>.json`)

```json
{"name": "probe-fear-then-pet", "description": "무서움을 올린 뒤 쓰다듬으면 행복이 함께 오르나",
 "personality": "평균", "seed": 1, "start": "2026-10-19T09:00",
 "steps": [
   {"event": "throw", "context": {"impact": 0.95, "bounces": 3, "flight_seconds": 1.6}},
   {"event": "pet", "context": {"seconds": 4.0}},
   {"wait": 600, "quiet": false},
   {"get_state": true}
 ]}
```

- `personality`: `평균` `과묵·차분` `예민·성마름` `활발·변덕쟁이`(`sim/simulate.py` ARCHETYPES), `random`(시드로 탄생), `all`(네 유형 모두 따로 실행)
- 단계

| 단계 | 뜻 |
|---|---|
| `{"say": "글"}` | 화면처럼 10글자마다 `typing`, 끝에 `message` |
| `{"event": 종류, "context": {...}, "nowait": true}` | 이벤트 하나. `nowait`면 판단을 기다리지 않고 다음 단계로(묶음·말하는 중 메시지) |
| `{"wait": 초, "away": false, "quiet": true}` | 가상 시계를 넘긴다. 30초마다 기분 시계. `quiet`면 화면처럼 조용함을 보낸다(자리 있음 10분, 비움 30분마다). 조용함 없이 2시간 넘으면 5분 간격 틱 |
| `{"restart": true}` | 두뇌를 끄고 같은 저장소로 다시 켠다 |
| `{"keys": "none\|bad\|fail\|ok"}` | 키 없음 / 키 오류 / 호출 실패 / 정상으로 |
| `{"disconnect": true}`, `{"connect": true}` | 화면 연결 끊기·다시 붙이기 |
| `{"reset": true}` | 초기화(강아지 새로 태어남) |
| `{"get_state": true}`, `{"get_log": true}` | 상태 탭·로그 탭 조회를 기록에 남긴다 |
| `{"note": "글"}` | 기록에 메모 |

- 이벤트 종류와 `context`는 [프로토콜](../../docs/brain-protocol.md)을 따른다. 예: `throw` `{"impact": 0~1, "bounces", "flight_seconds"}`, `pet` `{"seconds"}`, `quiet` `{"seconds"}`, `returned`·`house_out` `{"away_seconds"}`.
- 화면 흉내: 대사가 나오면 하네스가 `dog_spoke`를 보낸다.
- 검수자가 쓴 확인용 시나리오는 `probe-*.json`으로 남긴다.
