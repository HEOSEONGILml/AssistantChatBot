from dataclasses import replace

from brain import model
from brain.tuning import Tuning
from sim import record, simulate


def fake_recording():
    flat_a = {a: 1 / len(model.ACTIONS) for a in model.ACTIONS}
    return simulate.Recording({record.key(*c): {"action": flat_a, "speak": 0.5, "change": {"들뜸↑": 0.3, "변화없음": 0.7}}
                               for c in record.cases()})


def test_cases_cover_every_kind_preset_and_streak():
    assert len({record.key(*c) for c in record.cases()}) == 10 * 10 * 2 + 2 * 10 * 2  # 기분 프리셋 10개


def test_world_runs_a_day():
    s = simulate.run(simulate.archetype_dog("평균"), fake_recording(), Tuning(), days=1, seed=1).stats
    assert s.judged > 50
    for kind in ("typing", "message", "quiet"):
        assert 0 <= s.rate(kind) <= 1
    assert s.chains and all(1 <= c <= 3 for c in s.chains)
    assert sum(s.actions.values()) == s.judged - s.counts["dog_spoke"][0]  # 자기 말 뒤에는 동작을 고르지 않는다 (검수 011)


def test_bias_raises_rate():
    rec, base = fake_recording(), Tuning()
    def rate(b):
        t = replace(base, kind_bias={**base.kind_bias, "message": b})
        return simulate.run(simulate.archetype_dog("평균"), rec, t, days=3, seed=1).stats.rate("message")
    assert rate(3.0) > rate(-3.0)


def test_fit_returns_bias_for_four_kinds():
    bias = simulate.fit(fake_recording(), Tuning(), days=1, rounds=1)
    for kind in ("typing", "message", "quiet", "dog_spoke"):
        assert -10 <= bias[kind] <= 10


def test_archetypes_differ():
    assert simulate.archetype_dog("과묵·차분").personality != simulate.archetype_dog("활발·변덕쟁이").personality


def test_message_target_counts_plain_news_only():
    # 검수 015: 답하기 85% 목표에 질문(거의 늘 대답)이 섞여 물음표 없는 소식은 74%였다. 소식과 질문을 따로 센다
    from brain.tuning import Tuning
    s = simulate.run(simulate.archetype_dog("평균"), simulate.Recording.load(), Tuning(), days=2, seed=1).stats
    assert s.counts["message"][0] > 0 and s.counts["message_asked"][0] > 0
    assert s.rate("message_asked") > s.rate("message")
