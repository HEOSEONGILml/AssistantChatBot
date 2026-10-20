"""확률 모델 (두뇌 스펙 v2 4·6·6.5절, 단순화 스펙 15절). 화면·전송·저장을 모르는 순수 함수다. 시각과 난수는 인자로 받는다."""
import math
from dataclasses import asdict, dataclass

from .tuning import (ACTION_BASE, EVENT_ACTION, IDLE_MOOD, MOOD_ACTION, MOOD_REACTION_ID, MOODS, MOVE_BASE, MOVE_MOOD,
                     OPPOSITES, REACTION_ACTION, REST, RUN_BASE, RUN_MOOD, TEXT_KINDS, Tuning, appraisal)

LN2 = math.log(2)


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class Dog:
    mood: dict[str, float]          # 기분 9개 (0~1)
    updated_at: float


def new_dog(now: float) -> Dog:
    """처음 기분은 돌아가는 자리다. 초기화도 이것으로 한다 (단순화 스펙 3절)."""
    return Dog(mood=dict(REST), updated_at=now)


def advance(dog: Dog, now: float, t: Tuning) -> None:
    """지난 갱신 뒤로 흐른 시간만큼 기분을 기분별 반감기로 돌아가는 자리(REST)에 가깝게 한다 (0020)."""
    dt = now - dog.updated_at
    if dt <= 0:
        return
    for d in MOODS:
        e = math.exp(-LN2 / t.half_life_s[d] * dt)
        dog.mood[d] = REST[d] + (dog.mood[d] - REST[d]) * e
    dog.updated_at = now


def dog_to_dict(dog: Dog) -> dict:
    return asdict(dog)


def dog_from_dict(data: dict) -> Dog:
    """저장본에서 강아지를 만든다. 예전 저장본의 성격·친밀도·습관화는 버린다 (단순화 스펙 3절).
    모양이 어긋나면 TypeError·KeyError·ValueError가 난다(부르는 쪽이 처리)."""
    mood = {**REST, **{d: float(v) for d, v in data.get("mood", {}).items() if d in REST}}
    return Dog(mood=mood, updated_at=float(data["updated_at"]))


# ---- 어휘 (프로토콜 v2) ----

REACTIONS = (*MOOD_REACTION_ID.values(), "none")
ACTIONS = ("stand", "sit", "lie_down", "sleep", "beg", "bark", "none")
REACTION_NAMES = {"bored": "지루함", "sleepy": "하품", "excited": "신남", "sad": "서운함", "annoyed": "짜증",
                  "curious": "궁금함", "surprised": "놀람", "scared": "무서움", "happy": "행복", "none": "없음"}
ACTION_NAMES = {"stand": "서기", "sit": "앉기", "lie_down": "엎드리기", "sleep": "잠", "beg": "조르기", "bark": "짖기", "none": "없음"}


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _logit(p: float) -> float:
    p = clip(p, 1e-4, 1 - 1e-4)
    return math.log(p / (1 - p))


# ---- 기분 변화 (단순화 스펙 14·15절) ----

class Change(dict):
    """기분 변화(실제로 움직인 양). .signal은 반대 기분 억제 뒤, 자르기 전의 신호로 반응을 뽑는 데 쓴다."""
    signal: dict[str, float]


def apply_change(dog: Dog, change: dict[str, float], events: list[tuple[str, dict]], t: Tuning) -> Change:
    """기분 변화: 글 없는 사건의 평가값을 더하고, 글(메시지·타이핑)이 있으면 Jev가 고른 기분 확률 × 0.3을 더한다.
    한쪽이 오른 만큼 반대 기분을 같은 양 내린 뒤 0~1로 자른다 (0019·0020)."""
    signal = {d: 0.0 for d in MOODS}
    for k, ctx in events:
        for d, v in appraisal(k, ctx or {}).items():
            signal[d] += v
    if any(k in TEXT_KINDS for k, _ in events):  # Jev는 묶음에 한 번 불리므로 글이 있으면 한 번 더한다
        for d in MOODS:
            signal[d] += t.change_k * change.get(d, 0.0)
    rises = dict(signal)
    for a, c in OPPOSITES:  # 한쪽이 오른 만큼 반대쪽이 내린다
        signal[c] -= t.inhibit * max(rises[a], 0.0)
        signal[a] -= t.inhibit * max(rises[c], 0.0)
    deltas = Change()
    for d in MOODS:
        before = dog.mood[d]
        dog.mood[d] = clip(before + signal[d])
        deltas[d] = dog.mood[d] - before
    deltas.signal = signal
    return deltas


# ---- 반응·동작 (스펙 6절, 단순화 스펙 15절) ----

def reaction_from(deltas: dict[str, float], kinds: list[str], t: Tuning) -> str:
    """반응 = 이번에 가장 크게 오른 기분의 표출 (기분 8개 스펙 3절). 타이핑 판단은 늘 반응을 하나 낸다.
    apply_change의 결과를 받으면 반대 기분 억제 뒤의 신호로 뽑는다(0에 붙은 기분도 신호는 남는다)."""
    deltas = getattr(deltas, "signal", deltas)
    mood = max(MOODS, key=lambda d: deltas.get(d, 0.0))
    rise = deltas.get(mood, 0.0)
    if rise >= t.react_threshold:
        return MOOD_REACTION_ID[mood]
    if "typing" in kinds:  # 타이핑하는 동안 반응을 더 많이 (사용자 요청)
        return MOOD_REACTION_ID[mood] if rise > 0 else "curious"
    return "none"


