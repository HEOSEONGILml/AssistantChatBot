# 조수 1단계 백엔드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 백엔드(`brain/`)를 v6 프로토콜로 작업·스케줄·작업 기록을 다루고, 작업마다 Claude Code 세션을 띄워 일하게 만든다.

**Architecture:** 프론트 메시지는 `server.py`(전송)가 받아 `core.py`의 `App`에 넘긴다. `App`은 SQLite 저장소(`store.py`)에 작업 기록을 쓰고, 작업마다 `agent.py`의 `AgentRun`으로 Claude Code 세션(Agent SDK)을 돌린다. Claude Code는 백엔드 MCP 도구(`tools.py`)와 screenpipe MCP로 데이터를 찾고, 크롬 확장으로 브라우저를 조작한다. 스케줄러(`scheduler.py`)는 1분마다 때가 된 스케줄 세션을 이어 실행한다.

**Tech Stack:** Python 3.11+, uv, `claude-agent-sdk`, `websockets`, SQLite(FTS5), pytest·pytest-asyncio

**Spec:** [docs/superpowers/specs/2026-10-21-assistant-phase1-design.md](../specs/2026-10-21-assistant-phase1-design.md). 결정 기록 0026~0032가 근거다.

**범위:** 백엔드만. 프론트(강아지 창·패널)는 별도 계획이다. 이 계획을 마치면 프론트(v5)는 v6 백엔드에 붙지 못한다(버전 불일치로 끊김). 프론트 계획에서 맞춘다.

## Global Constraints

- 문서와 코드는 같은 커밋에서 맞춘다 (CLAUDE.md 1절). 각 Task의 커밋에 관련 문서 수정을 함께 넣는다.
- 환경 변수와 경로는 `brain/brain/config.py`에서만 읽는다 (CLAUDE.md 3절).
- 외부 호출(Claude Code SDK, `claude` CLI, screenpipe)은 `agent.py`·`clients.py`를 거친다. 실패는 로그에 남기고 작업은 `failed`로 끝낸다.
- 라이브러리 API는 Context7(`/anthropics/claude-agent-sdk-python`)로 확인하고 쓴다.
- Claude Code는 `ANTHROPIC_API_KEY`를 뺀 환경으로 띄운다. 있으면 그 키로 과금되고 크롬 조작이 꺼진다.
- 작업 한도는 두지 않는다. `max_turns`, `max_budget_usd`를 쓰지 않는다. 모델은 지정하지 않는다.
- 로그에 사용자 글·대화 내용을 쓰지 않는다. 길이·ID·종류만 쓴다 (지금 코드와 같음).
- 시각은 PC 지역 시각. 저장은 ISO 8601 문자열(`datetime.now().astimezone().isoformat(timespec="seconds")`).
- 목록 한 쪽은 4줄 (디자인: "한 쪽에 4줄").

### 공통 값 (모든 Task가 이 이름을 쓴다)

| 이름 | 값 |
|---|---|
| `PROTOCOL_VERSION` | `6` |
| 작업 출처 `source` | `"user"`, `"schedule"` |
| 작업 상태 `state` | `"working"`(일하는 중), `"waiting"`(답 기다림), `"done"`(다 함), `"failed"`(못 함), `"stopped"`(멈춤) |
| 대화 줄 종류 `kind` | `"user"`(사용자 말), `"progress"`(진행), `"question"`(질문), `"result"`(결과), `"failure"`(실패), `"proposal"`(등록 확인), `"run"`(실행 구분선), `"edit"`(지시서 수정) |
| 권한 모드 | `"default"`, `"acceptEdits"`, `"plan"`, `"auto"`, `"bypassPermissions"` (기본 `"default"`) |
| 스케줄 규칙 `rule` | `{"repeat": "daily"\|"weekdays"\|"weekly"\|"monthly", "time": "HH:MM", "weekday": 0-6 (weekly, 월=0), "day": 1-31 (monthly)}` |

