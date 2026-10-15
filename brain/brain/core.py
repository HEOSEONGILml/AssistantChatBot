"""두뇌 핵심 (두뇌 스펙 v2): 화면이 보낸 이벤트를 모아 Jev를 한 번 부르고, 확률 모델로 뽑아 반응·대사를 낸다.
기분 시계는 Jev를 부르지 않고 기분을 갱신해, 움직임 경향이 바뀌면 화면에 보낸다. 전송 방식과 화면을 모른다."""
import asyncio
import logging
import random
import time
from typing import Awaitable, Callable

from . import model
from .clients import AuthError, CallError, Jev, Talker
from .persona import dialogue_prompt, system_instruction, trim_line
from .questions import jev_state
from .store import Event, Store, StoreError
from .tuning import EVENT_KINDS, Tuning

log = logging.getLogger(__name__)

Emit = Callable[[dict], Awaitable[None]]
MakeClients = Callable[[dict[str, str | None]], tuple[Jev, Talker]]
USER_KINDS = {"typing", "message", "poke", "pet", "throw", "returned"}  # 사용자가 한 일. 나머지는 화면이 알린 상황


class Brain:
    def __init__(self, *, emit: Emit, make_clients: MakeClients, store: Store,
                 clock: Callable[[], float] = time.time, rng: random.Random | None = None, tuning: Tuning = Tuning()):
        self._emit = emit
        self._make_clients = make_clients
        self._store = store
        self._clock = clock
        self._rng = rng or random.Random()
        self._t = tuning
        self._jev: Jev | None = None
        self._talker: Talker | None = None
        self._ai = "no_keys"
        self._connected = False
        self._pending: list[Event] = []
        self._task: asyncio.Task | None = None
        self._phase: str | None = None     # judging / speaking
        self._streak = 0                   # 사용자 입력 없이 강아지가 연달아 말한 횟수
        self._waiting = False              # 강아지가 질문하고 답을 기다리는 중
        self._sent_movement: dict | None = None
        self._can_save = True
        self._dog = self._load_dog()

    @property
    def dog(self) -> model.Dog:
        return self._dog

    def _load_dog(self) -> model.Dog:
        now = self._clock()
        try:
            data = self._store.load_dog()
        except StoreError:
            log.exception("강아지 상태를 읽지 못해 기본값으로 계속한다. 저장된 성격을 덮어쓰지 않도록 저장하지 않는다")
            self._can_save = False
            return model.default_dog(now)
        if data is None:
            dog = model.birth(self._rng, now)
            self._store.save_dog(model.dog_to_dict(dog))
            log.info("강아지가 태어났다")
            return dog
        return model.dog_from_dict(data)

    def _save(self) -> None:
        if self._can_save:
            self._store.save_dog(model.dog_to_dict(self._dog))

    # ---- 화면 연결과 설정 ----

    async def connected(self, on: bool) -> None:
        self._connected = on
        if on:
            await self._emit({"type": "status", "ai": self._ai})
            self._sent_movement = None
            await self._push_movement()
        else:
            self._cancel()
            self._pending.clear()

    async def set_keys(self, keys: dict[str, str | None]) -> None:
        await self._close_clients()
        if all(keys.get(name) for name in ("typesafe", "gemini")):
            self._jev, self._talker = self._make_clients(keys)
            await self._set_ai("ok")
        else:
            await self._set_ai("no_keys")

    async def clear_history(self) -> None:
        self._store.clear_events()

    async def aclose(self) -> None:
        self._cancel()
        await self._close_clients()
        self._save()

    # ---- 이벤트 ----

    async def handle_event(self, kind: str, context: dict) -> None:
        if kind not in EVENT_KINDS:
            log.warning("모르는 이벤트를 버림: %s", kind)
            return
        ev = Event(self._clock(), "user" if kind in USER_KINDS else "screen", kind, dict(context or {}))
        self._store.add(ev)
        if kind in ("message", "typing"):
            self._streak, self._waiting = 0, False
        if kind == "house_in" or (kind == "message" and self._phase == "speaking"):
            self._cancel()  # 만들던 대사를 버린다 (스펙 8절)
            if kind == "house_in":
                self._pending.clear()  # 집에서는 조용
        self._pending.append(ev)
        self._maybe_start()

    # ---- 기분 시계 (스펙 6.5) ----

    async def clock_tick(self) -> None:
        model.advance(self._dog, self._clock(), self._rng, self._t)
        model.record_mood(self._dog)
        self._save()
        await self._push_movement()

    async def run_clock(self) -> None:
        while True:
            await asyncio.sleep(self._t.clock_s)
            await self.clock_tick()

    async def drain(self) -> None:
        """진행 중인 판단과 이어지는 판단이 모두 끝날 때까지 기다린다 (테스트·종료용)."""
        while self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)
            await asyncio.sleep(0)

    # ---- 판단 ----

    def _busy(self) -> bool:
        return self._task is not None and not self._task.done()

    def _cancel(self) -> None:
        if self._busy():
            self._task.cancel()
        self._task, self._phase = None, None

    def _maybe_start(self) -> None:
        if self._busy() or not self._pending:
            return
        if not self._connected or self._ai != "ok":
            self._pending.clear()  # 기록에는 남았다
            return
        batch, self._pending = self._pending, []
        self._phase = "judging"
        self._task = asyncio.create_task(self._run(batch))

    async def _run(self, batch: list[Event]) -> None:
        try:
            await self._judge(batch)
        except Exception:
            log.exception("판단 중 예상하지 못한 오류")
        finally:
            if asyncio.current_task() is self._task:
                self._task, self._phase = None, None
                self._maybe_start()  # 판단 중에 온 이벤트를 묶어서 판단

    async def _judge(self, batch: list[Event]) -> None:
        assert self._jev is not None and self._talker is not None
        dog, t, now = self._dog, self._t, self._clock()
        model.advance(dog, now, self._rng, t)
        recent = [e for e in self._store.recent(t.recent_events + len(batch)) if e not in batch][-t.recent_events:]
        state = jev_state(dog, batch, recent, now)
        try:
            rd = await self._jev.judge(state)
        except AuthError:
            await self._set_ai("bad_key")
            return
        except CallError as e:
            log.warning("Jev 실패(%s). 이번 판단은 건너뛴다", e)
            return
        kinds = [e.kind for e in batch]
        reaction = model.pick(model.reaction_scores(rd.reaction, dog, model.habit_level(dog, kinds), t), self._rng)
        action = model.pick(model.action_scores(rd.action, dog, reaction, t), self._rng)
        model.apply_change(dog, rd.change, kinds, self._rng, t)
        speak = self._rng.random() < model.speak_probability(rd.speak, dog, kinds[-1], self._streak, self._waiting, t)
        self._save()
        shown = {k: v for k, v in (("reaction", reaction), ("action", action)) if v != "none"}
        if shown:
            await self._emit({"type": "reaction", **shown})
        self._store.add(Event(self._clock(), "dog", "dog", {"reaction": reaction, "action": action}))
        await self._push_movement()
        if not speak:
            return
        self._phase = "speaking"
        try:
            line = trim_line(await self._talker.say(system_instruction(), dialogue_prompt(state, reaction, action)))
        except AuthError:
            await self._set_ai("bad_key")
            return
        except CallError as e:
            log.warning("Gemini 실패(%s). 대사 없이 넘어간다", e)
            return
        if not line:
            return
        await self._emit({"type": "reaction", "utterance": line})
        self._store.add(Event(self._clock(), "dog", "dog", {"utterance": line}))
        self._streak += 1
        self._waiting = line.rstrip().endswith("?")

    async def _push_movement(self) -> None:
        if not self._connected:
            return
        mv = model.movement(self._dog, self._t)
        if model.movement_changed(self._sent_movement, mv, self._t):
            self._sent_movement = mv
            await self._emit({"type": "movement", **mv})

    async def _set_ai(self, ai: str) -> None:
        if ai == self._ai:
            return
        self._ai = ai
        # 판단 도중(키 오류)이면 그 판단은 곧 끝나므로 자기 자신은 취소하지 않는다
        if ai != "ok" and asyncio.current_task() is not self._task:
            self._cancel()
        if self._connected:
            await self._emit({"type": "status", "ai": ai})

    async def _close_clients(self) -> None:
        for c in (self._jev, self._talker):
            if c is None:
                continue
            try:
                await c.aclose()
            except Exception:
                log.exception("클라이언트 닫기 실패")
        self._jev = self._talker = None
