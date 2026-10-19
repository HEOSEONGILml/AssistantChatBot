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
    assert q1 < 0.2 and q1 < a1 < l1  # 과묵: 첫 이어 말하기 0.2 미만, 시뮬레이션 연달아 2번+ 10%
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


def test_long_alone_in_the_day_gets_sleepy_enough_to_nap():
    dog = calm_dog()
    rng = random.Random(0)
    for _ in range(6):  # 자리를 비운 3시간, 30분마다 조용함
        model.apply_change(dog, {}, [("quiet", {"seconds": 1800})], rng, QUIET, alone_s=3 * 3600)
    assert dog.mood["졸림"] - dog.personality.baseline["졸림"] > 0.2


# ---- 검수 006: 사과는 달램, 오래 비운 뒤 돌아오면 잠이 깬다 ----


def test_apology_soothes_even_if_jev_thinks_the_user_is_down():
    # 실측: "내가 말이 심했어 미안"에 Jev 사용자 속상함 0.61~0.67. 달램(soothe)이 높으면 공감보다 달램이 앞선다
    dog = calm_dog()
    dog.mood["시무룩"], dog.mood["무서움"] = 0.6, 0.35
    d = model.apply_change(dog, {"친밀도↑": 0.5, "무서움↓": 0.2}, [("message", {"text": "내가 말이 심했어 미안"})],
                           random.Random(0), QUIET, user_down=0.65, soothe=0.9)
    assert dog.mood["시무룩"] < 0.46 and dog.mood["무서움"] < 0.35  # 무서움은 조금만 준다(말보다 손길, 검수 008)
    assert model.reaction_from(d, ["message"], T) in ("happy", "none")


def test_long_away_return_wakes_and_excites():
    dog = calm_dog()
    dog.mood["졸림"] = 0.55
    model.apply_change(dog, {}, [("returned", {"away_seconds": 8 * 3600})], random.Random(0), QUIET)
    assert dog.mood["졸림"] < 0.4 and dog.mood["들뜸"] > model.BIRTH_BASELINE["들뜸"] + 0.1


def test_even_lively_dog_does_not_always_chain():
    from sim.simulate import archetype_dog
    assert model.chain_probability(archetype_dog("활발·변덕쟁이"), 1, T) <= 0.6


def test_burst_of_pokes_angers_but_does_not_pin_near_one():
    # 같은 자극이 한 묶음에 여럿이면 k번째는 1/√k만 센다 (검수 006: 연타 한 묶음에 분노 0.40 → 0.90)
    dog = calm_dog()
    for d in model.MOODS:
        dog.personality.sensitivity[d] = 0.8
    dog.personality.baseline["분노"] = dog.mood["분노"] = 0.4
    model.apply_change(dog, {}, [("poke", {})] * 7, random.Random(0), QUIET)
    assert 0.55 < dog.mood["분노"] < 0.8


# ---- 검수 007: 겁먹은 동안은 기뻐하지도 조르지도 수다 떨지도 않는다 ----


def test_scared_dog_pet_is_not_happy_even_if_jev_says_happy():
    dog = calm_dog()
    dog.mood["무서움"] = 0.59
    d = model.apply_change(dog, {"행복↑": 0.6, "친밀도↑": 0.3}, [("pet", {"seconds": 3.0})], random.Random(0), QUIET)
    assert model.reaction_from(d, ["pet"], T) not in ("happy", "excited")
    p = model.probabilities(model.action_scores({"beg": 0.9, "none": 0.1}, dog, "none", ["pet"], T))
    assert p["beg"] < 0.1


def test_scared_dog_hushes():
    from sim.simulate import archetype_dog
    lively = archetype_dog("활발·변덕쟁이")
    calm_p = model.speak_probability(0.7, lively, "throw", 0, False, T)
    calm_c = model.chain_probability(lively, 1, T)
    lively.mood["무서움"] = lively.personality.baseline["무서움"] + 0.6
    assert model.speak_probability(0.7, lively, "throw", 0, False, T) < 0.3 * calm_p
    assert model.chain_probability(lively, 1, T) < 0.3 * calm_c


