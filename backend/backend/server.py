"""전송 계층: 화면 하나와 WebSocket으로 메시지를 주고받는다. 규약은 docs/backend-protocol.md가 기준이다."""
import asyncio
import hmac
import json
import logging

from websockets.exceptions import ConnectionClosed


log = logging.getLogger(__name__)

PROTOCOL_VERSION = 7
HELLO_TIMEOUT_S = 5
CLOSE_BAD_HELLO, CLOSE_REPLACED, CLOSE_VERSION = 4001, 4002, 4003

# 화면 메시지 type -> App 메서드에 넘길 필드와 타입 (순서대로 인자가 된다). 메서드 이름은 type과 같다.
ROUTES: dict[str, tuple[tuple[str, type], ...]] = {
    "login": (),
    "request": (("text", str),),
    "add_schedule": (("name", str), ("rule", dict), ("instruction", str)),
    "say": (("session_id", int), ("text", str)),
    "stop": (("session_id", int),),
    "seen": (("session_id", int),),
    "list_sessions": (("page", int), ("view", str)),
    "get_session": (("session_id", int),),
    "list_schedules": (("page", int),),
    "set_schedule": (("session_id", int), ("name", str), ("rule", dict), ("instruction", str)),
    "set_schedule_enabled": (("session_id", int), ("enabled", bool)),
    "get_settings": (),
    "set_permission_mode": (("mode", str),),
    "get_usage": (),
    "logout": (),
    "set_recording": (("enabled", bool),),
    "delete_session": (("session_id", int),),
    "nudge_open": (),
    "nudge_answer": (("help", bool),),
    "set_jev_key": (("key", str),),
}
# 기다리지 않고 따로 돌리는 메시지. 로그인은 사용자가 브라우저에서 끝낼 때까지 걸려 다른 메시지를 막으면 안 된다.
# 로그아웃도 CLI를 불러 최대 20초 걸릴 수 있다.
BACKGROUND = {"login", "logout"}


def parse(raw) -> dict | None:
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return msg if isinstance(msg, dict) and isinstance(msg.get("type"), str) else None


class Link:
    """지금 붙어 있는 화면 하나. 새 화면이 hello에 성공하면 이전 화면을 닫는다 (첫 버전은 화면이 하나)."""

    def __init__(self, token: str):
        self.token = token
        self.app = None  # 실행할 때 붙인다. App이 Link.send를 쓰므로 서로를 참조한다
        self._ws = None
        self._background: set[asyncio.Task] = set()  # 도는 중인 로그인·로그아웃. 참조를 쥐어야 GC되지 않는다

    async def send(self, msg: dict) -> None:
        ws = self._ws
        if ws is None:
            return
        try:
            await ws.send(json.dumps({"v": PROTOCOL_VERSION, **msg}, ensure_ascii=False))
        except ConnectionClosed:
            pass

    async def handler(self, ws) -> None:
        try:
            hello = parse(await asyncio.wait_for(ws.recv(), HELLO_TIMEOUT_S))
        except (TimeoutError, ConnectionClosed):
            return
        if (hello is None or hello["type"] != "hello"
                or not hmac.compare_digest(str(hello.get("token", "")).encode(), self.token.encode())):
            await ws.close(CLOSE_BAD_HELLO, "bad hello")
            return
        if hello.get("v") != PROTOCOL_VERSION:
            await ws.close(CLOSE_VERSION, f"protocol v{PROTOCOL_VERSION} only")
            return
        old, self._ws = self._ws, ws
        if old is not None:
            await old.close(CLOSE_REPLACED, "replaced")
        await self.app.connected(True)
        try:
            async for raw in ws:
                msg = parse(raw)
                if msg is None:
                    log.warning("해석할 수 없는 메시지를 버림")
                    continue
                await self._dispatch(msg)
        except ConnectionClosed:
            pass
        finally:
            if self._ws is ws:
                self._ws = None
                await self.app.connected(False)

    async def _dispatch(self, msg: dict) -> None:
        kind = msg["type"]
        fields = ROUTES.get(kind)
        if fields is None:
            log.warning("모르는 메시지를 버림: %s", kind)
            return
        # type()으로 비교한다: isinstance면 true가 int로, 1이 bool 자리에서 통과한다
        bad = [name for name, t in fields if type(msg.get(name)) is not t]
        if bad:
            log.warning("필드가 빠지거나 타입이 틀린 메시지를 버림: %s %s", kind, bad)
            return
        call = self._call(kind, getattr(self.app, kind)(*(msg[name] for name, _ in fields)))
        if kind in BACKGROUND:
            job = asyncio.create_task(call)
            self._background.add(job)
            job.add_done_callback(self._background.discard)
        else:
            await call

    @staticmethod
    async def _call(kind: str, coro) -> None:
        """App 메서드 하나의 실패는 로그만 남기고 연결은 유지한다. 내용은 쓰지 않는다(사용자 글이 섞일 수 있다)."""
        try:
            await coro
        except Exception as e:
            log.error("%s 처리 실패: %s", kind, type(e).__name__)
