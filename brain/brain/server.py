"""전송 계층: 화면 하나와 WebSocket으로 메시지를 주고받는다. 규약은 docs/brain-protocol.md가 기준이다."""
import asyncio
import hmac
import json
import logging

from websockets.exceptions import ConnectionClosed

from . import config

log = logging.getLogger(__name__)

PROTOCOL_VERSION = 2
HELLO_TIMEOUT_S = 5
CLOSE_BAD_HELLO, CLOSE_REPLACED, CLOSE_VERSION = 4001, 4002, 4003


def parse(raw) -> dict | None:
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return msg if isinstance(msg, dict) and isinstance(msg.get("type"), str) else None


def tail_log(n: int) -> list[str]:
    """두뇌 실행 로그의 마지막 n줄. 키와 대화 내용은 원래 로그에 쓰지 않는다."""
    try:
        lines = (config.data_dir() / "logs" / "brain.log").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-n:]


class Link:
    """지금 붙어 있는 화면 하나. 새 화면이 hello에 성공하면 이전 화면을 닫는다 (첫 버전은 화면이 하나)."""

    def __init__(self, token: str):
        self.token = token
        self.brain = None  # 실행할 때 붙인다. Brain이 Link.send를 쓰므로 서로를 참조한다
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
        await self.brain.connected(True)
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
                await self.brain.connected(False)

    async def _dispatch(self, msg: dict) -> None:
        kind = msg["type"]
        if kind == "event" and isinstance(msg.get("kind"), str) and isinstance(msg.get("context", {}), dict):
            await self.brain.handle_event(msg["kind"], msg.get("context", {}))
        elif kind == "set_key":
            try:
                config.write_key(str(msg.get("name")), str(msg.get("value", "")))
            except Exception:
                log.exception("키 저장 실패")  # 키 값은 로그에 쓰지 않는다
                return
            await self.brain.set_keys(config.read_keys())
        elif kind == "clear_history":
            await self.brain.clear_history()
        elif kind == "get_state":  # 설정 창 상태 탭 (스펙 3.1)
            await self.send({"type": "state", **self.brain.state_snapshot()})
        elif kind == "get_log":    # 설정 창 로그 탭
            await self.send({"type": "log", **self.brain.log_snapshot(), "brain_log": tail_log(30)})
        else:
            log.warning("모르는 메시지를 버림: %s", kind)
