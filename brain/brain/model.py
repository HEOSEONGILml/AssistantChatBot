"""확률 모델 (두뇌 스펙 v2 4·6·6.5절). 화면·전송·저장을 모르는 순수 함수다. 시각과 난수는 인자로 받는다."""
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime

from .tuning import (BASELINE_RANGE, BIRTH_BASELINE, BIRTH_SD, BIRTH_SENS, BIRTH_WHIM, HABIT_KINDS,
                     INTIMACY_START, MOODS, SENS_RANGE, SENS_SD, WHIM_SD, Tuning)

LN2 = math.log(2)


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class Personality:
    baseline: dict[str, float]      # 기분마다 기준값: 아무 일 없을 때 돌아가는 값. 겪은 일로 천천히 변한다
    sensitivity: dict[str, float]   # 기분마다 민감도: 같은 일에 움직이는 폭. 태어날 때 고정
    whim: float                     # 변덕: 뽑기 온도. 태어날 때 고정


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


def half_life(t: Tuning, mood: str, baseline: float) -> float:
    # 기준값이 높은 기분일수록 늦게 풀린다 (사용자 결정: 반감기도 기존 성격에서)
    return t.half_life_s[mood] * (0.5 + baseline)


def advance(dog: Dog, now: float, rng, t: Tuning) -> None:
    """지난 갱신 뒤로 흐른 시간만큼 기분·친밀도·습관화를 평균 회귀시키고, 날이 바뀌었으면 기준값을 옮긴다."""
    dt = now - dog.updated_at
    if dt > 0:
        for d in MOODS:
            mu = dog.personality.baseline[d]
            e = math.exp(-LN2 / half_life(t, d, mu) * dt)
            dog.mood[d] = clip(mu + (dog.mood[d] - mu) * e + t.mood_noise * math.sqrt(1 - e * e) * rng.gauss(0, 1))
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
                b[d] = clip(b[d] + t.drift_rate * (dog.day_sum[d] / dog.day_count - b[d]), *BASELINE_RANGE)
        dog.day, dog.day_sum, dog.day_count = today, {d: 0.0 for d in MOODS}, 0


def record_mood(dog: Dog) -> None:
    """하루 기분 평균에 지금 기분을 더한다 (기분 시계가 일정 간격으로 부른다)."""
    for d in MOODS:
        dog.day_sum[d] += dog.mood[d]
    dog.day_count += 1


def dog_to_dict(dog: Dog) -> dict:
    return asdict(dog)


def dog_from_dict(data: dict) -> Dog:
    data = dict(data)
    return Dog(personality=Personality(**data.pop("personality")), **data)
