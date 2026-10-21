"""서비스 핵심. 조수 설계 전의 빈 껍데기다: 키 상태만 화면에 알리고, 받은 말은 아직 처리하지 않는다.
전송 방식과 화면을 모른다."""
import logging
from typing import Awaitable, Callable

log = logging.getLogger(__name__)

Emit = Callable[[dict], Awaitable[None]]


class App:
    def __init__(self, *, emit: Emit):
        self._emit = emit
        self._ai = "no_keys"

    async def connected(self, on: bool) -> None:
        if on:
            await self._emit({"type": "status", "ai": self._ai})

    async def set_keys(self, keys: dict[str, str | None]) -> None:
        self._ai = "ok" if all(keys.values()) else "no_keys"
        await self._emit({"type": "status", "ai": self._ai})

    async def handle_message(self, text: str) -> None:
        log.info("말을 받았지만 아직 처리하지 않는다 (%d자)", len(text))  # 내용은 로그에 쓰지 않는다
