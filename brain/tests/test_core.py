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
    assert [m for m in env.out if m["type"] == "reaction"] == [{"type": "reaction", "reaction": "excited", "action": "bark"}]  # 시드로 고정된 뽑기 (동작 모형 2026-10-16)
    assert [e.kind for e in env.store.recent(5)] == ["message", "dog"]
    assert env.store.recent(1)[0].data == {"reaction": "excited", "action": "bark"}
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
    env.jev.readout = Readout({"none": 1.0}, 0.5, {"변화없음": 1.0})
    await env.brain.handle_event("dog_spoke", {"text": "멍"})  # 자기 말은 기분을 바꾸지 않아 반응도 없다 (0015)
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
    env.jev.readout = Readout({"none": 1.0}, 0.5, {"졸림↑": 1.0})
    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    assert "movement" in [m["type"] for m in env.out]  # 졸림이 올라 경향이 바뀌었다 (하품 반응도 함께 나간다)
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


async def test_jev_call_error_still_reacts_by_our_appraisal(make):
    # Jev가 실패해도 찔리면 놀란다: 사전값은 우리 모형 몫이다. 대사는 없다 (검수 002)
    env = await make(tuning=SPEAK)
    env.jev.error = CallError("timeout")
    before = env.brain.dog.mood["놀람"]
    await env.brain.handle_event("poke", {})
    await env.brain.drain()
    reactions = [m for m in env.out if m["type"] == "reaction"]
    assert reactions and reactions[0]["reaction"] == "surprised" and "utterance" not in reactions[0]
    assert env.brain.dog.mood["놀람"] > before
    assert env.talker.calls == []


async def test_talker_error_keeps_reaction(make):
    env = await make(tuning=SPEAK)
    env.talker.error = CallError("timeout")
    await env.brain.handle_event("message", {"text": "a"})
    await env.brain.drain()
    assert env.out[0] == {"type": "reaction", "reaction": "excited", "action": "bark"}
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


async def test_quiet_after_a_full_chain_can_speak_again(make):
    # 연달아 말하기 상한은 한 흐름 안에서만이다. 10분 뒤 조용함에는 다시 먼저 말을 걸 수 있다 (시뮬레이션에서 발견)
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("message", {"text": "안녕"})
    await env.brain.drain()
    for _ in range(3):
        await env.brain.handle_event("dog_spoke", {"text": "멍! 안녕"})
        await env.brain.drain()
    assert len(utterances(env.out)) == 3
    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    assert len(utterances(env.out)) == 4


class SpyStore(Store):
    def __init__(self, dog_data):
        super().__init__(None)
        self._dog = dog_data
        self.saved = 0

    def save_dog(self, data):
        self.saved += 1


async def test_malformed_saved_dog_keeps_running_without_overwriting(make):
    # 리뷰 지적: JSON은 맞지만 모양이 어긋난 저장본이면 두뇌가 시작할 때마다 죽었다
    store = SpyStore({"intimacy": 0.4})
    env = await make(store=store)
    assert env.brain.dog.personality.baseline == BIRTH_BASELINE
    await env.brain.clock_tick()
    assert store.saved == 0


async def test_house_in_never_speaks(make):
    # 리뷰 지적: 집에 들어가는 판단에서 대사를 만들면 화면엔 안 보이는데 기록·연속 횟수에 남았다
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("house_in", {})
    await env.brain.drain()
    assert env.talker.calls == [] and utterances(env.out) == []


async def test_state_snapshot_shows_numbers(make):
    env = await make()
    snap = env.brain.state_snapshot()
    assert set(snap) == {"dog", "talkativeness", "movement"}
    assert set(snap["dog"]["mood"]) == set(BIRTH_BASELINE)
    assert "temperament" in snap["dog"]["personality"]
    assert set(snap["movement"]["weights"]) == {"rest", "sleep", "roam", "approach", "play", "explore"}


async def test_log_records_why_the_dog_acted(make):
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("poke", {})
    await env.brain.drain()
    j = env.brain.log_snapshot()["judgements"][-1]
    assert j["events"] == [{"종류": "찌르기"}]
    assert j["jev"]["action"] == {"beg": 1.0} and j["jev"]["speak"] == 0.5 and j["jev"]["change"] == {"들뜸↑": 1.0}
    assert j["picked"] == {"reaction": "surprised", "action": "bark", "speak": True}  # 찌르기는 우리 평가로 놀람이 1위 (0015)
    assert 0 <= j["model"]["speak"] <= 1 and "beg" in j["model"]["action"]
    assert j["mood_change"]["들뜸"] > 0
    assert j["utterance"] == "멍! 안녕"
    assert env.brain.log_snapshot()["events"][-1].endswith("강아지: 멍! 안녕")


