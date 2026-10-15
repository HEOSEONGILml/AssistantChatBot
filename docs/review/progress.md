# 검수 루프 진행 상황

- **다음 단계**: 단계 0 (하네스 만들기)
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
