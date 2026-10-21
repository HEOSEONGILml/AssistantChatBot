from backend.core import App


async def make():
    out = []

    async def emit(msg):
        out.append(msg)

    return App(emit=emit), out


async def test_status_follows_keys():
    app, out = await make()
    await app.set_keys({"typesafe": "t", "gemini": None})
    await app.set_keys({"typesafe": "t", "gemini": "g"})
    assert out == [{"type": "status", "ai": "no_keys"}, {"type": "status", "ai": "ok"}]


async def test_status_is_resent_on_connect():
    app, out = await make()
    await app.connected(True)
    await app.connected(False)
    assert out == [{"type": "status", "ai": "no_keys"}]


async def test_message_is_accepted_without_reply():
    app, out = await make()
    await app.handle_message("안녕")
    assert out == []
