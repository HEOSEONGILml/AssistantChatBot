import json

from backend import clients
from backend.clients import Auth, Recorder


def _runner(code, out="", calls=None):
    async def run(argv, env, timeout=None):
        if calls is not None:
            calls.append(argv)
        return code, out
    return run


def _status(**kw):
    return json.dumps({"loggedIn": True, "authMethod": "claude.ai", **kw})


async def test_logged_in_true_for_claude_ai():
    assert await Auth(run=_runner(0, _status()), exe="claude").logged_in() is True


async def test_logged_in_false_on_exit_code_1_or_api_key_method():
    assert await Auth(run=_runner(1, _status()), exe="claude").logged_in() is False
    assert await Auth(run=_runner(0, _status(authMethod="api_key")), exe="claude").logged_in() is False
    assert await Auth(run=_runner(0, "not json"), exe="claude").logged_in() is False
    assert await Auth(run=_runner(0, _status(loggedIn=False)), exe="claude").logged_in() is False


async def test_logged_in_false_when_claude_missing_or_run_fails(monkeypatch):
    monkeypatch.setattr(clients.shutil, "which", lambda name: None)
    assert await Auth(run=_runner(0, _status()), exe=None).logged_in() is False

    async def boom(argv, env, timeout=None):
        raise OSError("x")
    assert await Auth(run=boom, exe="claude").logged_in() is False


async def test_login_runs_then_rechecks():
    calls = []
    auth = Auth(run=_runner(0, _status(), calls), exe="claude")
    assert await auth.login() is True
    assert calls == [["claude", "auth", "login", "--claudeai"], ["claude", "auth", "status"]]


async def test_logout_runs_auth_logout_with_timeout():
    calls = []

    async def run(argv, env, timeout=None):
        calls.append((argv, timeout))
        return 0, ""
    await Auth(run=run, exe="claude").logout()
    assert calls == [(["claude", "auth", "logout"], 20)]

    async def boom(argv, env, timeout=None):
        raise OSError("x")
    await Auth(run=boom, exe="claude").logout()  # 실패는 로그만 남긴다


class FakeProc:
    def __init__(self):
        self.terminated = False

    pid = 1

    def poll(self):
        return None


async def test_recorder_skips_when_already_running():
    spawned = []

    async def healthy():
        return True
    rec = Recorder(spawn=lambda argv, env: spawned.append(argv), health=healthy)
    await rec.start()
    rec.stop()
    assert spawned == []


async def test_recorder_starts_and_stops_only_its_own(monkeypatch):
    monkeypatch.setattr(clients.shutil, "which", lambda name: None)
    procs = []

    def spawn(argv, env):
        procs.append((argv, FakeProc()))
        return procs[-1][1]

    async def down():
        return False
    killed = []
    rec = Recorder(spawn=spawn, health=down, kill=killed.append)
    await rec.start()
    await rec.start()  # 살아 있으면 또 띄우지 않는다
    assert len(procs) == 1
    assert procs[0][0] == ["npx", "-y", "screenpipe", "record", "--retention-days", "2", "--retention-mode", "all"]
    rec.stop()
    assert killed == [procs[0][1]]
    rec.stop()  # 두 번 불러도 안전
    assert len(killed) == 1


async def test_recorder_restart_waits_for_old_one_to_go_down(monkeypatch):
    """끈 직후 다시 켜면 죽어 가는 screenpipe가 health에 답해도 내려갈 때까지 기다렸다 띄운다."""
    monkeypatch.setattr(clients.shutil, "which", lambda name: None)
    spawned, slept = [], []
    answers = iter([False, True, True, False, False])  # 첫 start: 꺼짐 / 끈 뒤: 두 번 더 답하고 내려감 / 마지막 확인

    async def health():
        return next(answers)

    async def sleep(s):
        slept.append(s)
    rec = Recorder(spawn=lambda argv, env: spawned.append(argv) or FakeProc(), health=health,
                   kill=lambda p: None, sleep=sleep)
    await rec.start()
    rec.stop()
    await rec.start()
    assert len(spawned) == 2 and len(slept) == 2


async def test_recorder_start_failure_is_logged_not_raised():
    def spawn(argv, env):
        raise OSError("no npx")

    async def down():
        return False
    await Recorder(spawn=spawn, health=down).start()


async def test_recorder_resolves_npx_to_full_path(monkeypatch):
    monkeypatch.setattr(clients.shutil, "which", lambda name: "C:/nodejs/npx.CMD" if name == "npx" else None)
    spawned = []

    async def down():
        return False
    await Recorder(spawn=lambda argv, env: spawned.append(argv), health=down).start()
    assert spawned == [["C:/nodejs/npx.CMD", "-y", "screenpipe", "record", "--retention-days", "2", "--retention-mode", "all"]]


def test_resolve_falls_back_to_original_name(monkeypatch):
    monkeypatch.setattr(clients.shutil, "which", lambda name: None)
    assert clients._resolve(["npx", "-y"]) == ["npx", "-y"]


async def test_run_kills_and_raises_on_timeout():
    import asyncio
    import sys
    try:
        await clients._run([sys.executable, "-c", "import time; time.sleep(30)"], {}, timeout=0.5)
    except asyncio.TimeoutError:
        return
    raise AssertionError("timeout expected")


async def test_run_kills_process_when_cancelled(monkeypatch):
    """앱이 꺼지며 로그인 작업이 취소되면 claude auth login 프로세스도 끈다."""
    import asyncio
    import sys
    killed = []
    real_kill = clients._kill

    def kill(proc):
        killed.append(proc)
        real_kill(proc)
    monkeypatch.setattr(clients, "_kill", kill)
    job = asyncio.create_task(clients._run([sys.executable, "-c", "import time; time.sleep(30)"], {}))
    await asyncio.sleep(0.5)
    job.cancel()
    try:
        await job
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancel expected")
    [proc] = killed
    assert proc.returncode is not None
