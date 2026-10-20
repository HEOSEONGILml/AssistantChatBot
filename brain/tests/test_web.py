"""웹 모드 두뇌 (스펙 2026-10-19 웹 프로토타입, 0017): 정적 파일, 토큰, 출처 검사, WebSocket."""
import json
import urllib.request

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import InvalidStatus

from brain import config, web
from brain.tuning import Tuning
from brain.server import Link


def test_static_path_maps_root_to_web_page(tmp_path):
    (tmp_path / "web.html").write_text("dog")
    assert web.static_path(tmp_path, "/") == tmp_path / "web.html"
    assert web.static_path(tmp_path, "/web.html?x=1") == tmp_path / "web.html"


def test_static_path_stays_inside_root(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("no")
    assert web.static_path(root, "/../secret.txt") is None
    assert web.static_path(root, "/%2e%2e/secret.txt") is None
    assert web.static_path(root, "/missing.js") is None


def test_same_origin():
    assert web.same_origin("http://127.0.0.1:8787", "127.0.0.1:8787")
    assert web.same_origin("https://dog.example.com", "dog.example.com")
    assert not web.same_origin("https://evil.example", "127.0.0.1:8787")
    assert web.same_origin(None, "127.0.0.1:8787")  # 브라우저는 늘 Origin을 보낸다. 없으면 브라우저가 아니고 토큰이 막는다


class StubBrain:
    def __init__(self):
        self.on = []

    async def connected(self, on):
        self.on.append(on)


@pytest.fixture
async def site(tmp_path):
    (tmp_path / "web.html").write_text("<canvas id=stage></canvas>", encoding="utf-8")
    link = Link("tok")
    link.brain = StubBrain()
    async with serve(link.handler, "127.0.0.1", 0, process_request=web.make_process_request(tmp_path, link.token)) as server:
        port = server.sockets[0].getsockname()[1]
        yield port, link


def _get(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        return r.status, r.headers.get("Content-Type"), r.read().decode()


async def test_serves_page_and_token(site):
    import asyncio
    port, _ = site
    status, ctype, body = await asyncio.to_thread(_get, f"http://127.0.0.1:{port}/")
    assert status == 200 and ctype.startswith("text/html") and "stage" in body
    status, ctype, body = await asyncio.to_thread(_get, f"http://127.0.0.1:{port}/token")
    assert ctype.startswith("application/json") and json.loads(body) == {"token": "tok"}


async def test_websocket_from_same_origin_connects(site):
    port, link = site
    async with connect(f"ws://127.0.0.1:{port}/ws", origin=f"http://127.0.0.1:{port}") as ws:
        await ws.send(json.dumps({"v": 4, "type": "hello", "token": "tok"}))
        await ws.send(json.dumps({"v": 4, "type": "noop"}))  # 처리 순서상 hello 뒤에 온다
        await ws.close()
    assert link.brain.on[:1] == [True]


async def test_websocket_from_other_site_is_refused(site):
    port, _ = site
    with pytest.raises(InvalidStatus) as e:
        async with connect(f"ws://127.0.0.1:{port}/ws", origin="https://evil.example"):
            pass
    assert e.value.response.status_code == 403


@pytest.fixture
async def dogs(monkeypatch):
    """접속마다 강아지가 새로 태어나는 웹 두뇌 (0021). 키가 없어 Jev·Gemini는 부르지 않는다."""
    written = []
    monkeypatch.setattr(config, "write_key", lambda n, v: written.append(n))
    handler = web.make_dog_handler("tok", {"typesafe": None, "gemini": None}, Tuning())
    async with serve(handler, "127.0.0.1", 0) as server:
        yield f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/ws", written


async def _open(url):
    ws = await connect(url)
    await ws.send(json.dumps({"v": 4, "type": "hello", "token": "tok"}))
    return ws


async def _events(ws):
    await ws.send(json.dumps({"v": 4, "type": "get_log"}))
    while True:
        msg = json.loads(await ws.recv())
        if msg["type"] == "log":
            return msg["events"]


async def test_each_connection_gets_its_own_dog(dogs):
    url, _ = dogs
    a, b = await _open(url), await _open(url)
    try:
        await a.send(json.dumps({"v": 4, "type": "event", "kind": "poke", "context": {}}))
        assert len(await _events(a)) == 1
        assert await _events(b) == []  # 다른 탭의 강아지는 찔리지 않았다. 연결도 빼앗기지 않았다
    finally:
        await a.close()
        await b.close()


async def test_web_does_not_take_keys(dogs):
    url, written = dogs
    ws = await _open(url)
    try:
        await ws.send(json.dumps({"v": 4, "type": "set_key", "name": "gemini", "value": "g"}))
        await _events(ws)  # 앞 메시지가 처리된 뒤에 답한다
    finally:
        await ws.close()
    assert written == []
