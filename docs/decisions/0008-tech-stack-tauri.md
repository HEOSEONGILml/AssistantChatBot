# 0008. Windows 앱은 Tauri(Rust + TypeScript)로 만든다

- 상태: 채택
- 날짜: 2026-10-14

## 배경

Windows 앱이 풀어야 할 기술 과제는 다음과 같다.

1. 투명하고 항상 위에 떠 있는 창, 클릭 통과 (오버레이 모드)
2. 바탕화면 아이콘 뒤 레이어(WorkerW)에 창 붙이기 (배경 모드). 어떤 프레임워크도 기본 제공하지 않아 Win32를 직접 호출해야 한다.
3. 배경 모드에서 클릭 감지. 전역 마우스 훅이 필요하다.
4. 전역 단축키
5. 캐릭터 애니메이션과 말풍선 UI

## 결정

**Tauri**로 만든다. Rust 셸이 창과 Win32를 맡고, TypeScript 프론트엔드가 UI와 판단·대사 로직을 맡는다. 사용자가 선택한 사항이다.

## 검토한 대안

| 대안 | 장점 | 단점 | 채택하지 않은 이유 |
|---|---|---|---|
| Electron | TypeScript 하나로 개발. 데스크톱 펫 예제가 많다 | Chromium 포함으로 무겁다. Win32 호출에 네이티브 애드온 필요 | 항상 켜 두는 앱에 무겁고, 2·3번이 번거롭다 |
| PySide6 (Python + Qt) | 사내 주력 언어. 용인FC Jev 연동·평가 자산 재사용. ctypes로 Win32 호출 쉬움 | Jev 응답의 정적 타입 추론이 없다. 애니메이션 표현력이 웹보다 약하다 | 타입 안전성과 UI 표현력에서 Tauri가 낫다 |

## 근거 (Context7로 확인한 공식 문서, 2026-10-14)

- Tauri: 투명 창, `setAlwaysOnTop`, `setIgnoreCursorEvents`(클릭 통과), global-shortcut 플러그인을 지원한다. `setAlwaysOnTop`과 `setIgnoreCursorEvents`는 기본 권한에 없어서 capability에 따로 허용해야 한다.
- Tauri HTTP 플러그인(`@tauri-apps/plugin-http`): 프론트엔드에서 Rust를 거쳐 요청을 보내므로 CORS 제약이 없다. 허용할 URL을 capability scope에 적어야 한다.
- Jev TypeScript SDK(`TypeSafeClient`):
  - `fetch` 옵션으로 HTTP 구현을 바꿀 수 있다. Tauri HTTP 플러그인의 `fetch`를 넘긴다.
  - 브라우저 환경에서는 `dangerouslyAllowBrowser: true`가 필요하다. 사용자 본인 PC에서 본인 키를 쓰므로([0006](0006-user-provided-api-keys.md)) 허용한다.
  - `timeout`(기본 10초), `retry`, 요청 취소를 지원한다. 타이핑 중 이전 요청을 취소하는 데 쓴다.
  - `systemOne`의 응답 타입이 질문 정의로부터 추론된다.

## 결과

- 배경 모드(2번)와 클릭 감지(3번)는 Rust에서 `windows` 크레이트로 구현한다. Windows 버전마다 바탕화면 창 구조가 다를 수 있으므로, **구현 첫 단계에서 이 PC로 스파이크를 해서 가능 여부를 확인한다.**
- Gemini 호출도 프론트엔드에서 Tauri HTTP 플러그인을 거친다. SDK 사용법은 구현 전에 Context7로 확인한다.
- 개발 환경에 Rust 툴체인, Node.js, WebView2가 필요하다.
- 사내 Python 자산(용인FC 평가 스크립트 등)은 코드 재사용이 아니라 방식 참고로만 쓴다.
