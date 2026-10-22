# 백엔드 수동 확인

자동 시험은 Claude Code·screenpipe를 가짜로 바꿔 돈다. 아래는 실제 프로그램으로만 확인할 수 있다. 앞의 다섯 줄은 [조수 1단계 스펙](../superpowers/specs/2026-10-21-assistant-phase1-design.md) 8절 "시험하지 않은 것"이다. 안 되는 것은 스펙으로 돌아가 사용자와 정한다.

## 준비

- [README](../../README.md)의 "필요한 것"을 갖춘다: Claude Code, 구독 로그인, Claude in Chrome 확장, Node.js(`npx`).
- 화면 앱으로 확인해도 되지만([화면 수동 확인](frontend.md)), 메시지를 직접 보고 싶으면 백엔드만 띄우고(`cd backend && uv run python -m backend`), `backend.json`의 포트·토큰으로 WebSocket 클라이언트를 붙여 v7 메시지를 직접 보낸다 ([프로토콜](../backend-protocol.md)).
- 로그: `%APPDATA%\TamagotchiChatBot\backend\logs\backend.log`. 작업 기록: 같은 폴더의 `assistant.db`.

```mermaid
flowchart LR
  T["확인하는 사람<br>(WebSocket 클라이언트)"] -->|"hello v7, request, say ..."| B["백엔드"]
  B --> CC["Claude Code + 크롬"]
  B --> SP["screenpipe"]
  B --> L[("backend.log<br>assistant.db")]
```

## 확인 목록

