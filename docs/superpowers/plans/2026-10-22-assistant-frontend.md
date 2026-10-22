# 조수 1단계 화면(프론트) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `app/`(Tauri)을 디자인 18개 화면대로 다시 만들고, 프로토콜 v6으로 백엔드에 붙인다.

**Architecture:** 강아지와 패널은 **창 하나**(`main`)다. 투명·항상 위·테두리 없는 창으로, 패널이 닫히면 강아지 크기(128x96), 열리면 패널을 담는 크기로 바뀌고 오른쪽 아래(작업 영역 기준)에 붙는다. 백엔드 연결과 상태는 이 창 하나가 갖는다(백엔드는 화면 연결을 하나만 받는다). 상세 창(`detail`, 아트보드 12)은 별도 창이고, 메인 창이 Tauri 이벤트로 데이터를 넘기고 말하기·멈추기를 받아 대신 보낸다. 화면과 분리된 논리(프로토콜, 상태, 배지·자세, 대화 줄 묶기, 스케줄 양식 → 규칙, 사용량 표시)는 `src/shared/`의 순수 모듈로 두고 단위 테스트한다. 그리는 코드는 `src/ui/`이고 수동 확인 목록으로 확인한다.

**Tech Stack:** Tauri 2 (Rust + TypeScript), Vite, Vitest, 프레임워크 없는 TypeScript(DOM)

**Spec:** [docs/superpowers/specs/2026-10-21-assistant-phase1-design.md](../specs/2026-10-21-assistant-phase1-design.md) 3절, [프로토콜 v6](../../backend-protocol.md), [디자인 README](../../design/2026-10-21-output-ui/README.md), [디자인 다이제스트](../../design/2026-10-21-output-ui/digest.md)(아트보드 값 모음), 결정 0028·0030·0032·0033

## Global Constraints

- 문서와 코드는 같은 커밋 (CLAUDE.md 1절). Tauri·Vite API는 Context7(`/tauri-apps/tauri-docs`)로 확인하고 쓴다.
- 화면 값(색, 크기, 문구)은 [다이제스트](../../design/2026-10-21-output-ui/digest.md)의 값을 그대로 쓴다. 다이제스트가 비어 있거나 모호한 곳은 아래 "정한 값"을 따른다.
- 마우스로만 쓴다. 전역 단축키를 두지 않는다(사용자).
- 메시지 이름·필드는 [프로토콜 v6](../../backend-protocol.md)과 정확히 같다. `PROTOCOL_VERSION = 6`.
- 패널 문구는 한국어. 로그·콘솔에 사용자 글을 찍지 않는다.
- 개발용 앱(`npm run tauri dev`)은 확인이 끝나면 바로 닫는다 (CLAUDE.md 3절).

### 정한 값 (디자인에 없거나 모호한 곳, Claude 판단)

