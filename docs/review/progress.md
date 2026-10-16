# 검수 루프 진행 상황

- **다음 단계**: 단계 1 (검수 001)
- **연속 통과**: 0
- **회차**: 0

## 시작 방법 (사용자, 2026-10-16 예정)

Claude Code를 저장소 루트에서 열고 아래 한 줄을 입력한다.

```
/ralph-loop "docs/review/loop-prompt.md를 읽고 그대로 한 회차를 진행해." --completion-promise "REVIEW PASSED TWICE" --max-iterations 30
```

- 멈추기: `/cancel-ralph`
- 진행 확인: 이 파일, `docs/review/rounds/`, `git log --oneline ralph/review-loop`
- 상한 30은 잠정값이다(스펙 6절).

## 기록

- 2026-10-15 · 준비 · 스펙·검수자 정의·아는 결함·루프 프롬프트 작성, 브랜치 `ralph/review-loop` 생성 · 하네스는 아직 없음
- 2026-10-16 · 단계 0 · 하네스 완성(`brain/review/`, 기본 시나리오 17개, pytest 12개). 실제 키로 05-question-wait 실행: Jev 7번·Gemini 2번, 4초. 기본 세트 전체 추정 Jev 약 400번·Gemini 약 150번/회차 · (이 커밋) · 비용 미측정(호출 수만)
- 판단: 화면 콘솔이 cp949라 한글이 깨진다. 실행 시 `PYTHONIOENCODING=utf-8`을 쓴다(README).
