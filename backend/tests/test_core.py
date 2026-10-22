import asyncio
import json

import pytest

from backend import core
from backend.agent import AgentRun
from backend.core import App
from backend.store import Store
from backend.tools import build_tools

RULE = {"repeat": "daily", "time": "09:00"}


@pytest.fixture(autouse=True)
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))


class FakeAuth:
    def __init__(self, ok=True):
        self.ok = ok
        self.login_calls = 0
        self.logout_calls = 0

    async def logged_in(self):
        return self.ok

    async def login(self):
        self.login_calls += 1
        self.ok = True
        return True

    async def logout(self):
        self.logout_calls += 1
        self.ok = False


class FakeRecorder:
    def __init__(self):
        self.calls = []

    async def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")


class FakeRun:
    """테스트가 이벤트를 직접 일으킨다. run은 end()나 stop()까지 기다린다."""

    def __init__(self, session_id, events):
        self.session_id = session_id
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

    def notify(self, session):
        self.events.session_changed()

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


class IdleClient:
    """진짜 AgentRun용 가짜 Claude Code. 끊을 때까지 연결 중에 머문다."""

    def __init__(self, options):
        self._closed = asyncio.Event()

    async def connect(self):
        await self._closed.wait()

    async def interrupt(self):
        pass

    async def disconnect(self):
        self._closed.set()


def make(auth=None, real=False, store=None, recorder=None):
    store = store or Store(None)
    out, runs = [], []

    async def emit(msg):
        out.append(msg)

    def new_run(session_id, events):
        r = AgentRun(session_id, events, make_client=IdleClient) if real else FakeRun(session_id, events)
        runs.append(r)
        return r

    app = App(store, emit, auth or FakeAuth(), recorder or FakeRecorder(), new_run=new_run)
    return app, store, out, runs


def of(out, kind):
    return [m for m in out if m["type"] == kind]


async def test_request_creates_task_and_streams_entries():
    app, store, out, runs = make()
    text = "다음 주 회의 자료를 모아서 정리해 줘. 지난번 회의록도 같이 봐 줘."
    await app.request(text)
    await settle()
    session = store.get_session(1)
    assert session["source"] == "user" and session["title"] == text[:30] and session["state"] == "working"
    [run] = runs
    assert run.prompt == text and run.options.permission_mode == "default"
    assert "assistant" in run.options.mcp_servers and run.options.resume is None
    assert out[0] == {"type": "session", "session": session}
    assert out[1]["type"] == "entry" and out[1]["entry"]["kind"] == "user" and out[1]["entry"]["text"] == text

    run.events.claude_session("s1")
    run.events.progress("자료를 찾고 있어요")
    run.events.finished("다 모았어요", False)
    run.end()
    await settle()
    session = store.get_session(1)
    assert (session["state"], session["seen"], session["claude_session_id"]) == ("done", False, "s1")
    assert [(e["kind"], e["text"]) for e in store.entries(1)] == [
        ("user", text), ("progress", "자료를 찾고 있어요"), ("result", "다 모았어요")]
    entries = [m["entry"]["kind"] for m in of(out, "entry")]
    assert entries == ["user", "progress", "result"]
    assert of(out, "session")[-1]["session"]["state"] == "done"
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
    assert store.get_session(1)["state"] == "failed" and store.entries(1)[-1]["kind"] == "failure"
    assert store.get_session(2)["state"] == "failed" and store.entries(2)[-1]["kind"] == "failure"
    assert app._runs == {}


async def test_run_raising_after_finish_writes_no_second_failure():
    app, store, out, runs = make()
    await app.request("일")
    runs[0].events.finished("했어요", False)
    runs[0].fail = True
    runs[0].end()
    await settle()
    assert store.get_session(1)["state"] == "done"
    assert [e["kind"] for e in store.entries(1)] == ["user", "result"]


async def test_question_sets_waiting_and_say_resumes():
    app, store, out, runs = make()
    await app.request("휴지 주문해 줘")
    run = runs[0]
    run.events.question("어느 쇼핑몰로 할까요?", ["쿠팡", "11번가"])
    await settle()
    assert store.get_session(1)["state"] == "waiting"
    q = of(out, "entry")[-1]["entry"]
    assert q["kind"] == "question" and q["choices"] == ["쿠팡", "11번가"]
    assert of(out, "session")[-1]["session"]["state"] == "waiting"

    await app.say(1, "쿠팡")
    assert run.said == ["쿠팡"]
    assert store.entries(1)[-1]["kind"] == "user" and store.entries(1)[-1]["text"] == "쿠팡"
    run.events.answered()
    await settle()
    assert store.get_session(1)["state"] == "working"
    assert of(out, "session")[-1]["session"]["state"] == "working"


