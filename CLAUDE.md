# CLAUDE.md

이 프로젝트에서 작업할 때 지키는 규칙이다. 시스템 구조·문서 지도·결정 기록 표는 [`ARCHITECTURE.md`](ARCHITECTURE.md), 설치·실행은 [`README.md`](README.md)에 있다.

## 1. 문서 선행 (최우선 규칙)

- 코드보다 문서를 먼저 쓴다. 기능에 착수하기 전에 스펙(`docs/superpowers/specs/`)이나 결정 기록(`docs/decisions/`)이 있어야 한다.
- 코드를 바꾸면 관련 문서도 **같은 커밋에서** 갱신한다. 문서와 코드가 어긋난 상태로 커밋하지 않는다.
- 사용자가 제품 컨셉을 새로 알려주면 `docs/vision.md`에 바로 반영한다. 사용자가 말한 것과 추측한 것을 구분해 적는다.
- 새 용어가 생기면 `docs/glossary.md`에 추가한다.
- 문서를 추가·삭제하면 `ARCHITECTURE.md`의 문서 지도와 결정 기록 표도 갱신한다. 구조나 동작 원리가 바뀌면 `ARCHITECTURE.md` 본문도 같은 커밋에서 고친다. 설치·의존성·실행 방법이 바뀌면 `README.md`를 고친다.

## 2. 작업 순서

1. **vision 갱신**: 새로 알게 된 컨셉을 `docs/vision.md`에 반영
2. **설계**: brainstorming으로 설계를 합의하고 `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` 작성
3. **결정 기록**: 되돌리기 어렵거나 대안이 있었던 선택은 `docs/decisions/NNNN-<slug>.md`로 남긴다 (`0000-template.md` 참고)
4. **계획**: `docs/superpowers/plans/`에 구현 계획 작성
5. **구현**: TDD. 테스트를 먼저 쓴다
6. **문서 동기화**: 구현 중 바뀐 내용을 스펙·아키텍처 문서에 반영

각 단계는 사용자 승인 후 다음으로 넘어간다. 사용자는 큰 그림을 조금씩 공개하므로, 공개되지 않은 부분을 추측해서 설계에 넣지 않는다. 필요하면 질문한다.

## 3. 코드 원칙

- **단순성**: 지금 필요한 코드만 쓴다. "혹시 몰라서" 넣는 매개변수·추상화·설정은 만들지 않는다.
- **설정 중앙화**: API 키와 환경 변수는 설정 모듈 한 곳에서만 읽는다. 비즈니스 로직에서 환경 변수를 직접 읽지 않는다.
- **외부 호출 격리**: Jev, LLM 등 외부 AI 호출은 클라이언트 계층을 거친다. 실패 시 fallback 동작을 정하고 실패를 기록한다.
- **행동의 지역성**: 함수 하나만 감싸는 얇은 래퍼 모듈을 만들지 않는다.

화면은 Tauri(Rust + TypeScript)다. 앱은 `app/`에 있다. 백엔드는 파이썬이고 화면과 독립되어 있으며 `backend/`에 있다 ([0022](docs/decisions/0022-pivot-to-assistant.md)). 화면 ↔ 백엔드 규약은 [`docs/backend-protocol.md`](docs/backend-protocol.md)다.

| 작업 | 명령 (`app/`에서) |
|---|---|
| 개발 실행 | `npm run tauri dev` |
| 프론트엔드 테스트 | `npm test` |
| Rust 테스트 | `cd src-tauri && cargo test` |
| 백엔드 준비 (처음 한 번, 의존성 바뀔 때) | `cd ../backend && uv sync` |
| 백엔드 테스트 | `cd ../backend && uv run pytest` |
| 설치 파일 빌드 | `npm run tauri build` → `src-tauri/target/release/bundle/nsis/*-setup.exe`, `bundle/msi/*.msi` |

**개발용 앱(`npm run tauri dev`)은 확인이 끝나면 바로 닫는다.** 개발 서버가 꺼지면 앱 창이 오류 페이지를 띄운 채 남아 사용자 화면을 가릴 수 있다 (2026-10-14 사고).

화면과 분리된 순수 로직(`src/shared/*.ts`)과 백엔드(`backend/backend/*.py`)는 단위 테스트한다. 창·Win32·실제 브라우저에 의존하는 동작은 `docs/manual-checks/`에 체크리스트를 만들어 확인한다.

## 4. Jev 사용 규칙

- 지금은 Jev를 쓰지 않는다 ([0022](docs/decisions/0022-pivot-to-assistant.md)). 필요하다고 판단되면 결정 기록을 남기고 쓴다.
- 쓰게 되면: Jev는 판단의 분포만 준다(선택·점수·예/아니오의 확률). 텍스트 생성은 Jev의 역할이 아니다.
- 질문 정의(`instructions`, `criteria`)는 코드에 흩뿌리지 않고 한곳에서 관리한다. 임계값은 **근거와 함께** 문서에 기록하고, 잠정값이면 잠정값이라고 적는다.
- API 상세와 사내 사용 사례는 `docs/references/typesafe-jev.md`를 본다.

## 5. 도구 사용

- **superpowers**: 설계는 `brainstorming`, 계획은 `writing-plans`, 구현은 `test-driven-development`, 완료 선언 전에는 `verification-before-completion`을 쓴다.
- **Context7**: 라이브러리·프레임워크 API를 쓰기 전에 Context7로 최신 문서를 확인한다. 기억에 의존해 API를 쓰지 않는다. 스택을 고를 때도 후보 라이브러리 문서를 Context7로 확인한다.
- **serena**: 코드가 생긴 뒤에는 심볼 단위 탐색·편집에 serena를 쓴다.
- **chrome-devtools**: 웹 기반 UI는 실제 브라우저에서 동작을 확인한다.

## 6. 문서 작성 스타일

- 한국어로 쓴다. 문장은 짧게, 결론부터 쓴다.
- 흐름과 구조는 mermaid 다이어그램으로 그린다.
- 수치(임계값, 지연 시간, 비용)에는 출처나 근거를 붙인다.
