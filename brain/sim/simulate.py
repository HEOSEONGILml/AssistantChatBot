"""녹화한 Jev 분포로 확률 모델을 돌려 지표를 내고, 이벤트 종류별 보정값을 맞춘다 (두뇌 스펙 v2 10절).
실행: brain/에서  uv run python -m sim.simulate          # 지표 보고
                 uv run python -m sim.simulate --fit    # 보정값 맞춘 뒤 보고
가상 사용자 모형은 잠정값이다: 평일 9~18시 자리에 있고 12~13시 점심으로 비운다."""
import argparse
import json
import math
import random
import statistics
from dataclasses import dataclass, field, replace
from datetime import datetime

from brain import model
from brain.core import USER_KINDS
from brain.clients import Readout
from brain.tuning import BASELINE_RANGE, BIRTH_BASELINE, MOODS, Tuning

from .record import INTIMACY, OUT, PRESETS

ARCHETYPES = {  # 성격 유형 (기준값, 민감도, 변덕). 성격 유형 실측과 같은 값
    "평균": ({"심심함": .6, "졸림": .3, "들뜸": .4, "시무룩": .2, "분노": .1, "궁금함": .5, "놀람": .1, "무서움": .1, "행복": .4}, .5, .5),
    "과묵·차분": ({"심심함": .3, "졸림": .3, "들뜸": .2, "시무룩": .2, "분노": .1, "궁금함": .3, "놀람": .1, "무서움": .1, "행복": .3}, .4, .2),
    "예민·성마름": ({"심심함": .5, "졸림": .3, "들뜸": .3, "시무룩": .4, "분노": .4, "궁금함": .4, "놀람": .3, "무서움": .3, "행복": .3}, .8, .6),
    "활발·변덕쟁이": ({"심심함": .7, "졸림": .2, "들뜸": .7, "시무룩": .1, "분노": .1, "궁금함": .7, "놀람": .1, "무서움": .1, "행복": .6}, .6, .9),
}
# 스펙 10절 (평균 성격 기준). 끼어들기는 15% → 30% (사용자 요청 "타이핑하는 동안 반응을 더 많이", 기분 8개 스펙)
# 연달아 2번+ 실사용 목표 20%(검수 006). 실사용이 시뮬레이션의 약 2배로 나와(검수 008: 40% vs 19%) 시뮬레이션 목표는 10%
TARGETS = {"typing": 0.30, "message": 0.85, "quiet": 1 / 3, "chain2plus": 0.10}
START = datetime(2026, 10, 19).timestamp()  # 월요일 0시
P_MESSAGE, P_POKE, P_PET, P_THROW = 0.03, 0.005, 0.005, 0.002  # 분당 (잠정값)
P_ASK = 0.4          # 사용자 메시지 중 질문 비율 (잠정값, 검수 004)
P_REPLY = 0.5        # 강아지가 말하면 사용자가 답하는 비율 (잠정값)
P_QUESTION = 0.48    # 강아지 대사에 물음표가 있는 비율. 검수 002 실제 대사 85개 실측


class Recording:
    def __init__(self, data: dict):
        self.data = data
        self.moods = {p: {**BIRTH_BASELINE, **o} for p, o in PRESETS.items()}

    @classmethod
    def load(cls) -> "Recording":
        return cls(json.loads(OUT.read_text(encoding="utf-8")))

    def readout(self, kind: str, dog: model.Dog, streak: int) -> Readout:
        preset = min(self.moods, key=lambda p: sum((dog.mood[d] - self.moods[p][d]) ** 2 for d in MOODS))
        intimacy = min(INTIMACY, key=lambda x: abs(x - dog.intimacy))
        r = self.data[f"{kind}|{preset}|{intimacy}|{min(streak, 2) if kind == 'dog_spoke' else 0}"]
        return Readout(r["action"], r["speak"], r["change"], r.get("user_down", 0.0), r.get("soothe", 0.0), r.get("hush", 0.0), r.get("command", {}))