## Review Focus

1. **앱이 일하는 중에 꺼졌다 켜짐**: 저장소에 `working`·`waiting`으로 남은 작업은 세션 콜백이 사라졌으므로 시작할 때 `failed`로 바꾸고 실패 줄 "앱이 꺼져서 멈췄어요"를 남긴다. → Task 5 `test_startup_fails_orphaned_tasks`
2. **질문을 기다리는데 사용자가 멈춤**: 기다리던 Future를 거부로 풀고 세션을 끊어 `stopped`가 된다. 콜백이 영원히 매달리지 않는다. → Task 4 `test_stop_while_waiting_releases_question`
3. **매월 31일 스케줄**: 30일까지인 달에는 그 달 마지막 날에 돈다. → Task 2 `test_monthly_day_31_clamps_to_month_end`
4. **로그아웃 상태에서 요청**: 작업을 만들지 않고 실패 줄 없이 `status {logged_in: false}`를 다시 보낸다. → Task 5 `test_request_when_logged_out_resends_status`
5. **권한 모드 "묻지 않음"에서 스케줄 등록**: 권한 콜백이 오지 않아도 `create_schedule`은 등록 확인을 거친다(도구 안에서 확인을 기다린다). → Task 3 `test_create_schedule_waits_for_confirmation`

---

## 파일 구조

| 파일 | 할 일 |
|---|---|
| `brain/brain/config.py` (고침) | 데이터 폴더, 작업 폴더, DB 경로, screenpipe 명령. 키 보관(keyring)은 지운다 |
| `brain/brain/store.py` (새) | SQLite: `tasks`, `entries`, `schedules`, `settings`, FTS5 검색 |
| `brain/brain/schedule_rule.py` (새) | 스케줄 규칙 → 다음 실행 시각, 표시 글 |
| `brain/brain/tools.py` (새) | 백엔드 MCP 도구 7개 |
| `brain/brain/agent.py` (새) | Claude Code 세션 하나를 돌리고 질문·권한을 중계 |
| `brain/brain/harness.md` (새) | 하네스 문서 (0029 다섯 칸) |
| `brain/brain/clients.py` (새) | `claude auth status/login`, screenpipe 프로세스 |
| `brain/brain/core.py` (다시 씀) | `App`: 프론트 메시지 처리, 작업 관리, 사용량 |
| `brain/brain/scheduler.py` (새) | 1분 tick, 때가 된 스케줄 실행 |
| `brain/brain/server.py` (고침) | v6, 메시지 분배 |
| `brain/brain/__main__.py` (고침) | 조립과 실행 |
| `docs/brain-protocol.md` (다시 씀) | v6 |

---

### Task 1: 저장소

**Files:**
- Create: `brain/brain/store.py`, `brain/tests/test_store.py`
- Modify: `brain/brain/config.py` (`db_path()`, `work_dir()` 추가, keyring·`KEY_NAMES`·`read_keys`·`write_key` 삭제), `brain/tests/test_config.py`, `brain/pyproject.toml`(`uv remove keyring`)