| # | 무엇 | 어떻게 | 기대 | 결과 |
|---|---|---|---|---|
| 1 | 일하는 도중 덧붙이기(`say`) | 오래 걸리는 `request`를 보내고, 질문이 없는 동안 같은 `session_id`로 `say`를 보낸다 | 덧붙인 말이 세션에 들어가 에이전트가 반영한다. `entry {kind: user}`가 쌓이고 세션은 `working` 그대로 | [ ] |
| 2 | 여러 작업이 크롬 하나를 함께 쓰기 | 크롬을 쓰는 `request` 두 개를 잇달아 보낸다 | 두 작업이 서로의 탭을 망가뜨리지 않고 끝난다. 안 되면 동시 작업 방식을 다시 정한다 | [ ] |
| 3 | 로그인 흐름 (`claude auth login`) | `claude auth logout` 뒤 백엔드에 붙어 `status {logged_in: false}`를 확인하고 `login`을 보낸다 | 브라우저가 열리고, 로그인을 마치면 `status {logged_in: true}`가 온다. 끝나지 않고 멈추면 시간 제한을 정한다 | [ ] |
| 4 | 사용량 이벤트(`RateLimitEvent`)가 오는 때와 종류 이름 | 작업을 몇 개 돌리며 `usage` 메시지와 로그를 본다 | 언제 오는지, `type`에 어떤 이름이 오는지(예: 5시간·주간) 적는다. 사용량 탭 디자인에 맞는지 본다 | [ ] |
| 5 | 스케줄 세션을 며칠에 걸쳐 `resume` | `add_schedule`(매일)로 만들고 며칠 둔다 | 날마다 같은 `claude_session_id`로 이어지고, `run` 구분선 뒤에 결과가 쌓인다. 앞날의 대화를 기억한다 | [ ] |
| 6 | screenpipe 켜고 끄기 | 백엔드를 띄웠다가 Ctrl+C로 끈다 | 로그에 `screenpipe 시작`, 끝날 때 `taskkill /T`로 `npx` 밑의 `node`·`screenpipe.exe`까지 모두 꺼진다(작업 관리자에서 확인). 이미 떠 있으면 `screenpipe가 이미 떠 있어 그대로 둔다`가 찍히고 끌 때 건드리지 않는다 | [ ] |
| 7 | 윈도에서 screenpipe MCP (`cmd /c npx`) | screenpipe 기록을 찾아야 하는 `request`를 보낸다 (예: "아까 보던 문서 이름 알려줘") | Claude Code가 screenpipe MCP를 띄워 도구를 쓴다. 실패하면 Claude Code의 MCP 오류를 확인한다 ([agent.py](../../backend/backend/agent.py)의 `SCREENPIPE`) | [ ] |
| 8 | 세션 도중 끄기 | 크롬을 쓰는 `request`를 보내 일하는 동안 백엔드를 Ctrl+C로 끈다 | `claude` 프로세스와 그 밑의 MCP 서버(`screenpipe-mcp`의 `node`)·크롬 연결 프로세스가 모두 꺼진다(작업 관리자에서 확인). 남으면 끌 때 세션을 끊는 길을 만든다 | [ ] |
| 9 | 로그인 중 끄기 | `login`을 보내 브라우저가 열린 채로 백엔드를 Ctrl+C로 끈다 | `claude auth login` 프로세스가 트리째 꺼진다 | [ ] |
| 10 | 로그아웃 뒤 로그인 | 로그인된 상태에서 `logout`을 보낸 뒤 `request`를 보내고, 이어 `login`을 보낸다 | `logout` 뒤 `status {logged_in: false}`가 오고 `claude auth status`도 로그아웃으로 나온다. `request`에는 `status {logged_in: false}`만 다시 온다. `login`으로 다시 로그인되면 `status {logged_in: true}` | [ ] |
| 11 | 화면 기록 끄기·켜기 | 백엔드가 띄운 screenpipe가 도는 중에 `set_recording {enabled: false}`, 이어 `{enabled: true}`를 보낸다. 끈 상태로 백엔드를 다시 띄워 본다 | 끄면 `screenpipe.exe`와 그 위의 `npx`·`node`가 작업 관리자에서 사라지고, 켜면 다시 생긴다. 매번 `settings {recording}`이 온다. 끈 채 다시 띄우면 로그에 `screenpipe 시작`이 찍히지 않는다 | [ ] |
| 12 | 대화 탭 세션 이어 쓰기 | 접속해 받은 대화 세션(`source: chat`)에 `say`를 두 번 보내고, 백엔드를 껐다 켠 뒤 또 `say`를 보낸다. 한 번은 "회의 자료 모아 줘"처럼 일을 맡긴다 | 같은 `claude_session_id`로 이어지고 앞 이야기를 기억한다. 일을 맡기면 새 작업이 생기고 대화에 `chip` 줄이 남는다. 그냥 묻는 말에는 새 작업 없이 대화에서 답한다 | [ ] |
| 13 | 지우기: 돌고 있는 세션 (`delete_session`) | 크롬을 쓰는 오래 걸리는 `request`를 보내 일하는 동안 `delete_session`을 보낸다 | 먼저 멈추고(`claude` 프로세스와 그 밑 MCP·크롬 연결이 사라진다) `session_deleted {session_id}`가 온다. 지운 뒤 늦게 오는 `entry`·`activity`는 오지 않는다. `assistant.db`에서 세션·대화 줄이 사라진다 | [ ] |
| 14 | 지우기: 답 기다리는 세션 | 질문하게 될 `request`(예: "결제 전에 물어봐 줘")를 보내 질문이 오면 `delete_session`을 보낸다 | 질문이 거부로 풀리고 세션이 끊긴 뒤 `session_deleted`가 온다. 백엔드가 멈추거나 오류를 남기지 않는다 | [ ] |
| 15 | 지우기: 스케줄 세션 | `add_schedule`로 만든 스케줄(돌고 있을 때 한 번, 꺼진 채 한 번)에 `delete_session`을 보낸다 | 세션·대화 줄·지시서(`schedules`)가 지워지고 `session_deleted`가 온다. 다음 `tick`에서 더는 실행되지 않는다 | [ ] |
| 16 | 지우기: 대화 세션 | 접속해 받은 대화 세션(`source: chat`)에 `say`로 대화를 쌓은 뒤 `delete_session`을 보낸다 | `session_deleted` 뒤에 새 대화 세션이 `session`으로 온다(제목 `대화`, 새 `session_id`). 이어서 `say`를 보내면 이전 대화를 모른다 | [ ] |
| 17 | `activity` 실제 이벤트 | 생각·글·도구(크롬·`WebSearch`·`Read`·`Bash`·`AskUserQuestion`)를 쓰게 하는 `request`를 보내며 `activity` 메시지를 본다 | [backend-protocol.md](../backend-protocol.md) 표의 `kind`·`text`로 오고, 같은 값이 연달아 가지 않으며, `AskUserQuestion`은 보내지 않는다. 실제 `StreamEvent` 모양이 문서와 다르면 매핑을 고친다. 서브에이전트(`Task`) 안의 도구가 `activity`를 바꾸는지 적어 둔다 | [ ] |
| 18 | 먼저 말 걸기: 실제 배지 | 화면 기록을 켜고 `set_jev_key`로 실제 Jev 키를 넣는다. 엑셀에서 `#REF!` 오류를 몇 분 동안 고치는 척하며 헤맨다 | 1~2분 안에 `nudge {active: true}`가 오고 로그에 `배지 켬 (need_help …, declined_same …)`이 찍힌다. 로그에 키·화면 글이 없다. 유튜브만 볼 때는 오지 않는다 | [ ] |
| 19 | 먼저 말 걸기: 5분 뒤 꺼짐 | 18번처럼 배지를 띄우고 누르지 않는다 | 5분~5분 30초 뒤 `nudge {active: false}`가 온다 | [ ] |
| 20 | 먼저 말 걸기: [도와줘]·[괜찮아] | 배지가 뜨면 `nudge_open`, `nudge_answer {help: true}`를 보낸다. 다음 배지에는 `nudge_answer {help: false}`를 보내고 같은 작업을 계속한다 | [도와줘]: 대화 세션에 `nudge`·`user(도와줘)` 줄 뒤 두세 문장의 `result`가 온다(숨은 지시 글은 줄에 없다). [괜찮아]: 같은 작업에서는 배지가 더 드물게 뜨고, 다른 작업으로 옮기면 다시 뜰 수 있다 | [ ] |
| 21 | 먼저 말 걸기: screenpipe DB가 잠김 | screenpipe가 기록하는 중에 판단이 돈다(18번과 함께) | `화면 기록 읽기 실패`가 가끔 찍혀도 고리는 계속 돌고 백엔드가 멈추지 않는다 | [ ] |