@dataclass
class Stats:
    counts: dict = field(default_factory=dict)   # 꼬리표 → (판단 수, 말한 수)
    chains: list = field(default_factory=list)   # 사용자 입력 없이 이어 말한 길이
    actions: dict = field(default_factory=dict)  # 뽑힌 동작별 횟수, 자기 말 뒤는 빼고 (가장 흔한 동작 비율 ≤ 0.5, 동작 모형 스펙)
    judged: int = 0
    stuck: int = 0                               # 기분이 0.9 이상이거나 0.05 이하인 표본 수 (기분 차원별)
    reactions: dict = field(default_factory=dict)  # 반응별 횟수
    samples: int = 0

    def rate(self, tag: str) -> float:
        n, s = self.counts.get(tag, (0, 0))
        return s / n if n else float("nan")

    def chain2plus(self) -> float:
        return sum(c >= 2 for c in self.chains) / len(self.chains) if self.chains else float("nan")

    def stuck_ratio(self) -> float:
        return self.stuck / (self.samples * len(MOODS)) if self.samples else float("nan")


class World:
    """강아지 한 마리와 가상 사용자. 확률 모델만으로 처리하고 Jev는 녹화본을 쓴다."""

    def __init__(self, dog: model.Dog, rec: Recording, rng: random.Random, t: Tuning):
        self.dog, self.rec, self.rng, self.t = dog, rec, rng, t
        self.now = self.last = self.last_user = dog.updated_at
        self.unanswered, self.interjected, self.flow = 0, False, ""
        self.streak, self.waiting = 0, False
        self.stats = Stats()

    def _judge(self, kind: str, tag: str | None) -> bool:
        dog, t = self.dog, self.t
        model.advance(dog, self.now, self.rng, t)
        if kind != "dog_spoke":  # 두뇌 core와 같은 규칙: 연달아 말하기는 한 흐름 안에서만
            self.streak = 0
        if kind in ("message", "typing"):
            self.waiting = False
        rd = self.rec.readout(kind, dog, self.streak)
        if kind != "dog_spoke":
            self.flow = kind
        if kind in USER_KINDS:
            self.last_user = self.now
            self.unanswered = 0
        if kind == "message":
            self.interjected = False
        deltas = model.apply_change(dog, rd.change, [(kind, {})], self.rng, t, waiting=self.waiting, alone_s=self.now - self.last_user,
                                    user_down=rd.user_down, soothe=rd.soothe, hush=rd.hush)
        reaction = model.reaction_from(deltas, [kind], t)
        self.stats.reactions[reaction] = self.stats.reactions.get(reaction, 0) + 1
        scores = model.action_scores(rd.action, dog, reaction, [kind], t, command=rd.command if kind == "message" else None)
        a = model.pick(scores, self.rng)
        self.stats.judged += 1
        if kind != "dog_spoke":  # 자기 말 뒤에는 동작을 고르지 않는다 (검수 011)
            self.stats.actions[a] = self.stats.actions.get(a, 0) + 1
        asked = kind == "message" and self.rng.random() < P_ASK
        hurting = kind == "message" and rd.soothe < 0.5 and (rd.user_down >= 0.5 or deltas.signal.get("시무룩", 0.0) >= 0.05)
        asked = asked or (kind == "message" and rd.soothe >= 0.5)
        p = model.chain_probability(dog, self.streak, t, self.unanswered if self.flow == "quiet" else 0) if kind == "dog_spoke" else \
            0.0 if kind == "typing" and self.interjected else \
            model.speak_probability(rd.speak, dog, kind, self.streak, self.waiting, t, asked, hurting, self.unanswered)
        spoke = self.rng.random() < p
        n, s = self.stats.counts.get(tag or kind, (0, 0))
        self.stats.counts[tag or kind] = (n + 1, s + int(spoke))
        self.last = self.now
        if spoke:
            self.streak += 1
            if kind == "typing":
                self.interjected = True
            if kind == "quiet":
                self.unanswered += 1
            self.waiting = self.rng.random() < P_QUESTION
        return spoke

    def event(self, kind: str, tag: str | None = None) -> bool:
        """이벤트 하나를 처리하고, 강아지가 말하면 말풍선 이벤트(dog_spoke)로 이어 말할지 따진다."""
        if not self._judge(kind, tag) or kind == "dog_spoke":
            return False
        length = 1
        if kind == "typing":  # 두뇌 core와 같은 규칙: 타이핑 중 끼어들기는 한마디로 끝낸다 (검수 001)
            self.stats.chains.append(length)
            return True
        while not self.waiting:  # 두뇌 core와 같은 규칙: 질문했으면 이어 말하지 않는다 (검수 002)
            self.now += 2
            if not self._judge("dog_spoke", None):
                break
            length += 1
        self.stats.chains.append(length)
        return True

    def sample(self, minutes: int = 1) -> None:
        """기분 표본. 실제 두뇌는 하루 내내 30초마다 고르게 모으므로, 자리 비움 30분 표본은 30분 몫으로 센다."""
        model.advance(self.dog, self.now, self.rng, self.t)
        for _ in range(minutes):
            model.record_mood(self.dog)
        self.stats.samples += 1
        self.stats.stuck += sum(m >= 0.9 or m <= 0.05 for m in self.dog.mood.values())

    def away(self, until: float) -> None:
        while self.now + 1800 <= until:  # 자리 비움: 30분마다 조용함
            self.now += 1800
            self.event("quiet", "quiet_away")
            self.sample(30)
        self.now = until

    def present(self, until: float) -> None:
        while self.now < until:
            self.now += 60
            r, spoke = self.rng.random(), False
            if r < P_MESSAGE:
                self.event("typing")
                self.event("typing")
                spoke = self.event("message")
            elif r < P_MESSAGE + P_POKE:
                spoke = self.event("poke")
            elif r < P_MESSAGE + P_POKE + P_PET:
                spoke = self.event("pet")
            elif r < P_MESSAGE + P_POKE + P_PET + P_THROW:
                spoke = self.event("throw")
            elif self.now - self.last >= 600:
                spoke = self.event("quiet")
            if spoke and self.rng.random() < P_REPLY:
                self.now += 20
                self.event("typing")
                self.event("message")
            self.sample()

    def day(self, midnight: float) -> None:
        self.away(midnight + 9 * 3600)
        self.event("returned")
        self.present(midnight + 12 * 3600)
        self.away(midnight + 13 * 3600)
        self.event("returned")
        self.present(midnight + 18 * 3600)
        self.away(midnight + 24 * 3600)


