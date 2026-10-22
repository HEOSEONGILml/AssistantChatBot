# 먼저 말 걸기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 헤매는 것 같으면 강아지 머리 위에 "!" 배지를 띄우고, 누르면 대화 탭에서 "도움이 필요해?"를 묻고, [도와줘]면 Claude가 짧게 제안한다.

**Architecture:** 백엔드에 30초 판단 고리(`Proactive`)를 둔다. 스케줄러와 나란히 돈다. 고리는 screenpipe DB를 읽기 전용으로 직접 읽어 최근 5분 기록을 글로 줄이고, Jev(`noul` 질문 둘)에 묻는다. 배지 상태는 `nudge` 메시지로 화면에 알린다. 배지를 누르면 대화 세션에 `nudge` 줄이 생긴다. [도와줘]는 대화 세션에 숨은 지시를 보내고, [괜찮아]는 거절 내역에 남는다.

**Tech Stack:** Python 3 (uv, pytest, stdlib `sqlite3`·`urllib`), Tauri 2 + TypeScript (Vitest)

**Spec:** [docs/superpowers/specs/2026-10-22-proactive-help-design.md](../specs/2026-10-22-proactive-help-design.md), [0037](../../decisions/0037-jev-for-proactive-judgment.md), 디자인 23·24번([다이제스트](../../design/2026-10-21-output-ui/digest.md) 3절)

## Global Constraints

- 문서와 코드는 같은 커밋. 한국어 문서. 로그에 화면 기록 글·사용자 글·키를 찍지 않는다(종류만).
- 외부 호출(Jev, screenpipe DB)은 `backend/backend/clients.py`를 거친다. 실패하면 그 판단을 건너뛰고 실패 종류를 로그에 남긴다 (CLAUDE.md 3절).
- Jev 질문 정의(`instructions`)와 임계값은 한 파일(`backend/backend/proactive.py`)에만 두고, 근거와 함께 스펙에 적는다 (CLAUDE.md 4절).
- 새 의존성을 더하지 않는다. HTTP는 `urllib.request`를 `asyncio.to_thread`로 부른다.
- 프로토콜은 v7에 더한다(버전 그대로). 메시지 이름은 아래 "정한 값"과 같다.
- 실제 Jev 호출 시험은 루트 `.env`의 `TYPESAFE_API_KEY`로 한다. 키가 없으면 그 시험은 건너뛴다(`pytest.mark.skipif`). 키를 코드·로그·커밋에 넣지 않는다.

### 정한 값