## 화면 계획에 넘기는 주의

- Tauri가 백엔드를 강제로 끄면(`backend.rs`의 `child.kill`) 파이썬의 정리 코드가 돌지 않는다. 그러면 백엔드가 띄운 screenpipe와 `claude` 세션 프로세스(그 밑의 MCP·크롬 연결까지)가 고아로 남는다. 화면 계획에서는 백엔드를 정상 종료시키거나(종료 신호 → 정리 대기), 그게 안 되면 프로세스 트리째(`taskkill /T`) 끈다.
  - 반영: 화면은 앱이 끝날 때 백엔드를 `taskkill /PID <pid> /T /F`로 트리째 끈다(`backend.rs`의 `stop`). 실제로 남는 것이 없는지는 [화면 수동 확인](frontend.md)에서 본다.

## 지금까지 본 것

- 2026-10-21, 6번 일부: `uv run python -m backend`로 띄우자 로그에 `screenpipe 시작`, `백엔드 시작: 포트 …`가 찍혔다. `cmd /c npx.CMD` → `node npx-cli.js` → `cmd /c screenpipe record` → `node cli.js` → `screenpipe.exe`로 뜨는 것을 보았다. 18초 안에는 `localhost:3030/health`가 응답하지 않았다(처음 실행이라 준비 중으로 보인다). 끄기는 `taskkill /T /F`로 프로세스 트리를 죽여서 확인했고, 정상 종료(Ctrl+C) 경로의 `Recorder.stop()`은 아직 보지 못했다.
