# TamagotchiChatBot

사용자의 화면 히스토리를 파악해서, 작업 맥락을 일일이 설명하지 않아도 하고자 하는 일을 알아듣고 처리하는 computer-use 에이전트다. 화면 한 자리에 강아지 모습으로 있다 ([vision](docs/vision.md)).

- 상태: 다마고치에서 조수로 바꾸는 중이다 ([0022](docs/decisions/0022-pivot-to-assistant.md)). 백엔드는 [조수 1단계 스펙](docs/superpowers/specs/2026-10-21-assistant-phase1-design.md)대로 만들었다(작업·대화·스케줄, Claude Code 세션, 프로토콜 v6). 화면(`app/`)은 [화면 계획](docs/superpowers/plans/2026-10-22-assistant-frontend.md)대로 v6으로 다시 만들었다: 오른쪽 아래의 강아지와 패널, 큰 창.
- 구조: [`ARCHITECTURE.md`](ARCHITECTURE.md), 작업 규칙: [`CLAUDE.md`](CLAUDE.md)

## 구성

| 폴더 | 내용 | 스택 |
|---|---|---|
| `app/` | 화면: 강아지와 패널(알림·대화·작업·스케줄·사용량·설정 탭), 큰 창(패널 전체를 넓게), 트레이 | Tauri 2 (Rust + TypeScript, Vite) |
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
| Node.js의 `npx` | 위 Node.js | screenpipe(`npx -y screenpipe record --retention-days 2 --retention-mode all --language korean --language english`)와 screenpipe MCP(`npx -y screenpipe-mcp@latest`)를 받아 띄운다. 처음 실행 때 내려받는다 |

## 설치

```bash
git clone <이 저장소>
cd TamagotchiChatBot
cd backend && uv sync && cd ..      # 백엔드 의존성 (backend/.venv)
cd app && npm install && cd ..    # 화면 의존성
```

백엔드 의존성: `claude-agent-sdk`, `websockets` (개발: `pytest`, `pytest-asyncio`). 화면 의존성: `@tauri-apps/api`, Vite, Vitest. 정확한 버전은 `backend/uv.lock`, `app/package-lock.json`, `app/src-tauri/Cargo.lock`.

## 실행

```bash
cd app
npm run tauri dev
```

- 앱이 백엔드를 자동으로 띄우고 프로토콜 v7로 붙는다. 화면 오른쪽 아래(작업 표시줄 위)에 강아지가 뜨고, 트레이 아이콘이 생긴다. 강아지는 끌어서 옮길 수 있고, 옮긴 자리는 다시 켜도 남는다. 붙기 전에는 패널 맨 위에 `백엔드에 연결하는 중…`이 보인다.
- 마우스로만 쓴다. 단축키·입력창·API 키 설정은 없다. 강아지를 누르면 패널이 열리고, 다시 누르면 닫힌다.
  - 일 맡기기: 작업 탭 → [+ 새 작업]. 또는 대화 탭에서 말한다.
  - 질문에 답하기: 알림 탭의 질문 카드나 작업 대화에서.
  - 스케줄: 스케줄 탭 → [+ 새 스케줄].
  - 로그인: 로그아웃이면 강아지가 자고, 패널을 열면 설정 탭이 보인다. [로그인]을 누르면 브라우저에서 `claude auth login`이 진행된다.
  - 패널의 "크게 보기"를 누르면 작은 패널이 닫히고 큰 창(패널 전체를 넓게)이 보던 화면 그대로 열린다.
- 끌 때는 트레이 아이콘 → 종료. 앱이 띄운 백엔드를 프로세스 트리째(`taskkill /T /F`) 끄므로 screenpipe·Claude Code도 함께 꺼진다.
- 개발용 앱은 확인이 끝나면 바로 닫는다.
- 실제 앱으로만 확인할 수 있는 것은 [화면 수동 확인 목록](docs/manual-checks/frontend.md)에 있다.

백엔드만 따로 띄우기: `cd backend && uv run python -m backend`

- 띄우면 screenpipe가 떠 있지 않을 때 `npx -y screenpipe record`로 화면 기록을 시작한다. 기록은 이틀만 두고 모두 지운다(`--retention-days 2 --retention-mode all`). OCR은 한국어·영어로 읽는다(`--language korean --language english`). 백엔드가 끝나면 함께 끈다. 강제로 죽이면(작업 관리자 등) screenpipe가 남을 수 있으니 `taskkill /IM screenpipe.exe /F`로 끈다.
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
