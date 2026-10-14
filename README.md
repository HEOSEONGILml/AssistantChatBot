# TamagotchiChatBot

PC·모바일 배경화면에 사는 캐릭터(예: 강아지)와 대화하는 서비스.
사용자가 타이핑으로 말을 걸고, 캐릭터도 스스로 말을 건다.
**TypeSafe Jev**가 타이핑 도중의 반응, 끼어들기, 먼저 말 걸 시점을 실시간으로 결정한다.

> 상태: 설계 단계. 아직 코드가 없다.

## 문서 지도

모든 작업은 문서가 먼저다. 작업 규칙은 [`CLAUDE.md`](CLAUDE.md)를 본다.

| 문서 | 내용 |
|---|---|
| [`docs/vision.md`](docs/vision.md) | 제품 컨셉. 확정된 것과 미정인 것을 구분해 누적한다 |
| [`docs/glossary.md`](docs/glossary.md) | 용어 정의 (Jev, state, 끼어들기, 선발화 등) |
| [`docs/decisions/`](docs/decisions/) | 결정 기록(ADR). 결정 하나에 파일 하나 |
| [`docs/references/typesafe-jev.md`](docs/references/typesafe-jev.md) | Jev API 요약과 사내 사용 사례 |
| [`docs/references/similar-projects.md`](docs/references/similar-projects.md) | 비슷한 프로젝트 조사 (mochi-llm-pet) |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | 설계 스펙. 현재: [Windows 첫 버전](docs/superpowers/specs/2026-10-14-windows-desktop-pet-design.md) |
| [`docs/superpowers/plans/`](docs/superpowers/plans/) | 스펙별 구현 계획 |
| [`docs/spikes/`](docs/spikes/) | 스파이크(기술 검증) 결과. [배경 모드](docs/spikes/background-mode.md) |

## 결정 기록

| 번호 | 제목 | 상태 |
|---|---|---|
| [0001](docs/decisions/0001-jev-as-decision-engine.md) | 실시간 반응 결정에 Jev를 쓴다 | 채택 |
| [0002](docs/decisions/0002-platform-order.md) | Windows PC 먼저, Android는 그다음 | 채택 |
| [0003](docs/decisions/0003-windows-display-modes.md) | Windows 배경·오버레이 모드 모두 지원, 설정으로 고정 | 채택 |
| [0004](docs/decisions/0004-input-box-trigger.md) | 캐릭터 클릭·전역 단축키로 입력창, 상시 표시는 설정 | 채택 |
| [0005](docs/decisions/0005-local-history-storage.md) | 대화 기록은 PC에 저장 (서버 중계 부분은 0006으로 대체) | 일부 대체됨 |
| [0006](docs/decisions/0006-user-provided-api-keys.md) | 서버 없이 사용자가 입력한 API 키로 직접 호출 | 채택 |
| [0007](docs/decisions/0007-dialogue-llm.md) | 캐릭터 대사는 gemini-3.1-flash-lite로 생성 | 채택 |
| [0008](docs/decisions/0008-tech-stack-tauri.md) | Windows 앱은 Tauri(Rust + TypeScript) | 채택 |
