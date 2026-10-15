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
    dog = model.default_dog(ts())  # 분노 기준값 0.1 → 반감기 1800 × (0.5 + 0.1) = 1080초
    dog.mood["분노"] = 0.9
    model.advance(dog, ts() + 1080, random.Random(0), QUIET)
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
    assert dog.personality.baseline["들뜸"] == pytest.approx(0.4 + 0.05 * (0.9 - 0.4))
    model.advance(dog, ts(16, 18), random.Random(0), QUIET)
    assert dog.personality.baseline["들뜸"] == pytest.approx(0.425)


def test_round_trip_through_json():
    dog = model.birth(random.Random(5), ts())
    data = json.loads(json.dumps(model.dog_to_dict(dog), ensure_ascii=False))
    assert model.dog_from_dict(data) == dog
