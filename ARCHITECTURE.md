# ARCHITECTURE

TamagotchiChatBot의 구조와 동작 원리다. 지금 코드가 **어떻게 동작하는지**만 적는다.

> 기준: 브랜치 `feat/assistant`, 프로토콜 v5. 프로젝트를 조수로 바꾸면서 다마고치 기능을 모두 지웠다 ([0022](docs/decisions/0022-pivot-to-assistant.md)). 지금은 화면 ↔ 백엔드 **껍데기**만 있다. 조수 설계가 끝나면 이 문서를 다시 쓴다.

## 1. 한눈에 보기

```mermaid
flowchart LR
  U["사용자"] -->|"단축키, 입력"| IN["입력창"]
  U -->|"트레이 → 설정"| SET["설정 창<br>단축키·키"]
  IN -->|"input-sent"| MAIN["주 창 (보이지 않음)<br>백엔드 연결"]
  SET <-->|"brain-set-key, brain-status"| MAIN
  MAIN <-->|"WebSocket v5"| B["백엔드"]
  B --> K[("OS 자격 저장소<br>API 키")]
```

- 화면(Tauri 앱, `app/`)과 백엔드(`brain/`)는 localhost WebSocket으로 통신한다. 규약은 [프로토콜](docs/brain-protocol.md)이다.
- 백엔드는 화면을 모른다 ([0022](docs/decisions/0022-pivot-to-assistant.md)).
- 백엔드는 지금 키 상태만 알리고, 받은 요청은 처리하지 않는다.

## 2. 화면 (`app/`)

| 창 | 파일 | 하는 일 |
|---|---|---|
| 주 창 `main` | `index.html`, `src/main.ts` | 보이지 않는다. 백엔드 연결을 들고, 입력창·설정 창과 백엔드 사이를 잇는다. 입력창 단축키를 등록한다 |
| 입력창 `input` | `input.html`, `src/input.ts` | 단축키(기본 `Ctrl+Shift+Space`)로 화면 가운데에 열고 닫는다. Enter로 보낸다 |
| 설정 창 `settings` | `settings.html`, `src/settings-page.ts` | 트레이 메뉴로 연다. 단축키와 API 키를 저장한다 |

- `src/brain-link.ts`: 백엔드에 접속한다. 끊기거나 접속하지 못하면 2초 뒤 백엔드를 띄우고(이미 떠 있으면 그대로) 다시 접속한다.
- `src/shared/brain-protocol.ts`: 프로토콜 메시지 해석과 생성.
- `src/shared/settings.ts`: 화면 설정(단축키) 저장. 저장본에 예전 설정이 있어도 지금 쓰는 값만 꺼낸다.
- `src-tauri/src/brain.rs`: 접속 정보 파일 읽기, 개발 환경에서 `brain/.venv`의 파이썬으로 백엔드 띄우기, 앱이 끝날 때 함께 끄기.
- `src-tauri/src/lib.rs`: 트레이(설정, 종료)와 창 관리.
- `public/sprites/dog/`: 강아지 스프라이트. 지금은 쓰는 코드가 없다. 강아지가 화면 한 자리에 있다는 컨셉([vision](docs/vision.md))에 따라 둔다.

## 3. 백엔드 (`brain/`)

| 파일 | 하는 일 |
|---|---|
| `brain/__main__.py` | 실행 진입점. 이미 떠 있는 백엔드가 있으면 끝낸다. 빈 포트에서 WebSocket을 열고 `brain.json`에 포트·토큰을 쓴다 |
| `brain/server.py` | 전송 계층. `hello` 인증, 화면 교체, 메시지 분배 |
| `brain/core.py` | 서비스 핵심. 키가 모두 있으면 `ok`, 아니면 `no_keys`를 알린다. `message`는 받기만 한다 |
| `brain/config.py` | 데이터 폴더와 API 키를 읽는 유일한 곳 (CLAUDE.md 3절). 키는 Windows 자격 증명 관리자에 둔다 |

## 4. 저장과 실행

