"""claude CLI(로그인)와 screenpipe(화면 기록) 호출. 외부 프로세스는 여기서만 띄운다."""
import asyncio
import json
import logging
import shutil
import subprocess
import urllib.request

from backend import config

log = logging.getLogger(__name__)

HEALTH_URL = "http://localhost:3030/health"
# 콘솔 창이 번쩍이지 않게 한다. 윈도 밖에서는 없는 값이라 0.
_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


async def _run(argv: list[str], env: dict) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *argv, env=env, creationflags=_FLAGS,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await proc.communicate()
    return proc.returncode, out.decode("utf-8", "replace")


def _spawn(argv: list[str], env: dict):
    return subprocess.Popen(
        argv, env=env, creationflags=_FLAGS, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _health_ok() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


async def _health() -> bool:
    return await asyncio.to_thread(_health_ok)


class Auth:
    """구독 로그인 상태. API 키로 로그인된 경우는 로그인 안 된 것으로 본다(과금·크롬 조작 때문)."""

    def __init__(self, run=_run, exe: str | None = shutil.which("claude")):
        self._run = run
        self._exe = exe

    async def logged_in(self) -> bool:
        if not self._exe:
            log.warning("claude 실행 파일을 찾지 못함")
            return False
        try:
            code, out = await self._run([self._exe, "auth", "status"], config.claude_env())
            if code != 0:
                return False
            info = json.loads(out)
        except Exception as e:
            log.warning("로그인 상태 확인 실패: %s", type(e).__name__)
            return False
        return bool(info.get("loggedIn")) and info.get("authMethod") == "claude.ai"

    async def login(self) -> bool:
        if not self._exe:
            return False
        try:
            await self._run([self._exe, "auth", "login", "--claudeai"], config.claude_env())
        except Exception as e:
            log.warning("로그인 실행 실패: %s", type(e).__name__)
            return False
        return await self.logged_in()


class Recorder:
    """screenpipe를 띄운다. 이미 떠 있으면(사용자가 따로 켠 경우) 건드리지 않는다."""

    def __init__(self, spawn=_spawn, health=_health):
        self._spawn = spawn
        self._health = health
        self._proc = None

    async def start(self) -> None:
        if await self._health():
            return
        try:
            self._proc = self._spawn(config.screenpipe_cmd(), config.claude_env())
        except Exception as e:
            log.warning("screenpipe 실행 실패: %s", type(e).__name__)

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            proc.terminate()