**Interfaces:**
- Produces:
  - `config.db_path() -> Path` (`data_dir()/"assistant.db"`), `config.work_dir() -> Path` (`data_dir()/"work"`, 없으면 만듦)
  - `class Store(path: Path | None)` (`None`이면 메모리 DB). 메서드:
    - `create_task(source: str, title: str) -> dict` (state `"working"`, seen `False`)
    - `update_task(task_id: int, **fields) -> dict` (fields: `title`, `state`, `seen`, `session_id`)
    - `get_task(task_id: int) -> dict | None`
    - `add_entry(task_id: int, kind: str, text: str, choices: list[str] | None = None, data: dict | None = None) -> dict`
    - `entries(task_id: int) -> list[dict]` (오래된 것부터)
    - `list_tasks(page: int, view: str) -> tuple[list[dict], int]` — `view`: `"user"`(출처 user, 최신 위), `"alerts"`(waiting 또는 seen=False인 done·failed, 출처 무관; 순서 waiting → failed → done, 같은 성격은 최신 위). 반환은 (그 쪽 항목들, 전체 쪽 수)
    - `recent_tasks(limit: int) -> list[dict]`, `search_tasks(query: str, since: str | None, until: str | None, limit: int) -> list[dict]` (요청 글·제목·대화 글 FTS5)
    - `create_schedule(task_id: int, name: str, rule: dict, instruction: str) -> dict` (enabled `True`), `update_schedule(task_id: int, **fields) -> dict` (`name`, `rule`, `instruction`, `enabled`, `last_run_at`, `last_result`), `get_schedule(task_id: int) -> dict | None`, `list_schedules(page: int) -> tuple[list[dict], int]`, `all_schedules() -> list[dict]`
    - `get_setting(key: str, default: str) -> str`, `set_setting(key: str, value: str) -> None`
  - dict 모양: 작업 `{id, source, title, state, seen, session_id, created_at}`, 대화 줄 `{id, task_id, at, kind, text, choices, data}`, 스케줄 `{task_id, name, rule, instruction, enabled, last_run_at, last_result}`

- [ ] **Step 1: 실패하는 테스트 쓰기** — `test_store.py`

```python
def test_task_and_entries_roundtrip(): ...
    # create_task("user","휴지 주문") → id 1, state "working", seen False
    # add_entry(1,"question","결제할까요?",choices=["예","아니오"]) → entries(1)[0]["choices"] == ["예","아니오"]
def test_alerts_order_and_filter(): ...
    # done(seen) 제외, waiting → failed → done 순서
def test_user_view_excludes_schedules_and_pages_by_4(): ...
    # user 작업 5개 + schedule 작업 1개 → page 1에 4개, 쪽 수 2, schedule 없음
def test_search_tasks_finds_entry_text(): ...
    # 대화 글 "2만 원짜리 A 제품" → search_tasks("A 제품", None, None, 5)에 그 작업
def test_schedule_roundtrip_and_settings_default(): ...
    # rule dict 그대로 돌아옴; get_setting("permission_mode","default") == "default"
```

- [ ] **Step 2: 실패 확인** — `cd brain && uv run pytest tests/test_store.py -v` → FAIL (`ModuleNotFoundError: brain.store`)
- [ ] **Step 3: `store.py` 구현.** `sqlite3`, 시작 때 `CREATE TABLE IF NOT EXISTS`. `rule`·`choices`·`data`는 JSON 문자열로 저장. FTS5 가상 테이블 `task_text(task_id, text)`에 요청 글·제목·대화 글을 넣는다. config의 키 관련 코드와 테스트를 지우고 `uv remove keyring`.
- [ ] **Step 4: 통과 확인** — `uv run pytest -q` → 모두 PASS
- [ ] **Step 5: 커밋** — `feat(backend): 작업 기록 저장소 (tasks·entries·schedules·settings, FTS5)`

---

### Task 2: 스케줄 규칙

**Files:**
- Create: `brain/brain/schedule_rule.py`, `brain/tests/test_schedule_rule.py`

**Interfaces:**
- Produces: `next_run(rule: dict, after: datetime) -> datetime` (after보다 엄격히 뒤의 첫 실행 시각, 같은 tz), `label(rule: dict) -> str` (`"매일 09:00"`, `"평일 14:00"`, `"매주 월 10:30"`, `"매월 1일 09:00"`), `validate(rule: dict) -> None` (잘못되면 `ValueError`)

- [ ] **Step 1: 실패하는 테스트**

