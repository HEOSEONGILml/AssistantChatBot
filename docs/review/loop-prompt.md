# 검수 루프 프롬프트 (랄프 루프가 매 회 넣는 지시)

랄프 루프는 매번 같은 지시를 넣는다: "`docs/review/loop-prompt.md`를 읽고 그대로 한 회차를 진행해." 이 파일이 그 회차의 할 일이다. 설계는 [검수 루프 스펙](../superpowers/specs/2026-10-15-review-loop-design.md)이다.

## 규칙

- **사용자는 자리에 없다. 묻지 않는다.** 막히면 판단하고, 그 판단을 `progress.md`에 "판단:"으로 적고 계속한다(사용자: "그냥 막 돌려 마구 해버려").
- 고치는 범위는 제한이 없다(버그·수치·질문 문구·프롬프트·확률 모형·컨셉). 그래도 CLAUDE.md는 지킨다: 테스트 먼저, 두뇌·화면 테스트와 타입 검사 통과, 문서를 같은 커밋에서 갱신. 컨셉을 바꾸면 vision에 **"검수 루프 결정 (검수 NNN)"**으로 적는다.
- 질문 정의나 질문 문구를 바꾸면 Jev를 다시 녹화(`uv run python -m sim.record`)하고 보정값을 다시 맞춘다(`uv run python -m sim.simulate --fit`).
- 브랜치는 `ralph/review-loop`다. 다른 브랜치에 있으면 옮긴다. 푸시·병합하지 않는다.
- 개발용 앱(`npm run tauri dev`)은 띄우지 않는다. 두뇌만 본다.
- API 키·대화 내용을 로그·커밋에 쓰지 않는다.
- 한 번에 **한 단계만** 하고 `progress.md`를 갱신한 뒤 끝낸다(다음 회차가 이어 간다).

## 할 일: `progress.md`의 "다음 단계"를 하나 진행한다

`docs/review/progress.md`를 먼저 읽는다. 거기 적힌 "다음 단계"를 한다. 단계는 아래 중 하나다.

### 단계 0: 하네스 만들기 (처음 한 번)

스펙 2·3절대로 `brain/review/`를 만든다. superpowers `writing-plans`로 계획을 `docs/superpowers/plans/`에 쓰고, TDD로 구현한다(가짜 Jev·Gemini로 pytest).

- 시나리오 JSON 실행기: 단계 `event`, `wait`(가상 시계), `restart`(같은 저장소로 두뇌 다시 만들기), `keys`(키 빼기·잘못된 키), `disconnect`/`connect`, `reset`, `get_state`/`get_log`.
- 실제 클라이언트(`config.read_keys()`)와 가짜 클라이언트를 고를 수 있게.
- 성격 지정: 시나리오에 성격 유형(평균·과묵·예민·활발, `sim/simulate.py`의 ARCHETYPES) 또는 무작위.
- 기록 파일(`brain/review/out/<시나리오>.jsonl`, git 제외): 단계, 두뇌 메시지, 기분·친밀도·말수, 판단 로그, 가상 시각.
- 상태 분석표(`.../<시나리오>.analysis.md`): 기분 9개의 시간 흐름, 이벤트 뒤 반쯤 회복 시간(사람 시간 단위), 동시에 높았던 반대 기분 쌍과 그 시간, 인과 사슬, 성격 유형 비교, 며칠 변화.
- 커버리지 집계(`.../coverage.md`): 스펙 3절 표의 모든 칸과 일어난 횟수.
- 기본 시나리오 세트(`brain/review/scenarios/`): 스펙 2절 목록 전부.
- 실행: `cd brain && uv run python -m review run [시나리오...]`, 전체는 `--all`. 사용법은 `brain/review/README.md`.
- 실제 키로 짧은 시나리오 하나를 돌려 확인하고, 호출 수·대략 비용을 `progress.md`에 적는다.
- 끝나면 다음 단계를 "단계 1 (검수 001)"로 적는다.

### 단계 1: 검수

1. 두뇌 `uv run pytest`, 화면 `npm test`·`npx tsc --noEmit`이 통과하는지 본다. 실패하면 이 단계 대신 그것부터 고친다.
2. **새 서브에이전트**(Agent 도구, general-purpose, model `opus`)를 띄운다. 프롬프트 = `docs/review/reviewer.md` 전체 + "회차 번호 NNN, 커밋 <해시>. 판정을 `docs/review/rounds/NNN.md`에 써라." 이전 회차 판정·`known-defects.md`·`progress.md`는 넘기지 않는다.
3. **검수자 보정**: 판정을 `known-defects.md`와 비교한다. 아직 고치지 않은 아는 결함을 판정이 놓쳤으면, `reviewer.md`를 고치고 커밋한 뒤 같은 번호로 다시 검수한다(최대 3번. 그래도 놓치면 판단으로 적고 진행).
4. 통과면 연속 통과 수를 1 올린다. **2회 연속 통과**면 `progress.md`를 마무리하고 `<promise>REVIEW PASSED TWICE</promise>`를 출력한다. 1회면 다음 단계를 "단계 1 (검수 NNN+1)"로 적는다(고칠 것 없이 바로 새 검수자).
5. 불통과면 연속 통과 수를 0으로 하고, 다음 단계를 "단계 2 (검수 NNN 고치기)"로 적는다.
6. 판정 파일을 커밋한다.

### 단계 2: 고치기

1. `docs/review/rounds/NNN.md`의 지적을 모두 읽는다. 치명 → 중요 → 사소 순으로, 원인을 찾아(superpowers `systematic-debugging`) 고친다. 한 회차에 가능한 많이 고친다. 같은 원인을 공유하는 지적은 묶어 고친다.
2. 큰 설계 변경은 스펙(`docs/superpowers/specs/`)이나 결정 기록(`docs/decisions/`)을 먼저 쓴다.
3. 테스트 먼저, 그다음 수정. 모든 테스트·타입 검사 통과. 문서 동기화. 커밋 메시지: `review NNN: <요약>`.
4. 고치지 않기로 한 지적은 이유를 `progress.md`에 "판단:"으로 적는다.
5. 다음 단계를 "단계 1 (검수 NNN+1)"로 적는다.

## progress.md 갱신 형식

- 맨 위 "다음 단계", "연속 통과", "회차"를 고친다.
- 아래 "기록"에 한 줄씩 덧붙인다: `날짜 · 단계 · 결과 · 커밋 · 비용(대략)`.
