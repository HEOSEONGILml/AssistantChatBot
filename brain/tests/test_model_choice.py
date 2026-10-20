import math
import random
from dataclasses import replace

import pytest

from brain import model
from brain.tuning import MOODS, REST, Tuning

T = Tuning()
ZERO = replace(T, kind_bias={k: 0.0 for k in T.kind_bias})  # 이벤트 종류별 보정 없이 식만 본다


def neutral():
    """기분이 돌아가는 자리에 있어 기분 보정이 0인 강아지."""
    return model.new_dog(0.0)


JEV = {"beg": 0.6, "stand": 0.3, "none": 0.1}


def test_reaction_is_the_mood_that_rose_most():
    deltas = {d: 0.0 for d in MOODS} | {"분노": 0.1, "들뜸": 0.05}
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
    after_annoyed = model.probabilities(model.action_scores(jev, calm_dog(), "annoyed", ["message"], T))
    after_excited = model.probabilities(model.action_scores(jev, calm_dog(), "excited", ["message"], T))
    assert after_annoyed["bark"] > after_annoyed["beg"]
    assert after_excited["beg"] > after_excited["bark"]


def test_sleepy_mood_tilts_action_to_sleep():
    sleepy = neutral()
    sleepy.mood["졸림"] = 0.95
    jev = {"sleep": 0.3, "stand": 0.7}
    assert model.probabilities(model.action_scores(jev, sleepy, "none", ["message"], T))["sleep"] > \
        model.probabilities(model.action_scores(jev, neutral(), "none", ["message"], T))["sleep"]


def test_pick_follows_probabilities():
    scores = model.action_scores(JEV, neutral(), "none", ["message"], T)
    rng = random.Random(7)
    picks = [model.pick(scores, rng) for _ in range(4000)]
    assert picks.count("beg") / 4000 == pytest.approx(model.probabilities(scores)["beg"], abs=0.03)


def test_speak_probability_formula():
    # 말할 확률 = σ(logit P_Jev + 이벤트 종류 보정 − 연달아 말한 횟수) (0020)
    assert model.speak_probability(0.5, "message", 0, ZERO) == pytest.approx(0.5)
    assert model.speak_probability(0.5, "message", 1, ZERO) == pytest.approx(1 / (1 + math.e))
    biased = replace(ZERO, kind_bias={**ZERO.kind_bias, "quiet": -2.0})
    assert model.speak_probability(0.5, "quiet", 0, biased) == pytest.approx(0.1192, abs=1e-3)


def test_streak_cap():
    assert model.speak_probability(0.99, "message", 3, T) == 0.0
    assert model.chain_probability(3, T) == 0.0


def test_change_moves_mood_and_clips():
    dog = neutral()
    dog.mood["분노"] = 0.5
    model.apply_change(dog, {"분노": 1.0}, [("message", {})], T)
    assert dog.mood["분노"] == pytest.approx(0.5 + 0.3)  # 글은 0.3 × P(기분)만큼 (0019)
    model.apply_change(dog, {"분노": 1.0}, [("message", {})], replace(T, change_k=5.0))
    assert dog.mood["분노"] == 1.0


# ---- 기분 변화: 글 없는 사건은 우리 값, 글은 Jev 기분 질문, 반대 기분은 같은 양 (0019) ----

QUIET = T


def calm_dog():
    """기분이 돌아가는 자리에 있는 강아지."""
    return model.new_dog(0.0)


def test_message_mood_is_point_three_times_probability():
    dog = neutral()
    d = model.apply_change(dog, {"행복": 0.5, "궁금함": 0.1, "없음": 0.4}, [("message", {"text": "점심 맛있었어"})], T)
    assert d["궁금함"] == pytest.approx(0.03)
    assert d["행복"] == pytest.approx(0.15)


def test_typing_uses_jev_mood_too():
    dog = neutral()
    d = model.apply_change(dog, {"궁금함": 1.0}, [("typing", {"text": "오늘 회의가"})], T)
    assert d["궁금함"] == pytest.approx(0.3)


