import asyncio

import pytest

from backend.core import App
from backend.store import Store

RULE = {"repeat": "daily", "time": "09:00"}


@pytest.fixture(autouse=True)
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))


class FakeAuth:
    def __init__(self, ok=True):
        self.ok = ok
        self.login_calls = 0

    async def logged_in(self):
        return self.ok

    async def login(self):
        self.login_calls += 1
        self.ok = True
        return True


class FakeRun:
    """테스트가 이벤트를 직접 일으킨다. run은 end()나 stop()까지 기다린다."""

    def __init__(self, task_id, events):
        self.task_id = task_id
        self.events = events
        self.prompt = self.options = None
        self.said, self.answers = [], []
        self.stopped = False
        self.fail = False
        self._end = asyncio.Event()

    @property
    def waiting(self):
        return False

    async def run(self, prompt, options):
        self.prompt, self.options = prompt, options
        await self._end.wait()
        if self.fail:
            raise RuntimeError("boom")

    def end(self):
        self._end.set()

    async def can_use_tool(self, *a):
        raise AssertionError("쓰지 않음")

    async def confirm(self, kind, text, data):
        raise AssertionError("쓰지 않음")

    def notify(self, task):
        self.events.task_changed()

    def answer(self, value):
        self.answers.append(value)

    async def say(self, text):
        self.said.append(text)

    async def stop(self):
        self.stopped = True
        self._end.set()


async def settle():
    for _ in range(10):
        await asyncio.sleep(0)


def make(auth=None):
    store = Store(None)
    out, runs = [], []

    async def emit(msg):
        out.append(msg)

    def new_run(task_id, events):
        r = FakeRun(task_id, events)
        runs.append(r)
        return r

    app = App(store, emit, auth or FakeAuth(), new_run=new_run)
    return app, store, out, runs


def of(out, kind):
    return [m for m in out if m["type"] == kind]


async def test_request_creates_task_and_streams_entries():
    app, store, out, runs = make()
    text = "다음 주 회의 자료를 모아서 정리해 줘. 지난번 회의록도 같이 봐 줘."
    await app.request(text)
    await settle()
    task = store.get_task(1)
    assert task["source"] == "user" and task["title"] == text[:30] and task["state"] == "working"
    [run] = runs
    assert run.prompt == text and run.options.permission_mode == "default"
    assert "assistant" in run.options.mcp_servers and run.options.resume is None
    assert out[0] == {"type": "task", "task": task}
    assert out[1]["type"] == "entry" and out[1]["entry"]["kind"] == "user" and out[1]["entry"]["text"] == text

    run.events.session("s1")
    run.events.progress("자료를 찾고 있어요")
    run.events.finished("다 모았어요", False)
    run.end()
    await settle()
    task = store.get_task(1)
    assert (task["state"], task["seen"], task["session_id"]) == ("done", False, "s1")
    assert [(e["kind"], e["text"]) for e in store.entries(1)] == [
        ("user", text), ("progress", "자료를 찾고 있어요"), ("result", "다 모았어요")]
    entries = [m["entry"]["kind"] for m in of(out, "entry")]
    assert entries == ["user", "progress", "result"]
    assert of(out, "task")[-1]["task"]["state"] == "done"
    assert app._runs == {}


async def test_failed_finish_and_raising_run_mark_failed():
    app, store, out, runs = make()
    await app.request("하나")
    await app.request("둘")
    runs[0].events.finished("Claude Code를 실행하지 못했어요", True)
    runs[0].end()
    runs[1].fail = True
    runs[1].end()
    await settle()
    assert store.get_task(1)["state"] == "failed" and store.entries(1)[-1]["kind"] == "failure"
    assert store.get_task(2)["state"] == "failed" and store.entries(2)[-1]["kind"] == "failure"
    assert app._runs == {}


async def test_question_sets_waiting_and_say_resumes():
    app, store, out, runs = make()
    await app.request("휴지 주문해 줘")
    run = runs[0]
    run.events.question("어느 쇼핑몰로 할까요?", ["쿠팡", "11번가"])
    await settle()
    assert store.get_task(1)["state"] == "waiting"
    q = of(out, "entry")[-1]["entry"]
    assert q["kind"] == "question" and q["choices"] == ["쿠팡", "11번가"]
    assert of(out, "task")[-1]["task"]["state"] == "waiting"

    await app.say(1, "쿠팡")
    assert run.said == ["쿠팡"]
    assert store.entries(1)[-1]["kind"] == "user" and store.entries(1)[-1]["text"] == "쿠팡"
    run.events.answered()
    await settle()
    assert store.get_task(1)["state"] == "working"
    assert of(out, "task")[-1]["task"]["state"] == "working"


