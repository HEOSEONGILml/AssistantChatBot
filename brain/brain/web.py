"""웹 모드 두뇌 (웹 프로토타입 스펙, 0017): 한 포트에서 웹 화면(정적 파일), hello 토큰(/token), WebSocket(/ws)을 낸다.
접속 하나마다 강아지가 새로 태어나고 저장하지 않는다 (0021).
실행: brain/에서 `uv run python -m brain.web [--host 127.0.0.1] [--port 8787] [--static ../app/dist-web]`.
판단은 PC 모드와 같은 Brain·Link를 쓴다. 웹 데이터 폴더에는 로그만 남는다."""
import argparse
import asyncio
import json
import logging
import mimetypes
import secrets
from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote, urlparse

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

from . import config
from .__main__ import setup_logging
from .clients import make_clients
from .core import Brain
from .server import Link
from .store import Store
from .tuning import Tuning

log = logging.getLogger("brain.web")

DEFAULT_STATIC = Path(__file__).resolve().parents[2] / "app" / "dist-web"
INDEX = "web.html"


def static_path(root: Path, url_path: str) -> Path | None:
    """요청 경로에 맞는 정적 파일. 폴더 밖이거나 없으면 None."""
    rel = unquote(url_path.split("?", 1)[0]).lstrip("/") or INDEX
    base = root.resolve()
    target = (base / rel).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        return None
    return target


def same_origin(origin: str | None, host: str | None) -> bool:
    """WebSocket 요청이 이 페이지에서 왔나. 다른 사이트가 사용자의 브라우저로 두뇌에 붙는 것을 막는다.
    Origin이 없으면 브라우저가 아니다(브라우저는 늘 보낸다). 그때는 hello 토큰이 막는다."""
    if origin is None:
        return True
    return bool(host) and urlparse(origin).netloc.lower() == host.lower()


def _response(status: HTTPStatus, body: bytes, content_type: str) -> Response:
    headers = Headers([("Content-Type", content_type), ("Content-Length", str(len(body))), ("Cache-Control", "no-cache")])
    return Response(status.value, status.phrase, headers, body)


def make_process_request(root: Path, token: str):
    def process_request(connection, request):
        path = request.path.split("?", 1)[0]
        if path == "/ws":
            if not same_origin(request.headers.get("Origin"), request.headers.get("Host")):
                return connection.respond(HTTPStatus.FORBIDDEN, "forbidden origin\n")
            return None  # WebSocket 핸드셰이크로 넘긴다
        if path == "/token":  # 같은 출처에서만 읽힌다(CORS 헤더를 주지 않는다)
            return _response(HTTPStatus.OK, json.dumps({"token": token}).encode(), "application/json")
        file = static_path(root, path)
        if file is None:
            return _response(HTTPStatus.NOT_FOUND, b"not found\n", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        return _response(HTTPStatus.OK, file.read_bytes(), ctype)
    return process_request


def make_dog_handler(token: str, keys: dict[str, str | None], tuning: Tuning):
    """접속 하나 = 강아지 하나 (0021). 기록은 메모리에만 두고, 끊기면 강아지와 기분 시계를 정리한다."""
    async def handle(ws) -> None:
        link = Link(token, keys_settable=False)
        brain = Brain(emit=link.send, make_clients=lambda k: make_clients(k, tuning), store=Store(None), tuning=tuning)
        link.brain = brain
        await brain.set_keys(keys)
        clock = asyncio.create_task(brain.run_clock())
        try:
            await link.handler(ws)
        finally:
            clock.cancel()
            await brain.aclose()
    return handle


async def main(host: str, port: int, static: Path) -> None:
    data = config.web_data_dir()
    setup_logging(data / "logs")
    if not (static / INDEX).is_file():
        log.warning("웹 화면이 없다(%s). app/에서 npm run build:web을 먼저 한다", static)
    token = secrets.token_urlsafe(32)
    handler = make_dog_handler(token, config.read_keys(), Tuning())
    async with serve(handler, host, port, process_request=make_process_request(static, token), max_size=2**20) as server:
        log.info("웹 모드 두뇌 시작: http://%s:%d", host, port)
        print(f"웹 강아지: http://{host}:{port}/", flush=True)
        await server.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="TamagotchiChatBot 웹 모드 두뇌")
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0이면 다른 기기에서 접속할 수 있다(키를 함께 쓰게 된다)")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--static", type=Path, default=DEFAULT_STATIC, help="빌드한 웹 화면 폴더")
    args = ap.parse_args()
    asyncio.run(main(args.host, args.port, args.static))
