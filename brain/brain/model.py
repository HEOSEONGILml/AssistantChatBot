"""확률 모델 (두뇌 스펙 v2 4·6·6.5절). 화면·전송·저장을 모르는 순수 함수다. 시각과 난수는 인자로 받는다."""
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime

from .tuning import (IDLE_BASELINE, RUN_BASELINE, RELATION_MOOD, CIRCADIAN, CIRCADIAN_PEAK_HOUR, ACTION_BASE, EVENT_ACTION, JEV_WEIGHT, JEV_WEIGHT_OTHER, OPPOSITES, appraisal, appraisal_intimacy, BASELINE_RANGE, BIRTH_BASELINE, BIRTH_SD, BIRTH_SENS, BIRTH_WHIM, HABIT_KINDS,
                     IDLE_MOOD, INTIMACY_START, MOOD_ACTION, MOOD_REACTION_ID, MOODS, MOVE_BASE, MOVE_BASELINE,
                     MOVE_INTIMACY, MOVE_MOOD, REACTION_ACTION, RUN_BASE, RUN_MOOD, SENS_RANGE, SENS_SD,
                     TALK_BASELINE, TALK_MOOD, WHIM_SD, Tuning)

LN2 = math.log(2)


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class Personality:
    baseline: dict[str, float]      # 기분마다 기준값: 아무 일 없을 때 돌아가는 값. 겪은 일로 천천히 변한다
    sensitivity: dict[str, float]   # 기분마다 민감도: 같은 일에 움직이는 폭. 태어날 때 고정
    whim: float                     # 변덕: 뽑기 온도. 태어날 때 고정
    temperament: dict[str, float] = field(default_factory=dict)  # 타고난 기질: 태어날 때의 기준값. 기준값이 아주 약하게 되돌아가는 자리

    def __post_init__(self):
        if not self.temperament:  # 기질이 없던 예전 저장본은 지금 기준값을 기질로 본다
            self.temperament = dict(self.baseline)


@dataclass
class Dog:
    personality: Personality
    mood: dict[str, float]
    intimacy: float
    updated_at: float
    day: str                        # 기분 하루 평균을 모으는 날 (YYYY-MM-DD)
    day_sum: dict[str, float] = field(default_factory=lambda: {d: 0.0 for d in MOODS})
    day_count: int = 0
    habit: dict[str, float] = field(default_factory=lambda: {k: 0.0 for k in HABIT_KINDS})


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _new(p: Personality, now: float) -> Dog:
    return Dog(personality=p, mood=dict(p.baseline), intimacy=INTIMACY_START, updated_at=now, day=_day(now))


def default_dog(now: float) -> Dog:
    """탄생 분포의 평균. 저장된 상태를 읽지 못했을 때 쓴다."""
    return _new(Personality(dict(BIRTH_BASELINE), {d: BIRTH_SENS for d in MOODS}, BIRTH_WHIM), now)


def birth(rng, now: float) -> Dog:
    return _new(Personality(
        baseline={d: clip(rng.gauss(BIRTH_BASELINE[d], BIRTH_SD), *BASELINE_RANGE) for d in MOODS},
        sensitivity={d: clip(rng.gauss(BIRTH_SENS, SENS_SD), *SENS_RANGE) for d in MOODS},
        whim=clip(rng.gauss(BIRTH_WHIM, WHIM_SD))), now)


def circadian(hour: float) -> float:
    """하루 리듬값: 새벽 3시 +0.5, 오후 3시 −0.5, 하루 평균 0."""
    return 0.5 * math.cos(2 * math.pi * (hour - CIRCADIAN_PEAK_HOUR) / 24)


def rest_point(dog: "Dog", mood: str, ts: float, push: float = 0.0) -> float:
    """기분이 돌아가는 자리: 기준값 + 하루 리듬 (시간 모형 스펙) − 반대 기분이 누르는 만큼(push, 검수 004)."""
    dt = datetime.fromtimestamp(ts)
    base = clip(dog.personality.baseline[mood] + CIRCADIAN.get(mood, 0.0) * circadian(dt.hour + dt.minute / 60))
    return max(0.25 * base, base - push)  # 눌려도 자리의 4분의 1 아래로는 내려가지 않는다(0에 붙지 않게)


