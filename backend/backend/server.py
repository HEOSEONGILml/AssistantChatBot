"""전송 계층: 화면 하나와 WebSocket으로 메시지를 주고받는다. 규약은 docs/backend-protocol.md가 기준이다."""
import asyncio
import hmac
import json
import logging

from websockets.exceptions import ConnectionClosed

from . import config

log = logging.getLogger(__name__)

PROTOCOL_VERSION = 5
HELLO_TIMEOUT_S = 5
CLOSE_BAD_HELLO, CLOSE_REPLACED, CLOSE_VERSION = 4001, 4002, 4003


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
        if kind == "message" and isinstance(msg.get("text"), str):
            await self.app.handle_message(msg["text"])
        elif kind == "set_key":
            try:
                config.write_key(str(msg.get("name")), str(msg.get("value", "")))
            except Exception:
                log.exception("키 저장 실패")  # 키 값은 로그에 쓰지 않는다
                return
            await self.app.set_keys(config.read_keys())
        else:
            log.warning("모르는 메시지를 버림: %s", kind)
