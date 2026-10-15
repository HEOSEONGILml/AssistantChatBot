"""잠정값. 근거는 두뇌 스펙 4.4절. 서브 프로젝트 3과 실제 사용으로 다시 정한다."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Tuning:
    typing_chars: int = 10              # K: 한국어 두세 어절. 의미가 바뀔 만큼 입력됨
    typing_pause_s: float = 0.6         # T: 연속 타이핑 키 간격은 대개 0.5초 안쪽
    quiet_active_s: float = 60.0        # P_active: 하루 약 $0.09 (state 1,500토큰, 업체 발표 단가)
    quiet_away_s: float = 600.0         # P_away: 자리를 비운 동안 호출을 줄인다
    speak_threshold: float = 0.5        # speak_now 임계값: 데이터가 없어 중간값에서 시작
    recent_n: int = 20                  # 최근 대화 N: 말풍선 대사가 짧아 20개면 충분
    max_consecutive: int = 3            # 사용자 입력 없이 연달아 말하는 상한: 비용 폭주 방지
    jev_timeout_s: float = 3.0          # SDK 기본 10초는 실시간 반응에 너무 길다
    gemini_timeout_s: float = 5.0       # 늦은 대사는 상황이 바뀌어 버려질 가능성이 크다
    interaction_min_gap_s: float = 2.0  # 쓰다듬기 반복 시 호출 폭주 방지
    backoff_max_s: float = 300.0        # 연속 실패 시 조용함 주기를 늘리는 상한 (5분)
    tick_s: float = 0.1                 # 스케줄러 확인 간격. 멈춤 판정 T에 최대 0.1초가 더해진다
