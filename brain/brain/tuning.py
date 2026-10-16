"""잠정값·방향표와 근거 (두뇌 스펙 v2 4·6·6.5·9절). 시뮬레이션(brain/sim)으로 맞추고 평가로 다시 본다.
방향표는 +1/−1만 정하고, 세기는 Tuning의 w·scale 값이 정한다."""
from dataclasses import dataclass, field

# 기분 8차원. 궁금함·놀람·무서움은 반응이 곧 기분의 표출이 되도록 더했다 (사용자 결정, 기분 8개 스펙)
MOODS = ("심심함", "졸림", "들뜸", "시무룩", "분노", "궁금함", "놀람", "무서움", "행복")  # 행복: 들뜸(흥분)과 다른 편안한 기쁨 (사용자 지적)
EVENT_KINDS = ("typing", "message", "dog_spoke", "quiet", "returned", "house_in", "house_out", "poke", "pet", "throw")

# 탄생 (스펙 4.1): "호기심 많고 수다스러운 강아지"를 숫자로 옮긴 평균
BIRTH_BASELINE = {"심심함": 0.6, "졸림": 0.3, "들뜸": 0.4, "시무룩": 0.2, "분노": 0.1, "궁금함": 0.5, "놀람": 0.1, "무서움": 0.1, "행복": 0.4}
BIRTH_SD = 0.1
BASELINE_RANGE = (0.05, 0.95)
BIRTH_SENS, SENS_SD, SENS_RANGE = 0.5, 0.1, (0.2, 0.9)
BIRTH_WHIM, WHIM_SD = 0.5, 0.15
INTIMACY_START = 0.3

# 반응 = 가장 크게 오른 기분의 표출 (기분 8개 스펙 3절). 반응 id는 프로토콜 어휘다
MOOD_REACTION_ID = {"심심함": "bored", "졸림": "sleepy", "들뜸": "excited", "시무룩": "sad", "분노": "annoyed",
                    "궁금함": "curious", "놀람": "surprised", "무서움": "scared", "행복": "happy"}
# 동작 보정 (스펙 6절): 기분→동작 B, 반응→동작 C
# 동작 선택 (스펙 2026-10-16 동작 모형): 우리 모형 중심, Jev는 약하게. 기분은 기준값 대비로 본다
MOOD_ACTION = {"stand": {"궁금함": 0.5, "놀람": 0.3}, "sit": {"행복": 0.3, "궁금함": 0.5, "졸림": 0.3},
               "lie_down": {"졸림": 0.7, "시무룩": 1, "무서움": 1}, "sleep": {"졸림": 1.5, "들뜸": -1, "무서움": -1},
               "beg": {"행복": 1, "들뜸": 0.7, "심심함": 0.5}, "bark": {"분노": 1, "놀람": 0.8, "들뜸": 0.5}}
ACTION_BASE = {"stand": 0.3, "sit": 0.3, "lie_down": 0.0, "sleep": -1.5, "beg": -0.5, "bark": -0.5, "none": 0.3}
EVENT_ACTION = {"poke": {"bark": 0.8, "stand": 0.3}, "pet": {"beg": 0.8, "sit": 0.8, "lie_down": 0.3},
                "throw": {"bark": 0.6, "lie_down": 0.6}, "quiet": {"lie_down": 0.8, "sit": 0.5, "sleep": 0.3},
                "returned": {"beg": 1.0, "bark": 0.5}, "house_out": {"stand": 0.5},
                "message": {"sit": 0.5, "stand": 0.2}, "typing": {"sit": 0.5, "stand": 0.2}, "dog_spoke": {"none": 1.2}}
REACTION_ACTION = {"excited": {"beg": 1}, "annoyed": {"bark": 0.7, "none": 0.5}, "surprised": {"bark": 1}, "scared": {"lie_down": 1},
                   "sad": {"lie_down": 1}, "curious": {"sit": 0.6, "stand": 0.4}, "sleepy": {"lie_down": 1}, "happy": {"beg": 1}}
