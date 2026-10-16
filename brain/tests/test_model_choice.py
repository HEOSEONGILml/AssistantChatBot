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
    sharp = model.probabilities(model.action_scores(JEV, neutral(whim=0.0), "none", ["pet"], T))
    flat = model.probabilities(model.action_scores(JEV, neutral(whim=1.0), "none", ["pet"], T))
    assert max(sharp.values()) > max(flat.values()) + 0.05


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
    after_annoyed = model.probabilities(model.action_scores(jev, neutral(), "annoyed", ["message"], T))
    after_excited = model.probabilities(model.action_scores(jev, neutral(), "excited", ["message"], T))
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
    model.apply_change(dog, {"분노↑": 1.0}, [("message", {})], random.Random(0), replace(T, change_noise=0.0))
    assert dog.mood["분노"] == pytest.approx(0.5 + 0.3 * 2 * 0.8 * 0.5)  # 메시지는 Jev 가중치 1, 민감도 0.5가 배율 1, 남은 여유 0.5만큼
    model.apply_change(dog, {"분노↑": 1.0}, [("message", {})], random.Random(0), replace(T, change_noise=0.0, change_k=5.0))
    assert dog.mood["분노"] == 1.0


def test_intimacy_change():
    dog = neutral()
    model.apply_change(dog, {"친밀도↓": 1.0}, [("message", {})], random.Random(0), replace(T, change_noise=0.0))
    assert dog.intimacy == pytest.approx(0.48)


def test_repeated_stimulus_habituates():
    quiet = replace(T, change_noise=0.0)
    dog = neutral()
    deltas = [model.apply_change(dog, {"놀람↑": 1.0}, [("poke", {})], random.Random(0), quiet)["놀람"] for _ in range(5)]
    assert deltas[0] > deltas[1] > deltas[2] > deltas[4] > 0
    assert model.habit_level(dog, ["poke"]) > 0.7
    assert model.habit_level(dog, ["message"]) == 0.0


def test_sensitive_dog_habituates_slower():
    quiet = replace(T, change_noise=0.0)
    calm, touchy = neutral(), neutral()
    calm.personality.sensitivity["놀람"], touchy.personality.sensitivity["놀람"] = 0.2, 0.9
    for dog in (calm, touchy):
        model.apply_change(dog, {}, [("poke", {})], random.Random(0), quiet)
    assert calm.habit["poke"] > touchy.habit["poke"]


def test_message_has_no_habituation():
    dog = neutral()
    model.apply_change(dog, {}, [("message", {}), ("message", {})], random.Random(0), T)
    assert all(h == 0.0 for h in dog.habit.values())


# ---- 평가 사전값 + Jev 조정 (스펙 2026-10-16, 검수 001) ----

QUIET = replace(T, change_noise=0.0)


def calm_dog():
    """기분이 기준값(탄생 평균)에 있는 평균 강아지."""
    dog = neutral()
    dog.mood = dict(model.BIRTH_BASELINE)
    dog.personality.baseline = dict(model.BIRTH_BASELINE)
    return dog


def test_throw_scares_even_if_jev_says_happy():
    dog = calm_dog()
    deltas = model.apply_change(dog, {"행복↑": 0.25, "분노↑": 0.2, "놀람↑": 0.17}, [("throw", {"impact": 0.9})], random.Random(0), QUIET)
    assert model.reaction_from(deltas, ["throw"], T) in ("scared", "surprised")
    assert deltas["무서움"] > 0.2 and deltas["행복"] < 0


def test_pet_makes_happy():
    dog = calm_dog()
    deltas = model.apply_change(dog, {"궁금함↑": 0.3}, [("pet", {"seconds": 3.0})], random.Random(0), QUIET)
    assert model.reaction_from(deltas, ["pet"], T) == "happy"


def test_own_words_do_not_move_mood():
    dog = calm_dog()
    deltas = model.apply_change(dog, {"분노↑": 0.9}, [("dog_spoke", {"text": "왈!"})], random.Random(0), QUIET)
    assert max(abs(v) for v in deltas.values()) < 0.005
    assert model.reaction_from(deltas, ["dog_spoke"], T) == "none"


def test_rising_anger_pushes_happiness_down():
    dog = calm_dog()
    before = dog.mood["행복"]
    model.apply_change(dog, {"분노↑": 1.0}, [("message", {"text": "저리 가"})], random.Random(0), QUIET)
    assert dog.mood["행복"] < before - 0.03  # 억제 ρ 0.3, 지금 값에 비례해 내린다 (검수 002)