def test_hard_throw_in_a_mixed_burst_still_scares():
    # 찌르기·던지기·쓰다듬기·메시지가 한 묶음이어도 세게 던진 무서움은 단독에 가깝다 (검수 007 사소)
    alone, burst = calm_dog(), calm_dog()
    a = model.apply_change(alone, {"무서움↓": 0.3}, [("throw", {"impact": 0.85})], random.Random(0), QUIET).signal["무서움"]
    b = model.apply_change(burst, {"무서움↓": 0.3}, [("poke", {}), ("throw", {"impact": 0.85}), ("pet", {"seconds": 2}), ("message", {"text": "괜찮아?"})],
                           random.Random(0), QUIET).signal["무서움"]
    assert b > 0.6 * a


def test_words_ease_sadness_but_fear_needs_touch():
    # 사과 한 마디는 서운함을 크게, 무서움은 조금만 던다. 무서움은 손길(쓰다듬기)이 더 푼다 (검수 008)
    said, petted = calm_dog(), calm_dog()
    for dog in (said, petted):
        dog.mood["무서움"], dog.mood["시무룩"] = 0.4, 0.4
    model.apply_change(said, {}, [("message", {"text": "미안해 괜찮아?"})], random.Random(0), QUIET, soothe=0.95)
    model.apply_change(petted, {}, [("pet", {"seconds": 3.0})], random.Random(0), QUIET)
    assert 0.4 - said.mood["무서움"] < 0.06
    assert 0.4 - said.mood["시무룩"] > 0.08


def test_startled_dog_rarely_adds_a_follow_up():
    dog = calm_dog()
    calm = model.chain_probability(dog, 1, T)
    dog.mood["놀람"] = dog.personality.baseline["놀람"] + 0.3
    assert model.chain_probability(dog, 1, T) < 0.5 * calm


def test_ignored_or_hushed_dog_does_not_pile_on_follow_ups():
    # 대꾸 없는 흐름에서 덧말은 갈수록 준다. "말 걸지 마" 동안은 덧말이 없다 (검수 009: 활발 강아지가 갈수록 길게 조름)
    from sim.simulate import archetype_dog
    dog = archetype_dog("활발·변덕쟁이")
    base = model.chain_probability(dog, 1, T)
    assert model.chain_probability(dog, 1, T, ignored=2) < 0.25 * base
    assert model.chain_probability(dog, 1, T, hushed=True) == 0.0


def test_apology_reaction_is_not_curiosity():
    dog = calm_dog()
    dog.mood["시무룩"] = 0.5
    d = model.apply_change(dog, {"궁금함↑": 0.4, "친밀도↑": 0.4}, [("message", {"text": "아까는 미안해"})], random.Random(0), QUIET, soothe=0.9)
    assert model.reaction_from(d, ["message"], T) != "curious"


def test_commands_in_messages_are_mostly_followed():
    # "엎드려"처럼 글 내용이 동작을 정하면 Jev가 그 동작을 크게 준다. 메시지에서는 Jev 동작 판단을 더 믿는다 (검수 010: 엎드려 0/4)
    dog = calm_dog()
    p = model.probabilities(model.action_scores({"lie_down": 0.9, "none": 0.1}, dog, "none", ["message"], T))
    assert p["lie_down"] > 0.6
    q = model.probabilities(model.action_scores({"lie_down": 0.9, "none": 0.1}, dog, "surprised", ["poke"], T))
    assert q["lie_down"] < 0.4  # 몸 이벤트에서는 여전히 우리 모형이 정한다


def test_owner_venting_saddens_less_than_being_insulted():
    vent, insult = calm_dog(), calm_dog()
    model.apply_change(vent, {"궁금함↑": 0.4}, [("message", {"text": "오늘 팀장한테 혼났어"})], random.Random(0), QUIET, user_down=0.95)
    model.apply_change(insult, {"친밀도↓": 0.66, "분노↑": 0.24}, [("message", {"text": "저리 가 귀찮아"})], random.Random(0), QUIET)
    assert vent.mood["시무룩"] < insult.mood["시무룩"]


def test_poke_wakes_a_sleepy_dog():
    dog = calm_dog()
    dog.mood["졸림"] = 0.75
    model.apply_change(dog, {}, [("poke", {})], random.Random(0), QUIET)
    assert dog.mood["졸림"] < 0.68


# ---- 검수 011: 사과는 기준값 쪽으로 풀어 준다 ----