```python
def test_daily_next_day_when_time_passed():      # 10/21 09:30 이후 → 10/22 09:00
def test_weekdays_skips_weekend():                # 금 15:00 이후, 14:00 → 월 14:00
def test_weekly_monday():                         # weekday 0, 10:30
def test_monthly_day_31_clamps_to_month_end():    # 11/1 이후, day 31 → 11/30
def test_label_texts():                           # 위 네 표시 글
def test_validate_rejects_bad_time_and_missing_weekday():
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_schedule_rule.py -v` → FAIL
- [ ] **Step 3: 구현.** `calendar.monthrange`로 달 마지막 날을 구한다. 요일 표시는 `["월","화","수","목","금","토","일"]`.
- [ ] **Step 4: 통과 확인** — PASS
- [ ] **Step 5: 커밋** — `feat(backend): 스케줄 규칙의 다음 실행 시각과 표시 글`

---

### Task 3: 백엔드 MCP 도구

**Files:**
- Create: `brain/brain/tools.py`, `brain/tests/test_tools.py`

**Interfaces:**
- Consumes: `Store`(Task 1), `schedule_rule.validate/label/next_run`(Task 2)
- Produces:
  - `class TaskContext` — 도구가 지금 작업과 이야기하는 통로. 필드 `task_id: int`, 메서드 `async def confirm(kind: str, text: str, data: dict) -> str | dict` (대화 줄을 남기고 상태를 `waiting`으로 바꾼 뒤 사용자 답을 기다린다. 반환: `"등록"`·`"예"` 같은 글, 또는 [고치기]로 저장된 값 dict), `notify(task: dict) -> None`
  - `build_tools(store: Store, ctx: TaskContext) -> list[SdkMcpTool]` — 도구 이름: `recent_tasks`, `search_tasks`, `get_task`, `get_schedule`, `set_task_title`, `create_schedule`, `update_schedule`
  - `backend_server(store, ctx) -> McpSdkServerConfig` (`create_sdk_mcp_server(name="assistant", ...)`)
  - `MCP_PREFIX = "mcp__assistant__"`
- 도구 동작:
  - `get_schedule`: 이 작업(`ctx.task_id`)의 스케줄 지시서. 없으면 `is_error`.
  - `set_task_title {title}`: 제목을 바꾸고 `ctx.notify`.
  - `create_schedule {name, rule, instruction}`: `validate` → `ctx.confirm("proposal", "이렇게 등록할까요?", {name, rule, label, instruction, first_run})`. 답이 `"등록"`이면 그대로, dict면 그 값으로 `store.create_schedule(ctx.task_id, ...)`, 출처를 `"schedule"`로. 그 밖의 답은 저장하지 않고 그 글을 도구 결과로 돌려준다(에이전트가 뜻을 알아듣는다).
  - `update_schedule {name?, rule?, instruction?}`: 바뀐 내용으로 `ctx.confirm("proposal", "이렇게 고칠까요?", ...)` → 저장하면 `edit` 줄 `"작업 지시서를 고쳤어요: …"`.
  - 확인을 도구 안에서 기다리므로 권한 모드("묻지 않음" 포함)와 상관없이 확인을 거친다. 스펙 11절의 "권한 콜백으로 받는다"를 이렇게 구현하고, 같은 커밋에서 스펙 11절을 고친다.

- [ ] **Step 1: 실패하는 테스트** — 가짜 `TaskContext`(답을 미리 정해 둠)로 핸들러를 직접 부른다.

```python
async def test_search_tasks_returns_matches(): ...
async def test_create_schedule_waits_for_confirmation(): ...
    # confirm이 불리기 전에는 store.get_schedule(id) is None; 답 "등록" 뒤 저장, 출처 "schedule"
async def test_create_schedule_with_edited_values(): ...      # 답이 dict면 그 값으로 저장
async def test_create_schedule_declined_saves_nothing(): ...   # 답 "아니 9시 말고 10시" → 저장 없음, 결과 글에 그 답
async def test_update_schedule_leaves_edit_entry(): ...
async def test_create_schedule_rejects_bad_rule(): ...         # is_error, confirm 안 불림
```