async def test_say_after_finish_resumes_session():
    app, store, out, runs = make()
    await app.request("요약해 줘")
    runs[0].events.claude_session("s1")
    runs[0].events.finished("요약했어요", False)
    runs[0].end()
    await settle()
    await app.say(1, "더 짧게")
    assert len(runs) == 2 and runs[1].prompt == "더 짧게" and runs[1].options.resume == "s1"
    assert store.get_session(1)["state"] == "working"


async def test_stop_sets_stopped():
    app, store, out, runs = make()
    await app.request("오래 걸리는 일")
    await app.stop(1)
    await settle()
    assert runs[0].stopped
    assert store.get_session(1)["state"] == "stopped"
    assert of(out, "session")[-1]["session"]["state"] == "stopped"
    assert app._runs == {}
    runs[0].events.finished("늦게 온 결과", False)  # 멈춘 뒤 온 끝은 버린다
    assert store.get_session(1)["state"] == "stopped" and store.entries(1)[-1]["kind"] == "user"


async def test_say_while_run_is_ending_resumes_instead_of_dropping():
    app, store, out, runs = make()
    await app.request("일")
    runs[0].events.claude_session("s1")
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
    await app.list_sessions(1, "alerts")
    msg = of(out, "sessions")[-1]
    assert (msg["view"], msg["page"], msg["pages"]) == ("alerts", 1, 1)
    assert [t["title"] for t in msg["items"]] == ["질문하는 일", "끝난 일"]
    await app.seen(1)
    assert store.get_session(1)["seen"] is True
    await app.list_sessions(1, "alerts")
    assert [t["title"] for t in of(out, "sessions")[-1]["items"]] == ["질문하는 일"]


async def test_request_when_logged_out_resends_status():
    auth = FakeAuth(ok=False)
    app, store, out, runs = make(auth)
    await app.request("해 줘")
    assert out == [{"type": "status", "logged_in": False}]
    assert runs == [] and store.get_session(1) is None
    await app.login()
    assert auth.login_calls == 1 and out[-1] == {"type": "status", "logged_in": True}
    await app.connected(True)
    assert out[-2:] == [{"type": "status", "logged_in": True}, {"type": "nudge", "active": False}]


async def test_say_when_logged_out_resends_status():
    auth = FakeAuth()
    app, store, out, runs = make(auth)
    await app.request("일")
    auth.ok = False
    out.clear()
    await app.say(1, "더 해 줘")
    assert out == [{"type": "status", "logged_in": False}]
    assert runs[0].said == [] and len(store.entries(1)) == 1


async def test_startup_fails_orphaned_sessions():
    app, store, out, runs = make()
    for title, state in [("w", "working"), ("q", "waiting"), ("d", "done")]:
        t = store.create_session("user", title)
        store.update_session(t["id"], state=state, seen=True)
    await app.startup()
    assert [store.get_session(i)["state"] for i in (1, 2, 3)] == ["failed", "failed", "done"]
    assert store.get_session(1)["seen"] is False
    assert store.entries(1)[-1]["kind"] == "failure" and store.entries(1)[-1]["text"] == "앱이 꺼져서 멈췄어요"
    assert store.entries(3) == []


async def test_add_schedule_saves_without_confirmation():
    app, store, out, runs = make()
    await app.add_schedule("메일 요약", RULE, "받은 메일을 요약해")
    await app.add_schedule("잘못", {"repeat": "hourly", "time": "09:00"}, "x")  # 저장하지 않는다
    await app.add_schedule("잘못", "매일", "x")
    assert runs == []
    session = store.get_session(1)
    assert session["source"] == "schedule" and session["title"] == "메일 요약"
    assert session["state"] not in ("working", "waiting")  # 아직 돈 적 없다
    assert store.get_session(2) is None and len(store.all_schedules()) == 1
    assert store.get_schedule(1)["instruction"] == "받은 메일을 요약해"
    assert of(out, "session")[-1]["session"]["id"] == 1
    [msg] = of(out, "schedule")
    assert msg["schedule"]["name"] == "메일 요약" and msg["schedule"]["enabled"] is True
    assert store.entries(1) == []