async def test_log_records_jev_failure(make):
    env = await make()
    env.jev.error = CallError("timeout")
    await env.brain.handle_event("poke", {})
    await env.brain.drain()
    assert "error" in env.brain.log_snapshot()["judgements"][-1]


async def test_typing_always_shows_a_reaction(make):
    env = await make()
    env.jev.readout = Readout({"none": 1.0}, 0.5, {"변화없음": 1.0})
    await env.brain.handle_event("typing", {"text": "오늘은"})
    await env.brain.drain()
    assert [m for m in env.out if m["type"] == "reaction"] == [{"type": "reaction", "reaction": "curious"}]  # 오른 기분이 없어도 타이핑엔 궁금함


async def test_reset_gives_birth_to_a_new_dog(make):
    # 설정 창 초기화: 새 성격으로 다시 태어나고 기록도 지운다. 키·연결은 그대로 (사용자 결정 2026-10-15)
    env = await make()
    await env.brain.handle_event("message", {"text": "안녕"})
    await env.brain.drain()
    old = model.dog_to_dict(env.brain.dog)
    env.clock.t += 100
    env.out.clear()
    await env.brain.reset()
    new = model.dog_to_dict(env.brain.dog)
    assert new["personality"] != old["personality"]
    assert new["updated_at"] == env.clock.t
    assert env.store.recent(5) == []
    assert env.store.load_dog() == new
    assert env.brain.log_snapshot()["judgements"] == []
    assert [m["type"] for m in env.out] == ["movement"]  # 새 강아지의 움직임 경향을 바로 보낸다
    await env.brain.handle_event("message", {"text": "또 안녕"})
    await env.brain.drain()
    assert len(env.jev.calls) == 2  # 계속 판단한다


async def test_reset_overwrites_a_malformed_saved_dog():
    # 읽지 못한 저장본은 평소엔 덮어쓰지 않지만, 사용자가 초기화하면 새 강아지로 덮어쓴다
    from .conftest import build
    store = Store(None)
    store.save_dog({"broken": True})
    env = await build(store=store)
    await env.brain.reset()
    assert env.store.load_dog() == model.dog_to_dict(env.brain.dog)
    await env.brain.aclose()


async def test_interjection_while_typing_is_one_line(make):
    # 타이핑 중 끼어들기는 한마디로 끝낸다. 사용자가 아직 치는 중이라 이어 재촉하지 않는다 (검수 001 사소)
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("typing", {"text": "오늘 회사에서 있잖아"})
    await env.brain.drain()
    await env.brain.handle_event("dog_spoke", {"text": "멍! 안녕"})
    await env.brain.drain()
    assert utterances(env.out) == ["멍! 안녕"]
    await env.brain.handle_event("message", {"text": "있잖아 그래서"})
    await env.brain.drain()
    await env.brain.handle_event("dog_spoke", {"text": "멍! 안녕"})
    await env.brain.drain()
    assert len(utterances(env.out)) == 3  # 답한 뒤에는 이어 말할 수 있다


async def test_question_waits_for_an_answer_even_with_a_trailing_bark(make):
    # "…? 멍!"처럼 물음표 뒤에 의성어가 붙어도 질문이다. 질문했으면 이어 말하지 않고 답을 기다린다 (검수 002)
    env = await make(tuning=SPEAK)
    env.talker.line = "밖은 날씨가 어때? 멍멍!"
    await env.brain.handle_event("message", {"text": "오늘 기분 좋다"})
    await env.brain.drain()
    await env.brain.handle_event("dog_spoke", {"text": "밖은 날씨가 어때? 멍멍!"})
    await env.brain.drain()
    assert utterances(env.out) == ["밖은 날씨가 어때? 멍멍!"]
    await env.brain.handle_event("message", {"text": "맑아"})
    await env.brain.drain()
    assert len(utterances(env.out)) == 2  # 답이 오면 다시 말한다
