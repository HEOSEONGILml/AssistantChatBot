import asyncio
import json
import socket

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from brain import config
from brain.__main__ import already_running
from brain.server import CLOSE_BAD_HELLO, CLOSE_REPLACED, CLOSE_VERSION, Link

TOKEN = "secret-token"


class FakeBrain:
    def __init__(self):
        self.events = []

    async def connected(self, on):
        self.events.append(("connected", on))

    async def handle_event(self, kind, context):
        self.events.append(("event", kind, context))

    async def set_keys(self, keys):
        self.events.append(("keys", keys))

    async def clear_history(self):
        self.events.append(("clear",))

    def state_snapshot(self):
        return {"dog": {"mood": {}}, "talkativeness": 0.1, "movement": {}}

    def log_snapshot(self):
        return {"judgements": [], "events": ["방금 · 찌르기"]}


@pytest.fixture
async def server():
    link = Link(TOKEN)
    link.brain = FakeBrain()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    async with serve(link.handler, sock=sock):
        yield link, f"ws://127.0.0.1:{sock.getsockname()[1]}"


def hello(token=TOKEN, v=3):
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
    assert link.brain.events == []


async def test_wrong_version_is_rejected(server):
    _, url = server
    async with connect(url) as ws:
        await ws.send(hello(v=2))
        with pytest.raises(ConnectionClosed):
            await ws.recv()
        assert ws.close_code == CLOSE_VERSION


async def test_signal_reaches_brain_and_send_reaches_screen(server):
    link, url = server
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.send(json.dumps({"v": 3, "type": "event", "kind": "message", "context": {"text": "안녕"}}))
        await wait_for(lambda: ("event", "message", {"text": "안녕"}) in link.brain.events)
        await link.send({"type": "reaction", "utterance": "멍!"})
        assert json.loads(await ws.recv()) == {"v": 3, "type": "reaction", "utterance": "멍!"}
    await wait_for(lambda: link.brain.events[-1] == ("connected", False))
    assert link.brain.events[0] == ("connected", True)


async def test_new_screen_replaces_old(server):
    link, url = server
    async with connect(url) as first:
        await first.send(hello())
        await wait_for(lambda: ("connected", True) in link.brain.events)
        async with connect(url) as second:
            await second.send(hello())
            with pytest.raises(ConnectionClosed):
                await first.recv()
            assert first.close_code == CLOSE_REPLACED
            await link.send({"type": "status", "ai": "ok"})
            assert json.loads(await second.recv())["type"] == "status"
    await wait_for(lambda: ("connected", False) in link.brain.events)
    # 교체된 첫 연결은 끊김을 알리지 않는다: 연결 True 두 번, 끊김은 두 번째가 닫힐 때 한 번
    assert link.brain.events.count(("connected", False)) == 1


async def test_garbage_is_ignored(server):
    link, url = server
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.send("{not json")
        await ws.send(json.dumps({"v": 3, "type": "dance"}))
        await ws.send(json.dumps({"v": 3, "type": "event", "kind": "poke", "context": "not-a-dict"}))
        await ws.send(json.dumps({"v": 3, "type": "event", "kind": 3}))
        await ws.send(json.dumps({"v": 3, "type": "event", "kind": "poke"}))
        await wait_for(lambda: ("event", "poke", {}) in link.brain.events)


async def test_set_key_and_clear_history(server, monkeypatch):
    link, url = server
    written = {}
    monkeypatch.setattr(config, "write_key", lambda n, v: written.__setitem__(n, v))
    monkeypatch.setattr(config, "read_keys", lambda: {"typesafe": None, "gemini": "g"})
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.send(json.dumps({"v": 3, "type": "set_key", "name": "gemini", "value": "g"}))
        await ws.send(json.dumps({"v": 3, "type": "clear_history"}))
        await wait_for(lambda: ("clear",) in link.brain.events)
    assert written == {"gemini": "g"}
    assert ("keys", {"typesafe": None, "gemini": "g"}) in link.brain.events


async def test_already_running(tmp_path, server):
    _, url = server
    info = tmp_path / "brain.json"
    assert await already_running(info) is False
    info.write_text(json.dumps({"port": int(url.rsplit(":", 1)[1]), "token": "x"}), encoding="utf-8")
    assert await already_running(info) is True
    info.write_text(json.dumps({"port": 1, "token": "x"}), encoding="utf-8")
    assert await already_running(info) is False


async def test_get_state_and_get_log(server, monkeypatch, tmp_path):
    link, url = server
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "brain.log").write_text("\n".join(f"줄 {i}" for i in range(40)), encoding="utf-8")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.send(json.dumps({"v": 3, "type": "get_state"}))
        state = json.loads(await asyncio.wait_for(ws.recv(), 2))
        await ws.send(json.dumps({"v": 3, "type": "get_log"}))
        got = json.loads(await asyncio.wait_for(ws.recv(), 2))
    assert state == {"v": 3, "type": "state", "dog": {"mood": {}}, "talkativeness": 0.1, "movement": {}}
    assert got["type"] == "log" and got["judgements"] == [] and got["events"] == ["방금 · 찌르기"]
    assert got["brain_log"][0] == "줄 10" and len(got["brain_log"]) == 30
