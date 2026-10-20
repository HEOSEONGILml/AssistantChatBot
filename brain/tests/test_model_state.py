import json
import math
from datetime import datetime

import pytest

from brain import model
from brain.tuning import MOODS, REST, Tuning

T = Tuning()


def ts(d=15, h=12):
    return datetime(2026, 10, d, h).timestamp()


def test_new_dog_starts_at_rest():
    dog = model.new_dog(ts())
    assert dog.mood == REST and dog.updated_at == ts()


def test_zero_gap_keeps_mood():
    dog = model.new_dog(ts())
    dog.mood["분노"] = 0.9
    model.advance(dog, ts(), T)
    assert dog.mood["분노"] == 0.9


def test_mood_halves_toward_rest_in_half_life():
    dog = model.new_dog(ts())  # 분노 반감기 360초 (검수 001: 30분은 너무 길었다)
    dog.mood["분노"] = 0.9
    model.advance(dog, ts() + 360, T)
    assert dog.mood["분노"] == pytest.approx(0.5, abs=1e-6)


def test_long_gap_returns_near_rest():
    dog = model.new_dog(ts())
    dog.mood = {d: 1.0 for d in MOODS}
    model.advance(dog, ts() + 3 * 86400, T)
    for d in MOODS:
        assert 0 <= dog.mood[d] <= 1
        assert abs(dog.mood[d] - REST[d]) < 0.25


def test_round_trip_through_json():
    dog = model.new_dog(ts())
    dog.mood["분노"] = 0.7
    data = json.loads(json.dumps(model.dog_to_dict(dog), ensure_ascii=False))
    assert model.dog_from_dict(data) == dog


def test_old_saved_dog_keeps_only_mood():
    # 예전 저장본의 성격·친밀도·습관화·하루 평균은 버린다 (단순화 스펙 3절)
    data = {"personality": {"baseline": dict(REST), "sensitivity": dict(REST), "whim": 0.5}, "mood": {**REST, "분노": 0.7},
            "intimacy": 0.4, "updated_at": ts(), "day": "2026-10-15", "day_sum": {}, "day_count": 0, "habit": {"poke": 0.5}}
    dog = model.dog_from_dict(data)
    assert dog == model.Dog(mood={**REST, "분노": 0.7}, updated_at=ts())


def test_nine_moods():
    dog = model.new_dog(ts())
    assert list(dog.mood) == ["심심함", "졸림", "들뜸", "시무룩", "분노", "궁금함", "놀람", "무서움", "행복"]
    assert dog.mood["궁금함"] == 0.5 and dog.mood["행복"] == 0.4


def test_old_saved_dog_with_five_moods_gets_new_moods():
    data = model.dog_to_dict(model.new_dog(ts()))
    data["mood"] = {k: v for k, v in data["mood"].items() if k not in ("궁금함", "놀람", "무서움")}
    dog = model.dog_from_dict(data)
    assert set(dog.mood) == set(MOODS) and dog.mood["궁금함"] == 0.5


# ---- 시간 감각 (스펙 2026-10-16 시간 모형, 검수 001) ----


def test_poke_irritation_mostly_gone_in_ten_minutes():
    dog = model.new_dog(ts())
    dog.mood["분노"] = 0.5  # 찔려서 크게 짜증 남 (자리 0.1)
    model.advance(dog, ts() + 600, T)
    assert dog.mood["분노"] - 0.1 < 0.4 * 0.35  # 10분이면 초과분이 3분의 1 아래로


def test_surprise_fades_within_a_minute_or_two():
    dog = model.new_dog(ts())
    dog.mood["놀람"] = 0.6
    model.advance(dog, ts() + 120, T)
    assert dog.mood["놀람"] < 0.25


def test_advance_has_no_noise_and_follows_half_life_exactly():
    # 흔들림·하루 리듬·반대 기분 누르기 없이 기분별 반감기로 REST에 돌아간다 (0020)
    dog = model.new_dog(ts())
    dog.mood = {d: 1.0 for d in MOODS}
    model.advance(dog, ts() + 600, T)
    for d in MOODS:
        expected = REST[d] + (1.0 - REST[d]) * math.exp(-math.log(2) / T.half_life_s[d] * 600)
        assert dog.mood[d] == pytest.approx(expected, abs=1e-12)


def test_dog_at_rest_stays_at_rest_any_time_of_day():
    dog = model.new_dog(ts(15, 23))
    model.advance(dog, ts(16, 3), T)
    assert dog.mood == pytest.approx(REST)