def half_life(t: Tuning, mood: str, baseline: float) -> float:
    # 기준값이 높은 기분일수록 늦게 풀린다 (사용자 결정: 반감기도 기존 성격에서)
    return t.half_life_s[mood] * (0.5 + baseline)


def advance(dog: Dog, now: float, rng, t: Tuning) -> None:
    """지난 갱신 뒤로 흐른 시간만큼 기분·친밀도·습관화를 평균 회귀시키고, 날이 바뀌었으면 기준값을 옮긴다."""
    dt = now - dog.updated_at
    if dt > 0:
        b, m0 = dog.personality.baseline, dict(dog.mood)
        lam = {d: LN2 / half_life(t, d, b[d]) for d in MOODS}
        # 반대 기분이 기준값보다 높은 만큼 돌아갈 자리를 누른다: 겁먹은 동안 들뜸도 가라앉는다 (검수 004).
        # 그 높은 정도도 이 시간 동안 풀리므로 구간 평균(1 − e^−λΔt)/(λΔt)을 쓴다
        avg = {d: (1 - math.exp(-lam[d] * dt)) / (lam[d] * dt) for d in MOODS}
        push = {d: 0.0 for d in MOODS}
        for a, c in OPPOSITES:
            push[c] += t.rest_inhibit * max(0.0, m0[a] - b[a]) * avg[a]
            push[a] += t.rest_inhibit * max(0.0, m0[c] - b[c]) * avg[c]
        for d in MOODS:
            mu = rest_point(dog, d, now, push[d])
            e = math.exp(-lam[d] * dt)
            dog.mood[d] = clip(mu + (m0[d] - mu) * e + t.mood_noise * math.sqrt(1 - e * e) * rng.gauss(0, 1))
        e = math.exp(-LN2 / t.intimacy_half_life_s * dt)
        dog.intimacy = clip(INTIMACY_START + (dog.intimacy - INTIMACY_START) * e)
        e = math.exp(-LN2 / t.habit_half_life_s * dt)
        dog.habit = {k: h * e for k, h in dog.habit.items()}
        dog.updated_at = now
    today = _day(now)
    if today != dog.day:
        if dog.day_count:
            b = dog.personality.baseline
            for d in MOODS:
                # 겪은 일(어제 기분 평균) 쪽으로 끌리고, 타고난 기질 쪽으로 약하게 되돌아간다: 개성이 경험에 다 지워지지 않게
                mean = dog.day_sum[d] / dog.day_count
                pull = dog.personality.temperament[d] - b[d]
                b[d] = clip(b[d] + t.drift_rate * (mean - b[d]) + t.temperament_pull * pull, *BASELINE_RANGE)
        dog.day, dog.day_sum, dog.day_count = today, {d: 0.0 for d in MOODS}, 0


def record_mood(dog: Dog) -> None:
    """하루 기분 평균에 지금 기분을 더한다 (기분 시계가 일정 간격으로 부른다)."""
    for d in MOODS:
        dog.day_sum[d] += dog.mood[d]
    dog.day_count += 1


def dog_to_dict(dog: Dog) -> dict:
    return asdict(dog)


def dog_from_dict(data: dict) -> Dog:
    """저장본에서 강아지를 만든다. 모양이 어긋나면 TypeError·KeyError·ValueError가 난다(부르는 쪽이 처리)."""
    data = dict(data)
    p = dict(data.pop("personality"))
    # 기분 차원이 늘면(5개 → 8개) 새 차원을 탄생 평균값으로 채운다
    for key, default in (("baseline", BIRTH_BASELINE), ("sensitivity", {d: BIRTH_SENS for d in MOODS}), ("temperament", BIRTH_BASELINE)):
        if key in p or key != "temperament":
            p[key] = {**default, **p.get(key, {})}
    data["mood"] = {**{d: p["baseline"][d] for d in MOODS}, **data.get("mood", {})}
    data["day_sum"] = {**{d: 0.0 for d in MOODS}, **data.get("day_sum", {})}
    dog = Dog(personality=Personality(**p), **data)
    dog.habit = {**{k: 0.0 for k in HABIT_KINDS}, **dog.habit}  # 습관화 대상이 늘어도 예전 저장본을 읽는다
    return dog