def test_quiet_is_boring_not_scary():
    dog = calm_dog()
    deltas = model.apply_change(dog, {"무서움↑": 0.4}, [("quiet", {"seconds": 1800})], random.Random(0), QUIET)
    assert model.reaction_from(deltas, ["quiet"], T) == "bored"
    assert deltas["무서움"] < 0.05


def test_return_is_welcome():
    dog = calm_dog()
    deltas = model.apply_change(dog, {"놀람↑": 0.5}, [("returned", {"away_seconds": 3600})], random.Random(0), QUIET)
    assert model.reaction_from(deltas, ["returned"], T) in ("happy", "excited")


# ---- 동작 = 우리 모형 중심 + Jev 약한 조정 (스펙 2026-10-16, 검수 001) ----

STAND = {"stand": 0.98, "bark": 0.01, "none": 0.01}  # 검수 001에서 Jev가 늘 주던 쏠린 분포


def share(scores, actions):
    p = model.probabilities(scores)
    return sum(p[a] for a in actions)


def test_pet_leads_to_beg_or_sit_even_if_jev_says_stand():
    dog = calm_dog()
    assert share(model.action_scores(STAND, dog, "happy", ["pet"], T), ("beg", "sit")) > 0.5


def test_sleepy_dog_left_alone_lies_down_or_sleeps():
    dog = calm_dog()
    dog.mood["졸림"] = dog.personality.baseline["졸림"] + 0.35
    assert share(model.action_scores(STAND, dog, "sleepy", ["quiet"], T), ("lie_down", "sleep")) > 0.5


def test_poke_barks_more_than_it_stands():
    p = model.probabilities(model.action_scores(STAND, calm_dog(), "surprised", ["poke"], T))
    assert p["bark"] > p["stand"]


def test_high_baseline_alone_does_not_force_sleep():
    # 늘 졸린 성격이라도 평소만큼 졸리면 자지 않는다 (기분은 기준값 대비)
    dog = calm_dog()
    dog.personality.baseline["졸림"] = dog.mood["졸림"] = 0.8
    assert model.probabilities(model.action_scores(STAND, dog, "none", ["message"], T))["sleep"] < 0.1


# ---- 기분 갱신 수식 (스펙 2026-10-16 mood-update-math, 검수 002) ----


def test_one_pet_does_not_wipe_bad_moods():
    dog = calm_dog()
    model.apply_change(dog, {}, [("pet", {"seconds": 3.0})], random.Random(0), QUIET)
    for d in ("시무룩", "분노", "무서움"):
        assert dog.mood[d] > 0.5 * model.BIRTH_BASELINE[d]


def test_moods_do_not_stick_at_the_top():
    dog = calm_dog()
    dog.mood["놀람"] = 0.95
    deltas = model.apply_change(dog, {}, [("poke", {})], random.Random(0), QUIET)
    assert 0 < deltas["놀람"] < 0.02 and dog.mood["놀람"] < 1.0


def test_burst_of_pokes_saturates_and_habituates_inside_the_batch():
    dog = calm_dog()
    deltas = model.apply_change(dog, {}, [("poke", {})] * 7, random.Random(0), QUIET)
    assert deltas.signal["놀람"] < 1.0
    assert dog.habit["poke"] > 0.8


def test_repeated_pokes_turn_surprise_into_annoyance():
    dog = calm_dog()
    rng = random.Random(0)
    first = model.apply_change(dog, {}, [("poke", {})], rng, QUIET).signal
    for _ in range(5):
        later = model.apply_change(dog, {}, [("poke", {})], rng, QUIET).signal
    assert later["놀람"] < first["놀람"] and later["분노"] > first["분노"]
    assert model.reaction_from(later, ["poke"], T) == "annoyed"


def test_angry_dog_is_wary_of_the_first_pet():
    calm, angry = calm_dog(), calm_dog()
    angry.mood["분노"] = 0.6
    a = model.apply_change(calm, {}, [("pet", {"seconds": 3.0})], random.Random(0), QUIET).signal["행복"]
    b = model.apply_change(angry, {}, [("pet", {"seconds": 3.0})], random.Random(0), QUIET).signal["행복"]
    assert b < 0.3 * a


def test_noise_alone_never_makes_a_reaction():
    noisy = replace(T, change_noise=0.05)
    for seed in range(200):
        d = model.apply_change(calm_dog(), {"분노↑": 0.9}, [("dog_spoke", {"text": "멍?"})], random.Random(seed), noisy)
        assert model.reaction_from(d, ["dog_spoke"], T) == "none"


# ---- 거절·무시는 서운함 (검수 002) ----


