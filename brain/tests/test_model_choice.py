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


JEV = {"beg": 0.6, "stand": 0.3, "none": 0.1}


def test_whim_controls_temperature():
    sharp = model.probabilities(model.action_scores(JEV, neutral(whim=0.0), "none", T))
    flat = model.probabilities(model.action_scores(JEV, neutral(whim=1.0), "none", T))
    assert sharp["beg"] == pytest.approx(0.78, abs=0.01)
    assert flat["beg"] == pytest.approx(0.52, abs=0.01)


def test_reaction_is_the_mood_that_rose_most():
    deltas = {d: 0.0 for d in MOODS} | {"분노": 0.1, "들뜸": 0.05, "친밀도": 0.3}
    assert model.reaction_from(deltas, ["poke"], T) == "annoyed"


def test_small_rise_is_no_reaction():
    deltas = {d: 0.0 for d in MOODS} | {"들뜸": 0.01}
    assert model.reaction_from(deltas, ["poke"], T) == "none"


def test_typing_always_reacts():
    small = {d: 0.0 for d in MOODS} | {"들뜸": 0.01}
    falling = {d: -0.05 for d in MOODS}
    assert model.reaction_from(small, ["typing"], T) == "excited"
    assert model.reaction_from(falling, ["typing"], T) == "curious"  # 오른 기분이 없으면 궁금함


def test_every_mood_has_a_reaction():
    assert set(model.MOOD_REACTION_ID) == set(MOODS)
    assert model.MOOD_REACTION_ID["행복"] == "happy"
    assert set(model.REACTIONS) == set(model.MOOD_REACTION_ID.values()) | {"none"}


def test_dominant_mood():
    dog = neutral()
    assert model.dominant_mood(dog, T) == "calm"
    dog.mood["무서움"] = 0.7
    dog.mood["분노"] = 0.6
    assert model.dominant_mood(dog, T) == "scared"


def test_reaction_tilts_action():
    jev = {"bark": 0.4, "beg": 0.4, "none": 0.2}
    after_annoyed = model.probabilities(model.action_scores(jev, neutral(), "annoyed", T))
    after_excited = model.probabilities(model.action_scores(jev, neutral(), "excited", T))
    assert after_annoyed["bark"] > after_annoyed["beg"]
    assert after_excited["beg"] > after_excited["bark"]


def test_sleepy_mood_tilts_action_to_sleep():
    sleepy = neutral()
    sleepy.mood["졸림"] = 0.95
    jev = {"sleep": 0.3, "stand": 0.7}
    assert model.probabilities(model.action_scores(jev, sleepy, "none", T))["sleep"] > \
        model.probabilities(model.action_scores(jev, neutral(), "none", T))["sleep"]


def test_pick_follows_probabilities():
    scores = model.action_scores(JEV, neutral(), "none", T)
    rng = random.Random(7)
    picks = [model.pick(scores, rng) for _ in range(4000)]
    assert picks.count("beg") / 4000 == pytest.approx(model.probabilities(scores)["beg"], abs=0.03)


def test_talkativeness_directions():
    base = model.talkativeness(neutral(), T)
    angry, bored_type, scared = neutral(), neutral(), neutral()
    angry.mood["분노"] = 0.9
    scared.mood["무서움"] = 0.9
    bored_type.personality.baseline["심심함"] = 0.9
    assert model.talkativeness(neutral(intimacy=0.9), T) > base
    assert model.talkativeness(angry, T) < base
    assert model.talkativeness(scared, T) < base
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
    deltas = [model.apply_change(dog, {"놀람↑": 1.0}, ["poke"], random.Random(0), quiet)["놀람"] for _ in range(5)]
    assert deltas[0] > deltas[1] > deltas[2] > deltas[4] > 0
    assert model.habit_level(dog, ["poke"]) > 0.7
    assert model.habit_level(dog, ["message"]) == 0.0


def test_sensitive_dog_habituates_slower():
    quiet = replace(T, change_noise=0.0)
    calm, touchy = neutral(), neutral()
    calm.personality.sensitivity["놀람"], touchy.personality.sensitivity["놀람"] = 0.2, 0.9
    for dog in (calm, touchy):
        model.apply_change(dog, {}, ["poke"], random.Random(0), quiet)
    assert calm.habit["poke"] > touchy.habit["poke"]


def test_message_has_no_habituation():
    dog = neutral()
    model.apply_change(dog, {}, ["message", "message"], random.Random(0), T)
    assert all(h == 0.0 for h in dog.habit.values())
