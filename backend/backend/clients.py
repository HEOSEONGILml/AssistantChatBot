"""claude CLI(로그인)와 screenpipe(화면 기록) 호출. 외부 프로세스는 여기서만 띄운다."""
import asyncio
import json
import logging
import shutil
import subprocess
import sys
import urllib.request

from backend import config

log = logging.getLogger(__name__)

STATUS_TIMEOUT = 20  # 초. 상태 확인이 멈추면 로그인 안 된 것으로 본다
LOGOUT_TIMEOUT = 20  # 초. 로그아웃은 브라우저를 거치지 않아 상태 확인과 같은 제한을 둔다 (잠정)
HEALTH_URL = "http://localhost:3030/health"
# 콘솔 창이 번쩍이지 않게 한다. 윈도 밖에서는 없는 값이라 0.
_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


async def _run(argv: list[str], env: dict, timeout: float | None = None) -> tuple[int, str]:
    """끝나면 (종료 코드, 출력). timeout을 넘기거나 취소되면(앱 종료) 프로세스를 트리째 죽이고 다시 던진다."""
    proc = await asyncio.create_subprocess_exec(
        *argv, env=env, creationflags=_FLAGS,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        _kill(proc)
        await proc.wait()
        raise
    return proc.returncode, out.decode("utf-8", "replace")


def _resolve(argv: list[str]) -> list[str]:
    """윈도의 npx는 npx.CMD라 이름만으로는 Popen이 못 찾는다. 전체 경로로 바꾼다."""
    return [shutil.which(argv[0]) or argv[0], *argv[1:]]


def _spawn(argv: list[str], env: dict):
    return subprocess.Popen(
        argv, env=env, creationflags=_FLAGS, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _kill(proc) -> None:
    """윈도에서는 npx.cmd 밑의 node까지 트리째 끈다. terminate()만 하면 자식이 남는다."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], creationflags=_FLAGS,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        proc.terminate()


def _health_ok() -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 프록시를 타면 localhost도 막힐 수 있다
        with opener.open(HEALTH_URL, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


async def _health() -> bool:
    return await asyncio.to_thread(_health_ok)


class Auth:
    """구독 로그인 상태. API 키로 로그인된 경우는 로그인 안 된 것으로 본다(과금·크롬 조작 때문)."""

    def __init__(self, run=_run, exe: str | None = None):
        self._run = run
        self._exe = exe or shutil.which("claude")

    async def logged_in(self) -> bool:
        if not self._exe:
            log.warning("claude 실행 파일을 찾지 못함")
            return False
        try:
            code, out = await self._run([self._exe, "auth", "status"], config.claude_env(), timeout=STATUS_TIMEOUT)
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

    async def logout(self) -> None:
        if not self._exe:
            return
        try:
            await self._run([self._exe, "auth", "logout"], config.claude_env(), timeout=LOGOUT_TIMEOUT)
        except Exception as e:
            log.warning("로그아웃 실행 실패: %s", type(e).__name__)


class Recorder:
    """screenpipe를 띄운다. 이미 떠 있으면(사용자가 따로 켠 경우) 건드리지 않는다."""

    def __init__(self, spawn=_spawn, health=_health, kill=_kill):
        self._spawn = spawn
        self._health = health
        self._kill = kill
        self._proc = None

    async def start(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return  # 내가 띄운 게 아직 살아 있다
        if await self._health():
            log.info("screenpipe가 이미 떠 있어 그대로 둔다")
            return
        try:
            self._proc = self._spawn(_resolve(config.screenpipe_cmd()), config.claude_env())
        except Exception as e:
            log.warning("screenpipe 실행 실패: %s", type(e).__name__)
            return
        log.info("screenpipe 시작")

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            self._kill(proc)
