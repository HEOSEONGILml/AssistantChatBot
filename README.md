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
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | 기능별 설계 스펙 |
| [`docs/superpowers/plans/`](docs/superpowers/plans/) | 스펙별 구현 계획 |

## 결정 기록

| 번호 | 제목 | 상태 |
|---|---|---|
| [0001](docs/decisions/0001-jev-as-decision-engine.md) | 실시간 반응 결정에 Jev를 쓴다 | 채택 |
| [0002](docs/decisions/0002-platform-order.md) | Windows PC 먼저, Android는 그다음 | 채택 |
| [0003](docs/decisions/0003-windows-display-modes.md) | Windows 배경·오버레이 모드 모두 지원, 설정으로 고정 | 채택 |
| [0004](docs/decisions/0004-input-box-trigger.md) | 캐릭터 클릭·전역 단축키로 입력창, 상시 표시는 설정 | 채택 |
| [0005](docs/decisions/0005-local-history-storage.md) | 대화 기록은 PC에만 저장, 서버 없음 | 채택 |
