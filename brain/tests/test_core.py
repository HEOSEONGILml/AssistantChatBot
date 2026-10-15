import asyncio
from dataclasses import replace

from brain import model
from brain.clients import AuthError, CallError, Readout
from brain.store import Store, StoreError
from brain.tuning import BIRTH_BASELINE

from .conftest import BOTH_KEYS, SILENT, SPEAK, kinds_in, settle, utterances


async def test_message_emits_reaction_and_logs(make):
    env = await make()
    await env.brain.handle_event("message", {"text": "안녕"})
    await env.brain.drain()
    assert env.out == [{"type": "reaction", "reaction": "joy", "action": "beg"}]
    assert [e.kind for e in env.store.recent(5)] == ["message", "dog"]
    assert env.store.recent(1)[0].data == {"reaction": "joy", "action": "beg"}
    assert kinds_in(env.jev.calls[0]) == ["메시지 보냄"]
    assert env.talker.calls == []


async def test_speaks_and_logs_utterance(make):
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("message", {"text": "안녕"})
    await env.brain.drain()
    assert utterances(env.out) == ["멍! 안녕"]
    assert env.store.recent(1)[0].data == {"utterance": "멍! 안녕"}
    assert "이번에 뽑힌 반응" in env.talker.calls[0][1]


async def test_none_picks_are_not_sent(make):
    env = await make()
    env.jev.readout = Readout({"none": 1.0}, {"none": 1.0}, 0.5, {"변화없음": 1.0})
    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    assert [m for m in env.out if m["type"] == "reaction"] == []


async def test_events_during_judgement_are_batched(make):
    env = await make()
    env.jev.gate = asyncio.Event()
    await env.brain.handle_event("poke", {})
    await settle(lambda: len(env.jev.calls) == 1)
    for kind in ("poke", "poke", "pet"):
        await env.brain.handle_event(kind, {})
    env.jev.gate.set()
    await env.brain.drain()
    assert len(env.jev.calls) == 2
    assert kinds_in(env.jev.calls[1]) == ["찌르기", "찌르기", "쓰다듬기"]


async def test_message_discards_line_being_spoken(make):
    env = await make(tuning=SPEAK)
    env.talker.gate = asyncio.Event()
    await env.brain.handle_event("message", {"text": "a"})
    await settle(lambda: len(env.talker.calls) == 1)
    await env.brain.handle_event("message", {"text": "b"})
    await settle(lambda: len(env.talker.calls) == 2)
    env.talker.gate.set()
    await env.brain.drain()
    assert utterances(env.out) == ["멍! 안녕"]
    assert env.jev.calls[1]["이번 이벤트들"] == [{"종류": "메시지 보냄", "맥락": {"글": "b"}}]


async def test_house_in_discards_and_clears_pending(make):
    env = await make()
    env.jev.gate = asyncio.Event()
    await env.brain.handle_event("poke", {})
    await settle(lambda: len(env.jev.calls) == 1)
    await env.brain.handle_event("poke", {})
    await env.brain.handle_event("house_in", {})
    await settle(lambda: len(env.jev.calls) == 2)
    env.jev.gate.set()
    await env.brain.drain()
    assert len(env.jev.calls) == 2
    assert kinds_in(env.jev.calls[1]) == ["강아지가 집에 들어감"]


async def test_dog_spoke_chain_stops_at_cap(make):
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("message", {"text": "안녕"})
    await env.brain.drain()
    for _ in range(3):
        await env.brain.handle_event("dog_spoke", {"text": "멍! 안녕"})
        await env.brain.drain()
    assert len(utterances(env.out)) == 3  # 사용자 입력 없이 3번이면 멈춘다
    await env.brain.handle_event("typing", {"text": "그래서"})
    await env.brain.drain()
    assert len(utterances(env.out)) == 4  # 타이핑도 사용자 입력이라 다시 셀 수 있다


