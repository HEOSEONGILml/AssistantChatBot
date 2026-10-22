# 화면 설계 변경 반영 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026-10-22에 바뀐 화면 설계를 구현한다. 세션 지우기(19번), 강아지 크기 1.5배와 끌어 옮기기(20·21번), 큰 창(12번, 패널 전체), 대화 탭의 "대화 지우기" 줄(18번), 대답 준비 중 표시(22번).

**Architecture:** 백엔드에 `delete_session`·`session_deleted`·`activity` 메시지를 더한다(프로토콜 v7에 더함, 버전은 그대로). `activity`는 Claude Code를 `include_partial_messages`로 띄워 받은 `StreamEvent`의 `content_block_start`에서 만든다(스펙 5.1, 0030 "수정: 준비 중 표시"). 강아지와 패널은 지금처럼 창 하나(`main`)이고, 창 안에서 강아지·패널의 자리를 순수 함수(`src/shared/placement.ts`)가 계산한다. 큰 창은 지금의 상세 창(`detail`)을 바꾼 것이다. 백엔드는 화면 연결을 하나만 받으므로 큰 창은 백엔드에 따로 붙지 않는다. 주 창이 상태를 통째로 넘기고, 큰 창이 보내는 메시지를 대신 보낸다(지금 상세 창과 같은 방식을 넓힌 것).

**Tech Stack:** Tauri 2 (Rust + TypeScript), Vite, Vitest, Python 3 (uv, pytest)

**Spec:** [스펙](../specs/2026-10-21-assistant-phase1-design.md) 3절, [프로토콜](../../backend-protocol.md), [디자인 README](../../design/2026-10-21-output-ui/README.md), [다이제스트](../../design/2026-10-21-output-ui/digest.md) 2절·3절 11·12·16·18·19·20·21번, [0030](../../decisions/0030-io-interface-task-as-conversation.md) "수정: 지우기", [0034](../../decisions/0034-session-as-top-level-term.md)

## Global Constraints

- 문서와 코드는 같은 커밋 (CLAUDE.md 1절). Tauri API는 Context7(`/tauri-apps/tauri-docs`)로 확인하고 쓴다.
- 화면 값은 다이제스트와 아트보드(`docs/design/2026-10-21-output-ui/*.dc.html`) 값을 그대로 쓴다. 비어 있거나 모호한 곳만 아래 "정한 값"을 따른다.
- 용어는 세션(0034). 메시지·코드 이름은 `session`이다. 0030의 `delete_task`·`task_deleted`는 v7 이름 `delete_session`·`session_deleted`로 쓴다. `activity`의 작업 ID는 `session_id`다.
- 로그·콘솔에 사용자 글을 찍지 않는다.
- 개발용 앱(`npm run tauri dev`)은 확인이 끝나면 바로 닫는다.

### 정한 값 (디자인에 없거나 모호한 곳)

