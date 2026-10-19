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
    assert 0 <= j["model"]["speak"] <= 1 and len(j["model"]["action"]) == 3  # 찔려 화가 오르면 조르기는 상위에서 빠진다 (검수 013)
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


async def test_after_a_rebuke_the_dog_does_not_keep_talking(make):
    # 핀잔("시끄러워")을 들은 흐름에서는 이어 말하지 않는다 (검수 002 사소)
    env = await make(tuning=SPEAK)
    env.jev.readout = Readout({"none": 1.0}, 0.9, {"친밀도↓": 0.67, "분노↑": 0.16})
    await env.brain.handle_event("message", {"text": "너 진짜 시끄러워"})
    await env.brain.drain()
    await env.brain.handle_event("dog_spoke", {"text": "멍! 안녕"})
    await env.brain.drain()
    assert len(utterances(env.out)) == 1


async def test_dialogue_knows_how_long_the_user_has_been_away(make):
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("message", {"text": "일 좀 할게"})
    await env.brain.drain()
    env.clock.t += 3600
    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    assert "1시간" in env.talker.calls[-1][1]  # '십 분'이 아니라 실제로 혼자 있은 시간


async def test_ignored_once_then_no_more_sadness_buildup(make):
    # 질문하고 무시당하면 한 번 서운하다. 조용함이 이어질 때마다 쌓이지 않는다 (검수 003)
    env = await make(tuning=SPEAK)
    env.talker.line = "뭐 해?"
    await env.brain.handle_event("message", {"text": "일 좀 할게"})
    await env.brain.drain()
    assert env.brain._waiting
    env.talker.line = "심심해"
    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    assert not env.brain._waiting


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


async def test_rhetorical_question_outside_a_conversation_does_not_wait(make):
    # 조용함에서 나온 혼잣말 질문("놀아 줄 사람 없나?")은 답을 기다리지 않는다. 대화 중 질문만 기다린다 (검수 004)
    env = await make(tuning=SPEAK)
    env.talker.line = "놀아 줄 사람 없나?"
    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    assert not env.brain._waiting
    await env.brain.handle_event("message", {"text": "안녕"})
    await env.brain.drain()
    assert env.brain._waiting


async def test_core_marks_question_and_sad_message(make):
    from brain.tuning import Tuning
    env = await make(tuning=Tuning())
    env.jev.readout = Readout({"none": 1.0}, 0.3, {"시무룩↑": 0.6})
    await env.brain.handle_event("message", {"text": "오늘 회사에서 크게 혼났어"})
    await env.brain.drain()
    sad = env.brain.log_snapshot()["judgements"][-1]["model"]["speak"]
    env.jev.readout = Readout({"none": 1.0}, 0.3, {"변화없음": 1.0})
    await env.brain.handle_event("message", {"text": "그냥 그래"})
    await env.brain.drain()
    flat = env.brain.log_snapshot()["judgements"][-1]["model"]["speak"]
    await env.brain.handle_event("message", {"text": "너는 기분 어때?"})
    await env.brain.drain()
    asked = env.brain.log_snapshot()["judgements"][-1]["model"]["speak"]
    assert sad > flat + 0.2 and asked > flat + 0.2


async def test_dialogue_gets_presence_and_house_facts(make):
    # 주인이 곁에 있는지·자리를 비웠는지, 집에서 나온 쪽이 강아지인지를 사실로 준다 (검수 005: 지어냄)
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    assert "곁에" in env.talker.calls[-1][1]
    await env.brain.handle_event("quiet", {"seconds": 1800})
    await env.brain.drain()
    assert "자리를 비웠" in env.talker.calls[-1][1]
    await env.brain.handle_event("house_in", {})
    await env.brain.drain()
    await env.brain.handle_event("house_out", {"away_seconds": 600})
    await env.brain.drain()
    assert "강아지(나)가 집에서 나왔" in env.talker.calls[-1][1]
    await env.brain.handle_event("message", {"text": "집에서 뭐 하고 있었어?"})
    await env.brain.drain()
    assert "조금 전까지 집 안에 있던 쪽은 강아지(나)" in env.talker.calls[-1][1]