- [ ] **Step 2: 실패 확인** — FAIL
- [ ] **Step 3: 구현.** `@tool`과 `create_sdk_mcp_server`(Context7 확인). 결과는 JSON 글 하나(`{"type":"text","text": json.dumps(..., ensure_ascii=False)}`).
- [ ] **Step 4: 통과 확인** — PASS
- [ ] **Step 5: 커밋** — `feat(backend): 작업 기록·스케줄 MCP 도구` (스펙 11절 수정 포함)

---

### Task 4: Claude Code 세션 하나 돌리기

**Files:**
- Create: `brain/brain/agent.py`, `brain/brain/harness.md`, `brain/tests/test_agent.py`
- Modify: `brain/brain/config.py` (`claude_env() -> dict[str, str]`: 지금 환경에서 `ANTHROPIC_API_KEY` 뺀 것), `brain/pyproject.toml` (`uv add claude-agent-sdk`)

**Interfaces:**
- Consumes: `tools.backend_server`, `TaskContext`(Task 3)
- Produces:
  - `HARNESS: str` (`harness.md` 내용)
  - `build_options(*, permission_mode: str, can_use_tool, mcp_servers: dict, resume: str | None) -> ClaudeAgentOptions` — 값은 스펙 5.1 표 그대로: `system_prompt={"type":"preset","preset":"claude_code","append":HARNESS}`, `setting_sources=[]`, `cwd=config.work_dir()`, `extra_args={"chrome": None}`, `disallowed_tools=["Bash","Write","Edit","NotebookEdit","Task","Skill"]`, `allowed_tools=[MCP_PREFIX+"*", "mcp__screenpipe__*"]`(데이터 찾기 도구는 묻지 않는다), `env=config.claude_env()`, `mcp_servers`(백엔드 + screenpipe stdio `{"command":"npx","args":["-y","screenpipe-mcp@latest"]}`)
  - `class AgentRun` — 생성자 `(task_id: int, events: RunEvents, make_client=ClaudeSDKClient)`. 메서드 `async def run(prompt: str, options) -> None`, `async def say(text: str) -> None`, `async def stop() -> None`, 속성 `waiting: bool`
  - `class RunEvents(Protocol)`: `progress(text)`, `question(text, choices) -> None`, `answered()`, `finished(result_text: str, is_error: bool)`, `session(session_id: str)`, `rate_limit(info: dict)`
- 동작:
  - `AssistantMessage`의 `TextBlock` → `events.progress`. `SystemMessage(init)`의 `session_id` → `events.session`. `RateLimitEvent` → `events.rate_limit({"type","utilization","resets_at"})`. `ResultMessage` → `events.finished(result, is_error)`.
  - `can_use_tool`: `AskUserQuestion`이면 질문마다 `events.question(question, [옵션 label들])` 후 `say`를 기다려 `answers[질문 글] = 답`, 모두 모이면 `PermissionResultAllow(updated_input={**input, "answers": answers})`. 그 밖의 도구는 `events.question(ctx.title or f"{tool_name} 사용을 허용할까요?", ["허용","거부"])` → 답이 `"허용"`이면 Allow, 아니면 `PermissionResultDeny(message=답)`.
  - `say`: 질문을 기다리는 중이면 그 Future를 답으로 푼다. 아니면 `client.query(text)`로 진행 중인 세션에 넣는다(덧붙이기).
  - `stop`: 기다리는 Future가 있으면 `"거부"`로 풀고 `client.interrupt()` 후 연결을 끊는다.
  - `TaskContext.confirm`(Task 3)도 같은 기다림 장치를 쓴다: `AgentRun`이 `TaskContext`를 구현한다.
- `harness.md`: 0029의 1~5절과 "스케줄 실행" 규칙을 그대로 옮긴다. 맥락 찾기 절에는 도구 이름을 적는다: 화면 기록은 `mcp__screenpipe__activity-summary`·`search-content`·`frame-context`, 작업 기록은 `recent_tasks`·`search_tasks`·`get_task`. 작업을 시작하면 `set_task_title`로 짧은 제목을 붙인다.