def run(dog: model.Dog, rec: Recording, t: Tuning, days: int, seed: int) -> World:
    w = World(dog, rec, random.Random(seed), t)
    for i in range(days):
        w.day(START + i * 86400)
    return w


def archetype_dog(name: str) -> model.Dog:
    base, sens, whim = ARCHETYPES[name]
    dog = model.default_dog(START)
    dog.personality = model.Personality(dict(base), {d: sens for d in MOODS}, whim)
    dog.mood = dict(base)
    return dog


def fit(rec: Recording, t: Tuning, days: int = 10, seed: int = 1, rounds: int = 3) -> dict:
    """평균 성격 강아지가 목표 지표에 맞도록 이벤트 종류별 보정값을 이분 탐색한다 (보정값이 커지면 비율이 커진다)."""
    bias = dict(t.kind_bias)
    goals = [("typing", lambda s: s.rate("typing"), TARGETS["typing"]),
             ("message", lambda s: s.rate("message"), TARGETS["message"]),
             ("quiet", lambda s: s.rate("quiet"), TARGETS["quiet"]),
             ("dog_spoke", lambda s: s.chain2plus(), TARGETS["chain2plus"])]
    chain = t.chain_base
    for _ in range(rounds):
        for kind, metric, target in goals:
            # 이어 말하기는 kind_bias가 아니라 chain_base로 맞춘다 (검수 005)
            lo, hi = (0.01, 0.9) if kind == "dog_spoke" else (-10.0, 10.0)
            for _ in range(14):
                mid = (lo + hi) / 2
                tt = replace(t, chain_base=mid, kind_bias=bias) if kind == "dog_spoke" else replace(t, chain_base=chain, kind_bias={**bias, kind: mid})
                v = metric(run(archetype_dog("평균"), rec, tt, days, seed).stats)
                if math.isnan(v) or v < target:
                    lo = mid
                else:
                    hi = mid
            if kind == "dog_spoke":
                chain = round((lo + hi) / 2, 3)
            else:
                bias[kind] = round((lo + hi) / 2, 2)
    return {**bias, "chain_base": chain}