| 무엇 | 위치 |
|---|---|
| 백엔드 로그 | `%APPDATA%\TamagotchiChatBot\brain\logs\brain.log` |
| 백엔드 접속 정보 | `%APPDATA%\TamagotchiChatBot\brain\brain.json` |
| API 키 | Windows 자격 증명 관리자 (`TamagotchiChatBot.brain`) |
| 화면 설정 | `%APPDATA%\com.tamagotchi.app\settings.json` |

## 5. 문서 지도

| 문서 | 내용 |
|---|---|
| [`docs/vision.md`](docs/vision.md) | 제품 비전. 사용자가 말하거나 확인한 것만 적는다 |
| [`docs/glossary.md`](docs/glossary.md) | 용어집 |
| [`docs/brain-protocol.md`](docs/brain-protocol.md) | 화면 ↔ 백엔드 프로토콜 |
| [`docs/decisions/`](docs/decisions/) | 결정 기록. 결정 하나에 파일 하나 |
| [`docs/design/`](docs/design/) | 디자인 요청서와 결과. [출력 계층 요청서](docs/design/2026-10-21-output-ui-brief.md), [출력 계층 화면 디자인](docs/design/2026-10-21-output-ui/README.md) |
| [`docs/spikes/`](docs/spikes/) | 기술 확인 시험. [Agent SDK로 띄운 Claude Code의 크롬 조작·질문·권한](docs/spikes/2026-10-21-agent-sdk-claude-code.md) |
| [`docs/references/similar-products.md`](docs/references/similar-products.md) | 비슷한 제품 조사: 실행 쪽(UFO², Cowork, 브라우저 에이전트)과 기억 쪽(screenpipe, Recall) |
| [`docs/references/typesafe-jev.md`](docs/references/typesafe-jev.md) | Jev API 요약. Jev를 다시 쓰게 되면 본다 |
| `docs/superpowers/specs/`, `plans/` | 조수 설계 스펙과 구현 계획 (아직 없음) |

다마고치 시절의 스펙·계획·실측·검수 기록은 지웠다. git 기록 `4b8c747`에 있다.

## 6. 결정 기록

| 번호 | 제목 | 상태 |
|---|---|---|
| [0022](docs/decisions/0022-pivot-to-assistant.md) | 다마고치를 접고 브라우저를 조작하는 조수로 바꾼다 | 채택 |
| [0023](docs/decisions/0023-claude-code-first-then-own-agent.md) | 에이전트는 Claude Code로 먼저, 나중에 직접 설계한 에이전트로 | 채택 |
| [0024](docs/decisions/0024-observation-common-plus-enrichment.md) | 지금 상황은 공통 관찰 + 프로그램별 선택적 강화 | 채택 |
| [0025](docs/decisions/0025-own-scheduler.md) | 스케줄 작업은 직접 구현한다 | 채택 |
| [0026](docs/decisions/0026-input-layer-passes-request-only.md) | 입력 계층은 요청만 넘기고, 맥락은 에이전트가 화면 기록에서 찾는다 | 채택 |
| [0027](docs/decisions/0027-data-layer-ownership.md) | 데이터 계층: 데이터마다 저장소·쓰기·읽기·관리 주체 | 채택 |
| [0028](docs/decisions/0028-output-layer-is-ui.md) | 출력 계층은 사용자 인터페이스만, 행동은 백엔드 | 채택 |
| [0029](docs/decisions/0029-claude-code-harness-and-session-per-task.md) | Claude Code는 하네스 문서로 동작 원칙을 받고, 작업 하나에 세션 하나 | 채택 |
| [0030](docs/decisions/0030-io-interface-task-as-conversation.md) | 입출력 인터페이스: 작업 하나를 대화 하나로 | 채택 (구현 전) |
| [0031](docs/decisions/0031-retrieval-by-agent-tool-search.md) | 에이전트는 데이터 계층을 검색 도구로 직접 찾아본다 (의미 검색은 나중에) | 채택 |

0001~0021은 다마고치 시절 기록이라 지웠다. 아직 유효한 원칙은 0022에 옮겼고, 원문은 git 기록 `4b8c747`에 있다.