# ---- 어휘 (프로토콜 v2) ----

REACTIONS = (*MOOD_REACTION_ID.values(), "none")
ACTIONS = ("stand", "sit", "lie_down", "sleep", "beg", "bark", "none")
REACTION_NAMES = {"bored": "지루함", "sleepy": "하품", "excited": "신남", "sad": "서운함", "annoyed": "짜증",
                  "curious": "궁금함", "surprised": "놀람", "scared": "무서움", "happy": "행복", "none": "없음"}
ACTION_NAMES = {"stand": "서기", "sit": "앉기", "lie_down": "엎드리기", "sleep": "잠", "beg": "조르기", "bark": "짖기", "none": "없음"}


def _log(p: float) -> float:
    return math.log(max(p, 1e-6))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _logit(p: float) -> float:
    p = clip(p, 1e-4, 1 - 1e-4)
    return math.log(p / (1 - p))


def _affinity(row: dict[str, float], values: dict[str, float]) -> float:
    return sum(w * (values[d] - 0.5) for d, w in row.items())


# ---- 뽑기: 점수 = Jev 로그확률 / 온도 + 우리 모형 보정 (스펙 6절) ----

def temperature(dog: Dog) -> float:
    return 0.5 + dog.personality.whim


def reaction_from(deltas: dict[str, float], kinds: list[str], t: Tuning) -> str:
    """반응 = 이번에 가장 크게 오른 기분의 표출 (기분 8개 스펙 3절). 타이핑 판단은 늘 반응을 하나 낸다.
    apply_change의 결과를 받으면 잡음을 뺀 신호로 뽑는다(잡음만으로 반응이 뜨지 않게, 검수 002)."""
    deltas = getattr(deltas, "signal", deltas)
    mood, rise = max(((d, deltas.get(d, 0.0)) for d in MOODS), key=lambda x: x[1])
    if rise >= t.react_threshold:
        return MOOD_REACTION_ID[mood]
    if "typing" in kinds:  # 타이핑하는 동안 반응을 더 많이 (사용자 요청)
        return MOOD_REACTION_ID[mood] if rise > 0 else "curious"
    return "none"


def dominant_mood(dog: Dog, t: Tuning) -> str:
    """평소 모습을 정하는 기분: 기준값보다 가장 많이 높은 기분. 충분히 높지 않으면 calm."""
    mood, rise = max(((d, dog.mood[d] - dog.personality.baseline[d]) for d in MOODS), key=lambda x: x[1])
    return MOOD_REACTION_ID[mood] if rise >= t.dominant_threshold else "calm"


def action_scores(jev: dict[str, float], dog: Dog, reaction: str, kinds: list[str], t: Tuning) -> dict[str, float]:
    """동작 점수 (동작 모형 스펙): 기본 + 이벤트 사전값 + 기분(기준값 대비) + 반응 + Jev 약한 조정, 온도로 나눈다."""
    T = temperature(dog)
    m, b = dog.mood, dog.personality.baseline
    scores = {}
    for a in ACTIONS:
        x = (ACTION_BASE.get(a, 0.0) + sum(EVENT_ACTION.get(k, {}).get(a, 0.0) for k in kinds)
             + t.w_mood * sum(w * (m[d] - b[d]) for d, w in MOOD_ACTION.get(a, {}).items())
             + t.w_react * REACTION_ACTION.get(reaction, {}).get(a, 0)
             + t.w_jev_action * math.log(jev.get(a, 0.0) + t.jev_action_floor))
        if a == "sleep" and m["졸림"] - b["졸림"] < t.sleep_gate:
            x -= 10.0  # 평소보다 졸리지 않으면 자지 않는다. 변덕(온도)으로도 뒤집히지 않게 크게 (검수 003)
        scores[a] = x / T
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


