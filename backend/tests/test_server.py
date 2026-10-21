import asyncio
import json
import socket

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from backend import config
from backend.__main__ import already_running
from backend.server import CLOSE_BAD_HELLO, CLOSE_REPLACED, CLOSE_VERSION, Link

TOKEN = "secret-token"


class FakeApp:
    def __init__(self):
        self.events = []

    async def connected(self, on):
        self.events.append(("connected", on))

    async def handle_message(self, text):
        self.events.append(("message", text))

    async def set_keys(self, keys):
        self.events.append(("keys", keys))



@pytest.fixture
async def server():
    link = Link(TOKEN)
    link.app = FakeApp()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    async with serve(link.handler, sock=sock):
        yield link, f"ws://127.0.0.1:{sock.getsockname()[1]}"


def hello(token=TOKEN, v=5):
    return json.dumps({"v": v, "type": "hello", "token": token})


async def wait_for(pred, tries=100):
    for _ in range(tries):
        if pred():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("시간 안에 조건이 만족되지 않음")


async def test_bad_token_is_rejected(server):
    link, url = server
    async with connect(url) as ws:
        await ws.send(hello("wrong"))
        with pytest.raises(ConnectionClosed):
            await ws.recv()
        assert ws.close_code == CLOSE_BAD_HELLO
    assert link.app.events == []


async def test_wrong_version_is_rejected(server):
    _, url = server
    async with connect(url) as ws:
        await ws.send(hello(v=2))
        with pytest.raises(ConnectionClosed):
            await ws.recv()
        assert ws.close_code == CLOSE_VERSION


async def test_signal_reaches_app_and_send_reaches_screen(server):
    link, url = server
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.send(json.dumps({"v": 5, "type": "message", "text": "안녕"}))
        await wait_for(lambda: ("message", "안녕") in link.app.events)
        await link.send({"type": "status", "ai": "ok"})
        assert json.loads(await ws.recv()) == {"v": 5, "type": "status", "ai": "ok"}
    await wait_for(lambda: link.app.events[-1] == ("connected", False))
    assert link.app.events[0] == ("connected", True)


async def test_new_screen_replaces_old(server):
    link, url = server
    async with connect(url) as first:
        await first.send(hello())
        await wait_for(lambda: ("connected", True) in link.app.events)
        async with connect(url) as second:
            await second.send(hello())
            with pytest.raises(ConnectionClosed):
                await first.recv()
            assert first.close_code == CLOSE_REPLACED
            await link.send({"type": "status", "ai": "ok"})
            assert json.loads(await second.recv())["type"] == "status"
    await wait_for(lambda: ("connected", False) in link.app.events)
    # 교체된 첫 연결은 끊김을 알리지 않는다: 연결 True 두 번, 끊김은 두 번째가 닫힐 때 한 번
    assert link.app.events.count(("connected", False)) == 1


async def test_garbage_is_ignored(server):
    link, url = server
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.send("{not json")
        await ws.send(json.dumps({"v": 5, "type": "dance"}))
        await ws.send(json.dumps({"v": 5, "type": "message", "text": 3}))
        await ws.send(json.dumps({"v": 5, "type": "message", "text": "됨"}))
        await wait_for(lambda: ("message", "됨") in link.app.events)
    assert ("message", 3) not in link.app.events


async def test_set_key(server, monkeypatch):
    link, url = server
    written = {}
    monkeypatch.setattr(config, "write_key", lambda n, v: written.__setitem__(n, v))
    monkeypatch.setattr(config, "read_keys", lambda: {"typesafe": None, "gemini": "g"})
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.send(json.dumps({"v": 5, "type": "set_key", "name": "gemini", "value": "g"}))
        await wait_for(lambda: any(e[0] == "keys" for e in link.app.events))
    assert written == {"gemini": "g"}
    assert ("keys", {"typesafe": None, "gemini": "g"}) in link.app.events


async def test_already_running(tmp_path, server):
    _, url = server
    info = tmp_path / "backend.json"
    assert await already_running(info) is False
    info.write_text(json.dumps({"port": int(url.rsplit(":", 1)[1]), "token": "x"}), encoding="utf-8")
    assert await already_running(info) is True
    info.write_text(json.dumps({"port": 1, "token": "x"}), encoding="utf-8")
    assert await already_running(info) is False
