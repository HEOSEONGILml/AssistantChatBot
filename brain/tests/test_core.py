import asyncio
import json
from dataclasses import replace

from brain import model
from brain.clients import AuthError, CallError, Readout
from brain.store import Store, StoreError
from brain.tuning import REST

from .conftest import BOTH_KEYS, SILENT, SPEAK, kinds_in, settle, utterances


async def test_message_emits_reaction_and_logs(make):
    env = await make()
    await env.brain.handle_event("message", {"text": "안녕"})
    await env.brain.drain()
    assert [m for m in env.out if m["type"] == "reaction"] == [{"type": "reaction", "reaction": "excited", "action": "beg"}]  # 메시지는 Jev 동작(조르기)을 크게 믿는다 (검수 010)
    assert [e.kind for e in env.store.recent(5)] == ["message", "dog"]
    assert env.store.recent(1)[0].data == {"reaction": "excited", "action": "beg"}
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
    env.jev.readout = Readout({"none": 1.0}, 0.5, {"없음": 1.0})
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
    await env.brain.handle_event("typing", {"text": "그래서 오늘은 뭘 할 거냐면"})
    await env.brain.drain()
    assert len(utterances(env.out)) == 4  # 타이핑도 사용자 입력이라 다시 셀 수 있다


async def test_movement_on_connect_and_when_changed(make):
    env = await make(tuning=replace(SILENT, change_k=3.0), connect=False)
    await env.brain.connected(True)
    assert [m["type"] for m in env.out] == ["status", "movement"]
    env.out.clear()
    await env.brain.clock_tick()
    assert env.out == []  # 바뀐 게 없으면 보내지 않는다
    env.jev.readout = Readout({"none": 1.0}, 0.5, {"졸림": 1.0})
    await env.brain.handle_event("message", {"text": "졸리다"})
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
    assert env.out[0] == {"type": "reaction", "reaction": "excited", "action": "beg"}
    assert utterances(env.out) == []


class BrokenStore(Store):
    def __init__(self):
        super().__init__(None)
        self.saved = 0

    def load_dog(self):
        raise StoreError("읽기 실패")

    def save_dog(self, data):
        self.saved += 1


async def test_unreadable_state_is_not_overwritten(make):
    store = BrokenStore()
    env = await make(store=store)
    assert env.brain.dog.mood == REST
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
    saved = model.new_dog(1_760_000_000.0)
    saved.mood["분노"] = 0.7
    store.save_dog(model.dog_to_dict(saved))
    env = await make(store=store)
    assert env.brain.dog.mood == saved.mood


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
    assert env.brain.dog.mood == REST
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
    assert set(snap) == {"dog", "movement"}
    assert set(snap["dog"]) == {"mood", "updated_at"}  # 기분만 남았다 (단순화 스펙 10절)
    assert set(snap["dog"]["mood"]) == set(REST)
    assert set(snap["movement"]["weights"]) == {"rest", "sleep", "roam", "approach", "play", "explore"}


async def test_log_records_why_the_dog_acted(make):
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("poke", {})
    await env.brain.drain()
    j = env.brain.log_snapshot()["judgements"][-1]
    assert j["events"] == [{"종류": "찌르기"}]
    assert j["jev"]["action"] == {"beg": 1.0} and j["jev"]["speak"] == 0.5 and j["jev"]["change"] == {"들뜸": 1.0}
    assert j["picked"] == {"reaction": "surprised", "action": "bark", "speak": True}  # 찌르기는 우리 평가로 놀람이 1위 (0015)
    assert 0 <= j["model"]["speak"] <= 1 and len(j["model"]["action"]) == 3  # 찔려 화가 오르면 조르기는 상위에서 빠진다 (검수 013)
    assert j["mood_change"]["놀람"] > 0 and "들뜸" not in j["mood_change"]  # 찌르기는 Jev 기분을 쓰지 않는다 (0019)
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
    env.jev.readout = Readout({"none": 1.0}, 0.5, {"없음": 1.0})
    await env.brain.handle_event("typing", {"text": "오늘은"})
    await env.brain.drain()
    # 오른 기분이 없어도 타이핑엔 궁금함. 동작은 메시지가 아니라 우리 모형이 뽑는다 (0020)
    assert [m.get("reaction") for m in env.out if m["type"] == "reaction"] == ["curious"]


async def test_reset_returns_dog_to_rest(make):
    # 설정 창 초기화: 기분이 처음 자리로 돌아가고 기록도 지운다. 키·연결은 그대로 (사용자 결정 2026-10-15, 단순화 스펙 3절)
    env = await make()
    await env.brain.handle_event("message", {"text": "안녕"})
    await env.brain.drain()
    old = model.dog_to_dict(env.brain.dog)
    env.clock.t += 100
    env.out.clear()
    await env.brain.reset()
    new = model.dog_to_dict(env.brain.dog)
    assert old["mood"] != new["mood"] and new["mood"] == REST
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