def test_apology_after_throw_eases_fear_even_if_jev_reads_fear_up():
    # 실측: "던져서 미안해 다신 안 그럴게"에 Jev 무서움↑ 0.66~0.87, 달램 0.9. 글이 던진 일을 말해도 뜻은 사과다
    dog = calm_dog()
    dog.mood["무서움"] = 0.45
    model.apply_change(dog, {"무서움↑": 0.7, "친밀도↓": 0.1}, [("message", {"text": "던져서 미안해 다신 안 그럴게"})],
                       random.Random(0), QUIET, user_down=0.5, soothe=0.9)
    assert dog.mood["무서움"] < 0.45


def test_one_apology_does_not_fully_heal_a_sensitive_dog():
    # 예민한 강아지: "아까 짜증낸 거 미안해" 한 마디에 시무룩 0.54 → 0.19(기준값 0.40 아래)였다. 말은 기준값 아래로 누르지 않고 몇 번 달래야 풀린다
    dog = calm_dog()
    for d in model.MOODS:
        dog.personality.sensitivity[d] = 0.8
    dog.personality.baseline["시무룩"] = 0.4
    dog.mood["시무룩"] = 0.54
    model.apply_change(dog, {"친밀도↑": 0.64, "분노↓": 0.12}, [("message", {"text": "아까 짜증낸 거 미안해"})],
                       random.Random(0), QUIET, user_down=0.5, soothe=0.92)
    rest = model.rest_point(dog, "시무룩", dog.updated_at)
    assert rest + 0.03 < dog.mood["시무룩"] < 0.54


# ---- 검수 011 묶음 3: 명령을 따른다 ----


def _p(dog, jev, command, kinds=("message",)):
    return model.probabilities(model.action_scores(jev, dog, "none", list(kinds), T, command=command))


def test_dog_obeys_bark_command_even_if_jev_action_is_split():
    # 실측: "짖어 봐"에 Jev 동작 짖기 0.55·서기 0.42. 시킨 동작(command) 짖기 0.9면 대부분 짖는다
    p = _p(calm_dog(), {"bark": 0.55, "stand": 0.42, "none": 0.03}, {"bark": 0.9, "none": 0.1})
    assert p["bark"] > 0.7


def test_dog_obeys_stand_up_command_even_if_jev_action_says_none():
    # 실측: "일어나!"에 Jev 동작 없음 0.6·서기 0.38. 동작 질문이 기분 위주라 명령을 '하던 대로'로 읽는다
    p = _p(calm_dog(), {"none": 0.6, "stand": 0.38, "sit": 0.01}, {"stand": 0.85, "none": 0.15})
    assert p["stand"] > 0.7


def test_angry_or_scared_dog_obeys_less():
    calm, cross = calm_dog(), calm_dog()
    cross.mood["분노"] = cross.personality.baseline["분노"] + 0.4
    jev, cmd = {"none": 0.6, "stand": 0.38}, {"stand": 0.85}
    assert _p(cross, jev, cmd)["stand"] < _p(calm, jev, cmd)["stand"] - 0.2


def test_no_command_changes_nothing():
    dog = calm_dog()
    jev = {"sit": 0.5, "stand": 0.5}
    assert _p(dog, jev, {"none": 1.0}) == _p(dog, jev, None)


def test_own_words_do_not_change_posture():
    # 강아지가 자기 말을 한 직후에는 동작을 다시 뽑지 않는다: 말한 동작 = 뽑힌 동작이 바로 바뀌던 문제 (검수 011)
    p = model.probabilities(model.action_scores({"stand": 0.8, "beg": 0.2}, calm_dog(), "none", ["dog_spoke"], T))
    assert p == {"none": 1.0}


def test_command_outweighs_mood_based_action_reading():
    # 실측(대화 중): "일어나!" 시킨 동작 서기 0.73, Jev 동작 없음 0.68·서기 0.15. 시킨 게 분명할수록 동작 질문은 덜 믿는다
    p = _p(calm_dog(), {"none": 0.68, "stand": 0.15, "lie_down": 0.1}, {"stand": 0.73, "none": 0.25, "sit": 0.01})
    assert p["stand"] > 0.6


# ---- 검수 012 묶음 1: 평범한 말은 서운함이 아니다 ----


def _sad_rise(change, **kw):
    dog = calm_dog()
    before = dog.mood["시무룩"]
    model.apply_change(dog, change, [("message", {"text": "…"})], random.Random(0), QUIET, **kw)
    return dog.mood["시무룩"] - before