def test_rejection_hurts():
    # Jev는 "저리 가 귀찮아"에 친밀도↓를 주로 준다(0.66). 우리 모형은 그것을 서운함으로 읽는다
    dog = calm_dog()
    d = model.apply_change(dog, {"친밀도↓": 0.66, "분노↑": 0.24}, [("message", {"text": "저리 가 귀찮아"})], random.Random(0), QUIET)
    assert model.reaction_from(d, ["message"], T) == "sad"
    assert d["시무룩"] > 0.05


def test_warm_words_make_happy():
    dog = calm_dog()
    d = model.apply_change(dog, {"친밀도↑": 0.78, "행복↑": 0.11}, [("message", {"text": "너 좋아해"})], random.Random(0), QUIET)
    assert model.reaction_from(d, ["message"], T) == "happy"


def test_ignored_question_makes_sad():
    plain, ignored = calm_dog(), calm_dog()
    # 사용자가 자리에 있는데(조용함 10분) 질문에 답이 없을 때만. 자리를 비운 조용함(30분)은 서운하지 않다 (검수 003)
    a = model.apply_change(plain, {}, [("quiet", {"seconds": 600})], random.Random(0), QUIET).signal["시무룩"]
    b = model.apply_change(ignored, {}, [("quiet", {"seconds": 600})], random.Random(0), QUIET, waiting=True).signal["시무룩"]
    assert b > a + 0.04


# ---- 타이핑에 익숙해지면 글 내용이 드러난다 (검수 002) ----


def test_used_to_typing_lets_the_content_show():
    # 실측 Jev: 슬픈 글을 쓰는 동안에도 궁금함↑ 0.4~0.56, 시무룩↑ 0.14. 타이핑이 이어지면 궁금함만 무뎌진다
    dog = calm_dog()
    rng = random.Random(0)
    reactions = [model.reaction_from(model.apply_change(dog, {"궁금함↑": 0.4, "시무룩↑": 0.15}, [("typing", {})], rng, QUIET), ["typing"], T)
                 for _ in range(5)]
    assert reactions[0] == "curious" and reactions[-1] == "sad"


def test_habituation_only_dulls_its_target_mood_in_jev_part_too():
    dog = calm_dog()
    dog.habit["poke"] = 0.9
    d = model.apply_change(dog, {"분노↑": 0.5}, [("poke", {})], random.Random(0), QUIET)
    assert d.signal["분노"] > 0.15  # 찌르기에 익숙해도 Jev의 분노 신호는 줄지 않는다


# ---- 오래 혼자면 심심함 대신 졸음 (검수 002) ----


def test_long_alone_turns_boredom_into_sleepiness():
    short, long_ = calm_dog(), calm_dog()
    a = model.apply_change(short, {}, [("quiet", {"seconds": 1800})], random.Random(0), QUIET, alone_s=1800).signal
    b = model.apply_change(long_, {}, [("quiet", {"seconds": 1800})], random.Random(0), QUIET, alone_s=4 * 3600).signal
    assert b["심심함"] < 0.3 * a["심심함"]
    assert b["졸림"] > 0.1 and model.reaction_from(b, ["quiet"], T) == "sleepy"


# ---- 검수 003: 조용함은 심심함·졸음, 던지기 반복은 무서움, 사과는 서운함을 던다 ----


def test_quiet_while_user_is_away_is_not_sad_even_after_a_question():
    # 화면은 자리를 비우면 30분마다 조용함을 보낸다. 나간 주인은 무시한 게 아니다
    dog = calm_dog()
    d = model.apply_change(dog, {"시무룩↑": 0.4, "친밀도↓": 0.3}, [("quiet", {"seconds": 1800})], random.Random(0), QUIET, waiting=True)
    assert d.signal["시무룩"] < 0.03
    assert model.reaction_from(d, ["quiet"], T) in ("bored", "sleepy", "none")


def test_quiet_mood_is_ours_not_jevs():
    dog = calm_dog()
    d = model.apply_change(dog, {"시무룩↑": 0.5}, [("quiet", {"seconds": 600})], random.Random(0), QUIET)
    assert model.reaction_from(d, ["quiet"], T) == "bored"


def test_repeated_hard_throws_scare():
    dog = calm_dog()
    rng = random.Random(0)
    rs = [model.reaction_from(model.apply_change(dog, {}, [("throw", {"impact": 0.95})], rng, QUIET), ["throw"], T) for _ in range(3)]
    assert rs[1] == "scared" and rs[2] == "scared"


def test_apology_eases_sadness():
    dog = calm_dog()
    dog.mood["시무룩"] = 0.5
    model.apply_change(dog, {"친밀도↑": 0.78, "행복↑": 0.11}, [("message", {"text": "아까는 미안해"})], random.Random(0), QUIET)
    assert dog.mood["시무룩"] < 0.4