async def test_say_after_finish_resumes_session():
    app, store, out, runs = make()
    await app.request("요약해 줘")
    runs[0].events.session("s1")
    runs[0].events.finished("요약했어요", False)
    runs[0].end()
    await settle()
    await app.say(1, "더 짧게")
    assert len(runs) == 2 and runs[1].prompt == "더 짧게" and runs[1].options.resume == "s1"
    assert store.get_task(1)["state"] == "working"


async def test_stop_sets_stopped():
    app, store, out, runs = make()
    await app.request("오래 걸리는 일")
    await app.stop(1)
    await settle()
    assert runs[0].stopped
    assert store.get_task(1)["state"] == "stopped"
    assert of(out, "task")[-1]["task"]["state"] == "stopped"
    assert app._runs == {}
    runs[0].events.finished("늦게 온 결과", False)  # 멈춘 뒤 온 끝은 버린다
    assert store.get_task(1)["state"] == "stopped" and store.entries(1)[-1]["kind"] == "user"


async def test_say_while_run_is_ending_resumes_instead_of_dropping():
    app, store, out, runs = make()
    await app.request("일")
    runs[0].events.session("s1")
    runs[0].events.finished("했어요", False)  # 세션은 아직 정리 전
    await app.say(1, "하나 더")
    assert runs[0].said == [] and len(runs) == 2 and runs[1].options.resume == "s1"
    runs[0].end()
    await settle()
    assert 1 in app._runs and app._runs[1][0] is runs[1]


async def test_alerts_view_lists_waiting_first():
    app, store, out, runs = make()
    for text in ["끝난 일", "질문하는 일"]:
        await app.request(text)
    runs[0].events.finished("했어요", False)
    runs[1].events.question("할까요?", ["예", "아니오"])
    await settle()
    await app.list_tasks(1, "alerts")
    msg = of(out, "tasks")[-1]
    assert (msg["view"], msg["page"], msg["pages"]) == ("alerts", 1, 1)
    assert [t["title"] for t in msg["items"]] == ["질문하는 일", "끝난 일"]
    await app.seen(1)
    assert store.get_task(1)["seen"] is True
    await app.list_tasks(1, "alerts")
    assert [t["title"] for t in of(out, "tasks")[-1]["items"]] == ["질문하는 일"]


async def test_request_when_logged_out_resends_status():
    auth = FakeAuth(ok=False)
    app, store, out, runs = make(auth)
    await app.request("해 줘")
    assert out == [{"type": "status", "logged_in": False}]
    assert runs == [] and store.get_task(1) is None
    await app.login()
    assert auth.login_calls == 1 and out[-1] == {"type": "status", "logged_in": True}
    await app.connected(True)
    assert out[-1] == {"type": "status", "logged_in": True}


async def test_startup_fails_orphaned_tasks():
    app, store, out, runs = make()
    for title, state in [("w", "working"), ("q", "waiting"), ("d", "done")]:
        t = store.create_task("user", title)
        store.update_task(t["id"], state=state, seen=True)
    await app.startup()
    assert [store.get_task(i)["state"] for i in (1, 2, 3)] == ["failed", "failed", "done"]
    assert store.get_task(1)["seen"] is False
    assert store.entries(1)[-1]["kind"] == "failure" and store.entries(1)[-1]["text"] == "앱이 꺼져서 멈췄어요"
    assert store.entries(3) == []


async def test_schedule_request_uses_schedule_source_and_prompt():
    app, store, out, runs = make()
    await app.schedule_request("매일 아침 9시에 메일 요약")
    task = store.get_task(1)
    assert task["source"] == "schedule"
    assert runs[0].prompt == "새 스케줄을 만들어 줘: 매일 아침 9시에 메일 요약"
    assert store.entries(1)[0]["text"] == "매일 아침 9시에 메일 요약"