| 항목 | 값 | 근거·누가 |
|---|---|---|
| 판단 주기 | 30초 | 스펙 4절 |
| 판단 기록 | 최근 5분 `frames` 중 앱이 `app.exe`·`TamagotchiChatBot.exe`가 아닌 행. 줄마다 `HH:MM:SS 앱 · 창 제목` + 글 앞 300자. 전체 2,000자 안(새 것부터 채움) | 스펙 4절. 2천 토큰을 한글 기준 약 2,000자로 근사 (Claude) |
| 글 | `full_text`가 있으면 그것, 없으면 `accessibility_text` | screenpipe DB 열 (2026-10-22 확인) |
| 거절 내역 | 최근 1시간의 [괜찮아] `HH:MM 앱 · 창 제목`. 없으면 `최근 [괜찮아]: 없음` | 스펙 4절 |
| Jev 질문 | `need_help` (noul): `화면 기록을 보면 사용자가 지금 하는 일에서 막혀 있거나 헤매고 있다` / `declined_same` (noul): `'최근 [괜찮아]'에 지금 하는 작업과 같은 앱·창이 있다. 즉 사용자는 지금 이 작업에 대한 도움 제안을 최근에 이미 거절했다` | 2026-10-22 실측(아래). 한 문장에 둘을 섞으면 판단이 흐려졌다 (Claude) |
| 배지 조건 | `need_help ≥ 0.7`. 단 `declined_same ≥ 0.5`면 `need_help ≥ 0.9`일 때만 | 거절해도 판단은 계속하되 거절을 고려한다(사용자). 잠정값 (Claude) |
| 쉬는 때 | 화면 기록 꺼짐, Jev 키 없음, 배지가 떠 있음. 로그아웃은 배지를 켜기 직전에만 확인 | 스펙 4절. 로그인 확인은 CLI라 느려서 매번 하지 않는다 (Claude) |
| 배지 시간 | 켠 뒤 5분이 지나면 끈다 | 스펙 4절 |
| 메시지 | 백엔드→화면 `nudge {active: bool}` (접속할 때도 보냄). 화면→백엔드 `nudge_open`, `nudge_answer {help: bool}`, `set_jev_key {key: str}`. `settings`에 `jev_key_set: bool` | Claude |
| 대화 줄 | 새 `kind` `nudge`: `text` `도움이 필요해?`, `choices` `["도와줘", "괜찮아"]`, `data` `{app, window}` | Claude |
| [도와줘] | `user` 줄 `도와줘`를 남기고, 대화 세션에 숨은 지시를 보낸다: `[먼저 말 걸기] 사용자가 <앱> · <창 제목>에서 막힌 것 같아 도움을 청했다. 최근 화면 기록을 찾아보고 의견이나 해결 방법을 두세 문장으로 짧게 말해.` 대화 세션이 돌고 있으면 기존 `say`처럼 이어서 받는다 | 스펙 5절 |
| [괜찮아] | `user` 줄 `괜찮아`를 남기고 거절 내역에 `(시각, 앱, 창)`. 내역은 메모리(재시작하면 비움) | Claude |
| 답할 수 있는 `nudge` | 대화 세션의 마지막 `nudge` 줄이고, 그 뒤에 `user` 줄이 없을 때 | Claude |
| 배지 모양 | 23번: 22x22, bg #1D4ED8, 흰 테두리 2px, 13px/700 흰 `!`. 개수 배지 줄의 맨 앞. 툴팁 `할 말이 있어요` | 디자인 23번 |
| 배지 누름 | `nudge`가 켜져 있으면 강아지를 눌렀을 때 패널을 대화 탭으로 열고 `nudge_open`을 보낸다 | 디자인 23번 |
| 키 입력칸 | 설정 탭 맨 아래 `먼저 말 걸기` 칸: `Jev API 키` 비밀번호 입력 + [저장]. 저장되면 `입력됨`. 빈 값 저장은 키 지우기 | 사용자(설정에서 입력). 모양은 Claude |

Jev 실측 (2026-10-22, `jev-1.14.0`, 응답 0.2~0.3초): 엑셀 오류로 헤맴 → need_help 0.89 / declined_same 0.23. 같은 작업을 2분 전 거절 → 0.88 / 0.80. 다른 작업을 거절 → 0.88 / 0.16. 유튜브 시청 → 0.19 / 0.27.

## Review Focus

1. **screenpipe DB가 없거나 잠김**: 판단을 건너뛰고 고리는 계속 돈다. → Task 1 `test_history_missing_db_returns_empty`
2. **Jev 실패(키 틀림·시간 초과·이상한 응답)**: 배지를 켜지 않고 고리는 계속 돈다. 로그에 키·글이 없다. → Task 1 `test_jev_failure_returns_none`, Task 2 `test_tick_survives_jev_failure`
3. **배지가 5분 뒤 꺼지지 않음**: → Task 2 `test_badge_expires_after_5_minutes`
4. **한 배지에 [도와줘]를 두 번 누름**: 두 번째는 무시. → Task 2 `test_nudge_answer_only_once`
5. **배지 누름 사이에 대화 세션을 지움**: 새 대화 세션에 `nudge` 줄이 생긴다. → Task 2 `test_nudge_open_uses_current_chat`

---

## Task 1: 화면 기록 읽기, 줄이기, Jev 클라이언트

**Files:**
- Modify: `backend/backend/clients.py`, `backend/backend/config.py`
- Create: `backend/backend/proactive.py` (줄이기·질문 정의·배지 조건만, 고리는 Task 2)
- Test: `backend/tests/test_clients.py`, 새 `backend/tests/test_proactive.py`

**Interfaces:**
- Produces:
  - `config.screenpipe_db() -> Path` (`~/.screenpipe/db.sqlite`)
  - `clients.ScreenHistory(path: Path)`, `.recent(since: datetime) -> list[Frame]`. `Frame = {"at": datetime, "app": str, "window": str, "text": str}`. DB는 `file:...?mode=ro`로 열고, 없거나 열 수 없으면 `[]`
  - `clients.Jev(post=...)`, `async .ask(key: str, state: str, questions: dict) -> dict[str, float] | None` (noul 값들. 실패하면 `None`, 종류만 로그)
  - `proactive.summarize(frames, declines, now) -> str`
  - `proactive.QUESTIONS: dict`
  - `proactive.should_nudge(answers: dict[str, float]) -> bool`