async def test_set_schedule_answers_pending_proposal():
    app, store, out, runs = make()
    await app.request("매일 아침 메일 요약해 줘")
    run = runs[0]
    proposal = {"name": "메일 요약", "rule": RULE, "label": "매일 09:00", "instruction": "요약",
                "first_run": "2026-10-22T09:00:00+09:00"}
    run.events.confirm_request("proposal", "이렇게 등록할까요?", proposal)
    await settle()
    e = store.entries(1)[-1]
    assert (e["kind"], e["choices"], e["data"]) == ("proposal", ["등록", "고치기"], proposal)
    assert store.get_session(1)["state"] == "waiting"

    rule = {"repeat": "weekdays", "time": "08:30"}
    await app.set_schedule(1, "아침 메일", rule, "중요한 것만")
    assert run.answers == [{"name": "아침 메일", "rule": rule, "instruction": "중요한 것만"}]
    assert store.get_schedule(1) is None  # 저장은 도구가 한다
    # [고치기]도 사용자 답이라 user 줄을 남긴다 (이름·반복만)
    e = store.entries(1)[-1]
    assert (e["kind"], e["text"]) == ("user", "고쳐서 등록: 아침 메일 (평일 08:30)")
    assert of(out, "entry")[-1]["entry"] == e

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
    t = store.create_session("schedule", "메일")
    store.update_session(t["id"], state="done")
    store.create_schedule(t["id"], "메일 요약", RULE, "요약")
    await app.list_schedules(1)
    msg = of(out, "schedules")[-1]
    [item] = msg["items"]
    assert (msg["page"], msg["pages"]) == (1, 1)
    assert item["session_id"] == 1 and item["name"] == "메일 요약" and item["label"] == "매일 09:00"
    assert item["state"] == "next" and item["next_run"].endswith(":00")

    await app.set_schedule_enabled(1, False)
    assert of(out, "schedule")[-1]["schedule"]["enabled"] is False
    await app.list_schedules(1)
    item = of(out, "schedules")[-1]["items"][0]
    assert item["state"] == "off" and item["next_run"] is None

    store.update_session(1, state="waiting")
    await app.list_schedules(1)
    assert of(out, "schedules")[-1]["items"][0]["state"] == "running"

    await app.get_session(1)
    d = of(out, "session_detail")[-1]
    assert d["session"]["id"] == 1 and d["entries"] == [] and d["schedule"]["name"] == "메일 요약"
    await app.request("보통 일")
    await app.get_session(2)
    assert of(out, "session_detail")[-1]["schedule"] is None


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
    ev.rate_limit({"utilization": 0.5})  # 종류가 없으면 버린다
    await app.get_usage()
    assert len(of(out, "usage")[-1]["limits"]) == 2


async def test_permission_mode_saved_and_used_for_new_runs():
    app, store, out, runs = make()
    await app.get_settings()
    assert out[-1] == {"type": "settings", "permission_mode": "default", "recording": True, "jev_key_set": False}
    await app.set_permission_mode("acceptEdits")
    assert out[-1] == {"type": "settings", "permission_mode": "acceptEdits", "recording": True, "jev_key_set": False}
    await app.set_permission_mode("nonsense")
    assert store.get_setting("permission_mode", "default") == "acceptEdits"
    await app.request("일")
    assert runs[0].options.permission_mode == "acceptEdits"


async def test_run_schedule_opens_session_then_resumes_and_records_result():
    from datetime import datetime, timedelta, timezone
    app, store, out, runs = make()
    t = store.create_session("schedule", "메일")
    store.update_session(t["id"], state="done", seen=True)
    store.create_schedule(t["id"], "메일", RULE, "요약")
    now = datetime(2026, 10, 22, 18, 0, 5, tzinfo=timezone(timedelta(hours=9)))
    await app.run_schedule(1, now)
    await settle()
    [run] = runs
    assert run.prompt == "[스케줄 실행 · 10/22 (목) 18:00] get_schedule로 지금 작업 지시서를 읽고 그대로 한 번 실행해."
    assert run.options.resume is None  # 양식으로 만든 스케줄은 세션이 아직 없다
    assert store.get_session(1)["state"] == "working"
    assert [(e["kind"], e["text"]) for e in store.entries(1)] == [("run", "10/22 (목) 18:00 실행")]
    run.events.claude_session("s1")
    run.events.finished("메일 3통 요약", False)
    run.end()
    await settle()
    s = store.get_schedule(1)
    assert s["last_result"] == "done" and s["last_run_at"] == "2026-10-22T18:00:05+09:00"
    assert of(out, "schedule")[-1]["schedule"]["last_result"] == "done"

    await app.run_schedule(1, now)  # 두 번째는 저장된 세션을 이어간다
    await settle()
    assert runs[1].options.resume == "s1"
    runs[1].events.finished("실패", True)
    runs[1].end()
    await settle()
    assert store.get_schedule(1)["last_result"] == "failed"


async def test_run_schedule_skips_busy_and_logged_out():
    from datetime import datetime
    auth = FakeAuth(ok=False)
    app, store, out, runs = make(auth)
    t = store.create_session("schedule", "메일")
    store.update_session(t["id"], state="done")
    store.create_schedule(t["id"], "메일", RULE, "요약")
    now = datetime(2026, 10, 22, 18, 0).astimezone()
    await app.run_schedule(1, now)
    assert runs == [] and store.entries(1) == []
    auth.ok = True
    store.update_session(1, state="waiting")
    await app.run_schedule(1, now)
    assert runs == [] and store.entries(1) == []