| 항목 | 값 | 누가 |
|---|---|---|
| 강아지 위치 기억 | 옮긴 위치를 앱을 껐다 켜도 유지한다 | 사용자 |
| 위치 저장 | 주 창 웹뷰의 `localStorage`에 강아지 왼쪽 위의 화면 좌표(물리 px)를 둔다. 켤 때 그 점이 어느 모니터 작업 영역에도 없으면 처음 자리(주 모니터 오른쪽 아래)로 | Claude |
| 끌기와 누르기 | 누른 채 4px 넘게 움직이면 끌기, 아니면 누르기(패널 열고 닫기). 끈 뒤의 click은 버린다 | Claude |
| 끄는 동안 패널 | 끌기를 시작하면 패널을 닫는다. 놓은 뒤 강아지를 누르면 새 자리에서 연다 | Claude |
| 끌 수 있는 범위 | 강아지가 놓인 모니터의 작업 영역 안. 모니터를 넘어가면 그 모니터의 작업 영역 안으로 당긴다 | Claude |
| 패널 자리 | 강아지 위에 패널 높이 + 12px가 들어가면 위(오른쪽 끝을 강아지에 맞추고 작업 영역 안으로 당김, 꼬리 있음). 안 들어가면 옆(오른쪽에 들어가면 오른쪽, 아니면 왼쪽, 12px 간격, 위쪽 끝을 강아지에 맞추고 작업 영역 안으로 당김, 꼬리 없음). 21번이 옆 모양이다 | Claude |
| 꼬리 | 위 모양일 때만. 강아지 가운데를 가리키도록 패널 안 가로 위치를 계산한다 | Claude |
| 큰 창 처음 화면 | 작은 패널이 보던 탭·화면·세션 그대로 | Claude |
| 큰 창의 탭별 모양 | 알림·작업·스케줄은 두 칸(왼쪽 300px 목록, 오른쪽 고른 대화 또는 양식). 고른 것이 없으면 오른쪽에 `왼쪽 목록에서 골라 주세요`. 대화·사용량·설정은 한 칸 | Claude (12번은 작업 탭만 그렸다) |
| 큰 창 닫기 | 숨기기만 한다(지금 상세 창과 같음). 작은 패널은 다시 열지 않는다 | Claude |
| 지우기 확인 문구 | 작업: `이 작업을 지울까요?` / `**<제목>**과 그 대화 기록이 모두 지워져요. 되돌릴 수 없어요. 돌고 있는 작업이면 먼저 멈춰요.` 스케줄: `이 스케줄을 지울까요?` / `**<이름>**과 작업 지시서, 대화 기록이 모두 지워져요. 되돌릴 수 없어요. 돌고 있으면 먼저 멈춰요.` 대화: `대화를 지울까요?` / `Claude와 나눈 대화 기록이 모두 지워지고 새 대화로 시작해요. 되돌릴 수 없어요.` | 작업은 19번, 스케줄·대화는 Claude |
| 지운 뒤 화면 | 지운 세션의 대화를 보고 있었으면 그 탭 목록으로. 대화 탭은 새 대화 세션을 연다 | Claude |
| `activity` 모양 | `{session_id, kind, text}`. `kind`는 `thinking`(생각 중)·`tool`(도구 실행 중)·`writing`(답 쓰는 중) | Claude (스펙 4절의 세 종류) |
| 도구 이름 → 글 | `mcp__screenpipe__*` `화면 기록에서 찾는 중`, `mcp__claude-in-chrome__*` `크롬에서 작업하는 중`, 백엔드 MCP(`mcp__assistant__*`) `지난 작업 찾는 중`, `WebSearch` `웹에서 검색하는 중`, `WebFetch` `웹 페이지 읽는 중`, `Bash` `명령 실행하는 중`, `Read`·`Glob`·`Grep` `파일 읽는 중`, `Write`·`Edit`·`NotebookEdit` `파일 고치는 중`, `Task`·`Agent` `다른 에이전트에게 맡기는 중`, `AskUserQuestion`은 보내지 않음, 그 밖 `도구 쓰는 중`. `thinking` `생각하는 중`, `text` `답 쓰는 중` | Claude (22번 예시 문구를 따름) |
| 준비 중 줄과 진행 칩 | 준비 중 줄이 보이는 동안 진행 칩의 스피너는 그리지 않는다(돌고 있다는 표시가 둘이 되지 않게) | Claude |
| 걸린 시간 | 그 세션에서 이번 대답의 첫 `activity`를 받은 때부터 1초마다 센다. 다시 그려도 처음 시각을 지킨다 | Claude (스펙 4절) |
| 없는 세션 열기 | `get_session`이 없는 세션이면 백엔드가 `session_deleted`로 답한다(지운 세션의 칩을 눌렀을 때). 화면은 목록으로 돌아간다 | Claude |

## Review Focus

