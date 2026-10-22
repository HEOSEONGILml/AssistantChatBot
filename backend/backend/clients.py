"""claude CLI(로그인), screenpipe(화면 기록), Jev(판단) 호출. 외부 프로세스는 여기서만 띄운다."""
import asyncio
import json
import logging
import shutil
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from backend import config

log = logging.getLogger(__name__)

STATUS_TIMEOUT = 20  # 초. 상태 확인이 멈추면 로그인 안 된 것으로 본다
LOGOUT_TIMEOUT = 20  # 초. 로그아웃은 브라우저를 거치지 않아 상태 확인과 같은 제한을 둔다 (잠정)
JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_TIMEOUT = 10  # 초. 실측 응답은 0.2~0.3초라 넉넉히 둔다 (잠정)
# 강아지 앱 자신의 창은 판단 기록에서 뺀다 (스펙 5.1)
OWN_APPS = ("app.exe", "tamagotchichatbot.exe")
HEALTH_URL = "http://localhost:3030/health"
# 끈 직후 다시 켤 때 죽어 가는 screenpipe가 내려가길 기다린다: 0.5초씩 10번 = 5초 (잠정)
DOWN_WAIT_S, DOWN_WAIT_TRIES = 0.5, 10
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

    def __init__(self, spawn=_spawn, health=_health, kill=_kill, sleep=asyncio.sleep):
        self._spawn = spawn
        self._health = health
        self._kill = kill
        self._sleep = sleep
        self._proc = None
        self._just_stopped = False  # 내가 띄운 것을 방금 껐다

    async def start(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return  # 내가 띄운 게 아직 살아 있다
        if self._just_stopped:
            self._just_stopped = False
            await self._wait_down()
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
            self._just_stopped = True

    async def _wait_down(self) -> None:
        """끈 screenpipe가 아직 health에 답하면 내려갈 때까지 잠깐 기다린다 (남의 것으로 잘못 보지 않게)."""
        for _ in range(DOWN_WAIT_TRIES):
            if not await self._health():
                return
            await self._sleep(DOWN_WAIT_S)


class ScreenHistory:
    """screenpipe DB의 최근 화면 기록. 읽기 전용으로 열고, 없거나 열 수 없으면 빈 목록."""

    def __init__(self, path: Path):
        self._path = path

    def recent(self, since: datetime) -> list[dict]:
        """since 이후의 프레임을 오래된 것부터. Frame = {at, app, window, text}. 글은 full_text, 없으면 accessibility_text.
        앱 이름이 없는 프레임은 뺀다: 포커스 없는 다른 모니터를 찍은 것이라 같은 화면이 반복된다 (2026-10-22 확인)."""
        floor = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")  # timestamp는 UTC ISO. 앞부분 문자열 비교
        marks = ",".join("?" * len(OWN_APPS))
        try:
            con = sqlite3.connect(self._path.as_uri() + "?mode=ro", uri=True, timeout=2)
            try:
                rows = con.execute(
                    "select timestamp, app_name, window_name, coalesce(nullif(full_text, ''), accessibility_text, '') "
                    f"from frames where timestamp >= ? and coalesce(app_name, '') != '' and lower(app_name) not in ({marks}) order by timestamp",
                    (floor, *OWN_APPS)).fetchall()
            finally:
                con.close()
            return [{"at": _parse_utc(ts), "app": app or "", "window": win or "", "text": text} for ts, app, win, text in rows]
        except Exception as e:
            log.warning("화면 기록 읽기 실패: %s", type(e).__name__)
            return []


def _parse_utc(ts: str) -> datetime:
    """소수 자리가 7자리 이상이면(screenpipe는 9자리) 통째로 버린다. 판단에는 초 단위면 충분하다."""
    return datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"", ts).replace("Z", "+00:00"))


def _post_json(key: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(JEV_URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=JEV_TIMEOUT) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


class Jev:
    """판단 API. 실패하면 None을 돌려주고 종류만 로그에 남긴다 (키·글은 남기지 않는다)."""

    def __init__(self, post=_post_json):
        self._post = post  # (key, body) -> (상태 코드, JSON)

    async def ask(self, key: str, state: str, questions: dict) -> dict[str, float] | None:
        body = {"state": state, "model": "jev-latest", "questions": questions}
        try:
            status, data = await asyncio.to_thread(self._post, key, body)
            if status != 200:
                log.warning("Jev 응답 오류: %s", status)
                return None
            answers = data["answers"]
            return {name: float(answers[name]["noul"]) for name in questions}
        except Exception as e:
            log.warning("Jev 호출 실패: %s", type(e).__name__)
            return None