def test_going_to_work_is_not_rejection():
    # 실측: "나 이제 일 좀 할게"에 Jev 시무룩↑ 0.34·친밀도↓ 0.19, 속상함 0.3, 조용히 0.51 → 평균 강아지 시무룩 +0.11
    assert _sad_rise({"시무룩↑": 0.34, "친밀도↓": 0.19, "변화없음": 0.26}, user_down=0.3, soothe=0.08, hush=0.51) < 0.06


def test_never_mind_is_only_a_small_slight():
    # 실측: "아 아니다 됐어 신경 쓰지 마"에 시무룩↑ 0.48·친밀도↓ 0.27, 속상함 0.53, 조용히 0.67 → 시무룩 +0.18
    assert _sad_rise({"시무룩↑": 0.48, "친밀도↓": 0.27}, user_down=0.53, soothe=0.17, hush=0.67) < 0.07


def test_insult_still_hurts():
    # "너 싫어": 친밀도↓ 0.8, 조용히 0.13. 부탁이 아닌 거절은 그대로 서운하다
    assert _sad_rise({"친밀도↓": 0.8, "분노↑": 0.1}, user_down=0.46, soothe=0.03, hush=0.13) > 0.1


def test_three_readings_of_one_slight_do_not_stack():
    # 직접 시무룩↑, 관계 해석(친밀도↓), 공감(속상함)은 같은 서운함을 세 번 읽은 것이다. 가장 큰 하나만 센다
    one = _sad_rise({"시무룩↑": 0.5})
    three = _sad_rise({"시무룩↑": 0.5, "친밀도↓": 0.5}, user_down=0.9)
    assert three < 1.15 * one


def test_asking_for_space_barely_lowers_intimacy():
    asked, insulted = calm_dog(), calm_dog()
    model.apply_change(asked, {"친밀도↓": 0.7}, [("message", {"text": "말 걸지 마"})], random.Random(0), QUIET, hush=0.83)
    model.apply_change(insulted, {"친밀도↓": 0.7}, [("message", {"text": "저리 가"})], random.Random(0), QUIET, hush=0.1)
    assert 0.5 - asked.intimacy < 0.4 * (0.5 - insulted.intimacy)


# ---- 검수 012 묶음 2: 시킨 잠, 듣는 동안 자세 유지 ----


def test_told_to_sleep_lies_down_even_if_not_sleepy():
    # 실측: "이제 자"에 시킨 동작 잠 0.67~0.76인데 0/4(졸림 문턱이 잠을 막고 서기가 뽑힘). 졸리지 않아도 적어도 엎드린다
    p = _p(calm_dog(), {"stand": 0.4, "none": 0.4, "lie_down": 0.1}, {"sleep": 0.72, "none": 0.28})
    assert p["lie_down"] + p["sleep"] > 0.7


def test_holding_posture_keeps_the_current_action():
    p = model.probabilities(model.action_scores({"beg": 0.9}, calm_dog(), "curious", ["typing"], T, hold=True))
    assert p == {"none": 1.0}


# ---- 검수 013 묶음 1: 부탁과 모진 거절을 가른다 ----


def test_harsh_rejection_hurts_even_if_it_asks_for_space():
    # 실측: "저리 가 귀찮아" 친밀도↓ 0.48·시무룩↑ 0.18, 조용히 0.72, 모진 말 0.91 → 시무룩 +0.017뿐이었다
    assert _sad_rise({"친밀도↓": 0.48, "시무룩↑": 0.18}, user_down=0.4, soothe=0.03, hush=0.72, harsh=0.91) > 0.08


def test_harsh_rejection_lowers_intimacy_more_than_a_plain_request():
    plain, harsh = calm_dog(), calm_dog()
    model.apply_change(plain, {"친밀도↓": 0.5}, [("message", {"text": "일 좀 할게"})], random.Random(0), QUIET, hush=0.7, harsh=0.08)
    model.apply_change(harsh, {"친밀도↓": 0.5}, [("message", {"text": "저리 가 귀찮아"})], random.Random(0), QUIET, hush=0.7, harsh=0.91)
    assert 0.5 - harsh.intimacy > 2 * (0.5 - plain.intimacy)
