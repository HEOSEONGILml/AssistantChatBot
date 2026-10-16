import json
import random
from dataclasses import replace
from datetime import datetime

import pytest

from brain import model
from brain.tuning import BASELINE_RANGE, MOODS, SENS_RANGE, Tuning

T = Tuning()
QUIET = replace(T, mood_noise=0.0)


def ts(d=15, h=12):
    return datetime(2026, 10, d, h).timestamp()


def test_birth_is_random_within_ranges():
    a, b = model.birth(random.Random(1), ts()), model.birth(random.Random(2), ts())
    assert a.personality != b.personality
    for dog in (a, b):
        for d in MOODS:
            assert BASELINE_RANGE[0] <= dog.personality.baseline[d] <= BASELINE_RANGE[1]
            assert SENS_RANGE[0] <= dog.personality.sensitivity[d] <= SENS_RANGE[1]
        assert 0 <= dog.personality.whim <= 1
        assert dog.mood == dog.personality.baseline
        assert dog.intimacy == 0.3


def test_birth_mean_matches_default_personality():
    dogs = [model.birth(random.Random(i), ts()) for i in range(400)]
    assert abs(sum(x.personality.baseline["심심함"] for x in dogs) / 400 - 0.6) < 0.02


def test_zero_gap_keeps_mood():
    dog = model.default_dog(ts())
    dog.mood["분노"] = 0.9
    model.advance(dog, ts(), random.Random(0), T)
    assert dog.mood["분노"] == 0.9


def test_mood_halves_toward_baseline_in_half_life():
    dog = model.default_dog(ts())  # 분노 기준값 0.1 → 반감기 600 × (0.5 + 0.1) = 360초 (검수 001: 30분은 너무 길었다)
    dog.mood["분노"] = 0.9
    model.advance(dog, ts() + 360, random.Random(0), QUIET)
    assert dog.mood["분노"] == pytest.approx(0.5, abs=1e-6)


def test_higher_baseline_recovers_slower():
    low, high = model.default_dog(ts()), model.default_dog(ts())
    low.personality.baseline["분노"], high.personality.baseline["분노"] = 0.2, 0.8
    low.mood["분노"], high.mood["분노"] = 0.3, 0.9
    for dog in (low, high):
        model.advance(dog, ts() + 1800, random.Random(0), QUIET)
    assert (high.mood["분노"] - 0.8) / 0.1 > (low.mood["분노"] - 0.2) / 0.1


def test_long_gap_returns_near_baseline():
    dog = model.default_dog(ts())
    dog.mood = {d: 1.0 for d in MOODS}
    model.advance(dog, ts() + 3 * 86400, random.Random(3), T)
    for d in MOODS:
        assert 0 <= dog.mood[d] <= 1
        assert abs(dog.mood[d] - dog.personality.baseline[d]) < 0.25


def test_intimacy_cools_over_two_weeks():
    dog = model.default_dog(ts())
    dog.intimacy = 0.9
    model.advance(dog, ts() + 14 * 86400, random.Random(0), QUIET)
    assert dog.intimacy == pytest.approx(0.6, abs=1e-6)


def test_habit_recovers_with_time():
    dog = model.default_dog(ts())
    dog.habit["poke"] = 0.8
    model.advance(dog, ts() + 3600, random.Random(0), QUIET)
    assert dog.habit["poke"] == pytest.approx(0.4, abs=1e-6)


def test_drift_once_per_day_change():
    dog = model.default_dog(ts(15, 10))
    for _ in range(10):
        dog.mood["들뜸"] = 0.9
        model.record_mood(dog)
    model.advance(dog, ts(16, 9), random.Random(0), QUIET)
    assert dog.personality.baseline["들뜸"] == pytest.approx(0.4 + 0.025 * (0.9 - 0.4))
    model.advance(dog, ts(16, 18), random.Random(0), QUIET)
    assert dog.personality.baseline["들뜸"] == pytest.approx(0.4125)


def test_round_trip_through_json():
    dog = model.birth(random.Random(5), ts())
    data = json.loads(json.dumps(model.dog_to_dict(dog), ensure_ascii=False))
    assert model.dog_from_dict(data) == dog


