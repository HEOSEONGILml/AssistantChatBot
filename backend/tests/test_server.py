import asyncio
import inspect
import json
import socket

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from backend.__main__ import already_running
from backend.core import App
from backend.server import CLOSE_BAD_HELLO, CLOSE_REPLACED, CLOSE_VERSION, Link
from backend.server import ROUTES as ROUTE_TABLE

TOKEN = "secret-token"


class FakeApp:
    """부른 메서드와 인자를 (이름, 인자...)로 적는다."""

    def __init__(self):
        self.events = []

    def __getattr__(self, name):
        async def method(*args):
            self.events.append((name, *args))
        return method


@pytest.fixture
async def server():
    link = Link(TOKEN)
    link.app = FakeApp()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    async with serve(link.handler, sock=sock):
        yield link, f"ws://127.0.0.1:{sock.getsockname()[1]}"


def hello(token=TOKEN, v=7):
    return json.dumps({"v": v, "type": "hello", "token": token})


async def wait_for(pred, tries=100):
    for _ in range(tries):
        if pred():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("시간 안에 조건이 만족되지 않음")


def calls(app):
    return [e for e in app.events if e[0] != "connected"]


async def test_bad_token_is_rejected(server):
    link, url = server
    async with connect(url) as ws:
        await ws.send(hello("wrong"))
        with pytest.raises(ConnectionClosed):
            await ws.recv()
        assert ws.close_code == CLOSE_BAD_HELLO
    assert link.app.events == []


async def test_v6_is_rejected(server):
    _, url = server
    async with connect(url) as ws:
        await ws.send(hello(v=6))
        with pytest.raises(ConnectionClosed):
            await asyncio.wait_for(ws.recv(), 2)
        assert ws.close_code == CLOSE_VERSION


async def test_request_reaches_app_and_send_reaches_screen(server):
    link, url = server
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.send(json.dumps({"v": 7, "type": "request", "text": "안녕"}))
        await wait_for(lambda: ("request", "안녕") in link.app.events)
        await link.send({"type": "status", "logged_in": True})
        assert json.loads(await ws.recv()) == {"v": 7, "type": "status", "logged_in": True}
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
            await link.send({"type": "status", "logged_in": True})
            assert json.loads(await second.recv())["type"] == "status"
    await wait_for(lambda: ("connected", False) in link.app.events)
    # 교체된 첫 연결은 끊김을 알리지 않는다: 연결 True 두 번, 끊김은 두 번째가 닫힐 때 한 번
    assert link.app.events.count(("connected", False)) == 1


async def test_garbage_and_unknown_types_are_ignored(server):
    link, url = server
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.send("{not json")
        await ws.send(json.dumps({"v": 7, "type": "dance"}))
        await ws.send(json.dumps({"v": 7, "type": "message", "text": "v5 메시지"}))
        await ws.send(json.dumps({"v": 7, "type": "set_key", "provider": "x", "key": "y"}))
        await ws.send(json.dumps({"v": 7, "type": "request", "text": "됨"}))
        await wait_for(lambda: ("request", "됨") in link.app.events)
    assert calls(link.app) == [("request", "됨")]


ROUTES = [
    ({"type": "login"}, ("login",)),
    ({"type": "request", "text": "메일 정리"}, ("request", "메일 정리")),
    ({"type": "add_schedule", "name": "아침", "rule": {"repeat": "daily", "time": "09:00"}, "instruction": "요약"},
     ("add_schedule", "아침", {"repeat": "daily", "time": "09:00"}, "요약")),
    ({"type": "say", "session_id": 3, "text": "응"}, ("say", 3, "응")),
    ({"type": "stop", "session_id": 3}, ("stop", 3)),
    ({"type": "seen", "session_id": 3}, ("seen", 3)),
    ({"type": "list_sessions", "page": 2, "view": "alerts"}, ("list_sessions", 2, "alerts")),
    ({"type": "get_session", "session_id": 3}, ("get_session", 3)),
    ({"type": "list_schedules", "page": 1}, ("list_schedules", 1)),
    ({"type": "set_schedule", "session_id": 3, "name": "아침", "rule": {"repeat": "weekdays", "time": "08:30"},
      "instruction": "요약"}, ("set_schedule", 3, "아침", {"repeat": "weekdays", "time": "08:30"}, "요약")),
    ({"type": "set_schedule_enabled", "session_id": 3, "enabled": False}, ("set_schedule_enabled", 3, False)),
    ({"type": "get_settings"}, ("get_settings",)),
    ({"type": "set_permission_mode", "mode": "plan"}, ("set_permission_mode", "plan")),
    ({"type": "get_usage"}, ("get_usage",)),
    ({"type": "logout"}, ("logout",)),
    ({"type": "set_recording", "enabled": False}, ("set_recording", False)),
]