async def test_agent_create_schedule_session_and_update():
    """create_session(schedule): 지금 세션에서 확인받고 새 스케줄 세션을 만든다. 수정은 그 스케줄 세션에서."""
    app, store, out, runs = make(real=True)
    await app.request("매일 아침 메일 요약해 줘")
    tools = {t.name: t for t in build_tools(store, runs[0])}
    job = asyncio.create_task(tools["create_session"].handler(
        {"source": "schedule", "name": "메일 요약", "rule": RULE, "instruction": "요약"}))
    await settle()
    await app.say(1, "등록")
    res = await asyncio.wait_for(job, 1)
    await settle()
    new_id = json.loads(res["content"][0]["text"])["session_id"]
    assert new_id != 1 and store.get_session(1)["source"] == "user"
    new = store.get_session(new_id)
    assert (new["source"], new["state"], new["seen"]) == ("schedule", "done", True)
    assert any(m["session"]["id"] == new_id for m in of(out, "session"))
    s = of(out, "schedule")[-1]["schedule"]
    assert (s["session_id"], s["name"], s["label"]) == (new_id, "메일 요약", "매일 09:00")
    chip = store.entries(1)[-1]
    assert (chip["kind"], chip["data"]) == ("chip", {"session_id": new_id, "source": "schedule"})
    assert new_id not in app._runs  # 스케줄 세션은 첫 실행 때 돈다
    await app.stop(1)
    await settle()


async def test_agent_update_schedule_in_schedule_session():
    app, store, out, runs = make(real=True)
    await app.add_schedule("메일 요약", RULE, "요약")
    sid = store.list_schedules(1)[0][0]["session_id"]
    await app.say(sid, "지시서 고쳐 줘")
    tools = {t.name: t for t in build_tools(store, runs[0])}
    out.clear()
    job = asyncio.create_task(tools["update_schedule"].handler({"instruction": "중요한 것만"}))
    await settle()
    await app.say(sid, "예")
    await asyncio.wait_for(job, 1)
    await settle()
    assert [m["entry"]["kind"] for m in of(out, "entry")] == ["proposal", "user", "edit"]
    assert of(out, "schedule")[-1]["schedule"]["instruction"] == "중요한 것만"
    await app.stop(sid)
    await settle()


async def test_start_failure_marks_session_failed(monkeypatch):
    def boom(**kw):
        raise RuntimeError("x")
    monkeypatch.setattr(core, "build_options", boom)
    app, store, out, runs = make()
    await app.request("일")
    await settle()
    assert store.get_session(1)["state"] == "failed" and store.entries(1)[-1]["kind"] == "failure"
    assert of(out, "session")[-1]["session"]["state"] == "failed"
    assert app._runs == {}

    from datetime import datetime
    t = store.create_session("schedule", "메일")
    store.update_session(t["id"], state="done")
    store.create_schedule(t["id"], "메일", RULE, "요약")
    await app.run_schedule(t["id"], datetime(2026, 10, 22, 18, 0).astimezone())  # 예외 없이 실패로 끝난다
    await settle()
    assert store.get_session(t["id"])["state"] == "failed"


async def test_stopped_schedule_run_does_not_record_over_new_run():
    from datetime import datetime
    app, store, out, runs = make()
    t = store.create_session("schedule", "메일")
    store.update_session(t["id"], state="done", seen=True)
    store.create_schedule(t["id"], "메일", RULE, "요약")
    await app.run_schedule(1, datetime(2026, 10, 22, 18, 0).astimezone())

    async def slow_stop():  # 진짜 세션처럼 끊기는 데 시간이 걸린다
        runs[0].stopped = True
    runs[0].stop = slow_stop
    await app.stop(1)
    await app.say(1, "다시 해 줘")  # 멈춘 실행이 정리되기 전에 새 실행
    runs[0].end()
    await settle()
    assert app._runs[1][0] is runs[1]
    assert store.get_schedule(1)["last_result"] is None  # 새 실행이 도는 중에 "working"을 적지 않는다


async def test_second_login_while_pending_is_ignored():
    gate = asyncio.Event()

    class SlowAuth(FakeAuth):
        async def login(self):
            self.login_calls += 1
            await gate.wait()
            self.ok = True
            return True

    auth = SlowAuth(ok=False)
    app, store, out, runs = make(auth)
    first = asyncio.create_task(app.login())
    await settle()
    await asyncio.wait_for(app.login(), 1)  # 로그인 창이 이미 떠 있다
    assert auth.login_calls == 1 and out == []
    gate.set()
    await first
    assert out == [{"type": "status", "logged_in": True}]
    await app.login()  # 끝난 뒤에는 다시 할 수 있다
    assert auth.login_calls == 2


