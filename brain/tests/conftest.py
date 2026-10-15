import asyncio
import random
from dataclasses import replace
from types import SimpleNamespace

import pytest

from brain.clients import Readout
from brain.core import Brain
from brain.store import Store
from brain.tuning import EVENT_KINDS, Tuning

BOTH_KEYS = {"typesafe": "t-key", "gemini": "g-key"}
_CALM = Tuning(mood_noise=0.0, change_noise=0.0)
SPEAK = replace(_CALM, kind_bias={k: 30.0 for k in EVENT_KINDS})    # 거의 늘 말함
SILENT = replace(_CALM, kind_bias={k: -30.0 for k in EVENT_KINDS})  # 거의 안 말함


class FakeClock:
    def __init__(self, t: float = 1_760_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


class FakeJev:
    def __init__(self):
        self.calls: list[dict] = []
        self.readout = Readout({"joy": 1.0}, {"beg": 1.0}, 0.5, {"변화없음": 1.0})
        self.error: Exception | None = None
        self.gate: asyncio.Event | None = None

    async def judge(self, state):
        self.calls.append(state)
        if self.gate:
            await self.gate.wait()
        if self.error:
            raise self.error
        return self.readout

    async def aclose(self):
        pass


class FakeTalker:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.line = "멍! 안녕"
        self.error: Exception | None = None
        self.gate: asyncio.Event | None = None

    async def say(self, system, prompt):
        self.calls.append((system, prompt))
        if self.gate:
            await self.gate.wait()
        if self.error:
            raise self.error
        return self.line

    async def aclose(self):
        pass


async def settle(predicate, tries: int = 100):
    for _ in range(tries):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("조건이 만족되지 않음")


async def build(tuning=SILENT, store=None, keys=BOTH_KEYS, connect=True):
    out: list[dict] = []

    async def emit(msg):
        out.append(msg)

    jev, talker, clock = FakeJev(), FakeTalker(), FakeClock()
    store = store if store is not None else Store(None)
    brain = Brain(emit=emit, make_clients=lambda k: (jev, talker), store=store, clock=clock,
                  rng=random.Random(0), tuning=tuning)
    await brain.set_keys(keys)
    if connect:
        await brain.connected(True)
    out.clear()
    return SimpleNamespace(brain=brain, out=out, jev=jev, talker=talker, clock=clock, store=store)


@pytest.fixture
async def make():
    built = []

    async def _make(**kw):
        env = await build(**kw)
        built.append(env)
        return env

    yield _make
    for env in built:
        await env.brain.aclose()


def utterances(out):
    return [m["utterance"] for m in out if m["type"] == "reaction" and "utterance" in m]


def kinds_in(state):
    return [e["종류"] for e in state["이번 이벤트들"]]
