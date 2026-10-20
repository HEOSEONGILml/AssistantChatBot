"""검수 하네스 실행기 (검수 루프 스펙 2절): 시나리오대로 두뇌를 돌리고 일어난 일을 모두 기록한다.

화면 대신 이벤트를 보내고, 가상 시계로 시간을 넘긴다. 화면이 하는 일 두 가지를 흉내 낸다:
대사가 나오면 `dog_spoke`를 보내고, 조용하면 `quiet`를 보낸다(`app/src/body/events.ts`와 같은 값).
두뇌 코드는 바꾸지 않는다. 단계 관찰만 두뇌 내부(`_phase`)를 쓴다(하네스 전용)."""
import asyncio
import json
import random
from datetime import datetime
from pathlib import Path

from brain import config, model
from brain.clients import AuthError, CallError, Readout, make_clients
from brain.core import Brain
from brain.store import Store
from brain.tuning import MOODS, Tuning

RUN = "기본"                               # 기록의 run 값. 성격 유형이 없어져 실행은 하나다 (단순화 스펙 11절)
QUIET_PRESENT_S, QUIET_AWAY_S = 600, 1800  # events.ts QUIET_PRESENT_MS, QUIET_AWAY_MS
TYPING_CHARS = 10                          # events.ts TYPING_CHARS: 이만큼 바뀌면 타이핑 이벤트
LONG_WAIT_S, LONG_TICK_S = 7200, 300       # 조용함 없이 2시간 넘게 기다리면 5분 간격 틱 (회차를 짧게, 사용자 요청).
                                           # 기분은 경과 시간으로 계산되므로 값은 같고 movement 전송 시점만 성겨진다


class Faults:
    """`keys` 단계가 정하는 고장: ok / fail(호출 실패) / bad(키 오류)."""
    def __init__(self):
        self.mode = "ok"
        self.failures = 0
        self.calls = {"jev": 0, "talker": 0}

    def check(self, who: str) -> None:
        self.calls[who] += 1
        if self.mode == "bad":
            self.failures += 1
            raise AuthError(who)
        if self.mode == "fail":
            self.failures += 1
            raise CallError(f"{who} 검수용 실패")


class FlakyJev:
    def __init__(self, inner, faults: Faults):
        self.inner, self.faults = inner, faults

    async def judge(self, state):
        self.faults.check("jev")
        return await self.inner.judge(state)

    async def aclose(self):
        await self.inner.aclose()


class FlakyTalker:
    def __init__(self, inner, faults: Faults):
        self.inner, self.faults = inner, faults

    async def say(self, system, prompt):
        self.faults.check("talker")
        return await self.inner.say(system, prompt)

    async def aclose(self):
        await self.inner.aclose()


class FakeJev:
    """가짜 Jev: 시드로 정해지는 아무 분포. 하네스 시험용이고 판정에는 쓰지 않는다."""
    def __init__(self, rng: random.Random, speak: float | None):
        self.rng, self.speak = rng, speak

    def _dist(self, keys):
        w = [self.rng.random() ** 3 for _ in keys]
        s = sum(w)
        return {k: x / s for k, x in zip(keys, w)}

    async def judge(self, state):
        speak = self.speak if self.speak is not None else self.rng.random()
        return Readout(self._dist(list(model.ACTION_NAMES)), min(speak, 0.999), self._dist([*MOODS, "없음"]))

    async def aclose(self):
        pass


class FakeTalker:
    def __init__(self, rng: random.Random):
        self.rng, self.n = rng, 0

    async def say(self, system, prompt):
        await asyncio.sleep(0.01)  # 실제 Gemini처럼 시간이 걸려야 '말하는 중' 단계가 생긴다
        self.n += 1
        return f"멍! 가짜 대사 {self.n}" + ("?" if self.rng.random() < 0.3 else "")

    async def aclose(self):
        pass


def _snapshot(dog: model.Dog, t: Tuning) -> dict:
    return {"mood": {d: round(v, 4) for d, v in dog.mood.items()}}


