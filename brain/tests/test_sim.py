from dataclasses import replace

from brain import model
from brain.tuning import Tuning
from sim import record, simulate


def fake_recording():
    flat_r = {r: 1 / len(model.REACTIONS) for r in model.REACTIONS}
    flat_a = {a: 1 / len(model.ACTIONS) for a in model.ACTIONS}
    return simulate.Recording({record.key(*c): {"reaction": flat_r, "action": flat_a, "speak": 0.5, "change": {"변화없음": 1.0}}
                               for c in record.cases()})


def test_cases_cover_every_kind_preset_and_streak():
    assert len({record.key(*c) for c in record.cases()}) == 10 * 6 * 2 + 2 * 6 * 2


def test_world_runs_a_day():
    s = simulate.run(simulate.archetype_dog("평균"), fake_recording(), Tuning(), days=1, seed=1).stats
    assert s.judged > 50
    for kind in ("typing", "message", "quiet"):
        assert 0 <= s.rate(kind) <= 1
    assert s.chains and all(1 <= c <= 3 for c in s.chains)
    assert 0 <= s.kept / s.judged <= 1


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