async def test_chat_session_created_once():
    app, store, out, runs = make()
    await app.startup()
    await app.startup()
    chat = store.chat_session()
    assert (chat["source"], chat["title"], chat["state"], chat["seen"], chat["claude_session_id"]) == (
        "chat", "대화", "done", True, None)
    assert [t["id"] for t in store.recent_sessions(10)] == [chat["id"]]
    assert store.entries(chat["id"]) == []


async def test_connect_sends_chat_session():
    app, store, out, runs = make()
    await app.startup()
    await app.connected(True)
    assert out == [{"type": "status", "logged_in": True}, {"type": "session", "session": store.chat_session()},
                   {"type": "nudge", "active": False}]


async def test_chat_resumes_after_restart():
    app, store, out, runs = make()
    await app.startup()
    chat_id = store.chat_session()["id"]
    await app.say(chat_id, "안녕")
    assert runs[0].prompt == "안녕" and runs[0].options.resume is None
    runs[0].events.claude_session("s1")
    # 일하는 중에 앱이 꺼졌다가 다시 켜진다
    app2, _, _, runs2 = make(store=store)
    await app2.startup()
    # 대화 세션은 실패로 닫지 않고 실패 줄도 남기지 않는다
    assert store.chat_session()["id"] == chat_id and store.chat_session()["state"] == "done"
    assert [e["kind"] for e in store.entries(chat_id)] == ["user"]
    await app2.say(chat_id, "아까 하던 얘기")
    assert runs2[0].prompt == "아까 하던 얘기" and runs2[0].options.resume == "s1"
    assert store.get_session(chat_id)["state"] == "working"


async def test_chat_create_session_through_agent_run():
    """대화의 create_session(user): 새 작업 세션이 생겨 돌고, 대화에는 칩 줄이 남는다."""
    app, store, out, runs = make(real=True)
    await app.startup()
    chat_id = store.chat_session()["id"]
    await app.say(chat_id, "회의 자료 모아 줘")
    tools = {t.name: t for t in build_tools(store, runs[0])}
    out.clear()
    res = await tools["create_session"].handler({"source": "user", "text": "회의 자료 모아 줘"})
    await settle()
    new_id = json.loads(res["content"][0]["text"])["session_id"]
    new = store.get_session(new_id)
    assert (new["source"], new["state"]) == ("user", "working")
    assert len(runs) == 2 and runs[1].session_id == new_id and new_id in app._runs
    assert [(e["kind"], e["text"]) for e in store.entries(new_id)] == [("user", "회의 자료 모아 줘")]
    chip = store.entries(chat_id)[-1]
    assert (chip["kind"], chip["data"]) == ("chip", {"session_id": new_id, "source": "user"})
    assert {"type": "entry", "session_id": chat_id, "entry": chip} in out
    assert of(out, "session")[0]["session"]["id"] == new_id
    await app.stop(chat_id)
    await app.stop(new_id)
    await settle()


async def test_logout_sends_status():
    auth = FakeAuth()
    app, store, out, runs = make(auth)
    await app.logout()
    assert auth.logout_calls == 1
    assert out == [{"type": "status", "logged_in": False}]
    await app.request("일")  # 로그아웃 뒤 요청은 기존대로 status만 다시 보낸다
    assert out[-1] == {"type": "status", "logged_in": False} and runs == []


async def test_settings_includes_recording():
    app, store, out, runs = make()
    await app.get_settings()
    assert out[-1] == {"type": "settings", "permission_mode": "default", "recording": True, "jev_key_set": False}
    assert app.recording_enabled() is True


async def test_set_recording_starts_and_stops():
    rec = FakeRecorder()
    app, store, out, runs = make(recorder=rec)
    await app.set_recording(False)
    assert rec.calls == ["stop"] and store.get_setting("recording", "on") == "off"
    assert out[-1] == {"type": "settings", "permission_mode": "default", "recording": False, "jev_key_set": False}
    await app.set_recording(True)
    assert rec.calls == ["stop", "start"] and store.get_setting("recording", "on") == "on"
    assert out[-1]["recording"] is True and app.recording_enabled() is True


async def test_recording_off_persists_across_start():
    store = Store(None)
    app, _, _, _ = make(store=store)
    await app.set_recording(False)
    rec = FakeRecorder()
    app2, _, _, _ = make(store=store, recorder=rec)
    assert app2.recording_enabled() is False
    await app2.startup()  # 저장된 "off"면 시작 때 screenpipe를 띄우지 않는다
    assert rec.calls == []
    rec_on = FakeRecorder()
    app3, _, _, _ = make(recorder=rec_on)
    await app3.startup()
    assert rec_on.calls == ["start"]