1. **돌고 있는 세션 지우기**: 먼저 멈추고(Claude Code 세션 끊기·답 기다림 풀기) 지운다. 지운 뒤 늦게 오는 진행·결과가 지운 세션을 되살리지 않는다. → Task 1 `test_delete_running_session_stops_then_deletes`, `test_late_events_after_delete_are_dropped`
2. **스케줄 지우기**: 스케줄러가 지운 스케줄을 다시 돌리지 않는다. → Task 1 `test_deleted_schedule_does_not_run`
3. **대화 탭 지우기**: 대화 세션이 늘 하나 남는다. → Task 1 `test_delete_chat_creates_new_chat_session`
4. **지운 세션이 화면에 남음**: 목록·배지·캐시·보던 화면에서 모두 빠진다. → Task 2 `session_deleted` 테스트
5. **패널이 화면 밖으로**: 강아지가 어느 구석에 있어도 패널과 강아지가 작업 영역 안에 들어간다. → Task 3 `placement` 테스트(네 구석, 모니터 원점이 음수)
6. **끌기와 누르기 혼동**: 조금 흔들린 클릭은 누르기다. → Task 3 `isDrag` 테스트
7. **준비 중 줄이 남음**: 결과·실패·질문·등록 확인 `entry`, 멈춤, 끊김, 세션이 일하는 중이 아니게 되면 줄이 사라진다. → Task 2b `activity` 테스트
8. **activity 홍수**: 글자 조각(`delta`)마다 보내지 않고, 하는 일이 바뀔 때만 보낸다. → Task 1b `test_activity_only_on_block_start`

---

## Task 1: 백엔드 — `delete_session`

**Files:** `backend/backend/{store,core,server,scheduler}.py`, `backend/tests/test_{store,core,server,scheduler}.py`, `docs/backend-protocol.md`

- [ ] `store.delete_session(session_id)`: 그 세션의 대화 줄(검색 색인 포함), 스케줄 행, 세션 행을 한 트랜잭션으로 지운다. 테스트 먼저.
- [ ] `App.delete_session(session_id)`: 없으면 `session_deleted`만 보낸다. 돌거나 답을 기다리면 `stop`과 같은 길로 멈추고, 멈춘 뒤 들어오는 이벤트(`_entry`·`_set`·`_finish`)가 지운 세션에 쓰지 않게 막는다. 지운 뒤 `session_deleted {session_id}`를 보낸다. 대화 세션이면 새 대화 세션을 만들고(`startup`과 같은 값) `session`을 보낸다. 테스트 먼저(Review Focus 1·3).
- [ ] `App.get_session`이 없는 세션이면 `session_deleted`로 답한다.
- [ ] 스케줄러가 지운 스케줄을 돌리지 않는지 확인하고, 아니면 고친다(Review Focus 2).
- [ ] `server.ROUTES`에 `delete_session: (("session_id", int),)`.
- [ ] `docs/backend-protocol.md`: 화면 → 백엔드 표에 `delete_session`, 백엔드 → 화면 표에 `session_deleted`, `get_session`의 없는 세션 답. "v7에 더함" 한 줄.
- [ ] `cd backend && uv run pytest` 전부 통과.

## Task 1b: 백엔드 — `activity`

**Files:** `backend/backend/{agent,core}.py`, `backend/tests/test_{agent,core}.py`, `docs/backend-protocol.md`

- [ ] `build_options`에 `include_partial_messages=True` (Context7로 이름 확인). 테스트 갱신.
- [ ] `AgentRun._handle`: `StreamEvent`의 `event["type"] == "content_block_start"`에서 블록 종류로 `(kind, text)`를 만들고, 바로 앞에 보낸 것과 다를 때만 `RunEvents.activity(kind, text)`. 도구 이름 → 글은 "정한 값" 표를 함수 하나로. 테스트 먼저(Review Focus 8).
- [ ] `core`: `activity`를 대화 기록에 남기지 않고 `{"type": "activity", "session_id", "kind", "text"}`로 바로 보낸다.
- [ ] 프로토콜 문서에 `activity`.
- [ ] `uv run pytest` 통과.

## Task 2: 프론트 상태 — 지우기