# 말수 (스펙 6절 3): 독립 파라미터가 아니라 친밀도·기분·기준값에서 계산한다 (사용자 결정, 분노는 −)
TALK_MOOD = {"심심함": 1, "들뜸": 1, "졸림": -1, "시무룩": -1, "분노": -1, "궁금함": 1, "무서움": -1, "행복": 1}
TALK_BASELINE = {"심심함": 1, "들뜸": 1, "졸림": -1, "시무룩": -1, "분노": -1, "궁금함": 1, "무서움": -1, "행복": 1}
# 습관화 (스펙 4.5): 대상 자극과 그 자극이 주로 건드리는 기분
HABIT_KINDS = {"poke": "놀람", "pet": "행복", "throw": "놀람", "typing": "궁금함"}  # 타이핑에 익숙해지면 글 내용이 드러난다 (검수 002)  # 반복해서 던지면 덜 무서워한다
# 하루 리듬 (시간 모형 스펙): 기분이 돌아가는 자리(기준값)가 시각에 따라 이만큼 × 리듬값(새벽 3시 +0.5, 오후 3시 −0.5) 움직인다.
# 하루 평균은 0이라 성격(기준값)과 하루 평균 기분은 그대로다. 검수 001: 새벽 2시에 졸리지 않고 놀자고 조름
CIRCADIAN = {"졸림": 0.6, "들뜸": -0.2, "심심함": -0.2}
CIRCADIAN_PEAK_HOUR = 3


# 기분 변화 = 우리 평가 사전값 + Jev 조정 (스펙 2026-10-16, 0015). 사전값은 평균 강아지가 느끼는 크기(잠정값)
def appraisal(kind: str, ctx: dict, habit: float = 0.0, wary: float = 0.0, waiting: bool = False,
              alone_s: float = 0.0) -> dict[str, float]:
    """이벤트 하나가 기분에 주는 충격. 뜻이 정해진 이벤트는 우리가 정한다(Jev가 던지기를 행복으로 읽는 등 틀리기 때문).
    habit: 이 자극에 익숙한 정도(찌르기는 익숙할수록 짜증이 쌓인다). wary: 지금 화나거나 무서운 정도(쓰다듬기를 경계한다)."""
    if kind == "poke":
        return {"놀람": 0.20, "분노": 0.06 + 0.15 * habit, "궁금함": 0.03}
    if kind == "pet":
        s = min(float(ctx.get("seconds") or 3.0), 5.0) / 3.0
        g = 1 - wary
        return {"행복": 0.12 * s * g, "들뜸": 0.04 * s * g, "분노": -0.03 * s, "시무룩": -0.03 * s, "무서움": -0.03 * s}
    if kind == "throw":
        i = float(ctx.get("impact", 0.5) or 0.0)
        # 세게 던지면 놀람보다 무서움이 크다. 반복하면 놀람은 무뎌지고 무서움은 남는다 (검수 003: 13번 던져도 무서움 반응 0)
        return {"놀람": 0.10 + 0.15 * i, "무서움": 0.35 * i, "분노": 0.05 * i, "행복": -0.10 * i, "졸림": -0.10 * i}
    if kind == "quiet":
        m = min(float(ctx.get("seconds") or 600) / 600, 3.0)
        # 물어봤는데 답이 없으면 서운하다 (검수 002: 3시간 무시당해도 시무룩 그대로)
        # 주인이 오래(30분 → 2시간) 없으면 심심함은 줄고 졸음으로 넘어간다: 혼자인 낮에 개는 대부분 잔다 (검수 002)
        f = min(1.0, max(0.0, (alone_s / 3600 - 0.5) / 1.5))
        # 화면은 사용자가 자리에 없으면 30분마다 조용함을 보낸다. 나간 주인은 무시한 게 아니라 서운하지 않다 (검수 003)
        away = float(ctx.get("seconds") or 600) >= 1800
        sad = 0.0 if away else (0.07 if waiting else 0.01)
        return {"심심함": 0.04 * m * (1 - f), "졸림": 0.06 * m * f, "시무룩": sad * m}
    if kind == "returned":
        return {"행복": 0.15, "들뜸": 0.12, "심심함": -0.10, "시무룩": -0.08}
    if kind == "house_out":
        return {"들뜸": 0.08, "행복": 0.06}
    if kind == "typing":
        return {"궁금함": 0.04}
    if kind == "message":
        return {"궁금함": 0.02, "심심함": -0.04}
    return {}  # house_in, dog_spoke(자기 말은 자기 기분을 키우지 않는다)


def appraisal_intimacy(kind: str, ctx: dict) -> float:
    if kind == "pet":
        return 0.005
    if kind == "throw":
        return -0.01 * float(ctx.get("impact", 0.5) or 0.0)
    return 0.0