async def test_login_failure_still_sends_status_and_unlocks():
    class BrokenAuth(FakeAuth):
        async def login(self):
            self.login_calls += 1
            raise OSError("claude 없음")

    auth = BrokenAuth(ok=False)
    app, store, out, runs = make(auth)
    await app.login()
    assert out == [{"type": "status", "logged_in": False}]
    await app.login()  # 잠금이 풀려 다시 할 수 있다
    assert auth.login_calls == 2


async def test_delete_session_removes_and_announces():
    app, store, out, runs = make()
    await app.request("일")
    runs[0].events.finished("했어요", False)
    runs[0].end()
    await settle()
    out.clear()
    await app.delete_session(1)
    assert store.get_session(1) is None and store.entries(1) == []
    assert out == [{"type": "session_deleted", "session_id": 1}]


async def test_delete_missing_session_still_answers():
    app, store, out, runs = make()
    await app.delete_session(42)
    assert out == [{"type": "session_deleted", "session_id": 42}]


async def test_get_missing_session_answers_deleted():
    app, store, out, runs = make()
    await app.get_session(42)
    assert out == [{"type": "session_deleted", "session_id": 42}]


async def test_delete_running_session_stops_then_deletes():
    app, store, out, runs = make()
    await app.request("오래 걸리는 일")
    runs[0].events.question("할까요?", ["예", "아니오"])  # 답 기다리는 중
    await settle()
    out.clear()
    await app.delete_session(1)
    await settle()
    assert runs[0].stopped
    assert store.get_session(1) is None and store.entries(1) == []
    assert out[-1] == {"type": "session_deleted", "session_id": 1}
    assert app._runs == {}


async def test_late_events_after_delete_are_dropped():
    app, store, out, runs = make()
    await app.request("일")
    ev = runs[0].events
    await app.delete_session(1)
    await settle()
    out.clear()
    ev.progress("늦은 진행")
    ev.question("늦은 질문", ["예"])
    ev.claude_session("s9")
    ev.activity("tool", "파일 읽는 중")
    ev.finished("늦은 결과", False)
    await settle()
    assert out == []
    assert store.get_session(1) is None and store.entries(1) == []


async def test_late_failure_after_delete_does_not_crash_drive():
    app, store, out, runs = make()
    await app.request("일")
    runs[0].fail = True
    await app.delete_session(1)  # FakeRun.stop이 run을 끝내고, run은 예외로 끝난다
    await settle()
    assert store.get_session(1) is None and app._runs == {}


async def test_delete_chat_creates_new_chat_session():
    app, store, out, runs = make()
    await app.startup()
    old = store.chat_session()["id"]
    await app.say(old, "안녕")
    out.clear()
    await app.delete_session(old)
    await settle()
    chat = store.chat_session()
    assert chat is not None and chat["id"] != old
    assert (chat["title"], chat["state"], chat["seen"], chat["claude_session_id"]) == ("대화", "done", True, None)
    assert out[-2:] == [{"type": "session_deleted", "session_id": old}, {"type": "session", "session": chat}]
    assert runs[0].stopped and store.entries(old) == []


async def test_activity_is_sent_not_stored():
    app, store, out, runs = make()
    await app.request("일")
    runs[0].events.activity("tool", "웹에서 검색하는 중")
    await settle()
    assert of(out, "activity") == [{"type": "activity", "session_id": 1, "kind": "tool", "text": "웹에서 검색하는 중"}]
    assert [e["kind"] for e in store.entries(1)] == ["user"]


class GatedAuth(FakeAuth):
    """logged_in이 gate가 켜질 때까지 걸린다 (그 사이 다른 메시지가 처리된다)."""

    def __init__(self):
        super().__init__()
        self.gate = asyncio.Event()

    async def logged_in(self):
        await self.gate.wait()
        return self.ok


async def test_schedule_deleted_during_login_check_does_not_start():
    from datetime import datetime
    auth = GatedAuth()
    app, store, out, runs = make(auth)
    t = store.create_session("schedule", "메일")
    store.update_session(t["id"], state="done", seen=True)
    store.create_schedule(t["id"], "메일", RULE, "요약")
    job = asyncio.create_task(app.run_schedule(1, datetime(2026, 10, 22, 18, 0).astimezone()))
    await settle()
    await app.delete_session(1)
    auth.gate.set()
    await asyncio.wait_for(job, 1)
    await settle()
    assert runs == [] and app._runs == {}
    assert store.get_session(1) is None and store.entries(1) == []


async def test_say_to_session_deleted_during_login_check_does_not_start():
    auth = GatedAuth()
    auth.gate.set()
    app, store, out, runs = make(auth)
    await app.startup()
    chat_id = store.chat_session()["id"]
    auth.gate.clear()
    job = asyncio.create_task(app.say(chat_id, "안녕"))
    await settle()
    await app.delete_session(chat_id)
    auth.gate.set()
    await asyncio.wait_for(job, 1)
    await settle()
    assert runs == [] and app._runs == {}
    assert store.get_session(chat_id) is None and store.entries(chat_id) == []