async def test_requests_without_question_mark_count_as_asked(make):
    # "다시 말해 줘"처럼 물음표 없는 부탁에도 거의 늘 대답한다 (검수 005 사소)
    from brain.tuning import Tuning
    env = await make(tuning=Tuning())
    env.jev.readout = Readout({"none": 1.0}, 0.6, {"변화없음": 1.0})
    await env.brain.handle_event("message", {"text": "그냥 그래"})
    await env.brain.drain()
    flat = env.brain.log_snapshot()["judgements"][-1]["model"]["speak"]
    await env.brain.handle_event("message", {"text": "아까 네가 뭐 골랐는지 다시 말해 줘"})
    await env.brain.drain()
    asked = env.brain.log_snapshot()["judgements"][-1]["model"]["speak"]
    assert asked > flat and asked > 0.95


async def test_ignored_dog_speaks_up_less_and_less(make):
    # 주인이 대꾸하지 않으면 먼저 말 걸기가 점점 준다 (검수 006: 활발한 강아지가 2시간 내내 조름)
    from brain.tuning import Tuning
    env = await make(tuning=Tuning())
    env.jev.readout = Readout({"none": 1.0}, 0.7, {"심심함↑": 0.5})
    ps = []
    for _ in range(4):
        env.brain._unanswered += 0  # 말했는지와 상관없이 판단 기록의 말할 확률을 본다
        await env.brain.handle_event("quiet", {"seconds": 600})
        await env.brain.drain()
        ps.append(env.brain.log_snapshot()["judgements"][-1]["model"]["speak"])
        env.brain._unanswered += 1
    assert ps[3] < ps[0] * 0.5
    await env.brain.handle_event("message", {"text": "왜"})
    await env.brain.drain()
    assert env.brain._unanswered == 0


async def test_one_interjection_per_message(make):
    env = await make(tuning=SPEAK)
    for text in ("오늘 산책 갈까 말까 고민", "오늘 산책 갈까 말까 고민 중이야", "오늘 산책 갈까 말까 고민 중이야 날씨가"):
        await env.brain.handle_event("typing", {"text": text})
        await env.brain.drain()
    assert len(utterances(env.out)) == 1


async def test_birthday_said_yesterday_is_today(make):
    # 날짜 계산은 우리 모형이 한다: "내일이 내 생일"을 들은 다음 날이면 오늘이 생일이라는 사실을 준다 (검수 006)
    from datetime import datetime
    env = await make(tuning=SPEAK)
    env.clock.t = datetime(2026, 10, 21, 20, 0).timestamp()
    env.brain.dog.updated_at = env.clock.t
    await env.brain.handle_event("message", {"text": "내일이 내 생일이야"})
    await env.brain.drain()
    env.clock.t = datetime(2026, 10, 22, 8, 0).timestamp()
    await env.brain.handle_event("message", {"text": "좋은 아침! 오늘 무슨 날이게?"})
    await env.brain.drain()
    prompt = env.talker.calls[-1][1]
    assert "내일 = 10-22" in prompt and "오늘은 사용자가 말한 생일" in prompt


async def test_reply_keeps_what_the_dog_just_said_while_interjecting(make):
    env = await make(tuning=SPEAK)
    env.talker.line = "바나나! 달콤해서 좋아"
    await env.brain.handle_event("typing", {"text": "사과랑 바나나 중에 뭐가 좋아"})
    await env.brain.drain()
    env.talker.line = "응"
    await env.brain.handle_event("message", {"text": "사과랑 바나나 중에 뭐가 좋아?"})
    await env.brain.drain()
    assert "방금 네가 한 말: 바나나! 달콤해서 좋아" in env.talker.calls[-1][1]


async def test_do_not_disturb_hushes_the_dog_for_an_hour(make):
    # "말 걸지 마"를 Jev가 hush로 읽으면 한 시간 동안(또는 사용자가 다시 말할 때까지) 먼저 말 걸기가 거의 없다 (검수 007)
    from brain.tuning import Tuning
    env = await make(tuning=Tuning())
    env.jev.readout = Readout({"none": 1.0}, 0.7, {"변화없음": 1.0}, 0.0, 0.0, 0.9)
    await env.brain.handle_event("message", {"text": "한 시간 집중해야 해. 말 걸지 마"})
    await env.brain.drain()
    env.jev.readout = Readout({"none": 1.0}, 0.7, {"심심함↑": 0.5})
    env.clock.t += 600
    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    hushed = env.brain.log_snapshot()["judgements"][-1]["model"]["speak"]
    env.clock.t += 3600
    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    later = env.brain.log_snapshot()["judgements"][-1]["model"]["speak"]
    assert hushed < 0.05 and later > 3 * hushed