**Files:** `app/src/shared/{protocol,state}.ts`, `app/tests/{protocol,state}.test.ts`

- [ ] `protocol.ts`: `Outgoing`에 `{ type: "delete_session"; session_id: number }`, `BackendMessage`에 `{ type: "session_deleted"; session_id: number }`와 모양 검사. 테스트 먼저.
- [ ] `state.apply`의 `session_deleted`: `sessions`·`entries`·`schedules`에서 빼고, `lists`(작업·알림·스케줄 목록)의 그 행을 뺀다. `chatSessionId`가 그 세션이면 `null`. 보던 화면(`view`)이 그 세션이면 그 탭 목록으로. 테스트 먼저(Review Focus 4).
- [ ] 목록에서 행을 뺀 뒤 그 쪽이 비면 `followUps`가 그 쪽을 다시 받게 한다(지금 "보던 쪽이 없어지면 당기는" 규칙과 같은 자리).
- [ ] `npm test`, `npx tsc --noEmit` 통과.

## Task 2b: 프론트 상태 — 준비 중

**Files:** `app/src/shared/{protocol,state}.ts`, `app/tests/{protocol,state}.test.ts`

- [ ] `activity` 모양 검사. `State.activity: Map<session_id, {kind, text, since}>`(`since`는 그 대답의 첫 `activity`를 받은 시각, 바뀐 하는 일에도 그대로).
- [ ] 지우는 때: 그 세션의 `result`·`failure`·`question`·`proposal` `entry`, 세션 상태가 `working`이 아니게 된 `session`, `session_deleted`, 끊김. 테스트 먼저(Review Focus 7).
- [ ] 걸린 시간 글 `<N>초`, 60초 넘으면 `<M>분 <N>초`. 순수 함수와 테스트.

## Task 3: 강아지 크기, 끌어 옮기기, 패널 자리

**Files:** 새 `app/src/shared/placement.ts`, 새 `app/tests/placement.test.ts`, `app/src/{main,window}.ts`, `app/src/ui/{dog,panel}.ts`, `app/src/ui/styles.css`, `app/index.html`, `app/src-tauri/tauri.conf.json`, `app/src-tauri/capabilities/default.json`

- [ ] `placement.ts`(순수, 논리 px): `layout(work, dog, panel)` — `work`는 작업 영역 사각형, `dog`는 강아지 왼쪽 위, `panel`은 `{width, height}` 또는 `null`. 돌려주는 값: 창 사각형, 창 안 강아지 자리, 창 안 패널 자리, 꼬리 가로 위치(위 모양일 때만). "정한 값"의 패널 자리 규칙. `clampDog(work, dog)`, `isDrag(dx, dy)`(4px 넘음). 테스트 먼저(Review Focus 5·6).
- [ ] 강아지 96x72. 스프라이트 시트 `768px 648px`, 자세별 위치는 다이제스트 7절 새 값. 꼬리는 `layout`이 준 위치.
- [ ] `window.ts`: 주 창을 `layout`이 준 사각형으로 놓는다(물리 px 변환은 강아지가 놓인 모니터의 배율). 지금의 "겹친 요청은 차례로, 밀린 것은 마지막만" 규칙은 그대로.
- [ ] 끌기: 강아지에서 pointerdown → `isDrag`면 끌기 시작(패널 닫기, 20번 모양: `grabbing` 커서, 떠 있는 그림자, 아래 타원 그림자). pointermove마다 화면 좌표로 창을 옮긴다. pointerup에서 `clampDog`로 당겨 놓고 `localStorage`에 저장. 끈 뒤의 click은 버린다.
- [ ] 켤 때 저장한 자리를 읽어 모니터 작업 영역 안이면 쓰고, 아니면 처음 자리.
- [ ] 창을 옮기는 데 필요한 권한(capabilities)을 Context7로 확인하고 더한다.
- [ ] `npm test`, `npx tsc --noEmit`, `cd src-tauri && cargo test` 통과.