def test_jev_change_is_ignored_for_poke_only_batch():
    with_jev, without = neutral(), neutral()
    a = model.apply_change(with_jev, {"행복": 1.0, "분노": 1.0}, [("poke", {})], T)
    b = model.apply_change(without, {}, [("poke", {})], T)
    assert dict(a) == pytest.approx(dict(b))


def test_message_has_no_model_value():
    dog = neutral()
    d = model.apply_change(dog, {"없음": 1.0}, [("message", {"text": "음"})], T)
    assert max(abs(v) for v in d.values()) == 0.0


def test_opposite_falls_by_the_same_amount():
    dog = neutral()
    d = model.apply_change(dog, {"분노": 0.5}, [("message", {})], T)
    assert d.signal["분노"] == pytest.approx(0.15)
    assert d.signal["행복"] == pytest.approx(-0.15)


def test_mood_is_clipped_at_zero():
    dog = neutral()
    dog.mood["행복"] = 0.05
    model.apply_change(dog, {"분노": 1.0}, [("message", {})], T)
    assert dog.mood["행복"] == 0.0


def test_happy_words_ease_sadness_through_opposites():
    # "미안해"에 행복 0.6이면 행복 +0.18, 반대 기분 억제로 시무룩 −0.18 (사용자 결정 예시, 0019)
    dog = neutral()
    dog.mood["시무룩"] = 0.5
    model.apply_change(dog, {"행복": 0.6, "없음": 0.4}, [("message", {"text": "미안해"})], T)
    assert dog.mood["시무룩"] == pytest.approx(0.32)


def test_throw_scares_even_if_jev_says_happy():
    dog = calm_dog()  # 던지기는 Jev를 쓰지 않는다 (0019)
    deltas = model.apply_change(dog, {"행복": 0.25, "분노": 0.2, "놀람": 0.17}, [("throw", {"impact": 0.9})], QUIET)
    assert model.reaction_from(deltas, ["throw"], T) in ("scared", "surprised")
    assert deltas["무서움"] > 0.2 and deltas["행복"] < 0


def test_pet_makes_happy():
    dog = calm_dog()
    deltas = model.apply_change(dog, {"궁금함": 0.3}, [("pet", {"seconds": 3.0})], QUIET)
    assert model.reaction_from(deltas, ["pet"], T) == "happy"


def test_own_words_do_not_move_mood():
    dog = calm_dog()
    deltas = model.apply_change(dog, {"분노": 0.9}, [("dog_spoke", {"text": "왈!"})], QUIET)
    assert max(abs(v) for v in deltas.values()) < 0.005
    assert model.reaction_from(deltas, ["dog_spoke"], T) == "none"


def test_rising_anger_pushes_happiness_down():
    dog = calm_dog()
    before = dog.mood["행복"]
    model.apply_change(dog, {"분노": 1.0}, [("message", {"text": "저리 가"})], QUIET)
    assert dog.mood["행복"] == pytest.approx(before - 0.3)  # 오른 만큼 같은 양 (0019)


def test_quiet_is_boring_not_scary():
    dog = calm_dog()
    deltas = model.apply_change(dog, {"무서움": 0.4}, [("quiet", {"seconds": 1800})], QUIET)
    assert model.reaction_from(deltas, ["quiet"], T) == "bored"
    assert deltas["무서움"] < 0.05


def test_return_is_welcome():
    dog = calm_dog()
    deltas = model.apply_change(dog, {"놀람": 0.5}, [("returned", {"away_seconds": 3600})], QUIET)
    assert model.reaction_from(deltas, ["returned"], T) in ("happy", "excited")


# ---- 동작 = 우리 모형 중심, 메시지만 Jev (스펙 2026-10-16, 검수 001, 0020) ----

STAND = {"stand": 0.98, "bark": 0.01, "none": 0.01}  # 검수 001에서 Jev가 늘 주던 쏠린 분포


def share(scores, actions):
    p = model.probabilities(scores)
    return sum(p[a] for a in actions)