- [ ] **Step 1: 실패하는 시험.** `test_history_reads_recent_and_skips_own_app`: 임시 sqlite에 `frames(timestamp, app_name, window_name, full_text, accessibility_text)` 행 4개(6분 전, 4분 전 chrome, 3분 전 app.exe, 1분 전 accessibility만). `recent(now-5분)` → chrome·1분 전 두 행, 1분 전은 `text`가 accessibility 값. `test_history_missing_db_returns_empty`. `test_summarize_budget`: 프레임 30개 × 글 500자 → 결과 2,000자 이하, 마지막 줄이 가장 최근 프레임, 각 글 300자에서 잘림, 끝에 `최근 [괜찮아]: 없음`. `test_summarize_declines`: 거절 `(15:42, EXCEL.EXE, 매출.xlsx)` → `최근 [괜찮아]: 15:42 EXCEL.EXE · 매출.xlsx`. `test_should_nudge`: `(0.89,0.23)→True`, `(0.88,0.80)→False`, `(0.95,0.80)→True`, `(0.19,0.27)→False`. `test_jev_failure_returns_none`: `post`가 예외·401·`answers` 없음 → `None`. `test_jev_parses_noul`: 정상 응답 → `{"need_help": 0.87, ...}`.
- [ ] **Step 2: 실패 확인** `cd backend && uv run pytest tests/test_proactive.py tests/test_clients.py -q`
- [ ] **Step 3: 구현.** screenpipe `timestamp`는 UTC ISO 문자열이다(예 `2026-10-22T05:30:10.358785400+00:00`, 소수 자리가 9자리일 수 있음). 비교는 UTC ISO 문자열 앞부분으로 SQL에서 한다.
- [ ] **Step 4: 통과 확인** 같은 명령. 그리고 `test_jev_live`(`skipif` 키 없음): 루트 `.env`의 키로 "엑셀 오류로 헤맴" 글 → `need_help ≥ 0.7`.
- [ ] **Step 5: 스펙 4절에 질문 문구·배지 조건·실측 표를 적고 커밋.**

## Task 2: 판단 고리, 배지, [도와줘]·[괜찮아], 키 저장

**Files:**
- Modify: `backend/backend/proactive.py` (고리), `backend/backend/core.py`, `backend/backend/server.py`, `backend/backend/__main__.py`, `docs/backend-protocol.md`, `ARCHITECTURE.md`, `docs/manual-checks/backend.md`
- Test: `backend/tests/test_proactive.py`, `backend/tests/test_core.py`, `backend/tests/test_server.py`

**Interfaces:**
- Consumes: Task 1 전부.
- Produces:
  - `proactive.Proactive(store, app, history, jev, clock)`, `async .tick()`, `async .run_forever(interval_s=30)`, `.decline(at, app, window)`, `.current_task() -> tuple[str, str] | None` (마지막 판단의 가장 최근 프레임 앱·창)
  - `App`의 `nudge_open()`, `nudge_answer(help: bool)`, `set_jev_key(key: str)`, `set_nudge(active: bool)`, `say(session_id, text, prompt: str | None = None)`. `prompt`가 있으면 줄에는 `text`, Claude에는 `prompt`
  - 메시지는 "정한 값" 그대로.

- [ ] **Step 1: 실패하는 시험.**
  - `test_tick_nudges_when_jev_says_so`: 가짜 history·jev(0.89/0.23)·키 있음·기록 켬·로그인 → `nudge {active: true}` 한 번.
  - `test_tick_rests`: 기록 꺼짐 / 키 없음 / 배지 켜짐 → Jev를 부르지 않음.
  - `test_tick_survives_jev_failure`: jev가 `None` → 배지 없음, 예외 없음.
  - `test_badge_expires_after_5_minutes`: 켠 뒤 시계 5분 1초 → 다음 tick에 `nudge {active: false}`.
  - `test_nudge_open_adds_entry_and_clears_badge`: 대화 세션에 `nudge` 줄(정한 값의 text·choices·data), `nudge {active: false}`.
  - `test_nudge_open_uses_current_chat`: 대화 세션을 지운 뒤 → 새 대화 세션에 줄.
  - `test_nudge_answer_help_sends_hidden_prompt`: `user` 줄 `도와줘`, Claude에 간 글은 정한 값의 지시문(앱·창 채움).
  - `test_nudge_answer_decline_records`: `user` 줄 `괜찮아`, 다음 `summarize`에 그 거절.
  - `test_nudge_answer_only_once`: 같은 `nudge`에 두 번 → 두 번째는 줄을 더하지 않음.
  - `test_set_jev_key`: 저장 뒤 `settings.jev_key_set == True`, 빈 값이면 False. `settings` 메시지에 키 원문이 없다.
  - `test_connected_sends_nudge_state`.
  - `test_server_routes`: 새 라우트 셋의 필드 타입.