- [ ] **Step 1: 실패하는 테스트** — 가짜 클라이언트(정해 둔 SDK 메시지 목록을 흘려보내고, `query`·`interrupt` 호출을 기록)로.

```python
async def test_text_becomes_progress_and_result_finishes(): ...
async def test_ask_user_question_answer_with_free_text(): ...
    # say("진행해. 그런데 example.org로") → updated_input["answers"]["…열까요?"] == 그 글
async def test_permission_allow_and_deny(): ...                # "허용" → Allow, "아니" → Deny(message="아니")
async def test_say_while_working_queries_session(): ...        # 질문 없을 때 say → client.query 호출
async def test_stop_while_waiting_releases_question(): ...     # 기다리던 콜백이 Deny로 끝나고 interrupt 호출
def test_build_options_values(): ...                            # 위 옵션 값, env에 ANTHROPIC_API_KEY 없음
```

- [ ] **Step 2: 실패 확인** — FAIL
- [ ] **Step 3: 구현.** 기다림은 `asyncio.Future` 하나. SDK 타입 이름은 Context7로 확인(`AssistantMessage`, `TextBlock`, `SystemMessage`, `ResultMessage`, `RateLimitEvent`, `PermissionResultAllow`, `PermissionResultDeny`).
- [ ] **Step 4: 통과 확인** — PASS
- [ ] **Step 5: 커밋** — `feat(backend): Claude Code 세션 실행과 질문·권한 중계, 하네스 문서`

---

### Task 5: App — 작업 관리

**Files:**
- Rewrite: `brain/brain/core.py`, `brain/tests/test_core.py`

**Interfaces:**
- Consumes: `Store`, `AgentRun`, `build_options`, `backend_server`, `schedule_rule`
- Produces: `class App(store: Store, emit: Emit, auth: Auth, new_run=AgentRun)` (`Emit = Callable[[dict], Awaitable[None]]`, `Auth`는 Task 7). 메서드는 프론트 메시지마다 하나: `request(text)`, `schedule_request(text)`, `say(task_id, text)`, `stop(task_id)`, `seen(task_id)`, `list_tasks(page, view)`, `get_task(task_id)`, `list_schedules(page)`, `set_schedule(task_id, name, rule, instruction)`, `set_schedule_enabled(task_id, enabled)`, `get_settings()`, `set_permission_mode(mode)`, `get_usage()`, `login()`, `connected(on)`, `startup()`, 그리고 스케줄러용 `run_schedule(task_id, now)`.
- 보내는 메시지 (`emit`), 필드 이름은 이대로:
  - `{"type":"status","logged_in": bool}`
  - `{"type":"task","task": 작업}` · `{"type":"entry","task_id": id,"entry": 대화 줄}`
  - `{"type":"tasks","view": v,"page": p,"pages": n,"items": [작업]}`
  - `{"type":"task_detail","task": 작업,"entries": [...],"schedule": 스케줄 | null}`
  - `{"type":"schedules","page": p,"pages": n,"items": [{task_id,name,label,state,next_run}]}` — state: `"running"`(working·waiting), `"next"`, `"off"`
  - `{"type":"schedule","schedule": {task_id,name,rule,label,instruction,enabled,next_run,last_run_at,last_result}}`
  - `{"type":"settings","permission_mode": m}` · `{"type":"usage","limits": [{type, utilization, resets_at, received_at}]}`