# 관계 해석: Jev는 거절하는 말("저리 가")에 친밀도↓를, 다정한 말에 친밀도↑를 주로 준다. 우리 모형은 그것을 기분으로도 읽는다.
# 거절은 서운함, 다정함은 행복 (검수 002: 욕을 들어도 서운해하지 않음). 값은 Jev 같은 기분↑ 대비 비율
RELATION_MOOD = {"친밀도↓": {"시무룩": 0.8}, "친밀도↑": {"행복": 0.5, "시무룩": -0.8}}  # 사과·다정한 말은 서운함을 던다 (검수 003)

# Jev 변화 분포를 얼마나 믿나: 글 내용이 중요한 메시지는 크게, 뜻이 정해진 이벤트는 작게, 자기 말은 0
JEV_WEIGHT = {"message": 1.0, "typing": 0.8, "dog_spoke": 0.0, "quiet": 0.1}  # 조용함의 기분은 우리 몫 (검수 003: Jev가 조용함마다 시무룩↑)  # 타이핑도 글 내용이 중요 (검수 002: 0.5 → 0.8)
JEV_WEIGHT_OTHER = 0.3
# 함께 높으면 어색한 반대 기분 쌍: 한쪽이 오르면 다른 쪽이 내린다 (검수 001)
OPPOSITES = (("무서움", "행복"), ("무서움", "들뜸"), ("분노", "행복"), ("시무룩", "들뜸"), ("시무룩", "행복"), ("졸림", "들뜸"))
# 평소 움직임 경향 (스펙 6.5). 기본값은 몸체 "보통" 프로필과 같다
MOVE_BASE = {"rest": 0.6, "sleep": 0.08, "roam": 0.4, "approach": 0.18, "play": 0.06, "explore": 0.2}
MOVE_MOOD = {"rest": {"졸림": 1, "시무룩": 1, "들뜸": -1, "무서움": 1}, "sleep": {"졸림": 2, "들뜸": -1, "심심함": -1},
             "roam": {"심심함": 1, "들뜸": 1, "졸림": -1, "시무룩": -1, "분노": 0.5},
             "approach": {"심심함": 1, "들뜸": 1, "분노": -1, "시무룩": -1, "궁금함": 1, "무서움": -1, "행복": 1},
             "play": {"들뜸": 1, "졸림": -1, "시무룩": -1, "분노": -1, "무서움": -1}, "explore": {"심심함": 1, "졸림": -1, "궁금함": 1, "분노": 0.5}}  # 화나면 사용자를 피해 돌아다닌다 (검수 003)
# 성격(기준값)의 평소 수준은 탄생 평균 대비로 본다 (검수 003: 활발이 과묵보다 덜 뛰었다)
MOVE_BASELINE = {"rest": {"졸림": 1, "들뜸": -1}, "sleep": {"졸림": 1}, "roam": {"심심함": 1, "들뜸": 1},
                 "approach": {"심심함": 1, "들뜸": 1, "행복": 1}, "play": {"들뜸": 1, "궁금함": 0.5}, "explore": {"심심함": 1, "궁금함": 1}}
RUN_BASELINE = {"들뜸": 2, "졸림": -1}
IDLE_BASELINE = {"들뜸": -1, "졸림": 1}
MOVE_INTIMACY = {"approach": 1, "play": 1}
RUN_BASE, RUN_MOOD = 0.2, {"들뜸": 1.5, "졸림": -1, "무서움": -0.5}  # 행복은 느긋한 기쁨이라 뛰지 않는다 (검수 003)
IDLE_MOOD = {"졸림": 1, "시무룩": 1, "들뜸": -1, "행복": 0.5}


