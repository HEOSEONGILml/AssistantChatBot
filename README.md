# TamagotchiChatBot

사용자의 화면 히스토리를 파악해서, 작업 맥락을 일일이 설명하지 않아도 하고자 하는 일을 알아듣고 처리하는 computer-use 에이전트다. 화면 한 자리에 강아지 모습으로 있다 ([vision](docs/vision.md)).

- 상태: 다마고치에서 조수로 바꾸는 중이다 ([0022](docs/decisions/0022-pivot-to-assistant.md)). 지금은 화면 ↔ 백엔드 껍데기만 있고, 조수 기능은 설계 전이다.
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

## 설치

```bash
git clone <이 저장소>
cd TamagotchiChatBot
cd backend && uv sync && cd ..      # 백엔드 의존성 (backend/.venv)
cd app && npm install && cd ..    # 화면 의존성
```

백엔드 의존성: `websockets`, `keyring` (개발: `pytest`, `pytest-asyncio`). 화면 의존성: `@tauri-apps/api`와 플러그인(global-shortcut, store, opener), Vite, Vitest. 정확한 버전은 `backend/uv.lock`, `app/package-lock.json`, `app/src-tauri/Cargo.lock`.

## 실행

```bash
cd app
npm run tauri dev
```

- 앱이 백엔드를 자동으로 띄우고 접속한다. 보이는 창은 없고 트레이 아이콘만 생긴다.
- `Ctrl+Shift+Space`로 입력창을 연다. 보낸 요청은 아직 백엔드가 처리하지 않는다.
- 트레이 아이콘 → 설정에서 단축키와 API 키를 넣는다. 키는 Windows 자격 증명 관리자에 저장된다.
- 끌 때는 트레이 아이콘 → 종료. 함께 띄운 백엔드도 꺼진다.
- 개발용 앱은 확인이 끝나면 바로 닫는다.

백엔드만 따로 띄우기: `cd backend && uv run python -m backend`

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