def test_pet_leads_to_beg_or_sit_even_if_jev_says_stand():
    dog = calm_dog()
    assert share(model.action_scores(STAND, dog, "happy", ["pet"], T), ("beg", "sit")) > 0.5


def test_sleepy_dog_left_alone_lies_down_or_sleeps():
    dog = calm_dog()
    dog.mood["졸림"] = REST["졸림"] + 0.35
    assert share(model.action_scores(STAND, dog, "sleepy", ["quiet"], T), ("lie_down", "sleep")) > 0.5


def test_poke_barks_more_than_it_stands():
    p = model.probabilities(model.action_scores(STAND, calm_dog(), "surprised", ["poke"], T))
    assert p["bark"] > p["stand"]


# ---- 글 없는 사건은 고정 평가값 (0020) ----


def test_burst_of_pokes_adds_up():
    # 한 묶음의 같은 자극은 그대로 더한다(포화 합산·1/√k 없음, 0020). 기분은 1에서 잘린다
    dog = calm_dog()
    deltas = model.apply_change(dog, {}, [("poke", {})] * 7, QUIET)
    assert deltas.signal["놀람"] == pytest.approx(7 * 0.20)
    assert dog.mood["놀람"] == 1.0


def test_pet_appraisal_is_fixed():
    # 쓰다듬은 시간이나 지금 기분과 상관없이 늘 같은 값이다 (0020)
    short, long_, angry = calm_dog(), calm_dog(), calm_dog()
    angry.mood["분노"] = 0.6
    a = model.apply_change(short, {}, [("pet", {"seconds": 1.0})], QUIET).signal
    b = model.apply_change(long_, {}, [("pet", {"seconds": 5.0})], QUIET).signal
    c = model.apply_change(angry, {}, [("pet", {"seconds": 3.0})], QUIET).signal
    assert a == b == c
    assert a["행복"] == pytest.approx(0.12) and a["들뜸"] == pytest.approx(0.04)


def test_quiet_is_fixed_boredom():
    # 조용함은 시간·혼자 있은 시간·자리 비움과 상관없이 심심함 +0.04만 (0020)
    for seconds in (600, 1800, 7200):
        d = model.apply_change(calm_dog(), {"시무룩": 0.9}, [("quiet", {"seconds": seconds})], QUIET)
        assert d.signal["심심함"] == pytest.approx(0.04)
        assert all(v == 0.0 for k, v in d.signal.items() if k != "심심함")


# ---- 검수 003: 조용함은 심심함·졸음, 던지기 반복은 무서움 ----


def test_quiet_mood_is_ours_not_jevs():
    dog = calm_dog()
    d = model.apply_change(dog, {"시무룩": 0.5}, [("quiet", {"seconds": 600})], QUIET)
    assert model.reaction_from(d, ["quiet"], T) == "bored"


def test_repeated_hard_throws_scare():
    dog = calm_dog()
    rs = [model.reaction_from(model.apply_change(dog, {}, [("throw", {"impact": 0.95})], QUIET), ["throw"], T) for _ in range(3)]
    assert rs[1] == "scared" and rs[2] == "scared"


def test_no_sleep_action_unless_sleepier_than_usual():
    dog = calm_dog()
    dog.mood["들뜸"] += 0.3
    p = model.probabilities(model.action_scores(STAND, dog, "excited", ["quiet"], T))
    assert p["sleep"] < 0.03


def test_annoyed_dog_does_not_only_bark():
    dog = calm_dog()
    dog.mood["분노"] += 0.4
    p = model.probabilities(model.action_scores(STAND, dog, "annoyed", ["poke"], T))
    assert 0.3 < p["bark"] < 0.85  # 찌르기에는 Jev 동작을 쓰지 않아 짖기가 예전(< 0.75)보다 조금 많다 (0020)


# ---- 검수 004: 밤에 졸리면 잠 ----


