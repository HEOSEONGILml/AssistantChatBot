# TamagotchiChatBot

사용자의 화면 히스토리를 파악해서, 작업 맥락을 일일이 설명하지 않아도 하고자 하는 일을 알아듣고 처리하는 computer-use 에이전트다. 화면 한 자리에 강아지 모습으로 있다 ([vision](docs/vision.md)).

- 상태: 다마고치에서 조수로 바꾸는 중이다 ([0022](docs/decisions/0022-pivot-to-assistant.md)). 백엔드는 [조수 1단계 스펙](docs/superpowers/specs/2026-10-21-assistant-phase1-design.md)대로 만들었다(작업·대화·스케줄, Claude Code 세션, 프로토콜 v6). 화면(`app/`)은 아직 v5라 **백엔드에 접속하지 못한다**. 화면 계획에서 v6으로 바꾼다.
- 구조: [`ARCHITECTURE.md`](ARCHITECTURE.md), 작업 규칙: [`CLAUDE.md`](CLAUDE.md)

## 구성

| 폴더 | 내용 | 스택 |
|---|---|---|
| `app/` | 화면: 입력창·설정 창·트레이 | Tauri 2 (Rust + TypeScript, Vite) |
| `backend/` | 백엔드: PC 안에서 도는 파이썬 프로세스 | Python, uv, WebSocket |
| `docs/` | 비전·결정 기록·프로토콜 | Markdown |

## 필요한 것

| 항목 | 확인한 버전 | 비고 |
|---|---|---|
| Windows | 10 Pro 19045 | |
| WebView2 런타임 | | Windows 10/11에 보통 설치되어 있음 |
| Node.js / npm | 24.21 / 11.19 | 화면 빌드 |
| Rust (stable) / cargo | 1.99 | Tauri 셸. [Tauri 사전 요구사항](https://tauri.app/start/prerequisites/)의 MSVC 빌드 도구 포함 |
| [uv](https://docs.astral.sh/uv/) | 0.11 | 백엔드의 파이썬 버전과 의존성 관리 (Python 3.11 이상) |
| [Claude Code](https://docs.claude.com/en/docs/claude-code) (`claude` CLI) | 2.1.305 | 에이전트. PATH에서 `claude`를 찾을 수 있어야 한다 |
| Claude 구독 로그인 | | `claude auth login`으로 claude.ai 계정 로그인. API 키 로그인은 로그인 안 된 것으로 본다(과금되고 크롬 조작이 꺼진다) |
| Claude in Chrome 확장 | | 크롬에 설치하고 같은 계정으로 로그인. 에이전트가 크롬을 조작한다 |
| Node.js의 `npx` | 위 Node.js | screenpipe(`npx -y screenpipe record`)와 screenpipe MCP(`npx -y screenpipe-mcp@latest`)를 받아 띄운다. 처음 실행 때 내려받는다 |

## 설치

```bash
git clone <이 저장소>
cd TamagotchiChatBot
cd backend && uv sync && cd ..      # 백엔드 의존성 (backend/.venv)
cd app && npm install && cd ..    # 화면 의존성
```

백엔드 의존성: `claude-agent-sdk`, `websockets` (개발: `pytest`, `pytest-asyncio`). 화면 의존성: `@tauri-apps/api`와 플러그인(global-shortcut, store, opener), Vite, Vitest. 정확한 버전은 `backend/uv.lock`, `app/package-lock.json`, `app/src-tauri/Cargo.lock`.

## 실행

```bash
cd app
npm run tauri dev
```

- 앱이 백엔드를 자동으로 띄운다. 보이는 창은 없고 트레이 아이콘만 생긴다.
- 지금 앱은 프로토콜 v5라 v6 백엔드가 접속을 끊는다(닫힘 코드 4003). 입력창(`Ctrl+Shift+Space`)에서 보낸 요청은 처리되지 않는다. 화면 계획에서 고친다.
- 끌 때는 트레이 아이콘 → 종료. 함께 띄운 백엔드도 꺼진다.
- 개발용 앱은 확인이 끝나면 바로 닫는다.

백엔드만 따로 띄우기: `cd backend && uv run python -m backend`

- 띄우면 screenpipe가 떠 있지 않을 때 `npx -y screenpipe record`로 화면 기록을 시작한다. 백엔드가 끝나면 함께 끈다. 강제로 죽이면(작업 관리자 등) screenpipe가 남을 수 있으니 `taskkill /IM screenpipe.exe /F`로 끈다.
- 스케줄러가 1분마다 돈다. 로그는 `%APPDATA%\TamagotchiChatBot\backend\logs\backend.log`.
- 실제 Claude Code로만 확인할 수 있는 것은 [수동 확인 목록](docs/manual-checks/backend.md)에 있다.

## 테스트

```bash
cd backend && uv run pytest              # 백엔드
cd app && npm test                     # 화면 순수 로직 (Vitest)
cd app && npx tsc --noEmit             # 타입 검사
cd app/src-tauri && cargo test         # Rust 셸
```

## 데이터 위치

[`ARCHITECTURE.md` 4절](ARCHITECTURE.md#4-저장과-실행)을 본다.

## 출처

강아지 스프라이트: [Benvictus – Pixel Dogs](https://benvictus.itch.io/pixel-dogs) ([`app/public/sprites/dog/LICENSE.md`](app/public/sprites/dog/LICENSE.md)).
