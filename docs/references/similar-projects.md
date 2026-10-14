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

### 움직임 구현 참고 (소스 확인, 2026-10-14)

`deskpet/body/body.py`, `executors.py`, `motion.py`, `brain/fallback.py`를 읽었다.

- 행동은 "의도(intent)" 단위다. 걷기는 목표 지점까지 가서 **멈추고**(`seek` → 도착하면 완료), 이후 감정에 맞는 대기 애니메이션을 보인다. 계속 순찰하지 않는다.
- 걷기 180px/s, 달리기 360px/s. 커서 따라가기는 스프링(지연 추종).
- 규칙 기반 두뇌(fallback): 에너지 낮음 → 낮잠, 사용자 3분 무입력 → 낮잠, 커서가 220px 이내 → 쫓기, 영상 재생 창 → 구경, 그 밖에는 활성 창 바라보기, 아무 일 없으면 대기.
- 같은 상태도 애니메이션 변형을 무작위로 고른다(`pick_variant`).
- 쓰다듬기(커서로 문지르기), 찌르기, 잡아 던지기 같은 반사 반응은 LLM을 거치지 않는다.
