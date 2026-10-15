import asyncio

from brain.clients import AuthError, CallError, Judgement
from brain.core import Brain
from brain.memory import History

from .conftest import BOTH_KEYS, FakeJev, FakeTalker, reactions, settle, utterances


async def send(env, text="안녕"):
    await env.brain.handle({"kind": "sent", "text": text})
    await env.brain.drain()


async def test_sent_emits_emotion_action_then_utterance(env):
    env.jev.result = Judgement("excited", "bark", 0.9)
    await send(env, "산책 갈래?")
    assert env.out == [
        {"type": "reaction", "emotion": "excited", "action": "bark"},
        {"type": "reaction", "utterance": "멍! 안녕"},
    ]
    assert [(who, text) for _, who, text in env.history.recent(5)] == [("user", "산책 갈래?"), ("dog", "멍! 안녕")]
    assert env.jev.calls[0]["상황"].startswith("사용자가 방금")


async def test_below_threshold_is_silent(env):
    env.jev.result = Judgement("curious", "sit", 0.3)
    await send(env)
    assert env.out == [{"type": "reaction", "emotion": "curious", "action": "sit"}]
    assert env.talker.calls == []


async def test_unchanged_emotion_and_none_action_are_omitted(env):
    env.jev.result = Judgement("calm", "none", 0.0)  # 시작 감정이 calm
    await send(env)
    assert env.out == []
    env.jev.result = Judgement("sad", "lie_down", 0.0)
    await send(env)
    await send(env)  # 같은 감정·행동이 또 나옴
    assert reactions(env.out) == [{"type": "reaction", "emotion": "sad", "action": "lie_down"}]


async def test_unknown_vocabulary_from_jev_is_ignored(env):
    env.jev.result = Judgement("hungry", "dance", 0.0)
    await send(env)
    assert env.out == []


async def test_user_message_is_saved_even_without_keys(env):
    await env.brain.set_keys({"typesafe": None, "gemini": None})
    await send(env, "키 없어도 기록")
    assert env.history.recent(1)[0][1:] == ("user", "키 없어도 기록")
    assert env.jev.calls == []
    assert {"type": "status", "ai": "no_keys"} in env.out


async def test_blank_sent_is_ignored(env):
    await send(env, "   ")
    assert env.history.recent(5) == [] and env.jev.calls == []


async def test_sent_cancels_inflight_line(env):
    env.jev.result = Judgement("excited", "none", 0.9)
    env.talker.gate = asyncio.Event()
    await env.brain.handle({"kind": "sent", "text": "첫 번째"})
    await settle(lambda: len(env.talker.calls) == 1)
    await env.brain.handle({"kind": "sent", "text": "두 번째"})
    await settle(lambda: len(env.talker.calls) == 2)
    env.talker.gate.set()
    await env.brain.drain()
    assert utterances(env.out) == ["멍! 안녕"]  # 첫 번째 대사는 버려짐


async def test_house_inside_discards_line_and_stops_calls(env):
    env.jev.result = Judgement("excited", "none", 0.9)
    env.talker.gate = asyncio.Event()
    await env.brain.handle({"kind": "sent", "text": "a"})
    await settle(lambda: len(env.talker.calls) == 1)
    await env.brain.handle({"kind": "house", "inside": True, "awayMs": 0})
    env.talker.gate.set()
    await env.brain.drain()
    assert utterances(env.out) == []
    await send(env, "집에 있을 때")
    assert len(env.jev.calls) == 1


async def test_house_out_reports_time_away(env):
    await env.brain.handle({"kind": "house", "inside": True, "awayMs": 0})
    await env.brain.handle({"kind": "house", "inside": False, "awayMs": 3_600_000})
    await env.brain.drain()
    assert env.jev.calls[-1]["상황"].startswith("강아지가 방금 자기 집")
    assert env.jev.calls[-1]["집에 있던 시간"] == "1시간 0분"


async def test_typing_k_chars_triggers_and_cancels_judging(env):
    env.jev.gate = asyncio.Event()
    await env.brain.handle({"kind": "typing", "text": "오늘 회의가 너무 길"})   # 11자
    await settle(lambda: len(env.jev.calls) == 1)
    await env.brain.handle({"kind": "typing", "text": "오늘 회의가 너무 길어서 정말 많이 힘들었어"})  # 13자 더 → 이전 판단 취소
    await settle(lambda: len(env.jev.calls) == 2)
    env.jev.gate.set()
    await env.brain.drain()
    assert env.jev.calls[-1]["사용자가 타이핑 중인 글"] == "오늘 회의가 너무 길어서 정말 많이 힘들었어"