@dataclass(frozen=True)
class Tuning:
    jev_timeout_s: float = 3.0          # SDK 기본 10초는 실시간 반응에 너무 길다 (v1)
    gemini_timeout_s: float = 5.0       # 늦은 대사는 버려질 가능성이 크다 (v1)
    recent_events: int = 30             # v1 대화 20개 + 찌르기 같은 짧은 이벤트
    max_streak: int = 3                 # 사용자 입력 없이 연달아 말하는 상한 (안전장치)
    # 기본 반감기 (기준값 0.5일 때). 실제 반감기 = 기본 × (0.5 + 기준값) (스펙 4.2)
    # 검수 001(사용자 K-2 "감쇠가 너무 느리다"): 찔린 짜증 30분, 놀람 몇 분은 사람 감각에 너무 길어 줄였다(잠정값).
    # 평균 강아지 실제 반감기: 분노 6분, 놀람 36초, 무서움 9분(검수 002: 던져진 경계는 오래), 궁금함 3분, 들뜸 5분, 행복·시무룩·심심함 15~20분, 졸림 48분
    half_life_s: dict = field(default_factory=lambda: {"심심함": 1800.0, "졸림": 3600.0, "들뜸": 600.0, "시무룩": 1800.0, "분노": 600.0,
                                                       "궁금함": 300.0, "놀람": 60.0, "무서움": 900.0, "행복": 1800.0})
    mood_noise: float = 0.03            # 오래 두었을 때 기준값 주변 흔들림 표준편차. 움직임 효과를 키우며(×4) 0.05는 경향이 너무 출렁여 줄였다
    intimacy_half_life_s: float = 14 * 86400.0
    change_k: float = 0.3               # 메시지의 강한 내용 (P↑−P↓) ±0.6 → 평균 강아지 ±0.18
    change_noise: float = 0.01          # 0.02는 Jev 신호와 같은 크기라 반응이 잡음으로 뽑혔다 (검수 001)
    inhibit: float = 0.3                # 반대 기분 억제 비율. 0.6은 쓰다듬기 한 번에 나쁜 기분을 0으로 지웠다 (검수 002)
    intimacy_k: float = 0.02            # 0.05는 첫 12분에 0.30 → 0.35로 빨랐다 (검수 001)
    # 기질로 되돌아가는 힘. drift_rate와 같으면 성격은 기질과 경험의 한가운데에 자리 잡는다.
    # 이 힘이 없으면 8주 시뮬레이션에서 모든 강아지가 같은 성격으로 수렴했다 (docs/spikes/2026-10-15-simulation.md)
    temperament_pull: float = 0.025
    drift_rate: float = 0.025           # 하루에 기준값이 어제 평균 쪽으로 2.5% 이동 (4주에 절반). 5%는 8주 시뮬레이션에서 20마리 중 8마리가 극단으로 감
    habit_rate: float = 0.3             # 같은 자극 5번이면 h≈0.83 (민감도 0.5)
    habit_half_life_s: float = 3600.0   # 1시간 쉬면 습관화가 절반 풀림
    react_threshold: float = 0.03      # 잡음을 뺀 변화가 이만큼 이상 오른 기분의 반응을 보인다 (잠정값, 검수 002)
    dominant_threshold: float = 0.15   # 기준값보다 이만큼 높은 기분이 평소 모습을 정한다 (잠정값)
    w_mood: float = 5.0                 # 기분이 기준값보다 0.2 높으면 점수 +1 (동작 모형 스펙)
    w_react: float = 1.5
    w_jev_action: float = 0.3           # Jev 동작 로그확률의 무게. 서기 0.98 쏠림도 최대 약 0.9로 묶인다 (검수 001)
    jev_action_floor: float = 0.05
    talk_scale: float = 0.7             # 말수 계수 크기. 기분 8개로 늘며 항이 많아져 1.0이면 활발한 강아지 끼어들기가 65%까지 벌어짐 (시뮬레이션)
    # 이벤트 종류별 말하기 보정. 평균 성격 강아지가 목표 지표(끼어들기 30%, 답하기 85%, 먼저 말 걸기 1/3,
    # 연달아 2번+ 30%)에 맞도록 녹화한 Jev 분포로 시뮬레이션해 맞춘 값 (docs/spikes/2026-10-15-simulation.md).
    # 질문 문구나 Jev 버전을 바꾸면 sim.record로 다시 녹화하고 sim.simulate --fit으로 다시 맞춘다
    kind_bias: dict = field(default_factory=lambda: {**{k: 0.0 for k in EVENT_KINDS},
                                                     "typing": -3.0, "message": -0.71, "dog_spoke": -0.47, "quiet": -2.02})
    streak_penalty: float = 1.0
    waiting_penalty: float = 1.0
    move_scale: float = 4.0             # 기분(기준값 대비) 효과. 기준값보다 0.3 높으면 경향 ×3.3 (검수 001: 1.0은 기분 차이가 안 보였다)
    move_personality: float = 2.0       # 성격(기준값, 탄생 평균 대비) 효과. 검수 003: 1.0·0.5 기준으로는 성격이 움직임에 안 보였다
    sleep_gate: float = 0.1             # 잠 동작은 졸림이 기준값보다 이만큼 높을 때부터 (검수 003: 들뜬 강아지가 잠)
    clock_s: float = 30.0               # 기분 반감기가 20분 이상이라 30초 갱신이면 충분
    send_weight_ratio: float = 0.30     # 움직임 경향 전송 기준. 사람 눈에 보일 만한 30% 변화. 0.10이면 시간당 95번 보냈다
    send_run_delta: float = 0.10
    send_idle_ratio: float = 0.30
