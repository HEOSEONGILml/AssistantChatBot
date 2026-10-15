import asyncio
from types import SimpleNamespace

import pytest

from brain.clients import Judgement
from brain.core import Brain
from brain.memory import History
from brain.tuning import Tuning

BOTH_KEYS = {"typesafe": "t-key", "gemini": "g-key"}


class FakeClock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


class FakeJev:
    def __init__(self):
        self.calls: list[dict] = []
        self.result = Judgement("calm", "none", 0.0)
        self.error: Exception | None = None
        self.gate: asyncio.Event | None = None  # 설정하면 열릴 때까지 응답을 미룬다

    async def judge(self, state):
        self.calls.append(state)
        if self.gate:
            await self.gate.wait()
        if self.error:
            raise self.error
        return self.result

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


async def settle(predicate, tries: int = 50):
    """비동기 작업이 조건을 만족할 때까지 이벤트 루프를 몇 번 돌린다."""
    for _ in range(tries):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("조건이 만족되지 않음")


@pytest.fixture
async def env():
    out: list[dict] = []

    async def emit(msg):
        out.append(msg)

    jev, talker, clock = FakeJev(), FakeTalker(), FakeClock()
    history = History(None)
    brain = Brain(emit=emit, make_clients=lambda keys: (jev, talker), history=history, clock=clock, tuning=Tuning())
    await brain.set_keys(BOTH_KEYS)
    await brain.connected(True)
    out.clear()
    yield SimpleNamespace(brain=brain, out=out, jev=jev, talker=talker, clock=clock, history=history)
    await brain.aclose()


def reactions(out):
    return [m for m in out if m["type"] == "reaction"]


def utterances(out):
    return [m["utterance"] for m in out if m["type"] == "reaction" and "utterance" in m]
