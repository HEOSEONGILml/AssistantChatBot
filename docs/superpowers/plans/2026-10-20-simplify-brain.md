# 두뇌 단순화 구현 계획

스펙: [2026-10-20-simplify-brain-design](../specs/2026-10-20-simplify-brain-design.md)

| 순서 | 할 일 | 파일 | 확인 |
|---|---|---|---|
| 1 | 테스트를 새 모양으로 고친다: `Dog`는 `mood`·`updated_at`만, 성격·친밀도·습관화·말수 테스트는 지운다 | `brain/tests/*` | 실패 확인 |
| 2 | `tuning.py`: 탄생·민감도·변덕·습관화·말수·친밀도·성격 항 상수를 지우고 `REST`, 접은 반감기, `obey_k` 4.8을 둔다 | `brain/brain/tuning.py` | |
| 3 | `model.py`: `Personality`, 탄생, 하루 평균, 습관화, 친밀도, 말수, 온도를 지운다 | `brain/brain/model.py` | `uv run pytest` |
| 4 | `questions.py`·`persona.py`: `jev_state`, `change` 선택지, `voice` 제거, 지시문 | | `uv run pytest` |
| 5 | `core.py`: 상태 조회, 초기화, 기분 시계, 핀잔 판정(`harsh`) | | `uv run pytest` |
| 6 | 프로토콜 v4: `server.py`, `brain-protocol.ts`, `status-view.ts`와 테스트, `docs/brain-protocol.md` | | `npm test` |
| 7 | 시뮬레이션·녹화·검수 하네스 정리, 시나리오 `personality` 필드 제거 | `brain/sim`, `brain/review` | `uv run pytest` |
| 8 | Jev 다시 녹화, 보정값 다시 맞춤 → `kind_bias`, `chain_base` | `sim/jev_recording.json`, `tuning.py` | `sim.simulate` 지표 |
| 9 | 문서 동기화: `ARCHITECTURE.md`, `glossary.md`, `review/README.md` | | |