# --- 먼저 말 걸기 ---
HELP_PROMPT = ("[먼저 말 걸기] 사용자가 EXCEL.EXE · 매출.xlsx에서 막힌 것 같아 도움을 청했다. "
               "최근 화면 기록을 찾아보고 의견이나 해결 방법을 두세 문장으로 짧게 말해.")


class FakeProactive:
    def __init__(self):
        self.declines = []

    def current_task(self):
        return ("EXCEL.EXE", "매출.xlsx")

    def decline(self, at, app, window):
        self.declines.append((app, window))


async def nudged(auth=None):
    """대화 세션이 있고 배지가 켜진 앱."""
    app, store, out, runs = make(auth)
    await app.startup()
    app.proactive = FakeProactive()
    await app.set_nudge(True)
    return app, store, out, runs


async def test_nudge_open_adds_entry_and_clears_badge():
    app, store, out, runs = await nudged()
    out.clear()
    await app.nudge_open()
    chat_id = store.chat_session()["id"]
    entry = store.entries(chat_id)[-1]
    assert (entry["kind"], entry["text"], entry["choices"], entry["data"]) == (
        "nudge", "도움이 필요해?", ["도와줘", "괜찮아"], {"app": "EXCEL.EXE", "window": "매출.xlsx"})
    assert out == [{"type": "entry", "session_id": chat_id, "entry": entry}, {"type": "nudge", "active": False}]
    assert app.nudge_active is False


async def test_nudge_open_without_badge_is_ignored():
    app, store, out, runs = make()
    await app.startup()
    app.proactive = FakeProactive()
    await app.nudge_open()
    assert store.entries(store.chat_session()["id"]) == [] and out == []


async def test_nudge_open_uses_current_chat():
    app, store, out, runs = await nudged()
    old = store.chat_session()["id"]
    await app.delete_session(old)
    await app.nudge_open()
    chat = store.chat_session()
    assert chat["id"] != old
    assert [e["kind"] for e in store.entries(chat["id"])] == ["nudge"]
    assert store.entries(old) == []


async def test_nudge_answer_help_sends_hidden_prompt():
    app, store, out, runs = await nudged()
    await app.nudge_open()
    await app.nudge_answer(True)
    chat_id = store.chat_session()["id"]
    assert [(e["kind"], e["text"]) for e in store.entries(chat_id)][-1] == ("user", "도와줘")
    assert runs[0].prompt == HELP_PROMPT
    assert store.get_session(chat_id)["state"] == "working"
    assert app.proactive.declines == []


async def test_nudge_answer_help_while_chat_is_working():
    app, store, out, runs = await nudged()
    chat_id = store.chat_session()["id"]
    await app.say(chat_id, "안녕")
    await app.nudge_open()
    await app.nudge_answer(True)
    assert len(runs) == 1 and runs[0].said == [HELP_PROMPT]
    assert [e["text"] for e in store.entries(chat_id) if e["kind"] == "user"] == ["안녕", "도와줘"]


async def test_nudge_answer_decline_records():
    app, store, out, runs = await nudged()
    await app.nudge_open()
    await app.nudge_answer(False)
    chat_id = store.chat_session()["id"]
    assert [(e["kind"], e["text"]) for e in store.entries(chat_id)][-1] == ("user", "괜찮아")
    assert app.proactive.declines == [("EXCEL.EXE", "매출.xlsx")]
    assert runs == []


async def test_nudge_answer_only_once():
    app, store, out, runs = await nudged()
    chat_id = store.chat_session()["id"]
    await app.nudge_answer(True)  # 아직 nudge 줄이 없다
    assert store.entries(chat_id) == [] and runs == []
    await app.nudge_open()
    await app.nudge_answer(True)
    await app.nudge_answer(True)
    await app.nudge_answer(False)
    assert [e["kind"] for e in store.entries(chat_id)] == ["nudge", "user"]
    assert len(runs) == 1 and runs[0].said == [] and app.proactive.declines == []


async def test_set_nudge_on_skips_when_logged_out():
    app, store, out, runs = make(FakeAuth(ok=False))
    await app.set_nudge(True)
    assert app.nudge_active is False and of(out, "nudge") == []


async def test_set_jev_key():
    app, store, out, runs = make()
    await app.set_jev_key("  secret-jev  ")
    assert store.get_setting("jev_key", "") == "secret-jev"
    assert out[-1] == {"type": "settings", "permission_mode": "default", "recording": True, "jev_key_set": True}
    assert "secret-jev" not in json.dumps(out, ensure_ascii=False)
    await app.set_jev_key("")
    assert store.get_setting("jev_key", "x") == "" and out[-1]["jev_key_set"] is False


