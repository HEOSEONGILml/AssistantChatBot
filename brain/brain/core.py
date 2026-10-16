"""두뇌 핵심 (두뇌 스펙 v2): 화면이 보낸 이벤트를 모아 Jev를 한 번 부르고, 확률 모델로 뽑아 반응·대사를 낸다.
기분 시계는 Jev를 부르지 않고 기분을 갱신해, 움직임 경향이 바뀌면 화면에 보낸다. 전송 방식과 화면을 모른다."""
import asyncio
import logging
import random
import re
import time
from datetime import datetime
from collections import deque
from typing import Awaitable, Callable

from . import model
from .clients import AuthError, CallError, Jev, Readout, Talker
from .persona import annotate_dates, date_facts, dialogue_prompt, frequent_phrases, system_instruction, trim_line, voice
from .questions import describe_event, format_log, jev_state
from .store import Event, Store, StoreError
from .tuning import EVENT_KINDS, Tuning

log = logging.getLogger(__name__)

Emit = Callable[[dict], Awaitable[None]]
MakeClients = Callable[[dict[str, str | None]], tuple[Jev, Talker]]
_REQUEST = re.compile(r"(줘|줄래|주라|주세요|봐|하자|가자|놀자)\s*[.!~ㅎㅋ]*\s*$")  # 부탁과 함께 하자는 말 (검수 005·008)
from .tuning import MOOD_REACTION_ID as _MRI
_MOOD_KO = {v: k for k, v in _MRI.items()}  # 반응 id → 기분 이름
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
        self._flow = ""                  # 지금 흐름을 연 이벤트 종류 (dog_spoke 말고 마지막 이벤트)
        self._hush_until = 0.0             # 이 시각까지 먼저 말 걸지 않는다("말 걸지 마", 검수 007)
        self._unanswered = 0               # 먼저 말을 건 뒤 사용자 대꾸가 없었던 횟수 (검수 006)
        self._interjected = False          # 이번 메시지를 치는 동안 이미 끼어들었다 (검수 006: 한 문장에 세 번)
        self._hold = False                 # 이 흐름에서는 이어 말하지 않는다: 타이핑 중 끼어들었거나(검수 001) 핀잔을 들었다(검수 002)
        self._user_away = False            # 사용자가 자리를 비웠다(화면이 30분 조용함을 보냄). 대사에 사실로 준다 (검수 005)
        self._in_house = False             # 집에 있는 동안은 움직임 경향도 보내지 않는다 (검수 002)
        self._sent_movement: dict | None = None
        self._can_save = True
        self._judgements: deque[dict] = deque(maxlen=200)  # 판단 로그: 설정 창 로그 탭용, 메모리에만 (스펙 3.1)
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
        try:
            return model.dog_from_dict(data)
        except (TypeError, KeyError, ValueError):
            log.exception("저장된 강아지 상태의 모양이 어긋나 기본값으로 계속한다. 저장본을 덮어쓰지 않는다")
            self._can_save = False
            return model.default_dog(now)

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

    async def reset(self) -> None:
        """설정 창 초기화: 강아지가 새 성격으로 다시 태어나고 이벤트 기록·판단 로그를 지운다. 키와 연결은 그대로다.
        사용자가 고른 일이므로 읽지 못한 저장본도 덮어쓴다."""
        self._cancel()
        self._pending.clear()
        self._streak, self._waiting, self._hold, self._in_house, self._user_away = 0, False, False, False, False
        self._store.clear_events()
        self._judgements.clear()
        self._dog = model.birth(self._rng, self._clock())
        self._can_save = True
        self._save()
        log.info("초기화: 강아지가 새로 태어났다")
        self._sent_movement = None
        await self._push_movement()

    async def aclose(self) -> None:
        self._cancel()
        await self._close_clients()
        self._save()

    # ---- 조회 (설정 창 상태·로그 탭, 스펙 3.1) ----

    def state_snapshot(self) -> dict:
        model.advance(self._dog, self._clock(), self._rng, self._t)  # 지금 시각의 기분을 보여 준다
        return {"dog": model.dog_to_dict(self._dog),
                "talkativeness": round(model.talkativeness(self._dog, self._t), 3),
                "movement": model.movement(self._dog, self._t)}

    def log_snapshot(self, n: int = 50) -> dict:
        return {"judgements": list(self._judgements)[-n:],
                "events": format_log(self._store.recent(n), self._clock())}

    # ---- 이벤트 ----

    async def handle_event(self, kind: str, context: dict) -> None:
        if kind not in EVENT_KINDS:
            log.warning("모르는 이벤트를 버림: %s", kind)
            return
        ev = Event(self._clock(), "user" if kind in USER_KINDS else "screen", kind, dict(context or {}))
        self._store.add(ev)
        # 연달아 말하기는 한 흐름(말풍선이 뜨고 이어 말하기) 안에서만 센다. 다른 일이 생기면 새 흐름이다
        if kind != "dog_spoke":
            self._streak = 0
            self._flow = kind  # 이 흐름을 연 이벤트
            self._hold = False
        if kind in ("message", "typing"):
            self._waiting = False
        if kind in USER_KINDS:
            self._user_away = False
            self._unanswered = 0
        if kind == "message":
            self._interjected = False
            self._hush_until = 0.0  # 사용자가 다시 말을 걸면 부탁은 끝난다(새 메시지가 다시 부탁이면 판단에서 다시 켠다)
        elif kind == "quiet" and float((context or {}).get("seconds") or 0) >= 1800:
            self._user_away = True
        if kind in ("house_in", "house_out"):
            self._in_house = kind == "house_in"
            self._sent_movement = None  # 나오면 지금 경향을 바로 다시 보낸다
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
        entry: dict = {"ts": now, "events": [describe_event(e.kind, e.data) for e in batch]}
        self._judgements.append(entry)
        try:
            rd = await self._jev.judge(state)
        except AuthError:
            # 키가 틀려도 찔리면 놀란다: 우리 평가 사전값으로 반응하고 말하지 않는다 (검수 003)
            entry["error"] = "키 오류"
            await self._set_ai("bad_key")
            rd = Readout({}, 0.0, {})
        except CallError as e:
            # Jev 없이도 우리 평가 사전값으로 기분·반응·동작은 낸다. 대사는 없다 (검수 002)
            entry["error"] = f"Jev 실패: {e}"
            log.warning("Jev 실패(%s). 우리 모형만으로 반응하고 말하지 않는다", e)
            rd = Readout({}, 0.0, {})
        kinds = [e.kind for e in batch]
        if kinds[-1] == "message" and rd.hush >= 0.5:
            self._hush_until = now + t.hush_s
        waiting = self._waiting
        if kinds[-1] == "quiet":
            self._waiting = False  # 무시당한 서운함은 한 번만. 조용함마다 쌓이지 않는다 (검수 003)
        # 기분이 먼저 변하고(우리 평가 사전값 + Jev 조정, 0015), 가장 크게 오른 기분이 곧 반응이다. 동작은 그 반응을 반영해 뽑는다
        last_user = max((e.ts for e in self._store.recent(500) if e.kind in USER_KINDS), default=now)  # 혼자 있은 시간
        deltas = model.apply_change(dog, rd.change, [(e.kind, e.data) for e in batch], self._rng, t, user_down=rd.user_down, soothe=rd.soothe,
                                    waiting=waiting, alone_s=now - last_user)
        reaction = model.reaction_from(deltas, kinds, t)
        a_scores = model.action_scores(rd.action, dog, reaction, kinds, t)
        action = model.pick(a_scores, self._rng)
        # 집에 들어가는 순간에는 말하지 않는다: 화면이 보여 주지 않으므로 대사가 기록·연속 횟수에만 남는다 (스펙 8절)
        # 타이핑 중에 끼어든 뒤에는 이어 말하지 않는다: 사용자가 아직 치는 중이다 (검수 001)
        # 질문했으면 이어 말하지 않고 답을 기다린다 (검수 002). 조용함이 오면 다시 말을 걸 수 있다
        if "error" in entry or kinds[-1] == "house_in" or (kinds[-1] == "dog_spoke" and (self._hold or self._waiting)) \
                or (kinds[-1] == "typing" and (self._interjected or len(str(batch[-1].data.get("text", ""))) < t.interject_min_chars)):
            p_speak = 0.0
        else:
            last = batch[-1]
            text = str(last.data.get("text", ""))
            # 물음표 없는 부탁("다시 말해 줘", "알려 줄래")도 묻는 말이다 (검수 005)
            asked = last.kind == "message" and ("?" in text or _REQUEST.search(text) is not None)
            hurting = last.kind == "message" and rd.soothe < 0.5 and (rd.user_down >= 0.5 or deltas.signal.get("시무룩", 0.0) >= 0.05)
            asked = asked or (last.kind == "message" and rd.soothe >= 0.5)  # 사과는 받아 준다 (검수 010)
            ignored = self._unanswered if self._flow not in ("message", "typing") else 0
            p_speak = model.chain_probability(dog, self._streak, t, ignored, now < self._hush_until) if kinds[-1] == "dog_spoke" else \
                model.speak_probability(rd.speak, dog, kinds[-1], self._streak, self._waiting, t, asked, hurting, self._unanswered,
                                        now < self._hush_until)
        speak = self._rng.random() < p_speak
        entry.update({"jev": {"action": _top(rd.action), "speak": round(rd.speak, 3), "change": _top(rd.change), "user_down": round(rd.user_down, 3), "soothe": round(rd.soothe, 3), "hush": round(rd.hush, 3)},
                      "model": {"action": _top(model.probabilities(a_scores)), "speak": round(p_speak, 3)},
                      "picked": {"reaction": reaction, "action": action, "speak": speak},
                      "mood_change": {k: round(v, 3) for k, v in deltas.items() if abs(v) >= 0.005}})
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
            own = [e.data["utterance"] for e in recent if e.kind == "dog" and "utterance" in e.data][-5:]
            # 대화 기록: 이벤트 창(30개)과 따로, 실제로 오간 말만 최근 20줄. 하룻밤이 지나도 들은 사실이 남는다 (검수 004)
            talk = [e for e in self._store.recent(500) if e.kind == "message" or (e.kind == "dog" and "utterance" in e.data)][-20:]
            conversation = [f"{datetime.fromtimestamp(e.ts):%m-%d(%a) %H:%M} · "
                            + (f"사용자: {annotate_dates(e.data.get('text', ''), e.ts)}" if e.kind == "message" else f"강아지(나): {e.data['utterance']}")
                            for e in talk]
            v = voice(dog, t)  # 성격에서 나온 말투 (검수 004)
            lines40 = [e.data["utterance"] for e in self._store.recent(500) if e.kind == "dog" and "utterance" in e.data][-40:]
            # 지금 상황 사실: 주인이 곁에 있는지, 집에서 나온 쪽이 누구인지 (검수 005: 지어냄)
            facts = ["주인은 자리를 비웠다. 아직 돌아오지 않았다" if self._user_away else
                     ("주인은 곁에서 조용히 뭔가 하고 있다(떠나지 않았다)" if kinds[-1] == "quiet" else "주인은 곁에 있다")]
            if "returned" in kinds:  # 돌아온 순간에는 "곁에 있다" 대신 이 사실만 (검수 007: "옆에 있는 거 다 아는데")
                facts = ["주인이 자리를 비웠다가 방금 돌아왔다"]
            if "house_out" in kinds:
                facts.append("방금 강아지(나)가 집에서 나왔다. 집에 들어가 있던 쪽은 나다. 주인이 꺼내 줬다")
            elif any(e.kind == "house_out" and now - e.ts < 600 for e in recent):
                facts.append("조금 전까지 집 안에 있던 쪽은 강아지(나)다. 주인은 밖에 있었다")
            facts += date_facts([(e.ts, e.data.get("text", "")) for e in self._store.recent(500) if e.kind == "message"], now)
            if kinds[-1] == "message":  # 끼어들며 한 말도 내 말이다: 메시지에 답할 때 뒤집지 않는다 (검수 006)
                said = [e.data["utterance"] for e in talk[:-1] if e.kind == "dog"]
                prev_msg = max((i for i, e in enumerate(talk[:-1]) if e.kind == "message"), default=-1)
                just = [e.data["utterance"] for e in talk[prev_msg + 1:-1] if e.kind == "dog"]
                if just and said:
                    facts.append(f"방금 네가 한 말: {just[-1]} — 이 말과 어긋나지 않게 이어 간다")
            line = trim_line(await self._talker.say(system_instruction(), dialogue_prompt(state, reaction, action, kinds, own, now - last_user,
                                                                                          conversation, v["지시"], rd.user_down >= 0.5 and rd.soothe < 0.5, facts,
                                                                                          _MOOD_KO.get(model.dominant_mood(dog, t), ""),
                                                                                          frequent_phrases(lines40))), v["문장 수"])
        except AuthError:
            await self._set_ai("bad_key")
            return
        except CallError as e:
            log.warning("Gemini 실패(%s). 대사 없이 넘어간다", e)
            return
        if not line:
            return
        await self._emit({"type": "reaction", "utterance": line})
        entry["utterance"] = line
        self._store.add(Event(self._clock(), "dog", "dog", {"utterance": line}))
        self._streak += 1
        if kinds[-1] == "typing":
            self._interjected = True
        if self._flow not in ("message", "typing") and self._streak == 1:
            self._unanswered += 1  # 먼저 말을 건 흐름 하나
        self._hold = kinds[-1] == "typing" or (kinds[-1] == "message" and rd.change.get("친밀도↓", 0.0) >= 0.4)
        # "…? 멍!"도 질문이다 (검수 002). 다만 사용자와 말을 주고받는 흐름의 질문만 답을 기다린다.
        # 조용함·몸 이벤트에서 나온 혼잣말 질문은 기다리지 않는다 (검수 004: 혼잣말 질문마다 서운함)
        self._waiting = "?" in line and self._flow in ("message", "typing")

    async def _push_movement(self) -> None:
        if not self._connected or self._in_house:
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


def _top(dist: dict[str, float], k: int = 3) -> dict[str, float]:
    return {key: round(v, 3) for key, v in sorted(dist.items(), key=lambda x: -x[1])[:k]}
