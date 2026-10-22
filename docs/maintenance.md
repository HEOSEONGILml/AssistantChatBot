# 보수 작업 목록

다음 보수 작업 때 처리할 것을 모은다. 착수하면 계획(`docs/superpowers/plans/`)을 쓰고, 끝나면 이 목록에서 지운다.

## 1. 사용량 체크가 제대로 안 된다 (2026-10-22 등록)

- **증상 (사용자):** 사용량 탭의 값이 제대로 나오지 않는 것 같다. 아직 원인을 보지 않았다.
- **지금 동작:**
  - 백엔드는 Claude Code가 작업 중에 보내는 `RateLimitEvent`(한도 종류, 쓴 비율, 초기화 시각)에서 종류별 마지막 값만 메모리에 둔다(`backend/backend/core.py` `rate_limit`, `_usage`). 작업이 돌지 않으면 갱신되지 않고, 백엔드를 다시 켜면 비워진다.
  - 화면은 받은 값만 막대로 그린다(`app/src/ui/usage.ts`). 종류 이름 대응(`five_hour` → 현재 세션, `seven_day` → 이번 주, `opus`·`sonnet` → 모델별)은 실제 값으로 확인하지 않은 짐작이다.
- **확인한 적 없는 것:** `RateLimitEvent`가 언제 오는지, 한도 종류 이름과 값의 모양 ([스펙](superpowers/specs/2026-10-21-assistant-phase1-design.md) 8절, [수동 확인](manual-checks/backend.md) 4번이 아직 비어 있다).
- **볼 것:** 실제 작업을 몇 개 돌리며 받은 `RateLimitEvent`를 기록해 이름·값 모양을 확인한다. 그다음 갱신 시점(작업이 없을 때, 재시작 뒤)과 화면 대응을 고친다.
- **참고: BusinessFactory (사용자: "거기 사용량 체크는 잘 동작하던데", 2026-10-23 조사)**
  - 같은 이벤트(`rate_limit_event`)를 쓰지만, 창별 값이 모두 든 `rate_limit_info.unifiedWindows`를 읽는다. 모양: `{five_hour: {utilization, resetsAt}, seven_day: {utilization, resetsAt}}`, `utilization`은 0~1, `resetsAt`은 epoch 초 (`C:\Users\lab2ai\BusinessFactory\engine\src\stream.ts:75-86`).
  - 받은 값을 파일(`.engine-usage.json`, `{at, status, windows}`)에 저장해 다시 켜도 남긴다 (`engine.ts:1022-1026`, `watch.ts:8-16`). 화면에는 "구독 사용량은 직원이 한 번 일하면 표시됩니다"라고 밝힌다.
  - 이름 대응: `five_hour` → 5시간 한도, `seven_day` → 주간 한도. 모르는 이름은 그대로 보인다.
  - 한도에 걸렸을 때는 결과 글의 "You've hit your … limit"과 "resets …"를 읽어 다시 시도할 시각을 잡는다 (`runner.ts:241-271`).
- **짐작되는 원인 (확인 안 함):** 우리 백엔드는 SDK가 풀어 준 칸(`rate_limit_type`, `utilization`, `resets_at`)만 읽는다. 이 칸은 이벤트마다 창 하나 분량이고 `utilization`이 비어 올 수 있다. 창별 값 전체는 `RateLimitInfo.raw["unifiedWindows"]`에 있다(설치된 SDK의 `types.py` `RateLimitInfo.raw`). BusinessFactory처럼 `raw`의 `unifiedWindows`를 읽고, 받은 값을 저장해 재시작 뒤에도 보이게 하는 쪽으로 고친다.

## 2. 답하기 전에 메시지를 연달아 보내면 답이 제대로 오지 않는다 (2026-10-22 등록)

- **증상 (사용자):** 메시지를 두 번 연속 보내면 답이 제대로 오지 않는 것 같다.
- **원하는 동작 (사용자):** 원래 Claude Code처럼, 답하기 전에 메시지가 하나 더 오면 그것까지 보고 답한다. 이 앱은 원래 Claude Code 동작을 기반으로 동작해야 한다.
- **지금 동작:** 일하는 중에 온 말은 `AgentRun.say`가 같은 Claude Code 세션에 `query`로 한 번 더 보낸다(`backend/backend/agent.py`). 그런데 실행 고리는 첫 `ResultMessage`를 받으면 끝내고 연결을 끊는다(`AgentRun.run`, `_handle`).
- **짐작 (확인 안 함):** 두 번째 말에 대한 답이 첫 결과 뒤에 오는데, 그 전에 연결을 끊어 버려 잃는 것 같다. 또는 두 말이 따로 답해져 앞 답이 결과로 남는 것 같다.
- **볼 것:** 원래 Claude Code(대화형)가 답하는 도중 들어온 메시지를 어떻게 처리하는지 Agent SDK 문서로 확인한다(스트리밍 입력, 메시지 대기열). 실제로 두 번 연속 보내 백엔드 로그·대화 줄을 기록한다. 그 동작에 맞춰 실행 고리를 고친다.