async def test_connected_sends_nudge_state():
    app, store, out, runs = await nudged()
    out.clear()
    await app.connected(True)
    assert out[-1] == {"type": "nudge", "active": True}


async def test_nudge_answer_help_while_chat_is_waiting_runs_after_answer():
    """질문·제안을 기다리는 대화 세션에는 숨은 지시를 답으로 넣지 않는다. 그 실행이 끝나면 새로 이어 묻는다."""
    app, store, out, runs = await nudged()
    chat_id = store.chat_session()["id"]
    await app.say(chat_id, "엑셀 파일 정리해 줘")
    runs[0].events.claude_session("s1")
    runs[0].events.question("어느 파일로 할까요?", ["매출.xlsx", "비용.xlsx"])
    await settle()
    await app.nudge_open()
    await app.nudge_answer(True)
    await settle()
    assert runs[0].answers == [] and runs[0].said == [] and len(runs) == 1
    assert store.get_session(chat_id)["state"] == "waiting"
    assert [e["text"] for e in store.entries(chat_id) if e["kind"] == "user"] == ["엑셀 파일 정리해 줘", "도와줘"]

    await app.say(chat_id, "매출.xlsx")  # 질문은 그대로 답할 수 있다
    assert runs[0].said == ["매출.xlsx"]
    runs[0].events.answered()
    runs[0].events.finished("정리했어요", False)
    runs[0].end()
    await settle()
    assert len(runs) == 2 and runs[1].prompt == HELP_PROMPT and runs[1].options.resume == "s1"
    assert store.get_session(chat_id)["state"] == "working"
    assert app._runs[chat_id][0] is runs[1]


async def test_pending_help_newer_replaces_older():
    app, store, out, runs = await nudged()
    chat_id = store.chat_session()["id"]
    await app.say(chat_id, "일")
    runs[0].events.question("계속할까요?", ["예", "아니오"])
    await app.nudge_open()
    await app.nudge_answer(True)
    app.proactive.current_task = lambda: ("WINWORD.EXE", "보고서.docx")
    await app.set_nudge(True)
    await app.nudge_open()
    await app.nudge_answer(True)
    runs[0].events.finished("끝", False)
    runs[0].end()
    await settle()
    assert len(runs) == 2 and "WINWORD.EXE · 보고서.docx" in runs[1].prompt
    runs[1].events.finished("도왔어요", False)
    runs[1].end()
    await settle()
    assert len(runs) == 2


async def test_pending_help_dropped_when_chat_deleted():
    app, store, out, runs = await nudged()
    chat_id = store.chat_session()["id"]
    await app.say(chat_id, "일")
    runs[0].events.question("계속할까요?", ["예", "아니오"])
    await app.nudge_open()
    await app.nudge_answer(True)
    await app.delete_session(chat_id)
    await settle()
    assert runs[0].stopped and len(runs) == 1 and app._runs == {}


async def test_help_prompt_never_leaks():
    app, store, out, runs = await nudged()
    chat_id = store.chat_session()["id"]
    await app.nudge_open()
    await app.nudge_answer(True)
    runs[0].events.finished("이렇게 해 보세요", False)
    runs[0].end()
    await settle()
    # 기다리는 중의 [도와줘]도 본다
    runs_before = len(runs)
    await app.say(chat_id, "또 질문")
    runs[-1].events.question("계속할까요?", ["예", "아니오"])
    await app.set_nudge(True)
    await app.nudge_open()
    await app.nudge_answer(True)
    runs[-1].events.finished("끝", False)
    runs[-1].end()
    await settle()
    assert len(runs) == runs_before + 2 and runs[-1].prompt == HELP_PROMPT
    for secret in ("막힌 것 같아", "두세 문장", "[먼저 말 걸기]"):
        assert secret not in json.dumps(store.entries(chat_id), ensure_ascii=False)
        assert secret not in json.dumps(out, ensure_ascii=False)
    assert store.search_sessions("먼저 말 걸기", None, None, 10) == []
    assert store.search_sessions("막힌", None, None, 10) == []


async def test_badge_on_is_logged_only_when_really_on(caplog):
    caplog.set_level("INFO")
    app, store, out, runs = make(FakeAuth(ok=False))
    await app.set_nudge(True)
    assert "배지 켬" not in caplog.text
    app._auth.ok = True
    await app.set_nudge(True)
    assert "배지 켬" in caplog.text


async def test_remembers_last_login_status_sent():
    app, store, out, runs = make(FakeAuth(ok=False))
    assert app.logged_in is None  # 아직 보낸 적 없음
    await app.connected(True)
    assert app.logged_in is False
    await app.login()
    assert app.logged_in is True
    await app.logout()
    assert app.logged_in is False
