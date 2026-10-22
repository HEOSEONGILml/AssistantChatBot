# 화면 기록 폴더 보기·비우기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 설정 탭에 screenpipe 기록 폴더 위치와 용량을 보이고, [비우기] → 확인(디자인 25번) → 기록을 지운다.

**Architecture:** 백엔드 `settings` 메시지에 `recording_dir`, `recording_bytes`를 더한다. `clear_recording`을 받으면 백엔드가 띄운 screenpipe를 멈추고 내려갈 때까지 기다린 뒤 기록 파일을 지우고, 화면 기록이 켜져 있으면 다시 띄운 뒤 `settings`를 보낸다. 파일 일(재기·지우기)은 클라이언트 계층(`clients.py`)에 둔다.

**Tech Stack:** Python 3 (uv, pytest, stdlib), Tauri 2 + TypeScript (Vitest)

**Spec:** [스펙](../specs/2026-10-21-assistant-phase1-design.md) 4절 "기록 폴더"·"비우기", [0030](../../decisions/0030-io-interface-task-as-conversation.md) "수정: 화면 기록 폴더와 비우기", [다이제스트](../../design/2026-10-21-output-ui/digest.md) 13번 기록 폴더 줄·25번

## Global Constraints

- 문서와 코드는 같은 커밋. 한국어 문서. 로그에 경로 안의 사용자 이름이나 파일 내용을 찍지 않는다(실패 종류만).
- 프로토콜 v7에 더한다(버전 그대로). 메시지·필드 이름은 아래 "정한 값"과 같다.
- 쓰는 중에 지우지 않는다. 반드시 멈추고 내려간 뒤 지운다 (0030).

### 정한 값

| 항목 | 값 | 누가 |
|---|---|---|
| 기록 폴더 | `config.screenpipe_dir()` = `~/.screenpipe` (설정 모듈 한 곳). `config.screenpipe_db()`는 이 아래 `db.sqlite` | 스펙 |
| 지우는 것 | 기록 폴더의 `db.sqlite`, `db.sqlite-shm`, `db.sqlite-wal`, `data/` 아래 전부. screenpipe 자체 설정(`secrets.sqlite`, `machine_id`, `pipes/`, `skills/`, `store.bin` 등)과 로그는 남긴다 | Claude (설정까지 지우면 screenpipe 인증·설정이 날아간다) |
| 용량 | 위 "지우는 것"의 바이트 합. 없는 파일은 0 | Claude (확인 상자의 "기록 폴더의 N GB가 지워져요"와 맞춘다) |
| 필드 | `settings`에 `recording_dir: str`, `recording_bytes: int` | 0030 (이름은 Claude) |
| 메시지 | 화면→백엔드 `clear_recording` (필드 없음) | 0030 |
| 남의 screenpipe | 백엔드가 띄우지 않은 screenpipe가 떠 있으면 지우지 않는다. 로그에 이유를 남기고 `settings`만 다시 보낸다(용량 그대로) | Claude (기존 규칙: 백엔드가 띄운 것만 끈다) |
| 지우기 실패 | 파일 하나를 못 지워도 나머지는 계속 지운다. 실패 종류만 로그. 끝나면 다시 재서 `settings` | Claude |
| 용량 표시 | `1024³` 이상 `X.X GB`, `1024²` 이상 `X MB`, 그 밖 `X KB`(0이면 `0 KB`) | Claude |
| 경로 표시 | 고정폭 한 줄 말줄임, `title`에 전체 경로 | 다이제스트 13번 |
| 확인 상자 | 25번 문구. `<용량>` 자리에 표시 용량 | 다이제스트 25번 |

## Review Focus

1. **screenpipe가 아직 파일을 쥐고 있음(Windows 잠금)**: 멈춘 뒤 내려갈 때까지 기다리고, 그래도 못 지우면 남은 채로 다시 띄운다. 앱은 멈추지 않는다. → Task 1 `test_clear_continues_when_a_file_is_locked`
2. **화면 기록이 꺼진 상태에서 비우기**: 지우고 다시 띄우지 않는다. → Task 1 `test_clear_when_recording_off_does_not_restart`
3. **남이 띄운 screenpipe**: 지우지 않는다. → Task 1 `test_clear_skips_foreign_screenpipe`
4. **폴더가 없음**: 용량 0, 비우기는 아무 일 없이 끝난다. → Task 1 `test_size_of_missing_dir_is_zero`

