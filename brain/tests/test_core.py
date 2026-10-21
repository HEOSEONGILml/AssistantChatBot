from brain.core import Brain


async def make():
    out = []

    async def emit(msg):
        out.append(msg)

    return Brain(emit=emit), out


async def test_status_follows_keys():
    brain, out = await make()
    await brain.set_keys({"typesafe": "t", "gemini": None})
    await brain.set_keys({"typesafe": "t", "gemini": "g"})
    assert out == [{"type": "status", "ai": "no_keys"}, {"type": "status", "ai": "ok"}]


async def test_status_is_resent_on_connect():
    brain, out = await make()
    await brain.connected(True)
    await brain.connected(False)
    assert out == [{"type": "status", "ai": "no_keys"}]


async def test_message_is_accepted_without_reply():
    brain, out = await make()
    await brain.handle_message("안녕")
    assert out == []