def dominant_mood(dog: Dog, t: Tuning) -> str:
    """평소 모습을 정하는 기분: 돌아가는 자리보다 가장 많이 높은 기분. 충분히 높지 않으면 calm."""
    mood, rise = max(((d, dog.mood[d] - REST[d]) for d in MOODS), key=lambda x: x[1])
    return MOOD_REACTION_ID[mood] if rise >= t.dominant_threshold else "calm"


def action_scores(jev: dict[str, float], dog: Dog, reaction: str, kinds: list[str], t: Tuning) -> dict[str, float]:
    """동작 점수 (동작 모형 스펙): 기본 + 이벤트 사전값 + 기분(자리 대비) + 반응. 메시지만 Jev 동작 판단을 더한다 (0020)."""
    if kinds and all(k == "dog_spoke" for k in kinds):
        return {"none": 0.0}  # 자기 말 뒤에는 자세를 바꾸지 않는다 (검수 011)
    m = dog.mood
    message = bool(kinds) and kinds[-1] == "message"  # "앉아"처럼 글 내용이 동작을 정할 수 있다 (검수 010)
    scores = {}
    for a in ACTIONS:
        x = (ACTION_BASE.get(a, 0.0) + sum(EVENT_ACTION.get(k, {}).get(a, 0.0) for k in kinds)
             + t.w_mood * sum(w * (m[d] - REST[d]) for d, w in MOOD_ACTION.get(a, {}).items())
             + t.w_react * REACTION_ACTION.get(reaction, {}).get(a, 0)
             + (t.w_jev_action_message * math.log(jev.get(a, 0.0) + t.jev_action_floor) if message else 0.0))
        if a == "sleep" and m["졸림"] - REST["졸림"] < t.sleep_gate:
            x -= 10.0  # 평소보다 졸리지 않으면 자지 않는다 (검수 003)
        scores[a] = x
    return scores


def probabilities(scores: dict[str, float]) -> dict[str, float]:
    top = max(scores.values())
    w = {k: math.exp(v - top) for k, v in scores.items()}
    z = sum(w.values())
    return {k: v / z for k, v in w.items()}


def pick(scores: dict[str, float], rng) -> str:
    r, acc, key = rng.random(), 0.0, ""
    for key, p in probabilities(scores).items():
        acc += p
        if r < acc:
            return key
    return key


# ---- 말하기 (스펙 6절 3, 단순화 스펙 15절) ----

def speak_probability(p_jev: float, kind: str, streak: int, t: Tuning) -> float:
    """말할 확률 = σ(logit P_Jev + 이벤트 종류 보정 − 연달아 말한 횟수). 연달아 상한이면 0."""
    if streak >= t.max_streak:
        return 0.0
    return _sigmoid(_logit(p_jev) + t.kind_bias.get(kind, 0.0) - t.streak_penalty * streak)


def chain_probability(streak: int, t: Tuning) -> float:
    """방금 한 말에 한마디 더 할 확률 (검수 005). Jev는 이어 말하기를 잘 판단하지 못해 우리 모형이 정한다: 이어 갈수록 줄어든다."""
    if streak >= t.max_streak:
        return 0.0
    return t.chain_base * t.chain_decay ** max(0, streak - 1)


# ---- 평소 움직임 경향 (스펙 6.5): 두뇌가 계산하고 화면이 샘플링한다 ----

MOVES = tuple(MOVE_BASE)


def movement(dog: Dog, t: Tuning) -> dict:
    """평소 움직임 경향. 기분은 돌아가는 자리 대비로 본다 (검수 001)."""
    dev = {d: dog.mood[d] - REST[d] for d in MOODS}

    def mood_term(row):
        return t.move_scale * sum(w * dev[d] for d, w in row.items())
    weights = {c: round(MOVE_BASE[c] * math.exp(mood_term(MOVE_MOOD[c])), 4) for c in MOVES}
    return {"weights": weights, "mood": dominant_mood(dog, t),
            "run": round(_sigmoid(_logit(RUN_BASE) + mood_term(RUN_MOOD)), 4),
            "idle_scale": round(math.exp(mood_term(IDLE_MOOD)), 4)}


def movement_changed(old: dict | None, new: dict, t: Tuning) -> bool:
    """화면에 보낼 만큼 경향이 바뀌었나 (사람이 움직임 차이를 느낄 만한 크기)."""
    if old is None or old.get("mood") != new.get("mood"):  # 평소 모습을 정하는 기분이 바뀌면 바로 보낸다
        return True
    # 나누지 않고 곱해 비교한다: 기분이 극단이면 반올림한 가중치가 0이 된다 (2026-10-20 웹 두뇌 오류)
    if any(abs(new["weights"][c] - old["weights"][c]) > t.send_weight_ratio * old["weights"][c] for c in MOVES):
        return True
    return (abs(new["run"] - old["run"]) > t.send_run_delta
            or abs(new["idle_scale"] / old["idle_scale"] - 1) > t.send_idle_ratio)