---

## Task 1: 백엔드

**Files:** Modify `backend/backend/{config,clients,core,server}.py`, `docs/backend-protocol.md`, `ARCHITECTURE.md`, `docs/manual-checks/backend.md`. Test `backend/tests/{test_clients,test_core,test_server,test_config}.py`

**Interfaces:**
- Produces: `config.screenpipe_dir() -> Path`; `clients.recording_bytes(dir: Path) -> int`; `clients.clear_recording_files(dir: Path) -> None`; `Recorder.owns() -> bool`(내가 띄운 것이 살아 있음), `async Recorder.stop_and_wait() -> None`(끄고 health가 내려갈 때까지); `App.clear_recording()`; `settings`의 `recording_dir`·`recording_bytes`.

- [ ] **Step 1: 실패하는 시험.** `test_size_*`(임시 폴더에 `db.sqlite` 10B, `db.sqlite-wal` 5B, `data/a/b.jpg` 7B, `secrets.sqlite` 100B → 22), `test_size_of_missing_dir_is_zero`, `test_clear_files_keeps_config`(지운 뒤 `secrets.sqlite`·`machine_id` 남고 `db.sqlite*`·`data/` 없음), `test_clear_continues_when_a_file_is_locked`(지우기 함수를 주입해 한 파일에서 `PermissionError` → 나머지는 지움, 예외 없음), `test_settings_has_recording_dir_and_bytes`, `test_clear_recording_stops_clears_restarts`(가짜 Recorder: 순서 `stop_and_wait` → 지움 → `start`, 마지막에 `settings`), `test_clear_when_recording_off_does_not_restart`, `test_clear_skips_foreign_screenpipe`(내가 띄우지 않았고 health는 살아 있음 → 지우지 않음), 라우트 `clear_recording: ()`.
- [ ] **Step 2: 실패 확인** `cd backend && uv run pytest -q`
- [ ] **Step 3: 구현.** 파일 일은 `asyncio.to_thread`로.
- [ ] **Step 4: 통과 확인** `uv run pytest -q`
- [ ] **Step 5: 프로토콜 문서(`clear_recording`, `settings` 새 필드), ARCHITECTURE(설정·screenpipe 절), 수동 확인 행(실제 비우기)을 고치고 커밋.**

## Task 2: 화면

**Files:** Modify `app/src/shared/{protocol,state,forms}.ts`, `app/src/ui/{settings,panel}.ts`, `app/src/ui/styles.css`, `docs/manual-checks/frontend.md`. Test `app/tests/{protocol,state,forms}.test.ts`

**Interfaces:**
- Consumes: Task 1의 메시지.
- Produces: `State.settings.recordingDir: string`, `recordingBytes: number`; `Outgoing` `{type: "clear_recording"}`; `bytesText(n: number) -> string`.

- [ ] **Step 1: 실패하는 시험.** `settings` 모양 검사(새 필드 필수), `apply`가 새 필드를 담음, `bytesText`(0 → `0 KB`, 1536 → `2 KB`, 5·1024² → `5 MB`, 1.8·1024³ → `1.8 GB`).
- [ ] **Step 2~4:** `cd app && npm test && npx tsc --noEmit` 실패 → 구현 → 통과.
- [ ] **Step 5:** 설정 탭 화면 기록 아래 기록 폴더 줄(13번 값)과 [비우기] → 기존 지우기 확인 상자(`openConfirm`)를 25번 문구로. [비우기]는 `clear_recording`을 보내고 닫는다(못 보내면 둔다). 끊겼으면 버튼을 막는다. 권한 모드 행을 min-height 40, padding 2px 8px로. 큰 창 설정 탭도 같다. 설정 탭 다시 그리기 키(`formKey`)에 새 필드를 넣는다.
- [ ] **Step 6:** `npm test && npx tsc --noEmit && npm run build`. 수동 확인 행 더하고 커밋.

## Task 3: 실제 확인

- [ ] 앱을 띄워 설정 탭에서 경로·용량이 보이는지, [비우기] 뒤 용량이 줄고 screenpipe가 다시 뜨는지(로그 `screenpipe 시작`), 먼저 말 걸기가 계속 도는지 본다. 결과를 수동 확인 목록에 적고 커밋. 앱은 사용자가 쓰는 중이면 닫지 않는다.