def test_sleepy_reaction_at_night_can_be_sleep():
    # 밤에 졸리면(자리보다 0.3 높음) 조용함에 잠 동작이 눈에 띄게 나온다 (검수 004 사소)
    dog = calm_dog()
    dog.mood["졸림"] += 0.3
    p = model.probabilities(model.action_scores(STAND, dog, "sleepy", ["quiet"], T))
    assert p["sleep"] > 0.2


# ---- 이어 말하기는 우리 모형: 갈수록 줄어든다 (검수 005) ----


def test_chain_probability_drops_with_depth():
    # 이어 말하기 = chain_base × 0.3^(k−1) (0020)
    assert model.chain_probability(1, T) == pytest.approx(T.chain_base)
    assert model.chain_probability(2, T) == pytest.approx(T.chain_base * T.chain_decay)
    assert model.chain_probability(3, T) == 0.0


# ---- 검수 006: 오래 비운 뒤 돌아오면 잠이 깬다 ----


def test_long_away_return_wakes_and_excites():
    dog = calm_dog()
    dog.mood["졸림"] = 0.55
    model.apply_change(dog, {}, [("returned", {"away_seconds": 8 * 3600})], QUIET)
    assert dog.mood["졸림"] < 0.4 and dog.mood["들뜸"] > REST["들뜸"] + 0.1


# ---- 검수 007: 겁먹으면 조르지 않는다 ----


def test_scared_dog_does_not_beg_after_a_pet():
    dog = calm_dog()
    dog.mood["무서움"] = 0.59
    p = model.probabilities(model.action_scores({"beg": 0.9, "none": 0.1}, dog, "none", ["pet"], T))
    assert p["beg"] < 0.1


def test_hard_throw_in_a_mixed_burst_still_scares():
    # 찌르기·던지기·쓰다듬기·메시지가 한 묶음이어도 세게 던진 무서움은 단독에 가깝다 (검수 007 사소)
    alone, burst = calm_dog(), calm_dog()
    a = model.apply_change(alone, {"없음": 1.0}, [("throw", {"impact": 0.85})], QUIET).signal["무서움"]
    b = model.apply_change(burst, {"없음": 1.0}, [("poke", {}), ("throw", {"impact": 0.85}), ("pet", {"seconds": 2}), ("message", {"text": "괜찮아?"})],
                           QUIET).signal["무서움"]
    assert b > 0.6 * a


def test_commands_in_messages_are_mostly_followed():
    # "엎드려"처럼 글 내용이 동작을 정하면 Jev가 그 동작을 크게 준다. 메시지에서는 Jev 동작 판단을 더 믿는다 (검수 010: 엎드려 0/4)
    dog = calm_dog()
    p = model.probabilities(model.action_scores({"lie_down": 0.9, "none": 0.1}, dog, "none", ["message"], T))
    assert p["lie_down"] > 0.6
    q = model.probabilities(model.action_scores({"lie_down": 0.9, "none": 0.1}, dog, "surprised", ["poke"], T))
    assert q["lie_down"] < 0.4  # 몸 이벤트에서는 여전히 우리 모형이 정한다


def test_poke_wakes_a_sleepy_dog():
    dog = calm_dog()
    dog.mood["졸림"] = 0.75
    model.apply_change(dog, {}, [("poke", {})], QUIET)
    assert dog.mood["졸림"] < 0.68


def test_own_words_do_not_change_posture():
    # 강아지가 자기 말을 한 직후에는 동작을 다시 뽑지 않는다: 말한 동작 = 뽑힌 동작이 바로 바뀌던 문제 (검수 011)
    p = model.probabilities(model.action_scores({"stand": 0.8, "beg": 0.2}, calm_dog(), "none", ["dog_spoke"], T))
    assert p == {"none": 1.0}


# ---- 검수 013 묶음 2: 화난 강아지는 조르지 않는다 ----


def test_angry_dog_does_not_beg():
    dog = calm_dog()
    calm = model.probabilities(model.action_scores({}, dog, "happy", ["pet"], T))["beg"]
    dog.mood["분노"] += 0.3
    assert model.probabilities(model.action_scores({}, dog, "happy", ["pet"], T))["beg"] < 0.5 * calm