- [ ] **Step 2: 실패 확인** `uv run pytest -q`
- [ ] **Step 3: 구현.** `__main__`에서 `Proactive(...).run_forever()`를 스케줄러와 함께 `asyncio.gather`로 돌린다. 키는 `settings` 테이블 `jev_key`.
- [ ] **Step 4: 통과 확인** `uv run pytest -q` 전부.
- [ ] **Step 5: 프로토콜 문서(새 메시지·`nudge` 줄), ARCHITECTURE(구성 요소·데이터 흐름), 수동 확인 행(실제 Jev·실제 screenpipe로 배지가 뜨는지)을 고치고 커밋.**

## Task 3: 화면 상태

**Files:** Modify `app/src/shared/{protocol,state,entries}.ts`. Test `app/tests/{protocol,state,entries}.test.ts`

**Interfaces:**
- Produces: `State.nudge: boolean`, `State.settings.jevKeySet: boolean`, `Outgoing`에 `nudge_open`·`nudge_answer`·`set_jev_key`, `Entry.kind`에 `nudge`, `Item.kind`에 `nudge`(답할 수 있는지는 `answerable`, 위 정한 값의 규칙).

- [ ] **Step 1: 실패하는 시험.** `nudge` 메시지 모양 검사. `apply`로 `nudge`가 켜지고 꺼짐. 끊기면 `false`. `settings`의 `jev_key_set`. `toItems`: 마지막 `nudge` 뒤 `user` 없으면 `answerable`, 있으면 아님, 앞쪽 `nudge`는 아님. `nudge` 줄은 대화 탭에서도 그린다.
- [ ] **Step 2~4:** `cd app && npm test && npx tsc --noEmit` 실패 → 구현 → 통과.
- [ ] **Step 5: 커밋.**

## Task 4: 화면 — 배지, 대화의 nudge, 설정의 키 입력

**Files:** Modify `app/src/ui/{dog,conversation,settings}.ts`, `app/src/main.ts`, `app/src/ui/styles.css`, `docs/manual-checks/frontend.md`

**Interfaces:**
- Consumes: Task 3.

- [ ] **Step 1:** 강아지 "!" 배지와 툴팁(정한 값). 켜져 있을 때 강아지를 누르면 패널을 대화 탭으로 열고 `nudge_open`. 큰 창이 떠 있어도 같다.
- [ ] **Step 2:** 대화의 `nudge` 줄(24번): 가운데 구분 글 `강아지가 먼저 말을 걸었어요 · HH:MM`(12px #5B6472) + 왼쪽 말풍선(bg #F3F4F6, 테두리 2px #1D4ED8) + 빠른 답 칩(min-height 32, radius 999, 테두리 1px #C4CAD3, 12px/500). 칩은 `answerable`일 때만, 누르면 `nudge_answer`(보낸 뒤 막기는 기존 선택지와 같은 방식).
- [ ] **Step 3:** 설정 탭 키 입력칸(정한 값). 입력 글은 다시 그려도 지우지 않는다(한글 조합·커서 보존은 기존 양식과 같은 방식).
- [ ] **Step 4:** `npm test && npx tsc --noEmit && npm run build` 통과.
- [ ] **Step 5:** 수동 확인 행(배지, 누름, 칩, 키 저장) 더하고 커밋.

## Task 5: 실제 확인

- [ ] `npm run tauri dev`로 띄워 설정에 키를 넣고, 일부러 같은 오류 화면을 몇 분 보며 배지가 뜨는지, [도와줘]·[괜찮아]가 정한 값대로 되는지 본다. 끝나면 바로 닫는다. 결과를 수동 확인 목록에 적고 커밋.