async def test_typing_does_not_discard_interrupting_line(env):
    env.jev.result = Judgement("curious", "none", 0.9)
    env.talker.gate = asyncio.Event()
    await env.brain.handle({"kind": "typing", "text": "오늘 회의가 너무 길"})
    await settle(lambda: len(env.talker.calls) == 1)
    await env.brain.handle({"kind": "typing", "text": "오늘 회의가 너무 길어서 정말 많이 힘들었어"})
    env.talker.gate.set()
    await env.brain.drain()
    assert utterances(env.out) == ["멍! 안녕"]
    assert len(env.jev.calls) == 1


async def test_auth_error_then_new_keys_recover(env):
    env.jev.error = AuthError("typesafe")
    await send(env)
    assert env.out[-1] == {"type": "status", "ai": "bad_key"}
    env.jev.error = None
    await send(env)
    assert len(env.jev.calls) == 1  # 키 오류 동안은 부르지 않는다
    await env.brain.set_keys(BOTH_KEYS)
    assert env.out[-1] == {"type": "status", "ai": "ok"}
    await send(env)
    assert len(env.jev.calls) == 2


async def test_talker_auth_error_sets_bad_key(env):
    env.jev.result = Judgement("excited", "none", 0.9)
    env.talker.error = AuthError("gemini")
    await send(env)
    assert {"type": "status", "ai": "bad_key"} in env.out
    assert utterances(env.out) == []


async def test_jev_call_error_skips_quietly(env):
    env.jev.error = CallError("timeout")
    await send(env)
    assert env.out == []


async def test_talker_call_error_keeps_reaction(env):
    env.jev.result = Judgement("excited", "beg", 0.9)
    env.talker.error = CallError("timeout")
    await send(env)
    assert env.out == [{"type": "reaction", "emotion": "excited", "action": "beg"}]


async def test_blank_line_not_sent(env):
    env.jev.result = Judgement("excited", "none", 0.9)
    env.talker.line = "  \n "
    await send(env)
    assert utterances(env.out) == []
    await env.brain.tick()
    await env.brain.drain()
    assert len(env.jev.calls) == 1  # 말하지 않았으니 "방금 말함" 판단도 없다


async def test_long_line_is_trimmed(env):
    env.jev.result = Judgement("excited", "none", 0.9)
    env.talker.line = "멍! 뭐 해? 나도 볼래. 같이 놀자."
    await send(env)
    assert utterances(env.out) == ["멍! 뭐 해?"]


async def test_interaction_respects_min_gap(env):
    await env.brain.handle({"kind": "interaction", "type": "poke"})
    await env.brain.drain()
    env.clock.t += 1
    await env.brain.handle({"kind": "interaction", "type": "pet"})
    await env.brain.drain()
    env.clock.t += 1.5
    await env.brain.handle({"kind": "interaction", "type": "throw"})
    await env.brain.drain()
    assert [c["상황"] for c in env.jev.calls] == ["사용자가 방금 강아지를 콕 찔렀다", "사용자가 방금 강아지를 들어서 던졌다"]


async def test_unread_bubble_tracking(env):
    env.jev.result = Judgement("excited", "none", 0.9)
    await send(env)
    env.jev.result = Judgement("excited", "none", 0.0)
    await send(env)
    assert env.jev.calls[-1]["강아지의 안 읽힌 말풍선"] == "있음"
    await env.brain.handle({"kind": "bubble_seen"})
    await send(env)
    assert env.jev.calls[-1]["강아지의 안 읽힌 말풍선"] == "없음"


async def test_disconnected_makes_no_calls(env):
    await env.brain.connected(False)
    await send(env)
    assert env.jev.calls == []


async def test_reconnect_keeps_house_state(env):
    await env.brain.handle({"kind": "house", "inside": True, "awayMs": 0})
    await env.brain.connected(False)
    await env.brain.connected(True)
    await send(env)
    assert env.jev.calls == []


async def test_connect_reports_status():
    out = []
    async def emit(m):
        out.append(m)
    b = Brain(emit=emit, make_clients=lambda k: (FakeJev(), FakeTalker()), history=History(None))
    await b.set_keys({"typesafe": "x", "gemini": None})
    assert out == []  # 연결 전에는 보내지 않는다
    await b.connected(True)
    assert out == [{"type": "status", "ai": "no_keys"}]
    await b.aclose()


async def test_clear_history(env):
    await send(env)
    await env.brain.clear_history()
    assert env.history.recent(5) == []


async def test_unknown_signal_is_ignored(env):
    await env.brain.handle({"kind": "teleport"})
    await env.brain.drain()
    assert env.jev.calls == [] and env.out == []
