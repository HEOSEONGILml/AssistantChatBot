import pytest

from brain import model
from brain.tuning import MOODS, MOVE_BASE, Tuning

T = Tuning()


def neutral():
    return model.Dog(personality=model.Personality({d: 0.5 for d in MOODS}, {d: 0.5 for d in MOODS}, 0.5),
                     mood={d: 0.5 for d in MOODS}, intimacy=0.5, updated_at=0.0, day="2026-10-15")


def test_average_dog_gets_base_tendency():
    # 성격의 평소 수준은 탄생 평균 대비로 본다: 탄생 평균 성격, 기분 = 기준값, 친밀도 0.5면 기본값 그대로 (검수 003)
    from brain.tuning import BIRTH_BASELINE
    dog = neutral()
    dog.personality.baseline = dict(BIRTH_BASELINE)
    dog.mood = dict(BIRTH_BASELINE)
    mv = model.movement(dog, T)
    assert mv["mood"] == "calm"
    assert mv["weights"] == pytest.approx(MOVE_BASE)
    assert mv["run"] == pytest.approx(0.2)
    assert mv["idle_scale"] == pytest.approx(1.0)


def test_sleepy_dog_rests_more_and_plays_less():
    dog = neutral()
    dog.mood["졸림"] = 0.95
    base, mv = model.movement(neutral(), T), model.movement(dog, T)
    assert mv["weights"]["sleep"] > base["weights"]["sleep"]
    assert mv["weights"]["rest"] > base["weights"]["rest"]
    assert mv["weights"]["play"] < base["weights"]["play"]
    assert mv["run"] < base["run"]
    assert mv["idle_scale"] > 1


def test_excited_dog_plays_and_runs():
    dog = neutral()
    dog.mood["들뜸"] = 0.95
    mv = model.movement(dog, T)
    assert mv["weights"]["play"] > MOVE_BASE["play"]
    assert mv["run"] > 0.2


def test_close_dog_approaches_more():
    dog = neutral()
    dog.intimacy = 0.95
    assert model.movement(dog, T)["weights"]["approach"] > MOVE_BASE["approach"]


def test_changed_threshold():
    a = model.movement(neutral(), T)
    small, big = neutral(), neutral()
    small.mood["졸림"] = 0.52
    big.mood["졸림"] = 0.8
    assert model.movement_changed(None, a, T)
    assert not model.movement_changed(a, model.movement(small, T), T)
    assert model.movement_changed(a, model.movement(big, T), T)


def test_scared_dog_hides_and_reports_mood():
    dog = neutral()
    dog.mood["무서움"] = 0.95
    mv = model.movement(dog, T)
    assert mv["mood"] == "scared"
    assert mv["weights"]["rest"] > MOVE_BASE["rest"] and mv["weights"]["approach"] < MOVE_BASE["approach"]


# ---- 기분별 움직임이 눈에 보일 만큼 (검수 001, 사용자 K-5) ----

def calm_avg():
    from brain.tuning import BIRTH_BASELINE
    return model.Dog(personality=model.Personality(dict(BIRTH_BASELINE), {d: 0.5 for d in MOODS}, 0.5),
                     mood=dict(BIRTH_BASELINE), intimacy=0.3, updated_at=0.0, day="2026-10-15")


def share(mv, moves):
    w = mv["weights"]
    return sum(w[c] for c in moves) / sum(w.values())


def test_excited_dog_visibly_runs_and_plays():
    calm, ex = calm_avg(), calm_avg()
    ex.mood["들뜸"] += 0.3
    a, b = model.movement(calm, T), model.movement(ex, T)
    assert share(b, ["play", "roam"]) > 1.5 * share(a, ["play", "roam"])
    assert b["run"] >= 0.45 > a["run"]


def test_sleepy_dog_mostly_rests():
    dog = calm_avg()
    dog.mood["졸림"] += 0.3
    mv = model.movement(dog, T)
    assert share(mv, ["rest", "sleep"]) > 0.6
    assert mv["idle_scale"] > 2


def test_bored_dog_wanders():
    calm, bored = calm_avg(), calm_avg()
    bored.mood["심심함"] += 0.3
    assert share(model.movement(bored, T), ["roam", "explore"]) > 1.4 * share(model.movement(calm, T), ["roam", "explore"])


def test_scared_dog_keeps_away():
    calm, scared = calm_avg(), calm_avg()
    scared.mood["무서움"] += 0.3
    assert share(model.movement(scared, T), ["approach", "play"]) < 0.5 * share(model.movement(calm, T), ["approach", "play"])


def test_sleepy_dog_naps_visibly():
    dog = calm_avg()
    dog.mood["졸림"] += 0.3
    assert share(model.movement(dog, T), ["sleep"]) > 0.25


# ---- 검수 003: 성격이 평소 움직임에 보이고, 행복은 느긋하게, 화나면 피한다 ----

def archetype(name):
    from sim.simulate import archetype_dog
    return archetype_dog(name)


def test_personality_shows_in_everyday_running_and_resting():
    lively, calm = model.movement(archetype("활발·변덕쟁이"), T), model.movement(archetype("과묵·차분"), T)
    assert lively["run"] >= 0.4 and calm["run"] <= 0.15
    assert share(calm, ["rest", "sleep"]) > 1.5 * share(lively, ["rest", "sleep"])
    assert share(lively, ["play", "roam"]) > 1.3 * share(calm, ["play", "roam"])


def test_happy_dog_stays_close_and_relaxed_not_running():
    calm, happy = calm_avg(), calm_avg()
    happy.mood["행복"] += 0.3
    a, b = model.movement(calm, T), model.movement(happy, T)
    assert b["run"] <= a["run"] + 0.02
    assert share(b, ["approach"]) > 1.5 * share(a, ["approach"])
    assert b["idle_scale"] >= 1.0


def test_annoyed_dog_keeps_away():
    calm, angry = calm_avg(), calm_avg()
    angry.mood["분노"] += 0.4
    a, b = model.movement(calm, T), model.movement(angry, T)
    assert share(b, ["approach"]) < 0.5 * share(a, ["approach"])
    assert share(b, ["roam", "explore"]) > share(a, ["roam", "explore"])
