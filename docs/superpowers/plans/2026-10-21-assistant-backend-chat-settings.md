# 조수 1단계 백엔드 추가분: 대화 탭·설정 탭 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 디자인 변경(대화 탭, 설정 탭의 로그아웃·화면 기록)을 백엔드에 반영한다.

**Architecture:** 대화 탭은 출처 `"chat"`인 작업 하나다. 앱이 처음 켜질 때 만들고 같은 세션을 이어 쓴다. 대화에서 일을 맡기면 에이전트가 새 도구 `create_task`로 새 사용자 작업을 만들고, 대화에는 작업 칩 줄이 남는다. 설정 탭에는 로그아웃과 화면 기록 켜기·끄기가 더해진다.

**Tech Stack:** 기존 백엔드와 같다 (Python, claude-agent-sdk, SQLite, websockets).

**Spec:** [docs/superpowers/specs/2026-10-21-assistant-phase1-design.md](../specs/2026-10-21-assistant-phase1-design.md), [0033](../../decisions/0033-chat-tab-single-session.md), [0030](../../decisions/0030-io-interface-task-as-conversation.md) "수정: 대화 탭", [디자인 README](../../design/2026-10-21-output-ui/README.md)

## Global Constraints

- 앞선 백엔드 계획([2026-10-21-assistant-backend.md](2026-10-21-assistant-backend.md))의 Global Constraints를 그대로 따른다. 로그에 사용자 글을 쓰지 않는다(예외 종류만), 문서와 코드는 같은 커밋, 경로·환경은 `config.py`에서만.
- 새 값:

| 이름 | 값 |
|---|---|
| 작업 출처 `source` | `"user"`, `"schedule"`, `"chat"` |
| 대화 줄 종류 `kind` 추가 | `"chip"` — 작업 칩. `text` = 작업 제목, `data` = `{"task_id": <새 작업 ID>}` |
| 설정 키 | `"permission_mode"`(기존), `"recording"` = `"on"`/`"off"` (기본 `"on"`) |
| `settings` 메시지 | `{"type":"settings","permission_mode": m,"recording": bool}` |
| 새 프론트 → 백엔드 메시지 | `logout` (필드 없음, 백그라운드 실행), `set_recording` (`enabled: bool`) |

## Review Focus

1. **대화 작업이 두 개 생김**: 앱을 여러 번 켜도 출처 `"chat"` 작업은 하나뿐이다. → Task 1 `test_chat_task_created_once`
2. **대화 작업이 알림·작업 목록에 섞임**: `list_tasks`의 `"user"`·`"alerts"` 보기 모두 `"chat"`을 뺀다. → Task 1 `test_chat_task_not_in_lists`
3. **앱이 일하는 중에 꺼졌다 켜짐 (대화 작업)**: 시작 때 고아 처리로 `failed`가 되더라도 대화 작업은 다시 말하면 이어진다(`say`가 저장된 세션을 이어 쓴다). → Task 1 `test_chat_resumes_after_restart`
4. **화면 기록을 끈 채 앱을 다시 켬**: 저장된 `"off"`면 시작 때 screenpipe를 띄우지 않는다. → Task 2 `test_recording_off_persists_across_start`
5. **로그아웃 중 요청**: 로그아웃 뒤 `status {logged_in:false}`를 보내고, 이후 `request`는 기존대로 status만 다시 보낸다. → Task 2 `test_logout_sends_status`

---

### Task 1: 대화 작업과 작업 칩

**Files:**
- Modify: `backend/backend/store.py` (보기에서 `"chat"` 제외, `chat_task() -> dict | None`), `backend/backend/core.py`, `backend/backend/tools.py`, `backend/backend/agent.py`, `backend/backend/harness.md`
- Test: `backend/tests/test_store.py`, `backend/tests/test_core.py`, `backend/tests/test_tools.py`