- 동작:
  - `request`: 로그아웃이면 `status`만 다시 보낸다. 아니면 작업(`user`, 제목 = 요청 글 앞 30자) + `user` 줄을 만들고 `AgentRun.run(text, options)`을 백그라운드로 돌린다. `RunEvents`를 받아 줄·상태를 저장하고 `task`·`entry`를 보낸다. 끝나면 `done`/`failed`, seen `False`.
  - `schedule_request`: 출처 `schedule` 후보 작업으로 같은 흐름. 첫 메시지는 `f"새 스케줄을 만들어 줘: {text}"`. `create_schedule`이 저장하면 그 세션이 스케줄 세션이다.
  - `set_schedule`: 확인을 기다리는 등록 확인이 있으면 이 값을 답(dict)으로 넘긴다. 아니면 바로 저장하고 `edit` 줄을 남긴다.
  - 질문이 오면 상태 `waiting`, 답이 오면 `working`.
  - `startup`: `working`·`waiting`으로 남은 작업을 `failed`로 바꾸고 실패 줄 `"앱이 꺼져서 멈췄어요"`.
  - 사용량: `rate_limit` 이벤트를 종류별 마지막 값으로 보관하고 `usage`를 보낸다.

- [ ] **Step 1: 실패하는 테스트** — 가짜 `AgentRun`(이벤트를 테스트가 직접 일으킴), 메모리 `Store`, 가짜 `Auth`.

```python
async def test_request_creates_task_and_streams_entries(): ...
async def test_question_sets_waiting_and_say_resumes(): ...
async def test_alerts_view_lists_waiting_first(): ...
async def test_request_when_logged_out_resends_status(): ...
async def test_startup_fails_orphaned_tasks(): ...
async def test_set_schedule_answers_pending_proposal(): ...
async def test_usage_keeps_latest_per_type(): ...
async def test_permission_mode_saved_and_used_for_new_runs(): ...
```

- [ ] **Step 2: 실패 확인** — FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — PASS
- [ ] **Step 5: 커밋** — `feat(backend): App — 작업·스케줄 메시지 처리와 사용량`

---

### Task 6: 스케줄러

**Files:**
- Create: `brain/brain/scheduler.py`, `brain/tests/test_scheduler.py`

**Interfaces:**
- Consumes: `Store.all_schedules`, `schedule_rule.next_run`, `App.run_schedule`
- Produces: `class Scheduler(store, app, clock=lambda: datetime.now().astimezone())`, `async def tick() -> None`, `async def run_forever(interval_s: float = 60) -> None`
- 동작:
  - 켜진 스케줄마다 "마지막으로 본 시각"(처음은 시작 시각) 이후 `next_run`이 지금 이전이면 실행할 때다. 놓친 것은 건너뛴다: 시작 시각 이전 실행은 따라잡지 않는다.
  - 그 스케줄 작업이 `working`·`waiting`이면 이번 실행을 건너뛴다.
  - `App.run_schedule(task_id, now)`: `run` 줄(`"10/22 (수) 18:00 실행"`)을 남기고, 저장된 `session_id`로 `resume`해 메시지 `"[스케줄 실행 · 10/22 (수) 18:00] get_schedule로 지금 작업 지시서를 읽고 그대로 한 번 실행해."`를 보낸다. 끝나면 `last_run_at`·`last_result` 갱신, `schedule` 메시지.

- [ ] **Step 1: 실패하는 테스트** — 가짜 시계, 가짜 App.

```python
async def test_due_schedule_runs_once(): ...
async def test_missed_while_off_is_skipped(): ...       # 시작 전 시각은 실행 안 함
async def test_running_schedule_skips_this_time(): ...
async def test_disabled_schedule_never_runs(): ...
```

- [ ] **Step 2: 실패 확인** — FAIL
- [ ] **Step 3: 구현** (Task 5의 `run_schedule`도 여기서 함께 테스트로 확인)
- [ ] **Step 4: 통과 확인** — PASS
- [ ] **Step 5: 커밋** — `feat(backend): 스케줄러 — 1분 tick, 겹침·놓침 건너뛰기`

---

### Task 7: 로그인과 screenpipe

**Files:**
- Create: `brain/brain/clients.py`, `brain/tests/test_clients.py`
- Modify: `brain/brain/config.py` (`screenpipe_cmd() -> list[str]` = `["npx","-y","screenpipe","record"]`. 소리 설정은 정하지 않았으니 기본값 그대로)