async def test_set_schedule_answers_pending_proposal():
    app, store, out, runs = make()
    await app.schedule_request("매일 아침 메일 요약")
    run = runs[0]
    proposal = {"name": "메일 요약", "rule": RULE, "label": "매일 09:00", "instruction": "요약",
                "first_run": "2026-10-22T09:00:00+09:00"}
    run.events.confirm_request("proposal", "이렇게 등록할까요?", proposal)
    await settle()
    e = store.entries(1)[-1]
    assert (e["kind"], e["choices"], e["data"]) == ("proposal", ["등록", "고치기"], proposal)
    assert store.get_task(1)["state"] == "waiting"

    rule = {"repeat": "weekdays", "time": "08:30"}
    await app.set_schedule(1, "아침 메일", rule, "중요한 것만")
    assert run.answers == [{"name": "아침 메일", "rule": rule, "instruction": "중요한 것만"}]
    assert store.get_schedule(1) is None  # 저장은 도구가 한다

    # 답을 받은 뒤의 수정은 바로 저장하고 수정 줄을 남긴다
    run.events.answered()
    store.create_schedule(1, "아침 메일", rule, "중요한 것만")
    await app.set_schedule(1, "아침 메일", rule, "전부")
    assert store.get_schedule(1)["instruction"] == "전부"
    assert store.entries(1)[-1]["kind"] == "edit" and "지시" in store.entries(1)[-1]["text"]
    s = of(out, "schedule")[-1]["schedule"]
    assert s["instruction"] == "전부" and s["label"] == "평일 08:30" and s["enabled"] is True
    assert s["next_run"] is not None and s["last_run_at"] is None


async def test_schedule_list_detail_and_enable():
    app, store, out, runs = make()
    t = store.create_task("schedule", "메일")
    store.update_task(t["id"], state="done")
    store.create_schedule(t["id"], "메일 요약", RULE, "요약")
    await app.list_schedules(1)
    msg = of(out, "schedules")[-1]
    [item] = msg["items"]
    assert (msg["page"], msg["pages"]) == (1, 1)
    assert item["task_id"] == 1 and item["name"] == "메일 요약" and item["label"] == "매일 09:00"
    assert item["state"] == "next" and item["next_run"].endswith(":00")

    await app.set_schedule_enabled(1, False)
    assert of(out, "schedule")[-1]["schedule"]["enabled"] is False
    await app.list_schedules(1)
    item = of(out, "schedules")[-1]["items"][0]
    assert item["state"] == "off" and item["next_run"] is None

    store.update_task(1, state="waiting")
    await app.list_schedules(1)
    assert of(out, "schedules")[-1]["items"][0]["state"] == "running"

    await app.get_task(1)
    d = of(out, "task_detail")[-1]
    assert d["task"]["id"] == 1 and d["entries"] == [] and d["schedule"]["name"] == "메일 요약"
    await app.request("보통 일")
    await app.get_task(2)
    assert of(out, "task_detail")[-1]["schedule"] is None


async def test_usage_keeps_latest_per_type():
    app, store, out, runs = make()
    await app.request("일")
    ev = runs[0].events
    ev.rate_limit({"type": "five_hour", "utilization": 0.1, "resets_at": 100})
    ev.rate_limit({"type": "seven_day", "utilization": 0.3, "resets_at": 200})
    ev.rate_limit({"type": "five_hour", "utilization": 0.2, "resets_at": 100})
    await settle()
    assert of(out, "usage")[-1]["limits"][0]["utilization"] == 0.2
    await app.get_usage()
    limits = of(out, "usage")[-1]["limits"]
    assert [(l["type"], l["utilization"]) for l in limits] == [("five_hour", 0.2), ("seven_day", 0.3)]
    assert all(l["received_at"] for l in limits)


async def test_permission_mode_saved_and_used_for_new_runs():
    app, store, out, runs = make()
    await app.get_settings()
    assert out[-1] == {"type": "settings", "permission_mode": "default"}
    await app.set_permission_mode("acceptEdits")
    assert out[-1] == {"type": "settings", "permission_mode": "acceptEdits"}
    await app.set_permission_mode("nonsense")
    assert store.get_setting("permission_mode", "default") == "acceptEdits"
    await app.request("일")
    assert runs[0].options.permission_mode == "acceptEdits"