def test_no_sleep_action_unless_sleepier_than_usual():
    for whim in (0.2, 0.9):
        dog = calm_dog()
        dog.personality.whim = whim
        dog.mood["들뜸"] += 0.3
        p = model.probabilities(model.action_scores(STAND, dog, "excited", ["quiet"], T))
        assert p["sleep"] < 0.03


def test_annoyed_dog_does_not_only_bark():
    dog = calm_dog()
    dog.mood["분노"] += 0.4
    p = model.probabilities(model.action_scores(STAND, dog, "annoyed", ["poke"], T))
    assert 0.3 < p["bark"] < 0.75


# ---- 검수 004: 성마른 강아지는 잘 안 풀리고, 무서울 때 쓰다듬어도 행복 반응이 아니다 ----


def test_irritable_dog_is_harder_to_please():
    calm, touchy = calm_dog(), calm_dog()
    for d in model.MOODS:
        touchy.personality.sensitivity[d] = 0.8
    touchy.personality.baseline["분노"] = 0.4
    touchy.mood["분노"] = 0.47
    a = model.apply_change(calm, {}, [("pet", {"seconds": 3.0})], random.Random(0), QUIET).signal["행복"]
    b = model.apply_change(touchy, {}, [("pet", {"seconds": 3.0})], random.Random(0), QUIET).signal["행복"]
    assert b < a


def test_scared_dog_is_not_happy_from_a_pet():
    dog = calm_dog()
    dog.mood["무서움"] = 0.84
    d = model.apply_change(dog, {"행복↑": 0.3}, [("pet", {"seconds": 3.0})], random.Random(0), QUIET)
    assert model.reaction_from(d, ["pet"], T) != "happy"


def test_direct_question_or_sad_disclosure_is_almost_always_answered():
    # 직접 물었거나 속상하다고 털어놓으면 거의 늘 대답한다 (검수 004: 메시지 무응답 31%)
    # Jev 말하기 확률은 검수 004 실측 질문에서 0.735~0.746
    plain = model.speak_probability(0.74, neutral(), "message", 0, False, T)
    asked = model.speak_probability(0.74, neutral(), "message", 0, False, T, asked=True)
    hurting = model.speak_probability(0.74, neutral(), "message", 0, False, T, hurting=True)
    assert asked > 0.93 and hurting > 0.93 and plain < asked


def test_sleepy_reaction_at_night_can_be_sleep():
    # 밤에 졸리면(기준값보다 0.3 높음) 조용함에 잠 동작이 눈에 띄게 나온다 (검수 004 사소)
    dog = calm_dog()
    dog.mood["졸림"] += 0.3
    p = model.probabilities(model.action_scores(STAND, dog, "sleepy", ["quiet"], T))
    assert p["sleep"] > 0.2


# ---- 이어 말하기는 우리 모형: 성격 따라, 갈수록 줄어든다 (검수 005) ----


def test_chain_probability_by_personality_and_depth():
    from sim.simulate import archetype_dog
    quiet, avg, lively = (archetype_dog(n) for n in ("과묵·차분", "평균", "활발·변덕쟁이"))
    q1, a1, l1 = (model.chain_probability(d, 1, T) for d in (quiet, avg, lively))
    assert q1 < 0.15 and q1 < a1 < l1
    assert model.chain_probability(lively, 2, T) < 0.6 * l1
    assert model.chain_probability(lively, 3, T) == 0.0


# ---- 주인의 슬픔에 공감 (검수 005) ----


def test_owner_sadness_makes_dog_sympathetic_not_curious_or_happy():
    # 실측 Jev: 슬픈 털어놓기에 궁금함↑·친밀도↑가 크고 시무룩↑는 작았다. user_down이 높으면 우리 모형이 공감으로 바꾼다
    dog = calm_dog()
    change = {"궁금함↑": 0.5, "친밀도↑": 0.3, "시무룩↑": 0.1}
    d = model.apply_change(dog, change, [("message", {"text": "그냥 다 내 잘못 같아서 마음이 무거워"})], random.Random(0), QUIET, user_down=0.9)
    assert model.reaction_from(d, ["message"], T) == "sad"
    assert d.signal["행복"] <= 0.0 and d.signal["궁금함"] < d.signal["시무룩"]


def test_owner_sadness_is_ignored_for_body_events():
    dog = calm_dog()
    d = model.apply_change(dog, {}, [("poke", {})], random.Random(0), QUIET, user_down=0.9)
    assert model.reaction_from(d, ["poke"], T) == "surprised"