# ---- 말하기 (스펙 6절 3) ----

def talkativeness(dog: Dog, t: Tuning) -> float:
    """말수는 독립 파라미터가 아니라 친밀도·지금 기분·기준값에서 계산한다 (사용자 결정)."""
    return t.talk_scale * ((dog.intimacy - 0.5) + _affinity(TALK_MOOD, dog.mood)
                           + _affinity(TALK_BASELINE, dog.personality.baseline))


def speak_probability(p_jev: float, dog: Dog, kind: str, streak: int, waiting: bool, t: Tuning) -> float:
    if streak >= t.max_streak:
        return 0.0
    x = (_logit(p_jev) + talkativeness(dog, t) + t.kind_bias.get(kind, 0.0)
         - t.streak_penalty * streak - (t.waiting_penalty if waiting else 0.0))
    return _sigmoid(x)


# ---- 기분·친밀도 변화와 습관화 (스펙 4.3·4.5) ----

def habit_level(dog: Dog, kinds: list[str]) -> float:
    return max((dog.habit[k] for k in kinds if k in HABIT_KINDS), default=0.0)


class Change(dict):
    """기분 변화(실제로 움직인 양). .signal은 잡음을 뺀 신호(사전값 + Jev)로 반응을 뽑는 데 쓴다 (검수 002)."""
    signal: dict[str, float]


def _combine(xs: list[float]) -> float:
    """같은 기분에 온 충격들을 확률의 합처럼 합친다: 연타가 몇 배로 쌓이지 않는다 (검수 002)."""
    up = 1.0 - math.prod(1 - min(x, 0.99) for x in xs if x > 0)
    down = 1.0 - math.prod(1 - min(-x, 0.99) for x in xs if x < 0)
    return up - down


def apply_change(dog: Dog, change: dict[str, float], events: list[tuple[str, dict]], rng, t: Tuning,
                 waiting: bool = False, alone_s: float = 0.0) -> Change:
    """기분 변화 (평가 사전값 스펙 + 기분 갱신 수식 스펙): 이벤트마다 사전값(대상 기분만 습관화)을 모아 포화 합산하고,
    Jev 조정을 더한 뒤 반대 기분을 억제한다. 기분에는 흔들림을 더해 남은 여유에 비례해 움직인다."""
    kinds = [k for k, _ in events]
    damp = 1 - habit_level(dog, kinds)   # 친밀도 조정에 쓰는 습관화 (묶음 시작 때)
    # Jev 조정도 습관화 대상 기분만 줄인다 (검수 002: 타이핑의 궁금함만 무뎌지고 글 내용의 기분은 남게)
    jev_damp = {d: 1 - max((dog.habit[k] for k in kinds if HABIT_KINDS.get(k) == d), default=0.0) for d in MOODS}
    w = JEV_WEIGHT.get(kinds[-1], JEV_WEIGHT_OTHER) if kinds else JEV_WEIGHT_OTHER
    sens = dog.personality.sensitivity
    m, b = dog.mood, dog.personality.baseline
    # 화나거나 무서운 정도(절대 수준): 성마른 강아지(분노 기준값이 높음)는 평소에도 잘 안 풀린다 (검수 004)
    wary = min(1.0, 2 * max(0.0, max(m["분노"], m["무서움"]) - 0.15))
    parts: dict[str, list[float]] = {d: [] for d in MOODS}
    for k, ctx in events:
        h = dog.habit.get(k, 0.0)
        for d, v in appraisal(k, ctx or {}, h, wary, waiting, alone_s).items():
            parts[d].append(v * 2 * sens[d] * ((1 - h) if HABIT_KINDS.get(k) == d else 1.0))
        if k in HABIT_KINDS:  # 같은 자극이 오면 익숙해진다. 민감한 강아지일수록 천천히 (사용자 결정). 묶음 안에서도 쌓인다
            lam = t.habit_rate * (1.5 - sens[HABIT_KINDS[k]])
            dog.habit[k] += lam * (1 - dog.habit[k])
    jev = {d: change.get(f"{d}↑", 0.0) - change.get(f"{d}↓", 0.0) for d in MOODS}
    for rel, moods in RELATION_MOOD.items():  # 거절은 서운함, 다정함은 행복 (관계 해석, 검수 002)
        for d, r in moods.items():
            jev[d] += r * change.get(rel, 0.0)
    signal = {d: _combine(parts[d]) + t.change_k * w * jev[d] * 2 * sens[d] * jev_damp[d] for d in MOODS}
    rises = dict(signal)
    for a, c in OPPOSITES:  # 한쪽이 오른 만큼 반대쪽이 내린다
        signal[c] -= t.inhibit * max(rises[a], 0.0)
        signal[a] -= t.inhibit * max(rises[c], 0.0)
    deltas = Change()
    for d in MOODS:
        x = signal[d] + rng.gauss(0, t.change_noise)
        before = m[d]
        m[d] = clip(before + (x * (1 - before) if x > 0 else x * before))  # 끝에 가까울수록 덜 움직인다
        deltas[d] = m[d] - before
    deltas.signal = signal
    delta = (t.intimacy_k * w * (change.get("친밀도↑", 0.0) - change.get("친밀도↓", 0.0))
             + sum(appraisal_intimacy(k, ctx or {}) for k, ctx in events)) * damp
    dog.intimacy = clip(dog.intimacy + delta)
    deltas["친밀도"] = delta
    return deltas