def test_personality_keeps_some_temperament():
    # 매일 같은 기분으로 지내도 타고난 기질 쪽으로 되돌아가는 힘 때문에 경험 쪽으로 끝까지 가지 않는다 (시뮬레이션에서 발견)
    dog = model.default_dog(ts(1, 10))
    assert dog.personality.temperament["들뜸"] == 0.4
    for day in range(1, 200):
        for _ in range(10):
            dog.mood["들뜸"] = 0.9
            model.record_mood(dog)
        dog.day = f"day-{day}"  # 날이 바뀐 것으로 만든다
        model.advance(dog, dog.updated_at, random.Random(0), QUIET)
    assert dog.personality.baseline["들뜸"] == pytest.approx(0.65, abs=0.01)


def test_old_saved_dog_gets_temperament_from_baseline():
    data = model.dog_to_dict(model.default_dog(ts()))
    del data["personality"]["temperament"]
    assert model.dog_from_dict(data).personality.temperament == data["personality"]["baseline"]


def test_saved_dog_missing_habit_keys_gets_defaults():
    data = model.dog_to_dict(model.default_dog(ts()))
    data["habit"] = {"poke": 0.5}
    dog = model.dog_from_dict(data)
    assert dog.habit == {"poke": 0.5, "pet": 0.0, "throw": 0.0, "typing": 0.0}


def test_nine_moods():
    dog = model.default_dog(ts())
    assert list(dog.mood) == ["심심함", "졸림", "들뜸", "시무룩", "분노", "궁금함", "놀람", "무서움", "행복"]
    assert dog.mood["궁금함"] == 0.5 and dog.mood["행복"] == 0.4


def test_old_saved_dog_with_five_moods_gets_new_moods():
    data = model.dog_to_dict(model.default_dog(ts()))
    for key in ("mood", "day_sum"):
        data[key] = {k: v for k, v in data[key].items() if k not in ("궁금함", "놀람", "무서움")}
    for key in ("baseline", "sensitivity", "temperament"):
        data["personality"][key] = {k: v for k, v in data["personality"][key].items() if k not in ("궁금함", "놀람", "무서움")}
    dog = model.dog_from_dict(data)
    assert set(dog.mood) == set(MOODS) and dog.personality.baseline["궁금함"] == 0.5


# ---- 시간 감각 (스펙 2026-10-16 시간 모형, 검수 001) ----


def test_poke_irritation_mostly_gone_in_ten_minutes():
    dog = model.default_dog(ts())
    dog.mood["분노"] = 0.5  # 찔려서 크게 짜증 남 (기준값 0.1)
    model.advance(dog, ts() + 600, random.Random(0), QUIET)
    assert dog.mood["분노"] - 0.1 < 0.4 * 0.35  # 10분이면 초과분이 3분의 1 아래로


def test_surprise_fades_within_a_minute_or_two():
    dog = model.default_dog(ts())
    dog.mood["놀람"] = 0.6
    model.advance(dog, ts() + 120, random.Random(0), QUIET)
    assert dog.mood["놀람"] < 0.25


def test_sleepy_at_night_not_in_the_afternoon():
    night, day = model.default_dog(ts(15, 23)), model.default_dog(ts(15, 11))
    model.advance(night, ts(16, 3), random.Random(0), QUIET)
    model.advance(day, ts(15, 15), random.Random(0), QUIET)
    assert night.mood["졸림"] > 0.5 > 0.2 > day.mood["졸림"]
    assert model.dominant_mood(night, T) == "sleepy"
    assert night.mood["들뜸"] < day.mood["들뜸"]


def test_circadian_does_not_shift_the_daily_mean():
    hours = [model.circadian(h) for h in range(24)]
    assert sum(hours) / 24 == pytest.approx(0.0, abs=1e-9)
    assert max(hours) == model.circadian(3) and min(hours) == model.circadian(15)


def test_fear_pulls_excitement_down_over_time():
    # 반대 기분은 시간 위에서도 서로 누른다: 겁먹은 동안 들뜸이 돌아갈 자리도 내려간다 (검수 004)
    dog = model.default_dog(ts())
    dog.personality.baseline["들뜸"] = dog.mood["들뜸"] = 0.7
    dog.mood["무서움"] = 0.8
    model.advance(dog, ts() + 600, random.Random(0), QUIET)
    assert dog.mood["들뜸"] < 0.5