class Runner:
    def __init__(self, scenario: dict, *, fake: bool, db: Path):
        self.sc, self.fake, self.db = scenario, fake, db
        self.t = Tuning()
        self.clock = datetime.fromisoformat(scenario.get("start", "2026-10-19T09:00")).timestamp()
        self.rng = random.Random(scenario.get("seed", 1))
        self.faults = Faults()
        self.records: list[dict] = []
        self.brain: Brain | None = None
        self.last_event_at = self.clock
        self.connected = True
        self.during = "step"
        self._spoken: list[str] = []
        self._seen: set[int] = set()

    # ---- 기록 ----

    def rec(self, type_: str, **kw) -> None:
        self.records.append({"type": type_, "t": self.clock, **kw})

    def snap(self, tick: bool = False) -> None:
        self.rec("snap", tick=tick, **_snapshot(self.brain.dog, self.t))

    def _collect_judgements(self) -> None:
        for e in self.brain.log_snapshot(200)["judgements"]:
            if id(e) not in self._seen:
                self._seen.add(id(e))
                self.rec("judgement", entry=e)

    # ---- 두뇌 ----

    def _keys(self) -> dict:
        return {"typesafe": "fake", "gemini": "fake"} if self.fake else config.read_keys()

    def _make_clients(self, keys):
        if self.fake:
            inner = (FakeJev(self.rng, self.sc.get("fake_speak")), FakeTalker(self.rng))
        else:
            inner = make_clients(keys, self.t)
        return FlakyJev(inner[0], self.faults), FlakyTalker(inner[1], self.faults)

    async def _emit(self, msg: dict) -> None:
        self.rec("out", msg=msg, during=self.during)
        if "utterance" in msg and self.connected:
            self._spoken.append(msg["utterance"])

    async def _boot(self) -> None:
        self.brain = Brain(emit=self._emit, make_clients=self._make_clients, store=Store(self.db),
                           clock=lambda: self.clock, rng=random.Random(self.rng.random()), tuning=self.t)
        self._seen.clear()
        await self.brain.set_keys(self._keys())
        if self.connected:
            await self.brain.connected(True)

    async def settle(self) -> None:
        """판단과 이어지는 판단이 끝날 때까지 기다린다. 대사가 나왔으면 화면처럼 dog_spoke를 보낸다."""
        while True:
            await self.brain.drain()
            if not self._spoken:
                break
            text = self._spoken.pop(0)
            await self.send("dog_spoke", {"text": text}, wait=False)
        self._collect_judgements()

    async def send(self, kind: str, context: dict | None = None, wait: bool = True) -> None:
        context = context or {}
        self.rec("sent", kind=kind, context=context, phase=self.brain._phase or "idle")
        self.last_event_at = self.clock
        await self.brain.handle_event(kind, context)
        if wait:
            await self.settle()

    # ---- 단계 ----

    async def step(self, s: dict) -> None:
        if "say" in s:
            text = s["say"]
            for n in range(TYPING_CHARS, len(text), TYPING_CHARS):
                await self.send("typing", {"text": text[:n]})
            await self.send("message", {"text": text})
        elif "event" in s:
            if s.get("during_speech"):  # 앞 판단이 대사를 만드는 중일 때 보낸다(말 버리기 검수)
                for _ in range(2000):
                    if self.brain._phase == "speaking" or self.brain._task is None:
                        break
                    await asyncio.sleep(0.005)
            await self.send(s["event"], s.get("context"), wait=not s.get("nowait"))
        elif "wait" in s:
            await self.wait(float(s["wait"]), away=bool(s.get("away")), quiet=s.get("quiet", True))
        elif "restart" in s:
            await self.settle()
            await self.brain.aclose()
            await self._boot()
            self.rec("restart", remembered=len(self.brain._store.recent(30)))
        elif "keys" in s:
            await self.settle()
            mode = s["keys"]
            if mode == "none":
                await self.brain.set_keys({})
            else:
                self.faults.mode = "ok" if mode == "ok" else mode
                if mode == "ok":
                    await self.brain.set_keys(self._keys())
            self.rec("keys", mode=mode)
        elif "disconnect" in s:
            await self.settle()
            self.connected = False
            await self.brain.connected(False)
            self.rec("connect", on=False)
        elif "connect" in s:
            self.connected = True
            await self.brain.connected(True)
            self.rec("connect", on=True)
        elif "reset" in s:
            await self.settle()
            await self.brain.reset()
            self._seen.clear()
            self.rec("reset")
        elif "get_state" in s:
            self.rec("state", state=self.brain.state_snapshot())
        elif "get_log" in s:
            self.rec("log", log=self.brain.log_snapshot())
        elif "note" in s:
            self.rec("note", text=s["note"])
        else:
            raise ValueError(f"모르는 단계: {s}")

    async def wait(self, seconds: float, away: bool, quiet: bool) -> None:
        await self.settle()
        end = self.clock + seconds
        gap = QUIET_AWAY_S if away else QUIET_PRESENT_S
        tick = LONG_TICK_S if not quiet and seconds > LONG_WAIT_S else self.t.clock_s
        self.during = "tick"
        while self.clock < end:
            self.clock = min(end, self.clock + tick)
            await self.brain.clock_tick()
            self.snap(tick=True)
            if quiet and self.connected and self.clock - self.last_event_at >= gap:
                self.during = "step"
                await self.send("quiet", {"seconds": int(self.clock - self.last_event_at)})
                self.during = "tick"
        self.during = "step"

    async def run(self) -> list[dict]:
        await self._boot()
        self.rec("start", name=self.sc.get("name"), mode="fake" if self.fake else "real")
        self.snap()
        try:
            for i, s in enumerate(self.sc["steps"]):
                self.rec("step", i=i, step=s)
                await self.step(s)
                if not s.get("nowait"):  # 기다리지 않는 단계는 다음 단계와 겹쳐야 묶음·말 버리기가 일어난다
                    await self.settle()
                self.snap()
        finally:
            await self.brain.aclose()
            self.rec("end", calls=dict(self.faults.calls), failures=self.faults.failures)
        return self.records


async def run_scenario(sc: dict, *, fake: bool, out_dir: Path) -> dict[str, list[dict]]:
    """시나리오를 돌려 {실행 이름: 기록}을 돌려주고 `out_dir/<이름>.jsonl`에 쓴다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    db = out_dir / f"{sc['name']}.db"
    db.unlink(missing_ok=True)
    runs = {RUN: await Runner(sc, fake=fake, db=db).run()}
    with (out_dir / f"{sc['name']}.jsonl").open("w", encoding="utf-8") as f:
        for n, recs in runs.items():
            for r in recs:
                f.write(json.dumps({"run": n, **r}, ensure_ascii=False) + "\n")
    return runs