def _row(name: str, s: Stats) -> str:
    return (f"| {name} | {s.rate('typing'):.2f} | {s.rate('message'):.2f} | {s.rate('quiet'):.2f} | {s.chain2plus():.2f} "
            f"| {max(s.actions.values()) / sum(s.actions.values()):.2f} | {s.stuck_ratio():.2f} |")


def report(rec: Recording, t: Tuning, days: int = 7, dogs: int = 100, weeks: int = 8) -> str:
    head = ["| 대상 | 끼어들기 (typing) | 답하기 (message) | 먼저 말 걸기 (quiet) | 연달아 2번+ | 가장 흔한 동작 비율 | 기분 고착 |",
            "|---|---|---|---|---|---|---|",
            f"| **목표** | {TARGETS['typing']:.2f} | {TARGETS['message']:.2f} | {TARGETS['quiet']:.2f} | {TARGETS['chain2plus']:.2f} | ≤ 0.50 | ≤ 0.20 |"]
    rows = [_row(name, run(archetype_dog(name), rec, t, days, 1).stats) for name in ARCHETYPES]
    pop = [run(model.birth(random.Random(i), START), rec, t, days, i).stats for i in range(dogs)]
    metrics = {"typing": [s.rate("typing") for s in pop], "message": [s.rate("message") for s in pop],
               "quiet": [s.rate("quiet") for s in pop], "chain": [s.chain2plus() for s in pop]}
    spread = " | ".join(f"{min(v):.2f} / {statistics.median(v):.2f} / {max(v):.2f}"
                        for v in ([x for x in vs if not math.isnan(x)] for vs in metrics.values()))
    rows.append(f"| 무작위 {dogs}마리 (최소/중앙/최대) | {spread} | | |")
    # 성격 변화: 기준값이 한계(0.05·0.95)에 붙는지, 얼마나 움직이는지, 개성(강아지 사이 차이)이 남는지
    at_edge, moved, born, grown = 0, [], [], []
    for i in range(20):
        dog = model.birth(random.Random(1000 + i), START)
        b0 = dict(dog.personality.baseline)
        b1 = run(dog, rec, t, weeks * 7, i).dog.personality.baseline
        edge = lambda b: {m for m, v in b.items() if v <= BASELINE_RANGE[0] + 0.01 or v >= BASELINE_RANGE[1] - 0.01}
        at_edge += bool(edge(b1) - edge(b0))  # 태어날 때 이미 한계였던 것은 빼고, 새로 붙은 것만
        moved.append(max(abs(b1[m] - b0[m]) for m in MOODS))
        born.append(b0)
        grown.append(b1)

    def spread(bs):
        return statistics.mean(statistics.pstdev([b[m] for b in bs]) for m in MOODS)

    tail = [f"\n{weeks}주 뒤 기준값이 새로 한계(0.05·0.95)에 붙은 강아지: 20마리 중 {at_edge}마리 (목표 0)",
            f"\n{weeks}주 동안 기준값이 가장 크게 움직인 폭: 중앙 {statistics.median(moved):.2f}, 최대 {max(moved):.2f}",
            f"\n강아지 사이 기준값 표준편차(개성): 태어날 때 {spread(born):.3f} → {weeks}주 뒤 {spread(grown):.3f}",
            f"\nkind_bias = {json.dumps(t.kind_bias, ensure_ascii=False)}"]
    return "\n".join(head + rows + tail)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--dogs", type=int, default=100)
    args = ap.parse_args()
    rec, t = Recording.load(), Tuning()
    if args.fit:
        f = fit(rec, t)
        chain = f.pop("chain_base")
        t = replace(t, kind_bias=f, chain_base=chain)
        print(f"chain_base = {chain}")
    print(report(rec, t, args.days, args.dogs))


if __name__ == "__main__":
    main()
