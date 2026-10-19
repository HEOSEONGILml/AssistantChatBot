# TamagotchiChatBot

Windows 화면 위를 돌아다니는 강아지와 타이핑으로 대화하는 데스크톱 펫이다. 강아지는 타이핑 도중 반응하고, 끼어들고, 먼저 말을 건다. 판단은 TypeSafe **Jev**의 분포와 우리 확률 모델이, 대사는 **Gemini**가 맡는다.

- 구조와 동작 원리: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- 작업 규칙: [`CLAUDE.md`](CLAUDE.md)
- 상태: 몸체 완료, 두뇌 v2(이벤트 단위 판단 + 확률 모델) 구현 완료, 실제 키로 수동 확인 중([체크리스트](docs/manual-checks/brain.md)). 대상은 개발자 본인과 팀 내부다(외부 배포 전).

## 구성

| 폴더 | 내용 | 스택 |
|---|---|---|
| `app/` | 화면: 강아지·집·말풍선·입력창·설정·트레이 | Tauri 2 (Rust + TypeScript, Vite) |
| `brain/` | 두뇌: 판단·대사·기억을 맡는 로컬 서비스 | Python, uv, WebSocket |
| `docs/` | 비전·스펙·결정 기록·프로토콜·체크리스트 | Markdown |

## 필요한 것