async def test_movement_on_connect_and_when_changed(make):
    env = await make(tuning=replace(SILENT, change_k=3.0), connect=False)
    await env.brain.connected(True)
    assert [m["type"] for m in env.out] == ["status", "movement"]
    env.out.clear()
    await env.brain.clock_tick()
    assert env.out == []  # 바뀐 게 없으면 보내지 않는다
    env.jev.readout = Readout({"none": 1.0}, {"none": 1.0}, 0.5, {"졸림↑": 1.0})
    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    assert [m["type"] for m in env.out] == ["movement"]
    env.out.clear()
    env.clock.t += 7200
    await env.brain.clock_tick()
    assert [m["type"] for m in env.out] == ["movement"]  # 기분이 풀리면 다시 보낸다


async def test_disconnected_makes_no_judgement(make):
    env = await make(connect=False)
    await env.brain.handle_event("message", {"text": "안녕"})
    await env.brain.drain()
    await env.brain.clock_tick()
    assert env.jev.calls == [] and env.out == []
    assert [e.kind for e in env.store.recent(5)] == ["message"]


async def test_auth_error_then_new_keys_recover(make):
    env = await make()
    env.jev.error = AuthError("typesafe")
    await env.brain.handle_event("message", {"text": "a"})
    await env.brain.drain()
    assert env.out[-1] == {"type": "status", "ai": "bad_key"}
    env.jev.error = None
    await env.brain.handle_event("message", {"text": "b"})
    await env.brain.drain()
    assert len(env.jev.calls) == 1
    await env.brain.set_keys(BOTH_KEYS)
    assert env.out[-1] == {"type": "status", "ai": "ok"}
    await env.brain.handle_event("message", {"text": "c"})
    await env.brain.drain()
    assert len(env.jev.calls) == 2


async def test_jev_call_error_skips(make):
    env = await make()
    env.jev.error = CallError("timeout")
    await env.brain.handle_event("message", {"text": "a"})
    await env.brain.drain()
    assert [m for m in env.out if m["type"] == "reaction"] == []


async def test_talker_error_keeps_reaction(make):
    env = await make(tuning=SPEAK)
    env.talker.error = CallError("timeout")
    await env.brain.handle_event("message", {"text": "a"})
    await env.brain.drain()
    assert env.out[0] == {"type": "reaction", "reaction": "joy", "action": "beg"}
    assert utterances(env.out) == []


class BrokenStore(Store):
    def __init__(self):
        super().__init__(None)
        self.saved = 0

    def load_dog(self):
        raise StoreError("읽기 실패")

    def save_dog(self, data):
        self.saved += 1


async def test_unreadable_state_keeps_stored_personality(make):
    store = BrokenStore()
    env = await make(store=store)
    assert env.brain.dog.personality.baseline == BIRTH_BASELINE
    await env.brain.handle_event("message", {"text": "a"})
    await env.brain.drain()
    await env.brain.clock_tick()
    await env.brain.aclose()
    assert store.saved == 0


async def test_new_dog_is_born_and_saved(make):
    store = Store(None)
    env = await make(store=store)
    assert store.load_dog() == model.dog_to_dict(env.brain.dog)


async def test_stored_dog_is_restored(make):
    import random
    store = Store(None)
    saved = model.birth(random.Random(9), 1_760_000_000.0)
    store.save_dog(model.dog_to_dict(saved))
    env = await make(store=store)
    assert env.brain.dog.personality == saved.personality


async def test_unknown_kind_is_ignored(make):
    env = await make()
    await env.brain.handle_event("teleport", {})
    await env.brain.drain()
    assert env.jev.calls == [] and env.store.recent(5) == []


async def test_clear_history_keeps_dog(make):
    env = await make()
    await env.brain.handle_event("message", {"text": "a"})
    await env.brain.drain()
    before = model.dog_to_dict(env.brain.dog)
    await env.brain.clear_history()
    assert env.store.recent(5) == []
    assert env.store.load_dog() == before
