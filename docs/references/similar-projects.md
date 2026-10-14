# 비슷한 프로젝트

## mochi-llm-pet

- 저장소: https://github.com/NatBrian/mochi-llm-pet (사용자 제보, 2026-10-14)
- 확인 범위: README와 파일 목록만 봤다. 소스 코드는 보지 않았다.

**요약**: Windows 바탕화면 위를 돌아다니는 픽셀 고양이. Python + PyQt6. 항상 위에 뜨는 투명 창(오버레이)만 쓰고 아이콘 뒤 레이어는 쓰지 않는다. LLM 백엔드는 Ollama(기본), Gemini, OpenAI, Anthropic 등.

**구조**

```
Sensors (ms, Win32) → WorldState → [trigger] → 멀티모달 LLM 1회 → JSON intent → Body + Render(60fps)
                          ↑
                    Memory (SQLite)
```

**참고할 점**

| 항목 | mochi-llm-pet | 우리 설계와의 관계 |
|---|---|---|
| LLM 호출 시점 | heartbeat + 실제 변화(앱 전환, 클립보드, 유휴 전환) | 우리 "고정 주기 + 이벤트"와 같은 구조 |
| 반응 속도 | 쓰다듬기·잡기 같은 직접 조작은 LLM을 거치지 않음. 렌더 루프는 LLM을 기다리지 않음 | 우리 "감정·행동 먼저, 대사는 나중"과 같은 원칙 |
| 모델 출력 | 행동만 정한다(verb, target, emotion, emote, say, thought). 좌표·저장은 코드가 한다. `say`는 null이 보통 | 우리 무응답(1발화 0답변)과 같은 발상. 우리는 판단을 Jev가 한다 |
| 애니메이션 | 스프라이트 manifest(`assets/anim_manifest.yaml`) + Aseprite 변환 도구 | 몸체 단계에서 참고 |
| 기억·상태 | SQLite. 사용자 사실 기억과 펫 상태(energy, mood, bond, level) | 우리는 장기 기억·상태 시스템을 나중으로 미뤘다 |
| 실패 대비 | LLM에 닿지 않으면 규칙 기반 행동으로 대체 | 우리 "강아지는 멈추지 않는다" 원칙과 같다 |
| 개인정보 | 클라우드 LLM에 스크린샷과 창 제목을 보낸다 | 우리는 스크린샷을 보내지 않는다 |

README에 없는 것: 창 구현 방식(Win32 API 이름), DPI 처리, 가림 판정, 호출 주기 값. 필요하면 소스 코드를 본다.
