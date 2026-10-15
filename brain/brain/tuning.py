"""잠정값·방향표와 근거 (두뇌 스펙 v2 4·6·6.5·9절). 시뮬레이션(brain/sim)으로 맞추고 평가로 다시 본다.
방향표는 +1/−1만 정하고, 세기는 Tuning의 w·scale 값이 정한다."""
from dataclasses import dataclass, field

MOODS = ("심심함", "졸림", "들뜸", "시무룩", "분노")
EVENT_KINDS = ("typing", "message", "dog_spoke", "quiet", "returned", "house_in", "house_out", "poke", "pet", "throw")

# 탄생 (스펙 4.1): "호기심 많고 수다스러운 강아지"를 숫자로 옮긴 평균
BIRTH_BASELINE = {"심심함": 0.6, "졸림": 0.3, "들뜸": 0.4, "시무룩": 0.2, "분노": 0.1}
BIRTH_SD = 0.1
BASELINE_RANGE = (0.05, 0.95)
BIRTH_SENS, SENS_SD, SENS_RANGE = 0.5, 0.1, (0.2, 0.9)
BIRTH_WHIM, WHIM_SD = 0.5, 0.15
INTIMACY_START = 0.3

# 반응·동작 보정 (스펙 6절): 기분→반응 A, 기분→동작 B, 반응→동작 C
MOOD_REACTION = {"annoyed": {"분노": 1}, "sad": {"시무룩": 1}, "joy": {"들뜸": 1, "심심함": 1},
                 "curious": {"심심함": 1}, "none": {"졸림": 1}}
MOOD_ACTION = {"sleep": {"졸림": 1}, "lie_down": {"졸림": 1, "시무룩": 1}, "bark": {"들뜸": 1, "분노": 1}, "beg": {"심심함": 1}}
REACTION_ACTION = {"surprised": {"bark": 1}, "annoyed": {"bark": 1}, "scared": {"bark": 1},
                   "joy": {"beg": 1}, "sad": {"lie_down": 1}, "curious": {"stand": 1}}
# 말수 (스펙 6절 3): 독립 파라미터가 아니라 친밀도·기분·기준값에서 계산한다 (사용자 결정, 분노는 −)
TALK_MOOD = {"심심함": 1, "들뜸": 1, "졸림": -1, "시무룩": -1, "분노": -1}
TALK_BASELINE = {"심심함": 1, "들뜸": 1, "졸림": -1, "시무룩": -1, "분노": -1}
# 습관화 (스펙 4.5): 대상 자극과 그 자극이 주로 건드리는 기분
HABIT_KINDS = {"poke": "분노", "pet": "들뜸", "throw": "들뜸"}
# 평소 움직임 경향 (스펙 6.5). 기본값은 몸체 "보통" 프로필과 같다
MOVE_BASE = {"rest": 0.6, "sleep": 0.02, "roam": 0.4, "approach": 0.18, "play": 0.06, "explore": 0.2}
MOVE_MOOD = {"rest": {"졸림": 1, "시무룩": 1, "들뜸": -1}, "sleep": {"졸림": 1, "들뜸": -1, "심심함": -1},
             "roam": {"심심함": 1, "들뜸": 1, "졸림": -1, "시무룩": -1},
             "approach": {"심심함": 1, "들뜸": 1, "분노": -1, "시무룩": -1},
             "play": {"들뜸": 1, "졸림": -1, "시무룩": -1, "분노": -1}, "explore": {"심심함": 1, "졸림": -1}}
MOVE_BASELINE = {"rest": {"졸림": 1}, "sleep": {"졸림": 1}, "roam": {"심심함": 1},
                 "approach": {"심심함": 1, "들뜸": 1}, "play": {"들뜸": 1}, "explore": {"심심함": 1}}
MOVE_INTIMACY = {"approach": 1, "play": 1}
RUN_BASE, RUN_MOOD = 0.2, {"들뜸": 1, "졸림": -1}
IDLE_MOOD = {"졸림": 1, "시무룩": 1, "들뜸": -1}


@dataclass(frozen=True)
class Tuning:
    jev_timeout_s: float = 3.0          # SDK 기본 10초는 실시간 반응에 너무 길다 (v1)
    gemini_timeout_s: float = 5.0       # 늦은 대사는 버려질 가능성이 크다 (v1)
    recent_events: int = 30             # v1 대화 20개 + 찌르기 같은 짧은 이벤트
    max_streak: int = 3                 # 사용자 입력 없이 연달아 말하는 상한 (안전장치)
    # 기본 반감기 (기준값 0.5일 때). 실제 반감기 = 기본 × (0.5 + 기준값) (스펙 4.2)
    half_life_s: dict = field(default_factory=lambda: {"심심함": 3600.0, "졸림": 7200.0, "들뜸": 1200.0, "시무룩": 3600.0, "분노": 1800.0})
    mood_noise: float = 0.05            # 오래 두었을 때 기준값 주변 흔들림 표준편차
    intimacy_half_life_s: float = 14 * 86400.0
    change_k: float = 0.3               # 강한 내용 (P↑−P↓) ±0.6~0.7 × 민감도 0.5 → 한 이벤트에 ±0.1
    change_noise: float = 0.02
    intimacy_k: float = 0.05            # 강하게 좋은 일 약 20번에 +0.5
    # 기질로 되돌아가는 힘. drift_rate와 같으면 성격은 기질과 경험의 한가운데에 자리 잡는다.
    # 이 힘이 없으면 8주 시뮬레이션에서 모든 강아지가 같은 성격으로 수렴했다 (docs/spikes/2026-10-15-simulation.md)
    temperament_pull: float = 0.025
    drift_rate: float = 0.025           # 하루에 기준값이 어제 평균 쪽으로 2.5% 이동 (4주에 절반). 5%는 8주 시뮬레이션에서 20마리 중 8마리가 극단으로 감
    habit_rate: float = 0.3             # 같은 자극 5번이면 h≈0.83 (민감도 0.5)
    habit_half_life_s: float = 3600.0   # 1시간 쉬면 습관화가 절반 풀림
    w_habit: float = 2.0
    w_mood: float = 1.0                 # 기분이 0.5 벗어나면 로그 점수 ±0.5. Jev 로그확률 차이(1~3)보다 작게
    w_sens: float = 1.0
    w_react: float = 1.0
    talk_scale: float = 1.0             # 말수 계수 크기
    # 이벤트 종류별 말하기 보정. 평균 성격 강아지가 목표 지표(끼어들기 15%, 답하기 85%, 먼저 말 걸기 1/3,
    # 연달아 2번+ 30%)에 맞도록 녹화한 Jev 분포로 시뮬레이션해 맞춘 값 (docs/spikes/2026-10-15-simulation.md).
    # 질문 문구나 Jev 버전을 바꾸면 sim.record로 다시 녹화하고 sim.simulate --fit으로 다시 맞춘다
    kind_bias: dict = field(default_factory=lambda: {**{k: 0.0 for k in EVENT_KINDS},
                                                     "typing": -4.28, "message": -0.71, "dog_spoke": -2.13, "quiet": -2.61})
    streak_penalty: float = 1.0
    waiting_penalty: float = 1.0
    move_scale: float = 1.0
    clock_s: float = 30.0               # 기분 반감기가 20분 이상이라 30초 갱신이면 충분
    send_weight_ratio: float = 0.10     # 움직임 경향 전송 기준
    send_run_delta: float = 0.05
    send_idle_ratio: float = 0.10