| 항목 | 값 |
|---|---|
| 강아지 크기 | 128x96 (스프라이트 2배, 아트보드 기준). manifest의 `scale`은 쓰지 않는다 |
| 강아지·패널 위치 | 주 모니터 작업 영역의 오른쪽 아래. 창 오른쪽 끝 = 작업 영역 오른쪽 − 20px, 창 아래 끝 = 작업 영역 아래. 패널은 강아지 위 12px, 오른쪽 정렬 |
| 툴팁 | 브라우저 기본 `title`. 일하는 중이면 `일하는 중 · 작업 N개`, 로그아웃이면 `눌러서 로그인하기`, 그 밖에는 `눌러서 일 맡기기`. 창을 강아지 크기로 유지하려고 아트보드의 검은 툴팁 대신 쓴다 |
| 입력칸 | 모든 대화 입력은 늘어나는 textarea(한 줄 40px → 최대 120px). Enter 보내기, Shift+Enter 줄바꿈, 한글 조합 중 Enter는 무시 |
| 패널 높이 | 목록 화면은 내용만큼. 작업 대화 440px, 스케줄 대화 460px, 대화 탭 본문 360px + 입력줄 |
| 매주 요일 칩 | 하나만 고른다(라디오처럼). 규칙의 `weekday`가 하나뿐이다 |
| 매월 날짜 | 반복이 매월이면 `일` 숫자 칸(1~31)을 시각 옆에 보인다 |
| 꺼진 스위치 | 트랙 #C4CAD3, 손잡이 왼쪽, 글자 `꺼짐` #5B6472 |
| 실패 줄 | 에이전트 말풍선 모양 + 앞에 노랑 `!` 아이콘(#B45309) |
| 수정 줄(`edit`) | 에이전트 말풍선 모양 |
| 진행 줄 묶기 | 이어진 `progress` 줄은 칩 하나로 접는다: `진행 N단계 · <마지막 글>`. 누르면 펼친다. 작업이 일하는 중이고 마지막 줄이 진행이면 칩 앞에 스피너 |
| 멈추기 | 확인창 없이 바로 `stop` |
| 로그아웃 상태 | 강아지 잠(배지 없음). 패널을 열면 설정 탭이 열린다. 다른 탭도 누를 수 있다 |
| 연결이 끊김 | 패널 맨 위에 `백엔드에 연결하는 중…` 띠(12px #5B6472, bg #F7F8FA). 강아지는 앉기 |
| 계정 이메일 | 백엔드가 보내지 않으므로 이메일 줄은 그리지 않는다 |
| 사용량 이름 | `type`에 `opus`가 들어가면 `Opus`, `sonnet`이면 `Sonnet`(둘 다 "모델별"), `five_hour`는 `현재 세션`, `seven_day`는 `이번 주`, 그 밖은 `type` 그대로("모든 모델 공통"). 값이 없으면 `아직 사용량 정보가 없어요. 작업이 돌면 채워져요.` 플랜 이름 자리는 그리지 않는다 |
| 글꼴 | `'Noto Sans KR', 'Malgun Gothic', sans-serif`. 웹 글꼴을 내려받지 않는다 |
| 트레이 | `종료` 하나 |
| 앱 종료 | 백엔드를 프로세스 트리째 끈다(Windows `taskkill /PID <pid> /T /F`). screenpipe·Claude Code가 남지 않게 한다 (백엔드 계획 Ruling 13) |
| 주 창 닫기 | 주 창이 닫히면(Alt+F4 등) 앱을 끝낸다. 백엔드만 남지 않게 (구현 중 추가) |
| 패널 그림자 | 없다. 창이 패널 크기에 딱 맞아 그림자가 창 끝에서 잘린다 (구현 중 추가) |
| 에이전트 글 | 작은 마크다운만 그린다: 문단·줄바꿈, `- `·`1. ` 목록, **굵게**, `코드`. 제목·링크 등은 글 그대로. DOM으로 만들고 `innerHTML`을 쓰지 않는다. 에이전트 말풍선 안의 인라인 코드는 흰 바탕(#F3F4F6 말풍선 위에서 보이게) (구현 중 추가) |
| 선택지 막기 | 질문·등록 확인 카드의 선택지는 `say`를 보낸 뒤에만 막는다. 끊겨 보내지 못하면 막지 않는다 (구현 중 추가) |
| [고치기] 양식 | 등록 확인의 [고치기]는 지시서 수정 양식을 확인 값으로 연다. 아직 등록 전이라 `저장하면 다음 실행부터 적용돼요` 힌트를 빼고, 저장하면 `set_schedule` (구현 중 추가) |
| 로그인 버튼 | [로그인]을 누르면 `status`가 올 때까지 `로그인하는 중…`으로 막는다 (구현 중 추가) |

## Review Focus

1. **백엔드가 늦게 뜨거나 재시작됨**: 접속이 끊겨도 앱이 멈추지 않고 2초마다 다시 붙는다. 다시 붙으면 열려 있던 화면의 데이터를 다시 요청한다. → Task 1 `test_reconnect_requests_current_view` (상태 모듈의 "다시 붙었을 때 보낼 요청" 함수)
2. **한글 입력 중 Enter**: 조합 중(`isComposing`)인 Enter는 보내지 않는다. → Task 2 `test_enter_while_composing_does_not_send` (입력 키 판정 순수 함수)
3. **같은 작업의 `entry`가 대화를 열기 전에 옴**: 캐시에 쌓였다가 대화를 열면(`task_detail`) 중복 없이 합쳐진다(줄 `id` 기준). → Task 1 `test_entries_merge_without_duplicates`
4. **대화 작업이 배지·알림에 섞임**: `source: "chat"`은 배지 개수와 자세 계산에서 뺀다. → Task 1 `test_chat_task_excluded_from_badges`
5. **매월 31일·요일 없는 매주**: 양식이 틀린 규칙을 만들지 않는다(매주는 요일 필수, 매월은 1~31). → Task 2 `test_rule_form_validation`

---

## 파일 구조

| 파일 | 할 일 |
|---|---|
| `app/src/shared/protocol.ts` (새, `backend-protocol.ts` 대체) | v6 타입, 들어온 메시지 해석, 나가는 메시지 만들기 |
| `app/src/shared/state.ts` (새) | 상태와 `apply(state, msg)`, 배지·자세·툴팁·다시 붙었을 때 요청 |
| `app/src/shared/entries.ts` (새) | 대화 줄 묶기(진행 접기), 줄별 표시 모델 |
| `app/src/shared/forms.ts` (새) | 스케줄 양식 ↔ 규칙, 입력 키 판정, 시각·사용량 표시 글 |
| `app/src/backend-link.ts` (고침) | v6 `hello`, 다시 붙기 |
| `app/src/window.ts` (새) | 창 크기·위치(오른쪽 아래), 상세 창 열기 |
| `app/src/main.ts` (다시 씀) | 조립: 연결 → 상태 → 그리기 |
| `app/src/ui/*.ts` (새) | `dog.ts`, `panel.ts`, `lists.ts`, `conversation.ts`, `schedule.ts`, `settings.ts`, `usage.ts`, `dom.ts`(작은 `h()` 도우미), `styles.css` |
| `app/detail.html`, `app/src/detail.ts` (새) | 상세 창 |
| `app/src-tauri/*` (고침) | 창 설정, 트레이 `종료`, 플러그인 정리, 백엔드 트리 종료 |
| 지움 | `input.html`, `settings.html`, `src/input.ts`, `src/settings-page.ts`, `src/shared/settings.ts`, `src/shared/backend-protocol.ts`, 관련 테스트, `@tauri-apps/plugin-global-shortcut`·`@tauri-apps/plugin-store`(npm·Cargo) |

---

### Task 1: 프로토콜 v6과 상태 모듈

**Files:** Create `app/src/shared/protocol.ts`, `app/src/shared/state.ts`, `app/tests/protocol.test.ts`, `app/tests/state.test.ts`. Delete `app/src/shared/backend-protocol.ts`, `app/tests/backend-protocol.test.ts`. Modify `app/src/backend-link.ts`(v6 `hello`), `app/src/main.ts`(새 모듈 이름으로 컴파일만 되게 최소 수정).

**Interfaces (Produces):**
- `protocol.ts`: 타입 `Task`, `Entry`, `Schedule`, `ScheduleRow`, `Rule`, `PermissionMode`, `Limit`, `BackendMessage`(백엔드 → 화면 9종의 합), `Outgoing`(화면 → 백엔드 16종의 합, 프로토콜 표 그대로); `parseBackendMessage(raw: unknown): BackendMessage | null` (버전이 6이 아니거나 모양이 틀리면 null), `outgoing(msg: Outgoing): string` (`v: 6` 붙임). `PROTOCOL_VERSION = 6`.
- `state.ts`:
  - `type View = { tab: "alerts"|"chat"|"tasks"|"schedules"|"usage"|"settings", screen: "list"|"task"|"newTask"|"newSchedule"|"schedule"|"editSchedule", taskId?: number, page: number }`
  - `type State = { connected: boolean, loggedIn: boolean|null, chatTaskId: number|null, tasks: Map<number, Task>, entries: Map<number, Entry[]>, schedules: Map<number, Schedule>, lists: { user?: Page<Task>, alerts?: Page<Task>, schedules?: Page<ScheduleRow> }, settings: {permissionMode, recording}|null, limits: Limit[], panelOpen: boolean, view: View }`
  - `initialState(): State`, `apply(s: State, m: BackendMessage): State` (불변 갱신), `badges(s): {red, yellow, green}`(알림 대상: waiting, failed+안 봄, done+안 봄; `source:"chat"` 제외), `pose(s): "sleep"|"beg"|"walk"|"lay"|"stand"|"sit"` (로그아웃→sleep, 빨강>0→beg, 일하는 중 작업>0→walk, 노랑>0→lay, 초록>0→stand, 그 밖 sit; 연결 끊김→sit), `tooltip(s): string`, `refreshRequests(s): Outgoing[]` (다시 붙었을 때·화면을 열 때 보낼 요청: 열린 탭의 목록, 열린 작업의 `get_task`, 설정 탭이면 `get_settings`, 사용량이면 `get_usage`, 그리고 배지를 위해 알림 목록 1쪽)
  - 배지 계산의 재료: `task` 메시지와 `tasks`(alerts·user) 목록으로 알게 된 작업 전부(`tasks` Map).

- [ ] **Step 1: 실패하는 테스트**: `protocol.test.ts` — 9종 메시지 해석, 버전 5 거부, 모르는 `type`·틀린 모양 null, `outgoing`이 `v:6`을 붙임. `state.test.ts` — `test_entries_merge_without_duplicates`, `test_chat_task_excluded_from_badges`, `test_reconnect_requests_current_view`, 접속 직후 `status`·대화 `task`로 `chatTaskId` 설정, 자세 우선순위 6가지, 툴팁 3가지, `tasks` 목록 반영, `schedule`·`settings`·`usage` 반영.
- [ ] **Step 2: 실패 확인** — `cd app && npm test` → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — `npm test`, `npx tsc --noEmit` 모두 통과
- [ ] **Step 5: 커밋** — `feat(app): 프로토콜 v6 클라이언트와 상태 모듈` (protocol 문서 변경 없음)

---

### Task 2: 대화 줄 묶기와 양식·표시 도우미

**Files:** Create `app/src/shared/entries.ts`, `app/src/shared/forms.ts`, `app/tests/entries.test.ts`, `app/tests/forms.test.ts`.

**Interfaces (Produces):**
- `entries.ts`: `type Item = { kind: "user"|"agent"|"failure"|"progress"|"question"|"proposal"|"run"|"chip", entries: Entry[], text: string, choices?: string[], data?: unknown, spinning?: boolean }`; `toItems(entries: Entry[], taskState: Task["state"]): Item[]` — 이어진 `progress`를 하나로(`text` = `진행 N단계 · <마지막 글>`), `result`·`edit`은 `agent`, `failure`는 `failure`, 마지막 묶음이 진행이고 작업이 `working`이면 `spinning: true`. 질문·등록 확인 카드는 그 줄이 아직 답을 기다리는(작업 `waiting`이고 그 뒤에 `user` 줄이 없는) 마지막 카드일 때만 버튼을 보인다: `answerable: boolean`.
- `forms.ts`:
  - `type RuleForm = { repeat: "daily"|"weekdays"|"weekly"|"monthly", time: string, weekday: number|null, day: number|null }`
  - `formToRule(f: RuleForm): Rule | string` (규칙 또는 한국어 오류 글: `요일을 골라 주세요`, `날짜는 1~31일이에요`, `시각을 골라 주세요`), `ruleToForm(r: Rule): RuleForm`
  - `REPEAT_LABELS = { daily: "매일", weekdays: "평일", weekly: "매주", monthly: "매월" }`, `WEEKDAY_LABELS = ["월","화","수","목","금","토","일"]`
  - `isSendKey(e: {key: string, shiftKey: boolean, isComposing: boolean}): boolean`
  - `timeText(iso: string, now: Date): string` (오늘이면 `HH:MM`, 아니면 `M/D`), `nextRunText(iso|null)`(스케줄 목록 오른쪽: `다음 14:00`·`다음 10/26`), `resetText(iso, now)` (`2시간 10분 뒤 초기화`, 하루 넘으면 `금 09:00 초기화`), `limitRows(limits: Limit[]): {common: Row[], models: Row[]}` (정한 값 표의 이름 규칙, `utilization`은 0~1을 %로 반올림; 1보다 크면 그대로 %로 본다)

- [ ] **Step 1: 실패하는 테스트**: 진행 접기(3줄 → 1개, 글), 스피너 조건, 답할 수 있는 카드는 마지막 하나, `test_rule_form_validation`(매주 요일 없음 → 오류, 매월 32 → 오류, 매일 09:00 → 규칙), `ruleToForm`↔`formToRule` 왕복, `test_enter_while_composing_does_not_send`, Shift+Enter는 false, 시간 글 4가지, 사용량 이름 규칙과 빈 목록
- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — `npm test`, `npx tsc --noEmit`
- [ ] **Step 5: 커밋** — `feat(app): 대화 줄 묶기, 스케줄 양식 규칙, 표시 글 도우미`

---

### Task 3: 창 껍데기와 강아지

**Files:** Modify `app/src-tauri/tauri.conf.json`(창 `main`: `transparent`, `decorations:false`, `alwaysOnTop`, `skipTaskbar`, `resizable:false`, `shadow:false`, `focus:false`, 128x96, `visible:true`; 창 `detail`: `detail.html`, 880x544, 숨김, 제목 `작업`; `input`·`settings` 창 삭제), `capabilities/default.json`(필요한 창 권한만: `main`, `detail`; set-size·set-position·show·hide·set-focus·set-title 등 Context7로 확인), `src-tauri/src/lib.rs`(트레이 `종료`만, 플러그인 global-shortcut·store 제거), `src-tauri/src/backend.rs`(`stop`이 Windows에서 `taskkill /PID <pid> /T /F`, `CREATE_NO_WINDOW`; 명령 인자를 만드는 함수 `kill_tree_args(pid: u32) -> Vec<String>`를 두고 Rust 테스트), `Cargo.toml`·`package.json`(플러그인 제거), `vite.config.ts`(입력: `index.html`, `detail.html`). Create `app/src/window.ts`, `app/src/ui/dom.ts`, `app/src/ui/styles.css`, `app/src/ui/dog.ts`, `app/detail.html`(빈 껍데기, Task 5에서 채움). Rewrite `app/src/main.ts`. Delete `app/input.html`, `app/settings.html`, `app/src/input.ts`, `app/src/settings-page.ts`, `app/src/shared/settings.ts`, `app/tests/settings.test.ts`.

**Interfaces:**
- Consumes: Task 1 `state.ts`(`pose`, `badges`, `tooltip`, `apply`, `refreshRequests`), `backend-link.ts`
- Produces: `window.ts` — `placeWindow(width: number, height: number): Promise<void>` (주 모니터 작업 영역 오른쪽 아래, 정한 값 표대로), `openDetail(taskId: number): Promise<void>`; `dom.ts` — `h(tag, attrs?, ...children): HTMLElement`; `dog.ts` — `renderDog(root, state, onClick)`: 스프라이트(`/sprites/dog/dog-02.png`, 시트 1024x864로 키움, 자세별 줄은 다이제스트 7절, 정지 프레임 첫 칸; 걷기는 아트보드대로 2번째 칸), 배지 알약(왼쪽 위, 빨강→노랑→초록, 0이면 숨김, 로그아웃이면 없음), `title` 툴팁, `aria-label`.
- `main.ts`: 연결 → `apply` → 다시 그리기. 강아지 클릭 → 패널 토글(이 Task에서는 패널 자리만 비워 두고 창 크기만 바꾼다). 패널을 열 때 로그아웃이면 설정 탭.

- [ ] **Step 1: 실패하는 테스트**: Rust `kill_tree_args(1234)` == `["/PID","1234","/T","/F"]`; 기존 `parse_endpoint` 테스트 유지
- [ ] **Step 2: 실패 확인** — `cd app/src-tauri && cargo test` → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 확인** — `cargo test`, `npm test`, `npx tsc --noEmit`, `npm run build` 통과. `npm run tauri dev`로 한 번 띄워 강아지가 오른쪽 아래에 보이는지 보고 **바로 닫는다**(트레이 → 종료). 본 것을 보고서에 적는다
- [ ] **Step 5: 커밋** — `feat(app): 창 하나로 강아지, 트레이 종료, 백엔드 트리 종료`

---

### Task 4: 패널 틀, 알림·작업 탭, 새 작업 화면

**Files:** Create `app/src/ui/panel.ts`, `app/src/ui/lists.ts`; Modify `main.ts`, `styles.css`.

**Interfaces:**
- Consumes: Task 1 상태·`refreshRequests`, Task 2 `timeText`, Task 3 `placeWindow`, `h`
- Produces: `renderPanel(root, state, send: (m: Outgoing) => void, go: (v: View) => void)`. 패널 크기가 바뀌면(`ResizeObserver`) `placeWindow(340, 패널높이 + 12 + 96)`. 탭 바(다이제스트 2절: 알림·대화·작업·스케줄 글자, 사용량·설정 아이콘, 알림 탭 미니 배지), 페이저(`1 / N`, 한 쪽 4줄), 꼬리.
- 알림 탭: 첫 `waiting` 작업만 질문 카드(그 작업의 마지막 질문 줄이 캐시에 없으면 `get_task`를 보내 받아 온다; 카드 버튼은 `say`), 나머지는 행(아이콘·이름·`스케줄` 태그·부가 글·[답하기] 또는 시각). 행·[답하기]·`대화 보기 ›` → 작업 대화 화면(Task 5).
- 작업 탭: 행(질문/진행 스피너+멈추기/스케줄 청록 스피너/못 함/다 함/멈춤), 하단 `+ 새 작업` → 새 작업 화면(다이제스트 6번: 160px textarea, [취소] [맡기기], 힌트). [맡기기] → `request`, 작업 탭으로 돌아간다.
- 행 부가 글: 질문을 기다리면 그 질문 글(캐시에 있으면), 아니면 상태 글(`일하는 중`, `답을 기다려요`, `다 했어요`, `못 했어요`, `멈췄어요`).
- 탭을 바꾸거나 쪽을 넘길 때 `refreshRequests`로 목록을 요청한다.

- [ ] **Step 1~2**: 이 Task의 순수 논리(예: 알림 카드에 쓸 작업 고르기 `firstWaiting(state)`)가 있으면 `state.ts`에 더하고 테스트 먼저(FAIL 확인)
- [ ] **Step 3: 구현**
- [ ] **Step 4: 확인** — `npm test`, `tsc`, `build`. 백엔드와 함께 `npm run tauri dev`로 띄워 패널 열기·탭 바꾸기·새 작업 맡기기를 한 번 해 보고 **바로 닫는다**. 본 것을 보고서에
- [ ] **Step 5: 커밋** — `feat(app): 패널, 알림·작업 탭, 새 작업 화면`

---

### Task 5: 대화 화면(작업 대화·대화 탭)과 상세 창

**Files:** Create `app/src/ui/conversation.ts`, `app/src/detail.ts`; Modify `app/detail.html`, `main.ts`, `panel.ts`, `styles.css`.

**Interfaces:**
- Consumes: Task 2 `toItems`, `isSendKey`; Task 3 `openDetail`
- Produces: `renderConversation(root, opts: { task, entries, height: number, compact: boolean }, send, go)` — 작업 대화(11번, 440px)와 대화 탭(18번, 본문 360px)과 상세 창(12번)이 같이 쓴다.
- 작업 대화 머리: 뒤로(이전 탭으로), 제목, 부제(`내 요청`·`스케줄`·상태 글), 창으로 크게 보기(`openDetail`), 멈추기(일하는 중·답 기다림일 때만, `stop`).
- 줄 그리기: 다이제스트 4절 + 정한 값. 질문 카드 버튼 → `say(choice)`. 등록 확인 [등록] → `say("등록")`, [고치기] → 지시서 수정 화면(Task 6)을 등록 확인 `data`로 채워 연다. 작업 칩 → 그 작업 대화.
- 입력: textarea, `isSendKey`면 `say`, 보낸 뒤 비우고 커서 유지. 스크롤은 사용자가 둔 자리를 지킨다(맨 아래에 있을 때만 새 줄에 따라 내려간다).
- 대화를 열면(`get_task`) 끝난 작업이면 `seen`을 보낸다.
- 대화 탭: `chatTaskId`로 열고, 탭 바 아래에 같은 대화 화면(머리 없음).
- 상세 창: 메인 창이 `detail-open {taskId}`로 열고 `detail-data {task, entries}`를 보낸다(작업·줄이 바뀔 때마다). 상세 창은 `detail-say {taskId, text}`, `detail-stop {taskId}`를 메인 창에 보내고, 메인 창이 백엔드로 보낸다. 상세 창 제목은 `작업 — <제목>`.

- [ ] **Step 1~2**: 새 순수 논리가 생기면 테스트 먼저
- [ ] **Step 3: 구현**
- [ ] **Step 4: 확인** — `npm test`, `tsc`, `build`. `tauri dev`로 작업 하나를 맡겨 진행 줄·결과가 쌓이는지, 대화 탭에서 말하기, 상세 창 열기를 해 보고 **바로 닫는다**. 본 것을 보고서에
- [ ] **Step 5: 커밋** — `feat(app): 작업 대화, 대화 탭, 상세 창`

---

### Task 6: 스케줄 탭

**Files:** Create `app/src/ui/schedule.ts`; Modify `panel.ts`, `main.ts`, `styles.css`.

**Interfaces:**
- Consumes: Task 2 `formToRule`, `ruleToForm`, `REPEAT_LABELS`, `WEEKDAY_LABELS`, `nextRunText`; Task 5 `renderConversation`
- Produces:
  - 스케줄 탭 목록(9번): 행 아이콘(도는 중 청록 스피너, 지난번 못 함 노랑, 지난번 완료 초록, 꺼짐 회색), 이름·`· label`, 오른쪽 `도는 중`·`다음 …`·`꺼짐`. 지난번 결과는 `schedules` 행에 없으므로 그 스케줄의 `schedule`(`last_result`)이 캐시에 있으면 쓰고 없으면 아이콘 없이. 하단 `+ 새 스케줄`.
  - 새 스케줄(15번): 이름, 반복 select, 시각, 매주 요일 칩(하나), 매월 날짜, 할 일, [취소] [등록] → `formToRule` 오류면 양식 아래 빨강 글(12px #B42318), 아니면 `add_schedule`.
  - 스케줄 대화(16번, 460px): 머리(이름, `스케줄`, 스위치 → `set_schedule_enabled`, 창으로 크게 보기), 작업 지시서 줄(`작업 지시서 · label · 다음 …`, 할 일 한 줄, `✎ 수정`), 아래는 `renderConversation`.
  - 지시서 수정(17번): 같은 양식 + 힌트 `저장하면 다음 실행부터 적용돼요`, [취소] [저장] → `set_schedule`. 등록 확인의 [고치기]로 열렸으면 그 `data`로 채우고 저장 뒤 그 작업 대화로 돌아간다.

- [ ] **Step 1~2**: 새 순수 논리가 생기면 테스트 먼저
- [ ] **Step 3: 구현**
- [ ] **Step 4: 확인** — `npm test`, `tsc`, `build`. `tauri dev`로 새 스케줄 등록, 켜고 끄기, 지시서 수정을 해 보고 **바로 닫는다**. 본 것을 보고서에
- [ ] **Step 5: 커밋** — `feat(app): 스케줄 탭 — 목록, 새 스케줄, 스케줄 대화, 지시서 수정`

---

### Task 7: 사용량·설정 탭, 로그아웃 상태

**Files:** Create `app/src/ui/settings.ts`, `app/src/ui/usage.ts`; Modify `panel.ts`, `main.ts`, `styles.css`.

**Interfaces:**
- Consumes: Task 2 `limitRows`, `resetText`
- Produces:
  - 설정 탭(13·10번): 계정 블록(로그인됨: 초록 점 `로그인됨 · Claude Code 구독` + [로그아웃] → `logout`; 안 됨: 회색 점 `로그인 안 됨` + 설명 + [로그인] → `login`, 누른 뒤 응답이 올 때까지 버튼을 `로그인하는 중…`으로 막는다), 화면 기록 스위치(`set_recording`), 권한 모드 라디오 5개(다이제스트 6절 문구, `set_permission_mode`), 안내 `새로 맡기는 작업부터 적용돼요`.
  - 사용량 탭(14번): `limitRows`로 두 묶음, 막대(`role=progressbar`), 근삿값 주석.
  - 로그아웃이면 강아지 잠, 배지 없음, 패널은 설정 탭으로 연다(Task 1 `pose`·Task 3 이미 반영, 여기서 확인).

- [ ] **Step 1~4**: 새 순수 논리는 테스트 먼저. `npm test`, `tsc`, `build`. `tauri dev`로 설정 탭(권한 모드 바꾸기, 화면 기록 끄고 켜기)과 사용량 탭을 보고 **바로 닫는다**. 로그아웃·로그인은 실제 계정에 영향을 주므로 하지 않는다. 본 것을 보고서에
- [ ] **Step 5: 커밋** — `feat(app): 사용량·설정 탭`

---

### Task 8: 문서와 수동 확인

**Files:** Modify `ARCHITECTURE.md`(2절 화면을 새 구조로: 창 하나, 상세 창, `src/shared`·`src/ui` 모듈, 트레이; 1절 그림), `README.md`(실행: 화면이 v6으로 붙는다, 단축키·입력창·키 설정 문구 삭제, 구성 표의 `app/` 설명, 앱 종료 시 트리 종료), `docs/backend-protocol.md`(맨 위 "현재 앱은 v5" 안내 삭제), `docs/manual-checks/frontend.md`(새: 화면별 확인 목록 — 디자인 18개 화면 상태를 실제 앱에서 보는 항목, 한글 입력 Enter, 다시 붙기, 상세 창, 앱 종료 뒤 screenpipe·claude 프로세스가 남지 않는지), ARCHITECTURE 문서 지도에 `frontend.md`·다이제스트·이 계획.

- [ ] **Step 1: 확인** — `cd app && npm test && npx tsc --noEmit && npm run build`, `cd src-tauri && cargo test`, `cd ../../backend && uv run pytest -q` 모두 통과
- [ ] **Step 2: 문서**
- [ ] **Step 3: 커밋** — `docs: 화면 v6 구조와 수동 확인 목록`
