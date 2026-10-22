# 보수: 사용량 체크, 연속 메시지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** [보수 작업 목록](../../maintenance.md) 1번(사용량이 제대로 안 나옴)과 2번(답하기 전에 연달아 보낸 메시지의 답을 잃음)을 고친다.

**Architecture:** (1) 사용량은 `RateLimitEvent`의 원본(`RateLimitInfo.raw`)에서 창별 값 전체(`unifiedWindows`)를 읽고, 받은 값을 백엔드 DB 설정에 저장해 다시 켜도 보이게 한다. (2) 실행 고리는 첫 `ResultMessage`에서 바로 끝내지 않는다. 실행 도중 덧붙인 말이 Claude Code 대기열에 남아 다음 차례로 처리되면, 그 차례의 결과까지 받고 끝낸다.

**Tech Stack:** Python 3 (uv, pytest, claude-agent-sdk), Tauri 2 + TypeScript (Vitest)

**Spec:** [docs/maintenance.md](../../maintenance.md) 1·2번, [스펙](../specs/2026-10-21-assistant-phase1-design.md) 5.1, [프로토콜](../../backend-protocol.md)

## Global Constraints

- 문서와 코드는 같은 커밋. 한국어 문서. Agent SDK API는 Context7·설치된 SDK 소스로 확인한다.
- 원래 Claude Code 동작을 따른다 (사용자, 2026-10-22: "원래 클로드 코드 동작 기반으로 동작해야지").
- 끝나면 `docs/maintenance.md`에서 1·2번을 지운다.

### 실측 (2026-10-23, 이 PC)

| 상황 | 결과 |
|---|---|
| 글로만 답하는 중(0~2.6초)에 1.5초에 두 번째 말 | 첫 `ResultMessage`(2.6초) 뒤 곧바로 `SystemMessage(init)`이 오고, 두 번째 차례의 답과 `ResultMessage`(4.6초, 두 말을 모두 반영)가 따로 온다 |
| 도구(Bash sleep 6)를 쓰는 중 4초에 두 번째 말 | 같은 차례 안에 합쳐진다. 두 번째 말에 맞춰 도구를 한 번 더 쓰고 `ResultMessage`는 하나(12.2초) |

지금 백엔드는 첫 `ResultMessage`에서 끝내고 연결을 끊어(`AgentRun._handle`이 True) 첫 경우의 두 번째 답을 잃는다.

### 정한 값

| 항목 | 값 | 누가 |
|---|---|---|
| 사용량 원천 | `RateLimitInfo.raw["unifiedWindows"]`의 창별 `{utilization(0~1), resetsAt(epoch 초)}`. 없으면 지금처럼 풀린 칸(`rate_limit_type`, `utilization`, `resets_at`) | BusinessFactory 방식 (`C:\Users\lab2ai\BusinessFactory\engine\src\stream.ts:75-86`) |
| 사용량 저장 | 백엔드 DB `settings`의 `usage` 키(JSON). 켤 때 읽어 `usage`로 보낸다 | Claude |
| `usage` 메시지 | 모양은 그대로(`limits: [{type, utilization, resets_at, received_at}]`). `type`은 창 이름(`five_hour`, `seven_day`, 그 밖 받은 이름) | Claude (화면을 덜 바꾸려고) |
| 실행 끝내기 | `ResultMessage`를 받으면, 이 실행 도중 덧붙인 말이 아직 처리되지 않았을 수 있는 경우에만 잠깐 더 기다린다. 다음 차례 시작(`SystemMessage` `init`)이 오면 계속 받고, 정해진 시간 안에 안 오면 끝낸다. 덧붙인 말이 없으면 지금처럼 바로 끝낸다 | Claude (위 실측) |
| 기다리는 시간 | 3초 (잠정값. 실측에서 init은 결과 직후(0.0초) 왔다) | Claude |
| 중간 결과 | 첫 차례의 결과 글은 `result` 줄로 남기되 세션 상태는 `working` 그대로. 마지막 차례가 끝날 때 `done`/`failed` | Claude |

더 나은 신호(예: 덧붙인 말이 처리됐다는 CLI 메시지)가 있으면 그것을 쓴다. 구현 중 Context7·SDK 소스로 확인하고, 쓴 근거를 스펙에 적는다.

## Review Focus

1. **도구 도중 합쳐진 경우 매달림**: 덧붙인 말이 같은 차례에 합쳐지면 결과가 하나뿐이다. 이때 다음 차례를 끝없이 기다리지 않는다. → Task 2 `test_merged_followup_finishes_after_grace`
2. **다음 차례 결과를 잃음**: → Task 2 `test_queued_followup_gets_its_own_result`
3. **사용량 원본 모양이 다름·없음**: 지금 칸으로 물러난다. → Task 1 `test_usage_falls_back_without_unified_windows`
4. **재시작 뒤 사용량**: 저장한 값이 보인다. → Task 1 `test_usage_survives_restart`

---

## Task 1: 사용량

**Files:** `backend/backend/core.py`(`_Events.rate_limit`, `_usage`, 시작 때 읽기), `backend/backend/agent.py`(`RateLimitEvent` → `rate_limit(info)`에 `raw` 포함), 테스트, `app/src/ui/usage.ts`·`app/src/shared/*`(이름 대응이 바뀌면), `docs/backend-protocol.md`, `ARCHITECTURE.md`, `docs/manual-checks/{backend,frontend}.md`

- [ ] **Step 0: 실제 원본 확인.** 짧은 실제 세션 하나로 `RateLimitEvent.rate_limit_info.raw`를 찍어(값만, 계정 정보 없이) 모양을 스펙에 적는다.
- [ ] **Step 1: 실패하는 시험** (Review Focus 3·4, `unifiedWindows` 두 창 → `limits` 두 줄).
- [ ] **Step 2~4:** 실패 확인 → 구현 → `uv run pytest -q`, 화면을 바꿨으면 `npm test && npx tsc --noEmit`.
- [ ] **Step 5:** 문서와 커밋.

## Task 2: 연속 메시지

**Files:** `backend/backend/agent.py`(`AgentRun.run`, `_handle`, `say`), `backend/backend/core.py`(`_finish` 중간 결과), 테스트, `docs/superpowers/specs/2026-10-21-assistant-phase1-design.md` 5.1, `docs/backend-protocol.md`, `ARCHITECTURE.md`

- [ ] **Step 1: 실패하는 시험** (Review Focus 1·2, 덧붙인 말이 없을 때는 지금처럼 바로 끝남, 멈추기는 기다리지 않음).
- [ ] **Step 2~4:** 실패 확인 → 구현 → `uv run pytest -q`.
- [ ] **Step 5:** 문서, `docs/maintenance.md`에서 1·2번 지우기, 커밋.

## Task 3: 실제 확인

- [ ] 앱을 띄워 작업을 하나 돌린 뒤 사용량 탭에 두 창이 보이는지, 백엔드를 다시 켜도 남는지 본다. 답하는 중에 두 번 연속 보내 두 답이 모두 오는지 본다.
