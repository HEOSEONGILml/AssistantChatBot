# 보수 작업 목록

다음 보수 작업 때 처리할 것을 모은다. 착수하면 계획(`docs/superpowers/plans/`)을 쓰고, 끝나면 이 목록에서 지운다.

## 1. 사용량 체크가 제대로 안 된다 (2026-10-22 등록)

- **증상 (사용자):** 사용량 탭의 값이 제대로 나오지 않는 것 같다. 아직 원인을 보지 않았다.
- **지금 동작:**
  - 백엔드는 Claude Code가 작업 중에 보내는 `RateLimitEvent`(한도 종류, 쓴 비율, 초기화 시각)에서 종류별 마지막 값만 메모리에 둔다(`backend/backend/core.py` `rate_limit`, `_usage`). 작업이 돌지 않으면 갱신되지 않고, 백엔드를 다시 켜면 비워진다.
  - 화면은 받은 값만 막대로 그린다(`app/src/ui/usage.ts`). 종류 이름 대응(`five_hour` → 현재 세션, `seven_day` → 이번 주, `opus`·`sonnet` → 모델별)은 실제 값으로 확인하지 않은 짐작이다.
- **확인한 적 없는 것:** `RateLimitEvent`가 언제 오는지, 한도 종류 이름과 값의 모양 ([스펙](superpowers/specs/2026-10-21-assistant-phase1-design.md) 8절, [수동 확인](manual-checks/backend.md) 4번이 아직 비어 있다).
- **볼 것:** 실제 작업을 몇 개 돌리며 받은 `RateLimitEvent`를 기록해 이름·값 모양을 확인한다. 그다음 갱신 시점(작업이 없을 때, 재시작 뒤)과 화면 대응을 고친다.
