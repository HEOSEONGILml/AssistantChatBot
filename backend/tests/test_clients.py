import json

from backend.clients import Auth, Recorder


def _runner(code, out="", calls=None):
    async def run(argv, env):
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


async def test_logged_in_false_when_claude_missing_or_run_fails():
    assert await Auth(run=_runner(0, _status()), exe=None).logged_in() is False

    async def boom(argv, env):
        raise OSError("x")
    assert await Auth(run=boom, exe="claude").logged_in() is False


async def test_login_runs_then_rechecks():
    calls = []
    auth = Auth(run=_runner(0, _status(), calls), exe="claude")
    assert await auth.login() is True
    assert calls == [["claude", "auth", "login", "--claudeai"], ["claude", "auth", "status"]]


class FakeProc:
    def __init__(self):
        self.terminated = False

    def terminate(self):
        self.terminated = True


async def test_recorder_skips_when_already_running():
    spawned = []

    async def healthy():
        return True
    rec = Recorder(spawn=lambda argv, env: spawned.append(argv), health=healthy)
    await rec.start()
    rec.stop()
    assert spawned == []


async def test_recorder_starts_and_stops_only_its_own():
    procs = []

    def spawn(argv, env):
        procs.append((argv, FakeProc()))
        return procs[-1][1]

    async def down():
        return False
    rec = Recorder(spawn=spawn, health=down)
    await rec.start()
    assert procs[0][0] == ["npx", "-y", "screenpipe", "record"]
    rec.stop()
    assert procs[0][1].terminated
    rec.stop()  # 두 번 불러도 안전


async def test_recorder_start_failure_is_logged_not_raised():
    def spawn(argv, env):
        raise OSError("no npx")

    async def down():
        return False
    await Recorder(spawn=spawn, health=down).start()