async def test_no_movement_while_in_house(make):
    # 집에 있는 동안은 움직임 경향도 보내지 않는다 (검수 002 사소). 나오면 다시 보낸다
    env = await make()
    await env.brain.handle_event("house_in", {})
    await env.brain.drain()
    env.out.clear()
    env.brain.dog.mood["졸림"] = 0.95
    env.clock.t += 600
    await env.brain.clock_tick()
    assert [m for m in env.out if m["type"] == "movement"] == []
    await env.brain.handle_event("house_out", {"away_seconds": 600})
    await env.brain.drain()
    assert [m for m in env.out if m["type"] == "movement"]


async def test_dialogue_knows_how_long_the_user_has_been_away(make):
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("message", {"text": "일 좀 할게"})
    await env.brain.drain()
    env.clock.t += 3600
    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    assert "1시간" in env.talker.calls[-1][1]  # '십 분'이 아니라 실제로 혼자 있은 시간


async def test_bad_key_still_reacts_by_our_appraisal(make):
    env = await make()
    env.jev.error = AuthError("typesafe")
    await env.brain.handle_event("poke", {})
    await env.brain.drain()
    assert any(m["type"] == "reaction" and m.get("reaction") == "surprised" for m in env.out)


async def test_dialogue_gets_the_conversation_even_after_many_events(make):
    # 생일처럼 들은 사실은 이벤트가 많이 쌓여도 대화 기록으로 대사에 남는다 (검수 004: 하룻밤 뒤 생일을 잊음)
    env = await make(tuning=SILENT)
    await env.brain.handle_event("message", {"text": "내일이 내 생일이야 기억해 줘"})
    await env.brain.drain()
    for _ in range(40):
        env.clock.t += 600
        await env.brain.handle_event("quiet", {"seconds": 600})
        await env.brain.drain()
    env.brain._t = SPEAK
    await env.brain.handle_event("message", {"text": "오늘 무슨 날이게?"})
    await env.brain.drain()
    prompt = env.talker.calls[-1][1]
    assert "내일이 내 생일이야 기억해 줘" in prompt and "대화 기록" in prompt


async def test_dialogue_gets_one_presence_fact(make):
    # 지금 상황 사실은 주인이 곁에 있는지 하나뿐이다: 곁에 있다 / 자리를 비웠다 / 방금 돌아왔다 (검수 005, 0020)
    env = await make(tuning=SPEAK)

    def facts():
        prompt = env.talker.calls[-1][1]
        return json.loads(prompt[:prompt.rindex("}") + 1])["지금 상황 사실"]

    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    assert facts() == ["주인은 곁에 있다"]
    await env.brain.handle_event("quiet", {"seconds": 1800})
    await env.brain.drain()
    assert facts() == ["주인은 자리를 비웠다. 아직 돌아오지 않았다"]
    await env.brain.handle_event("returned", {"away_seconds": 1800})
    await env.brain.drain()
    assert facts() == ["주인이 자리를 비웠다가 방금 돌아왔다"]
    await env.brain.handle_event("house_out", {"away_seconds": 600})
    await env.brain.drain()
    assert facts() == ["주인은 곁에 있다"]


async def test_one_interjection_per_message(make):
    env = await make(tuning=SPEAK)
    for text in ("오늘 산책 갈까 말까 고민", "오늘 산책 갈까 말까 고민 중이야", "오늘 산책 갈까 말까 고민 중이야 날씨가"):
        await env.brain.handle_event("typing", {"text": text})
        await env.brain.drain()
    assert len(utterances(env.out)) == 1


async def test_conversation_dates_are_annotated(make):
    # 날짜 계산은 우리 모형이 한다: 대화 기록의 "내일"에 들은 날 기준 실제 날짜를 붙인다 (검수 006)
    from datetime import datetime
    env = await make(tuning=SPEAK)
    env.clock.t = datetime(2026, 10, 21, 20, 0).timestamp()
    env.brain.dog.updated_at = env.clock.t
    await env.brain.handle_event("message", {"text": "내일이 내 생일이야"})
    await env.brain.drain()
    env.clock.t = datetime(2026, 10, 22, 8, 0).timestamp()
    await env.brain.handle_event("message", {"text": "좋은 아침! 오늘 무슨 날이게?"})
    await env.brain.drain()
    assert "내일 = 10-22" in env.talker.calls[-1][1]


async def test_no_interjection_on_a_short_fragment(make):
    # 첫 10글자 조각에서는 끼어들지 않는다(귀만 쫑긋). 뜻이 드러난 뒤에 끼어든다 (검수 008: 끼어들기 80%가 첫 조각)
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("typing", {"text": "나 지금부터 한 시"})
    await env.brain.drain()
    assert utterances(env.out) == []
    await env.brain.handle_event("typing", {"text": "나 지금부터 한 시간 집중해야 해서"})
    await env.brain.drain()
    assert len(utterances(env.out)) == 1


async def test_quiet_line_gets_a_topic(make):
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("message", {"text": "이따 같이 공놀이 하자"})
    await env.brain.drain()
    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    assert "꺼낼 이야기" in env.talker.calls[-1][1]