**Interfaces:**
- Produces:
  - `class Auth` — `async def logged_in() -> bool` (`claude auth status` JSON의 `loggedIn`이 참이고 `authMethod == "claude.ai"`; 실행 실패·종료 코드 1이면 `False`), `async def login() -> bool` (`claude auth login --claudeai`를 띄워 끝나기를 기다린 뒤 `logged_in()`)
  - `class Recorder` — `async def start() -> None` (`config.screenpipe_cmd()` 띄움, 이미 `localhost:3030/health`가 응답하면 띄우지 않음), `def stop() -> None` (내가 띄운 것만 끔)
  - 둘 다 명령 실행을 `run: Callable` 인자로 받아 테스트에서 바꾼다. 환경은 `config.claude_env()`.

- [ ] **Step 1: 실패하는 테스트**

```python
async def test_logged_in_true_for_claude_ai(): ...
async def test_logged_in_false_on_exit_code_1_or_api_key_method(): ...
async def test_login_runs_then_rechecks(): ...
async def test_recorder_skips_when_already_running(): ...
```

- [ ] **Step 2: 실패 확인** — FAIL
- [ ] **Step 3: 구현** — `asyncio.create_subprocess_exec`, Windows는 `CREATE_NO_WINDOW`.
- [ ] **Step 4: 통과 확인** — PASS
- [ ] **Step 5: 커밋** — `feat(backend): 로그인 상태·로그인, screenpipe 띄우기`

---

### Task 8: v6 전송과 조립, 문서

**Files:**
- Modify: `brain/brain/server.py`, `brain/brain/__main__.py`, `brain/tests/test_server.py`
- Rewrite: `docs/brain-protocol.md` (v6, Task 5의 메시지와 필드 그대로)
- Modify: `ARCHITECTURE.md` (3절 백엔드 표, 4절 저장 위치에 `assistant.db`·`work/`), `README.md` (의존성 `claude-agent-sdk`, 필요한 것: Claude Code·Claude in Chrome 확장·구독 로그인, 키 입력 문구 삭제), `docs/manual-checks/backend.md` (새: 실제 Claude Code로 확인할 것 — 스펙 8절 "시험하지 않은 것" 다섯 줄)

**Interfaces:**
- Consumes: `App` 메서드(Task 5), `Scheduler`(Task 6), `Auth`·`Recorder`(Task 7)
- `server.Link._dispatch`: `type`별로 `App` 메서드를 부른다. 필드가 빠지거나 타입이 틀리면 로그만 남기고 버린다(지금과 같음). `set_key` 처리를 지운다.
- `__main__.main`: `Store(config.db_path())` → `App` → `await app.startup()` → `Recorder.start()` → WebSocket 서버 → `Scheduler.run_forever()`를 함께 돌린다. 끝날 때 `Recorder.stop()`.

- [ ] **Step 1: 실패하는 테스트** — 기존 `test_server.py`를 v6으로: `hello`(v=6) 뒤 `request` → 가짜 App의 `request("…")` 호출, 버전 5 거부, 모르는 type 무시, `say`에 `task_id`가 문자열이면 버림.
- [ ] **Step 2: 실패 확인** — FAIL
- [ ] **Step 3: 구현과 문서**
- [ ] **Step 4: 전체 확인** — `cd brain && uv run pytest -q` → 모두 PASS. 그다음 `uv run python -m brain`을 띄워 `brain.log`에 "백엔드 시작"과 screenpipe 시작이 찍히는지 보고 끈다.
- [ ] **Step 5: 커밋** — `feat(backend): 프로토콜 v6 전송과 조립, 문서 v6`

---

## 실행 뒤 수동 확인

`docs/manual-checks/backend.md`의 다섯 가지(덧붙이기, 크롬 동시 사용, 로그인 흐름, 사용량 이벤트, 스케줄 세션 resume)를 실제 Claude Code로 확인한다. 안 되는 것은 스펙으로 돌아가 사용자와 정한다.