## Task 4: 지우기 화면, 대화 탭 줄

**Files:** `app/src/ui/{panel,schedule,conversation,dom}.ts`, `app/src/ui/styles.css`

- [ ] 휴지통 아이콘(다이제스트 3절 "지우기 버튼 위치"의 path).
- [ ] 작업 대화 머리(11번): 크게 보기와 멈추기 사이에 지우기(aria `작업 지우기`). 스케줄 대화 머리(16번): 켜짐 스위치와 크게 보기 사이(aria `스케줄 지우기`).
- [ ] 대화 탭(18번): 탭 바 아래 얇은 줄 `Claude와 나눈 대화` + `대화 지우기`. 본문 높이 324px.
- [ ] 지우기 확인(19번): 패널 안 덮개 + `role=alertdialog` 상자. 문구는 "정한 값". [취소]는 닫기, [지우기]는 `delete_session`을 보내고 닫는다. 보내지 못하면(끊김) 상자를 둔다.
- [ ] 다이제스트 2절대로 탭 바 오른쪽 끝에 크게 보기 아이콘(목록 화면). 작업·스케줄 대화 머리의 크게 보기도 같은 아이콘. 누르면 큰 창(Task 5).
- [ ] 준비 중 줄(22번): 대화 맨 아래(대화 탭·작업 대화·스케줄 대화·큰 창 모두). 점 3개 깜빡임, 굵은 하는 일 + `· <걸린 시간>`, `role=status` `aria-live=polite`. 1초마다 시간만 바꾼다(대화 전체를 다시 그리지 않는다).
- [ ] `docs/manual-checks/frontend.md`에 19번, 대화 지우기 줄, 22번.

## Task 5: 큰 창

**Files:** `app/detail.html`(→ 큰 창), `app/src/detail.ts`(→ 큰 창), `app/src/main.ts`, `app/src/window.ts`, `app/src/ui/*`, `app/src/ui/styles.css`, `app/src-tauri/{tauri.conf.json,src/lib.rs}`

- [ ] 창 이름과 제목: 큰 창 제목줄 `패널`(12번). 크기는 지금 상세 창(880x544)과 같다.
- [ ] 주 창: [크게 보기]를 누르면 작은 패널을 닫고 큰 창을 보인다. 큰 창이 보이는 동안 상태가 바뀌면 상태를 통째로 넘긴다(Map은 배열로). 큰 창이 보낸 메시지를 백엔드로 대신 보내고, 못 보냈으면 알린다(지금 상세 창의 `detail-say`·`detail-send-failed`를 일반화).
- [ ] 큰 창: 자기 화면(탭·화면·세션·쪽)을 갖는다. 화면이 바뀌면 그 화면에 필요한 요청(`refreshRequests`)을 주 창을 거쳐 보낸다. 보고 있는(창이 앞에 있는) 끝난 세션은 `seen`.
- [ ] 큰 창 모양(12번): 탭 바 글자 탭 6개, "정한 값"의 탭별 모양. 오른쪽 대화 머리: 제목 16px/700 + 부제, [지우기]·[멈추기] 글자 버튼. 진행 단계는 펼친 박스. 지우기 확인(19번)은 큰 창 안에 같은 상자.
- [ ] `ARCHITECTURE.md`·`docs/glossary.md`·`docs/manual-checks/frontend.md`의 상세 창 설명을 큰 창으로.
- [ ] `npm test`, `npx tsc --noEmit`, `cargo test` 통과.

## Task 6: 문서 동기화와 실제 확인

- [ ] 스펙 3절·4절, `ARCHITECTURE.md`(프로토콜 메시지, 화면 구성), [0030](../../decisions/0030-io-interface-task-as-conversation.md) "수정: 지우기"의 메시지 이름을 v7 이름으로.
- [ ] `npm run tauri dev`로 띄워 끌기·옮긴 뒤 패널·지우기·큰 창을 수동 확인 목록대로 본다. 끝나면 바로 닫는다.