@pytest.mark.parametrize("msg,call", ROUTES, ids=[m["type"] for m, _ in ROUTES])
async def test_each_type_calls_its_app_method(server, msg, call):
    link, url = server
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.send(json.dumps({"v": 7, **msg}))
        await wait_for(lambda: call in link.app.events)


def test_routes_match_app_methods():
    """경로표의 필드 이름이 실제 App 메서드의 인자 이름·순서와 같다."""
    for kind, fields in ROUTE_TABLE.items():
        params = list(inspect.signature(getattr(App, kind)).parameters)[1:]
        assert params == [name for name, _ in fields], kind


BAD = [
    {"type": "say", "session_id": "3", "text": "응"},
    {"type": "say", "session_id": 3},
    {"type": "say", "session_id": True, "text": "응"},
    {"type": "request"},
    {"type": "list_sessions", "page": "1", "view": "user"},
    {"type": "add_schedule", "name": "아침", "rule": "매일 9시", "instruction": "요약"},
    {"type": "set_schedule_enabled", "session_id": 3, "enabled": 1},
    {"type": "set_permission_mode", "mode": 3},
    {"type": "set_recording", "enabled": "off"},
    {"type": "set_recording", "enabled": 0},
    {"type": "set_recording"},
]


async def test_wrong_field_types_are_dropped(server):
    link, url = server
    async with connect(url) as ws:
        await ws.send(hello())
        for msg in BAD:
            await ws.send(json.dumps({"v": 7, **msg}))
        await ws.send(json.dumps({"v": 7, "type": "get_usage"}))
        await wait_for(lambda: ("get_usage",) in link.app.events)
    assert calls(link.app) == [("get_usage",)]


class SlowLoginApp(FakeApp):
    """로그인이 끝나지 않는다 (브라우저 로그인을 기다리는 중)."""

    def __init__(self):
        super().__init__()
        self.release = asyncio.Event()

    async def login(self):
        self.events.append(("login",))
        await self.release.wait()


class SlowLogoutApp(FakeApp):
    def __init__(self):
        super().__init__()
        self.release = asyncio.Event()

    async def logout(self):
        self.events.append(("logout",))
        await self.release.wait()


async def test_pending_logout_does_not_block_other_messages(server):
    link, url = server
    link.app = SlowLogoutApp()
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.send(json.dumps({"v": 7, "type": "logout"}))
        await ws.send(json.dumps({"v": 7, "type": "get_usage"}))
        try:
            await wait_for(lambda: ("get_usage",) in link.app.events)
        finally:
            link.app.release.set()


async def test_pending_login_does_not_block_other_messages(server):
    link, url = server
    link.app = SlowLoginApp()
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.send(json.dumps({"v": 7, "type": "login"}))
        await ws.send(json.dumps({"v": 7, "type": "get_usage"}))
        try:
            await wait_for(lambda: ("get_usage",) in link.app.events)
        finally:
            link.app.release.set()


class BrokenApp(FakeApp):
    async def get_settings(self):
        raise RuntimeError("고장")


async def test_app_error_keeps_connection(server):
    link, url = server
    link.app = BrokenApp()
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.send(json.dumps({"v": 7, "type": "get_settings"}))
        await ws.send(json.dumps({"v": 7, "type": "get_usage"}))
        await wait_for(lambda: ("get_usage",) in link.app.events)
        await link.send({"type": "status", "logged_in": True})
        assert json.loads(await ws.recv())["type"] == "status"  # 예외 뒤에도 같은 연결이 살아 있다


async def test_already_running(tmp_path, server):
    _, url = server
    info = tmp_path / "backend.json"
    assert await already_running(info) is False
    info.write_text(json.dumps({"port": int(url.rsplit(":", 1)[1]), "token": "x"}), encoding="utf-8")
    assert await already_running(info) is True
    info.write_text(json.dumps({"port": 1, "token": "x"}), encoding="utf-8")
    assert await already_running(info) is False
