import pytest

from brain import model
from brain.tuning import MOODS, MOVE_BASE, Tuning

T = Tuning()


def neutral():
    return model.Dog(personality=model.Personality({d: 0.5 for d in MOODS}, {d: 0.5 for d in MOODS}, 0.5),
                     mood={d: 0.5 for d in MOODS}, intimacy=0.5, updated_at=0.0, day="2026-10-15")


def test_neutral_dog_gets_base_tendency():
    mv = model.movement(neutral(), T)
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
