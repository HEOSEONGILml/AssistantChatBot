"""백엔드 실행: backend/ 에서 `uv run python -m backend`. 화면과 상관없이 혼자 실행할 수 있다 (0022)."""
import asyncio
import json
import logging
import os
import secrets
import socket
from logging.handlers import RotatingFileHandler
from pathlib import Path

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from . import config
from .core import App
from .server import Link

log = logging.getLogger("backend")


def setup_logging(logs: Path) -> None:
    logs.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logs / "backend.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


async def already_running(info: Path) -> bool:
    """backend.json의 포트에 다른 백엔드가 살아 있으면 True. 같은 데이터를 두 백엔드가 쓰지 않게 한다."""
    try:
        port = int(json.loads(info.read_text(encoding="utf-8"))["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    try:
        async with asyncio.timeout(1):
            async with connect(f"ws://127.0.0.1:{port}"):
                return True
    except Exception:
        return False


async def main() -> None:
    data = config.data_dir()
    setup_logging(data / "logs")
    info = data / "backend.json"
    if await already_running(info):
        log.info("백엔드가 이미 실행 중이라 끝낸다")
        return
    link = Link(secrets.token_urlsafe(32))
    app = App(emit=link.send)
    link.app = app
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))  # 이 PC 안에서만 받는다
    async with serve(link.handler, sock=sock, max_size=2**20):
        port = sock.getsockname()[1]
        info.write_text(json.dumps({"port": port, "token": link.token, "pid": os.getpid()}), encoding="utf-8")
        log.info("백엔드 시작: 포트 %d", port)
        try:
            await asyncio.Future()  # 끌 때까지 연결을 받는다
        finally:
            info.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