**Interfaces:**
- Produces:
  - `Store.chat_task() -> dict | None` (출처 `"chat"` 작업, 없으면 None)
  - `App.startup()`: 대화 작업이 없으면 만든다. 제목 `"대화"`, 상태 `done`, seen `True`, 세션 없음.
  - `App.connected(True)`: `status`에 이어 대화 작업의 `task` 메시지를 보낸다.
  - `TaskContext.start_task(text: str) -> dict` (Protocol에 추가) — `AgentRun`이 `RunEvents.start_task(text)`로 넘기고, App이 `request(text)`와 같은 흐름으로 새 사용자 작업을 만들어 돌린 뒤 그 작업 dict를 돌려준다. 로그아웃이면 만들지 않고 `None`을 돌려준다.
  - 도구 `create_task {text}`: `ctx.start_task(text)` → 대화 줄 `chip`(`text`=새 작업 제목, `data`={"task_id": id})을 지금 작업에 남기고 `ctx.entry_added`로 보낸다. 결과는 새 작업 ID와 제목. 로그아웃이면 `is_error`.
- 대화 작업의 `say`는 기존 `say`와 같다(세션이 있으면 resume, 없으면 새 세션). 상태가 `done`/`failed`여도 이어 말할 수 있다(기존 동작 확인만).
- `harness.md` 3절에 한 줄: "대화 작업에서 사용자가 일을 맡기면 `create_task`로 새 작업을 만든다. 그냥 묻는 말에는 대화에서 답한다."

- [ ] **Step 1: 실패하는 테스트**: `test_chat_task_created_once`(startup 두 번 → chat 작업 1개), `test_chat_task_not_in_lists`(user·alerts 보기에 chat 없음, chat이 failed·안 봄이어도), `test_connect_sends_chat_task`, `test_chat_resumes_after_restart`, `test_create_task_tool_starts_task_and_leaves_chip`, `test_create_task_when_logged_out_is_error`
- [ ] **Step 2: 실패 확인** — `cd backend && uv run pytest -q` → 새 테스트 FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — 전체 PASS
- [ ] **Step 5: 커밋** — `feat(backend): 대화 탭 작업과 작업 칩(create_task)` (문서는 Task 2에서 함께)

---

### Task 2: 로그아웃과 화면 기록 켜기·끄기, 전송, 문서

**Files:**
- Modify: `backend/backend/clients.py` (`Auth.logout() -> None`: `claude auth logout`, 20초 제한), `backend/backend/core.py` (`logout()`, `set_recording(enabled)`, `get_settings`의 `recording`), `backend/backend/server.py` (ROUTES에 `logout: ()`, `set_recording: (("enabled", bool),)`; `logout`은 BACKGROUND), `backend/backend/__main__.py` (Recorder를 만들어 App에 넘긴다. 시작 때 저장된 `recording`이 `"on"`일 때만 `Recorder.start()`하는 것은 `App.startup()`이 한다; App이 Recorder를 받아 켜고 끈다)
- Modify docs: `docs/backend-protocol.md` (`logout`, `set_recording`, `settings.recording`, 출처 `chat`, 줄 종류 `chip`, 접속 때 대화 작업 `task`), `ARCHITECTURE.md`, `docs/manual-checks/backend.md` (로그아웃 뒤 로그인, 화면 기록 끄기·켜기로 screenpipe 프로세스가 실제로 사라지고 생기는지)
- Test: `backend/tests/test_clients.py`, `test_core.py`, `test_server.py`

**Interfaces:**
- `App(store, emit, auth, recorder, new_run=AgentRun)` — `recorder`는 `start()`(async)·`stop()`을 가진 객체. 기존 생성자 순서를 확인해 맞춘다.
- `App.logout()`: `await auth.logout()` → `status {logged_in: false}`.
- `App.set_recording(enabled: bool)`: 설정 저장 → `recorder.start()` 또는 `stop()` → `settings` 메시지.
- `App.recording_enabled() -> bool` (`App.startup()`이 시작 때 읽는다. 구현 때 테스트하기 쉽게 `__main__`에서 옮겼다).

- [ ] **Step 1: 실패하는 테스트**: `test_logout_sends_status`, `test_set_recording_starts_and_stops`, `test_recording_off_persists_across_start`, `test_settings_includes_recording`, server의 `logout`·`set_recording` 라우트(타입이 틀리면 버림), `Auth.logout` 명령 인자
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현과 문서**
- [ ] **Step 4: 통과 확인** — `cd backend && uv run pytest -q` 전체 PASS
- [ ] **Step 5: 커밋** — `feat(backend): 로그아웃, 화면 기록 켜기·끄기, 프로토콜 문서`
