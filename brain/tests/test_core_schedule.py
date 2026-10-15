from brain.clients import CallError, Judgement

from .conftest import utterances


async def tick(env, advance=0.0):
    env.clock.t += advance
    await env.brain.tick()
    await env.brain.drain()


async def test_typing_pause_triggers_after_T(env):
    await env.brain.handle({"kind": "typing", "text": "안녕"})
    await tick(env, 0.5)
    assert env.jev.calls == []
    await tick(env, 0.2)
    assert len(env.jev.calls) == 1
    assert env.jev.calls[0]["사용자가 타이핑 중인 글"] == "안녕"
    await tick(env, 1.0)
    assert len(env.jev.calls) == 1  # 같은 글로 다시 부르지 않는다


async def test_cleared_typing_does_not_fire(env):
    await env.brain.handle({"kind": "typing", "text": "abc"})
    await env.brain.handle({"kind": "typing", "text": ""})
    await tick(env, 1.0)
    assert env.jev.calls == []


async def test_quiet_period_when_present(env):
    await tick(env, 59)
    assert env.jev.calls == []
    await tick(env, 2)
    assert env.jev.calls[0]["상황"] == "한동안 별일이 없다"


async def test_quiet_period_when_away(env):
    await env.brain.handle({"kind": "user_away"})
    await tick(env, 61)
    assert env.jev.calls == []
    await tick(env, 540)
    assert len(env.jev.calls) == 1


async def test_user_return_triggers_immediately(env):
    await env.brain.handle({"kind": "user_away"})
    await env.brain.handle({"kind": "user_return"})
    await env.brain.drain()
    assert env.jev.calls[0]["상황"].startswith("자리를 비웠던")


async def test_backoff_after_failures(env):
    env.jev.error = CallError("down")
    await tick(env, 61)
    assert len(env.jev.calls) == 1
    await tick(env, 61)
    assert len(env.jev.calls) == 1  # 실패 1번 → 주기 120초
    await tick(env, 60)
    assert len(env.jev.calls) == 2


async def test_consecutive_cap(env):
    env.jev.result = Judgement("excited", "none", 0.9)
    await env.brain.handle({"kind": "sent", "text": "안녕"})
    await env.brain.drain()
    for _ in range(5):
        await tick(env, 0.1)  # "방금 말함" 판단이 이어진다
    assert len(utterances(env.out)) == 3
    assert env.jev.calls[-1]["사용자 입력 없이 강아지가 연달아 말한 횟수"] == 3
    await env.brain.handle({"kind": "sent", "text": "또 말해"})
    await env.brain.drain()
    assert len(utterances(env.out)) == 4  # 사용자가 말하면 다시 셀 수 있다


async def test_no_quiet_call_in_house(env):
    await env.brain.handle({"kind": "house", "inside": True, "awayMs": 0})
    await tick(env, 3600)
    assert env.jev.calls == []