# ---- 평소 움직임 경향 (스펙 6.5): 두뇌가 계산하고 화면이 샘플링한다 ----

MOVES = tuple(MOVE_BASE)


def movement(dog: Dog, t: Tuning) -> dict:
    """평소 움직임 경향. 기분은 기준값 대비(하루 리듬 포함)로 크게, 성격은 기준값으로 작게 (검수 001, K-5)."""
    m, b = dog.mood, dog.personality.baseline
    dev = {d: m[d] - b[d] for d in MOODS}

    def mood_term(row):
        return sum(w * dev[d] for d, w in row.items())

    def trait_term(row):  # 성격의 평소 수준: 탄생 평균 대비
        return t.move_personality * sum(w * (b[d] - BIRTH_BASELINE[d]) for d, w in row.items())
    weights = {}
    for c in MOVES:
        x = (t.move_scale * mood_term(MOVE_MOOD[c]) + trait_term(MOVE_BASELINE.get(c, {}))
             + MOVE_INTIMACY.get(c, 0) * (dog.intimacy - 0.5))
        weights[c] = round(MOVE_BASE[c] * math.exp(x), 4)
    return {"weights": weights, "mood": dominant_mood(dog, t),
            "run": round(_sigmoid(_logit(RUN_BASE) + t.move_scale * mood_term(RUN_MOOD) + trait_term(RUN_BASELINE)), 4),
            "idle_scale": round(math.exp(t.move_scale * mood_term(IDLE_MOOD) + trait_term(IDLE_BASELINE)), 4)}


def movement_changed(old: dict | None, new: dict, t: Tuning) -> bool:
    """화면에 보낼 만큼 경향이 바뀌었나 (사람이 움직임 차이를 느낄 만한 크기)."""
    if old is None or old.get("mood") != new.get("mood"):  # 평소 모습을 정하는 기분이 바뀌면 바로 보낸다
        return True
    if any(abs(new["weights"][c] / old["weights"][c] - 1) > t.send_weight_ratio for c in MOVES):
        return True
    return (abs(new["run"] - old["run"]) > t.send_run_delta
            or abs(new["idle_scale"] / old["idle_scale"] - 1) > t.send_idle_ratio)