| 항목 | 확인한 버전 | 비고 |
|---|---|---|
| Windows | 10 Pro 19045 | 주 모니터만 지원 |
| WebView2 런타임 | | Windows 10/11에 보통 설치되어 있음 |
| Node.js / npm | 24.21 / 11.19 | 화면 빌드 |
| Rust (stable) / cargo | 1.99 | Tauri 셸. [Tauri 사전 요구사항](https://tauri.app/start/prerequisites/)의 MSVC 빌드 도구 포함 |
| [uv](https://docs.astral.sh/uv/) | 0.11 | 두뇌의 파이썬 버전과 의존성 관리 (Python 3.11 이상을 uv가 준비) |
| API 키 | | TypeSafe(Jev) 키, Gemini 키 각 1개. 앱 설정에서 넣는다 |

## 설치

```bash
git clone <이 저장소>
cd TamagotchiChatBot

# 두뇌 의존성 (brain/.venv 생성)
cd brain && uv sync && cd ..

# 화면 의존성
cd app && npm install && cd ..
```

두뇌 의존성: `typesafe-sdk`, `google-genai`, `websockets`, `keyring` (개발: `pytest`, `pytest-asyncio`). 화면 의존성: `@tauri-apps/api`와 플러그인(global-shortcut, store, opener), Vite, Vitest. 정확한 버전은 `brain/uv.lock`, `app/package-lock.json`, `app/src-tauri/Cargo.lock`.

## 실행

```bash
cd app
npm run tauri dev
```

- 앱이 두뇌(`brain/.venv`의 파이썬)를 자동으로 띄우고 접속한다. 두뇌를 따로 띄울 필요는 없다.
- **처음 실행하면** 강아지가 "설정에서 키를 넣어 주세요"라고 말한다. 트레이 아이콘 → 설정에서 TypeSafe 키와 Gemini 키를 넣고 저장한다. 키는 Windows 자격 증명 관리자에 저장된다.
- 끌 때는 트레이 아이콘 → 종료. 함께 띄운 두뇌도 꺼진다.
- 개발용 앱은 확인이 끝나면 바로 닫는다(개발 서버가 꺼지면 오류 창이 화면을 가릴 수 있다).

두뇌만 따로 띄우기(디버깅):

```bash
cd brain
uv run python -m brain
```

### 웹 버전 (프로토타입)

브라우저 페이지 안에서 강아지와 논다. 두뇌가 웹 페이지와 WebSocket을 함께 낸다([스펙](docs/superpowers/specs/2026-10-19-web-prototype-design.md), [0017](docs/decisions/0017-web-prototype-brain-serves-page.md)).

```bash
cd app && npm run build:web                       # app/dist-web/ 만들기 (화면 코드를 바꿨을 때만)
cd ../brain && uv run python -m brain.web         # http://127.0.0.1:8787/ 을 브라우저로 연다
```

- 키는 PC 앱과 같은 Windows 자격 증명 관리자에서 읽는다. 없으면 페이지의 톱니바퀴 → 설정에서 넣거나, 서버라면 환경 변수 `TYPESAFE_API_KEY`·`GEMINI_API_KEY`로 준다.
- 웹 강아지는 PC 강아지와 다른 강아지다(데이터 `%APPDATA%\TamagotchiChatBot\brain\web\`).
- `--host 0.0.0.0 --port 8787`로 열면 다른 기기에서도 접속한다. **주의**: 키가 두뇌에 있으므로 주소를 아는 사람은 누구나 그 키로 강아지와 대화한다. 프로토타입이라 사용자 구분이 없다.
- 끝낼 때는 두뇌 창에서 Ctrl+C.

### 사용법

| 하고 싶은 것 | 방법 |
|---|---|
| 말 걸기 | 집 옆 말풍선 아이콘 또는 `Ctrl+Shift+Space` → 입력 → Enter. 입력창은 Esc나 아이콘으로 닫을 때까지 열려 있다 |
| 강아지 집에 넣기/꺼내기 | 집 클릭, 트레이 메뉴, `Ctrl+Shift+H` |
| 쓰다듬기 / 찌르기 / 던지기 | 강아지 위에서 커서를 좌우로 문지르기 / 짧게 클릭 / 누른 채 끌어서 놓기 |
| 설정 | 집 옆 톱니바퀴 아이콘 또는 트레이 메뉴. **상태** 탭에서 기분·성격·친밀도 수치를, **로그** 탭에서 강아지가 왜 그렇게 행동했는지(판단마다 Jev 분포·보정·결과)를 본다 |

## 테스트

```bash
cd brain && uv run pytest              # 두뇌
cd app && npm test                     # 화면 순수 로직 (Vitest)
cd app && npx tsc --noEmit             # 타입 검사
cd app/src-tauri && cargo test         # Rust 셸
```

강아지 행동 빈도(끼어들기·먼저 말 걸기 등)를 맞추는 시뮬레이션:

```bash
cd brain
uv run python -m sim.record            # 실제 Jev 응답 녹화 (질문 문구·Jev 버전을 바꿨을 때, 키 필요)
uv run python -m sim.simulate --fit    # 녹화본으로 보정값 맞추고 지표 보고
```

창·Win32·실제 키가 필요한 동작은 [`docs/manual-checks/`](docs/manual-checks/)의 체크리스트로 확인한다.

## 설치 파일 만들기

```bash
cd app
npm run tauri build
```

결과: `app/src-tauri/target/release/bundle/nsis/*-setup.exe`, `bundle/msi/*.msi`. 지금은 두뇌를 저장소의 `brain/.venv`에서 띄우므로, 설치 파일만으로는 두뇌가 뜨지 않는다(두뇌 묶음 배포는 아직 범위 밖).

## 데이터 위치

| 무엇 | 위치 |
|---|---|
| 이벤트 기록·강아지 상태 | `%APPDATA%\TamagotchiChatBot\brain\brain.db` |
| 두뇌 로그 | `%APPDATA%\TamagotchiChatBot\brain\logs\brain.log` |
| 두뇌 접속 정보 | `%APPDATA%\TamagotchiChatBot\brain\brain.json` |
| API 키 | Windows 자격 증명 관리자 (`TamagotchiChatBot.brain`) |
| 화면 설정 | `%APPDATA%\com.tamagotchi.app\settings.json` |
| 웹 버전 두뇌 데이터 | `%APPDATA%\TamagotchiChatBot\brain\web\` (웹 화면 설정은 브라우저 localStorage) |

대화(이벤트) 기록은 설정의 "대화 기록 전체 삭제"로 지운다. Jev·Gemini 호출 때 타이핑 중인 글과 최근 기록이 각 업체로 전송된다([0006](docs/decisions/0006-user-provided-api-keys.md)).

## 문제가 생기면

| 증상 | 확인 |
|---|---|
| 설정의 AI 상태가 "두뇌에 연결되지 않음" | `brain/`에서 `uv sync`를 했는지, `brain.log`에 오류가 있는지 |
| "키를 확인해 주세요" | 설정에서 키를 다시 넣는다 |
| 강아지가 둘 보임 | 예전에 설치한 앱이 같이 켜져 있다. 트레이에서 하나를 끈다 |
| 앱을 강제로 끈 뒤 python 프로세스가 남음 | 다음 실행 때 그대로 다시 쓴다. 필요하면 작업 관리자에서 끈다 |

## 출처

강아지 스프라이트: [Benvictus – Pixel Dogs](https://benvictus.itch.io/pixel-dogs) ([`app/public/sprites/dog/LICENSE.md`](app/public/sprites/dog/LICENSE.md)).