async def test_no_interjection_on_a_short_fragment(make):
    # 첫 10글자 조각에서는 끼어들지 않는다(귀만 쫑긋). 뜻이 드러난 뒤에 끼어든다 (검수 008: 끼어들기 80%가 첫 조각)
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("typing", {"text": "나 지금부터 한 시"})
    await env.brain.drain()
    assert utterances(env.out) == []
    await env.brain.handle_event("typing", {"text": "나 지금부터 한 시간 집중해야 해서"})
    await env.brain.drain()
    assert len(utterances(env.out)) == 1


async def test_lets_play_counts_as_asked(make):
    # "놀자", "산책 가자"처럼 함께 하자는 말에도 대답한다 (검수 008 사소: "놀자"에 무응답 뒤 10분 뒤 "아무도 안 놀아주니까")
    from brain.tuning import Tuning
    env = await make(tuning=Tuning())
    env.jev.readout = Readout({"none": 1.0}, 0.6, {"변화없음": 1.0})
    await env.brain.handle_event("message", {"text": "우리 공놀이 하자"})
    await env.brain.drain()
    assert env.brain.log_snapshot()["judgements"][-1]["model"]["speak"] > 0.95


async def test_apology_gets_an_answer(make):
    # 사과는 받아 준다: 달램이 높은 메시지에도 대답 보정 (검수 010: 사과 11번 중 5번만 대답, 평균 p 0.38)
    from brain.tuning import Tuning
    env = await make(tuning=Tuning())
    env.jev.readout = Readout({"none": 1.0}, 0.4, {"친밀도↑": 0.5}, 0.3, 0.9)
    await env.brain.handle_event("message", {"text": "아까 짜증낸 거 미안해"})
    await env.brain.drain()
    assert env.brain.log_snapshot()["judgements"][-1]["model"]["speak"] > 0.9


async def test_dialogue_facts_keep_roles_and_house_cause(make):
    # 주인이 한 일은 주인 일이다, 집에 넣은 쪽은 주인이고 그 직전 말이 이유일 수 있다 (검수 011 역할 혼동)
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("message", {"text": "점심 먹었어"})
    await env.brain.drain()
    assert "주인 자신의 일" in env.talker.calls[-1][1] and "점심 먹었어" in env.talker.calls[-1][1]
    await env.brain.handle_event("message", {"text": "너 좀 시끄러워"})
    await env.brain.drain()
    await env.brain.handle_event("house_in", {})
    await env.brain.drain()
    await env.brain.handle_event("house_out", {"away_seconds": 900})
    await env.brain.drain()
    prompt = env.talker.calls[-1][1]
    assert "주인이 나를 집에 넣었다" in prompt and "너 좀 시끄러워" in prompt


async def test_quiet_line_gets_a_topic(make):
    env = await make(tuning=SPEAK)
    await env.brain.handle_event("message", {"text": "이따 같이 공놀이 하자"})
    await env.brain.drain()
    await env.brain.handle_event("quiet", {"seconds": 600})
    await env.brain.drain()
    assert "꺼낼 이야기" in env.talker.calls[-1][1]


async def test_listening_dog_keeps_its_posture_while_typing(make):
    # 검수 012: 한 문장을 치는 동안 앉기 → 조르기 → 조르기 → 앉기처럼 1~2초마다 자세가 바뀌었다
    env = await make()
    env.jev.readout = Readout({"beg": 1.0}, 0.0, {"궁금함↑": 0.6})
    for text in ("오늘은 회사에서", "오늘은 회사에서 회의가", "오늘은 회사에서 회의가 길었는데"):
        await env.brain.handle_event("typing", {"text": text})
        await env.brain.drain()
    moved = [m["action"] for m in env.out if m["type"] == "reaction" and m.get("action", "none") != "none"]
    assert len(moved) <= 1
