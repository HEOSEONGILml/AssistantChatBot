import random
from dataclasses import replace

import pytest

from brain import model
from brain.tuning import MOODS, Tuning

T = Tuning()
ZERO = replace(T, kind_bias={k: 0.0 for k in T.kind_bias})  # 이벤트 종류별 보정 없이 식만 본다


def neutral(**kw):
    """기분·기준값·친밀도가 모두 0.5라 우리 모형 보정이 0인 강아지."""
    dog = model.Dog(personality=model.Personality({d: 0.5 for d in MOODS}, {d: 0.5 for d in MOODS}, kw.pop("whim", 0.5)),
                    mood={d: 0.5 for d in MOODS}, intimacy=0.5, updated_at=0.0, day="2026-10-15")
    for k, v in kw.items():
        setattr(dog, k, v)
    return dog


JEV = {"joy": 0.6, "curious": 0.3, "none": 0.1}


def test_whim_controls_temperature():
    sharp = model.probabilities(model.reaction_scores(JEV, neutral(whim=0.0), 0.0, T))
    flat = model.probabilities(model.reaction_scores(JEV, neutral(whim=1.0), 0.0, T))
    assert sharp["joy"] == pytest.approx(0.78, abs=0.01)
    assert flat["joy"] == pytest.approx(0.52, abs=0.01)


def test_mood_tilts_reaction():
    angry = neutral()
    angry.mood["분노"] = 0.95
    jev = {"joy": 0.5, "annoyed": 0.5}
    assert model.probabilities(model.reaction_scores(jev, angry, 0.0, T))["annoyed"] > \
        model.probabilities(model.reaction_scores(jev, neutral(), 0.0, T))["annoyed"]


def test_habit_makes_reaction_none_likelier():
    fresh = model.probabilities(model.reaction_scores(JEV, neutral(), 0.0, T))
    used = model.probabilities(model.reaction_scores(JEV, neutral(), 0.9, T))
    assert used["none"] > fresh["none"]


def test_reaction_tilts_action():
    jev = {"bark": 0.4, "beg": 0.4, "none": 0.2}
    after_annoyed = model.probabilities(model.action_scores(jev, neutral(), "annoyed", T))
    after_joy = model.probabilities(model.action_scores(jev, neutral(), "joy", T))
    assert after_annoyed["bark"] > after_annoyed["beg"]
    assert after_joy["beg"] > after_joy["bark"]


def test_sleepy_mood_tilts_action_to_sleep():
    sleepy = neutral()
    sleepy.mood["졸림"] = 0.95
    jev = {"sleep": 0.3, "stand": 0.7}
    assert model.probabilities(model.action_scores(jev, sleepy, "none", T))["sleep"] > \
        model.probabilities(model.action_scores(jev, neutral(), "none", T))["sleep"]


def test_pick_follows_probabilities():
    scores = model.reaction_scores(JEV, neutral(), 0.0, T)
    rng = random.Random(7)
    picks = [model.pick(scores, rng) for _ in range(4000)]
    assert picks.count("joy") / 4000 == pytest.approx(model.probabilities(scores)["joy"], abs=0.03)


def test_talkativeness_directions():
    base = model.talkativeness(neutral(), T)
    angry, bored_type = neutral(), neutral()
    angry.mood["분노"] = 0.9
    bored_type.personality.baseline["심심함"] = 0.9
    assert model.talkativeness(neutral(intimacy=0.9), T) > base
    assert model.talkativeness(angry, T) < base
    assert model.talkativeness(bored_type, T) > base


def test_speak_probability_formula():
    assert model.speak_probability(0.5, neutral(), "message", 0, False, ZERO) == pytest.approx(0.5)
    assert model.speak_probability(0.5, neutral(), "message", 1, False, ZERO) < 0.5
    assert model.speak_probability(0.5, neutral(), "message", 0, True, ZERO) < 0.5
    biased = replace(ZERO, kind_bias={**ZERO.kind_bias, "dog_spoke": -2.0})
    assert model.speak_probability(0.5, neutral(), "dog_spoke", 0, False, biased) == pytest.approx(0.1192, abs=1e-3)


def test_streak_cap():
    assert model.speak_probability(0.99, neutral(), "dog_spoke", 3, False, T) == 0.0


def test_change_moves_mood_by_sensitivity_and_clips():
    dog = neutral()
    dog.personality.sensitivity["분노"] = 0.8
    model.apply_change(dog, {"분노↑": 1.0}, ["message"], random.Random(0), replace(T, change_noise=0.0))
    assert dog.mood["분노"] == pytest.approx(0.5 + 0.3 * 0.8)
    model.apply_change(dog, {"분노↑": 1.0}, ["message"], random.Random(0), replace(T, change_noise=0.0, change_k=5.0))
    assert dog.mood["분노"] == 1.0


def test_intimacy_change():
    dog = neutral()
    model.apply_change(dog, {"친밀도↓": 1.0}, ["message"], random.Random(0), replace(T, change_noise=0.0))
    assert dog.intimacy == pytest.approx(0.45)


def test_repeated_stimulus_habituates():
    quiet = replace(T, change_noise=0.0)
    dog = neutral()
    deltas = [model.apply_change(dog, {"분노↑": 1.0}, ["poke"], random.Random(0), quiet)["분노"] for _ in range(5)]
    assert deltas[0] > deltas[1] > deltas[2] > deltas[4] > 0
    assert model.habit_level(dog, ["poke"]) > 0.7
    assert model.habit_level(dog, ["message"]) == 0.0


def test_sensitive_dog_habituates_slower():
    quiet = replace(T, change_noise=0.0)
    calm, touchy = neutral(), neutral()
    calm.personality.sensitivity["분노"], touchy.personality.sensitivity["분노"] = 0.2, 0.9
    for dog in (calm, touchy):
        model.apply_change(dog, {}, ["poke"], random.Random(0), quiet)
    assert calm.habit["poke"] > touchy.habit["poke"]


def test_message_has_no_habituation():
    dog = neutral()
    model.apply_change(dog, {}, ["message", "message"], random.Random(0), T)
    assert all(h == 0.0 for h in dog.habit.values())
