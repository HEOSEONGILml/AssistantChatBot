import asyncio
import sys

from claude_agent_sdk import (AssistantMessage, PermissionResultAllow, PermissionResultDeny, RateLimitEvent,
                              RateLimitInfo, ResultMessage, SystemMessage, TextBlock, ToolPermissionContext)

from backend import agent, config
from backend.agent import HARNESS, AgentRun, build_options
from backend.tools import MCP_PREFIX

QUESTION = "브라우저로 example.com을 열까요?"


class FakeEvents:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args: self.calls.append((name, *args))

    def of(self, name):
        return [c[1:] for c in self.calls if c[0] == name]


class FakeClient:
    """정해 둔 메시지를 흘려보낸다. gate가 있으면 그 Event가 켜질 때까지 마지막 메시지를 붙잡는다."""

    def __init__(self, messages, gate=None):
        self.messages = messages
        self.gate = gate
        self.options = None
        self.queries = []
        self.interrupted = 0
        self.disconnected = 0
        self.closed = asyncio.Event()

    def __call__(self, options):
        self.options = options
        return self

    async def connect(self):
        pass

    async def query(self, text):
        self.queries.append(text)

    async def interrupt(self):
        self.interrupted += 1

    async def disconnect(self):
        self.disconnected += 1
        self.closed.set()

    async def receive_messages(self):
        for i, m in enumerate(self.messages):
            if self.gate is not None and i == len(self.messages) - 1:
                gate = asyncio.ensure_future(self.gate.wait())
                closed = asyncio.ensure_future(self.closed.wait())
                await asyncio.wait([gate, closed], return_when=asyncio.FIRST_COMPLETED)
                gate.cancel(), closed.cancel()
                if self.closed.is_set():
                    return
            yield m


def text(t):
    return AssistantMessage(content=[TextBlock(text=t)], model="m")


def result(t="다 했어요", is_error=False):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=is_error,
                         num_turns=1, session_id="s1", result=t)


def init():
    return SystemMessage(subtype="init", data={"session_id": "s1"})


async def until(cond):
    for _ in range(200):
        if cond():
            return
        await asyncio.sleep(0)
    raise AssertionError("조건이 끝내 맞지 않았다")


async def test_text_becomes_progress_and_result_finishes():
    limit = RateLimitEvent(rate_limit_info=RateLimitInfo(status="allowed", resets_at=100,
                                                         rate_limit_type="five_hour", utilization=0.3),
                           uuid="u", session_id="s1")
    client = FakeClient([init(), text("검색 중"), limit, result("찾았어요")])
    events = FakeEvents()
    run = AgentRun(7, events, make_client=client)
    await run.run("이어폰 찾아 줘", "OPTS")
    assert client.options == "OPTS"
    assert client.queries == ["이어폰 찾아 줘"]
    assert events.of("session") == [("s1",)]
    assert events.of("progress") == [("검색 중",)]
    assert events.of("rate_limit") == [({"type": "five_hour", "utilization": 0.3, "resets_at": 100},)]
    assert events.of("finished") == [("찾았어요", False)]
    assert client.disconnected == 1


async def test_run_failure_finishes_with_error():
    class Broken(FakeClient):
        async def connect(self):
            raise RuntimeError("없다")

    events = FakeEvents()
    await AgentRun(1, events, make_client=Broken([])).run("요청", None)
    [(_, is_error)] = events.of("finished")
    assert is_error is True


async def test_ask_user_question_answer_with_free_text():
    events = FakeEvents()
    run = AgentRun(1, events)
    tool_input = {"questions": [{"question": QUESTION, "options": [{"label": "열기"}, {"label": "취소"}]}]}
    pending = asyncio.ensure_future(run.can_use_tool("AskUserQuestion", tool_input, ToolPermissionContext()))
    await until(lambda: run.waiting)
    assert events.of("question") == [(QUESTION, ["열기", "취소"])]
    await run.say("진행해. 그런데 example.org로")
    res = await pending
    assert isinstance(res, PermissionResultAllow)
    assert res.updated_input["answers"][QUESTION] == "진행해. 그런데 example.org로"
    assert res.updated_input["questions"] == tool_input["questions"]
    assert events.of("answered") == [()]
    assert not run.waiting


async def test_permission_allow_and_deny():
    for answer, kind in (("허용", PermissionResultAllow), ("아니", PermissionResultDeny)):
        events = FakeEvents()
        run = AgentRun(1, events)
        pending = asyncio.ensure_future(run.can_use_tool("WebFetch", {"url": "x"}, ToolPermissionContext()))
        await until(lambda: run.waiting)
        assert events.of("question") == [("WebFetch 사용을 허용할까요?", ["허용", "거부"])]
        await run.say(answer)
        res = await pending
        assert isinstance(res, kind)
        if kind is PermissionResultDeny:
            assert res.message == "아니"


async def test_say_while_working_queries_session():
    gate = asyncio.Event()
    client = FakeClient([text("일하는 중"), result()], gate)
    run = AgentRun(1, FakeEvents(), make_client=client)
    task = asyncio.ensure_future(run.run("처음", None))
    await until(lambda: client.queries == ["처음"])
    await run.say("덧붙여 이것도")
    assert client.queries == ["처음", "덧붙여 이것도"]
    gate.set()
    await task


async def test_stop_while_waiting_releases_question():
    client = FakeClient([init(), result()], asyncio.Event())
    events = FakeEvents()
    run = AgentRun(1, events, make_client=client)
    task = asyncio.ensure_future(run.run("처음", None))
    await until(lambda: client.queries)
    pending = asyncio.ensure_future(run.can_use_tool("WebFetch", {}, ToolPermissionContext()))
    await until(lambda: run.waiting)
    await run.stop()
    res = await pending
    assert isinstance(res, PermissionResultDeny)
    assert client.interrupted == 1
    await task
    assert client.disconnected >= 1
    assert events.of("finished") == []
    assert events.of("answered") == []


async def test_confirm_uses_same_wait_and_accepts_dict():
    events = FakeEvents()
    run = AgentRun(3, events)
    assert run.task_id == 3
    pending = asyncio.ensure_future(run.confirm("proposal", "이렇게 등록할까요?", {"name": "뉴스"}))
    await until(lambda: run.waiting)
    assert events.of("confirm_request") == [("proposal", "이렇게 등록할까요?", {"name": "뉴스"})]
    run.answer({"name": "아침 뉴스"})
    assert await pending == {"name": "아침 뉴스"}
    assert events.of("answered") == [()]

    pending = asyncio.ensure_future(run.confirm("proposal", "또?", {}))
    await until(lambda: run.waiting)
    await run.say("등록")
    assert await pending == "등록"

    run.notify({"id": 3})
    assert events.of("task_changed") == [()]
    run.entry_added({"id": 9, "kind": "edit"})
    run.schedule_changed()
    assert events.of("entry_added") == [({"id": 9, "kind": "edit"},)]
    assert events.of("schedule_changed") == [()]


def _expected_screenpipe():
    if sys.platform == "win32":
        return {"command": "cmd", "args": ["/c", "npx", "-y", "screenpipe-mcp@latest"]}
    return {"command": "npx", "args": ["-y", "screenpipe-mcp@latest"]}


def test_build_options_values(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    async def cb(*a):
        pass

    o = build_options(permission_mode="default", can_use_tool=cb, mcp_servers={"assistant": "S"}, resume="r1")
    assert o.system_prompt == {"type": "preset", "preset": "claude_code", "append": HARNESS}
    assert o.setting_sources == []
    assert o.cwd == config.work_dir()
    assert o.extra_args == {"chrome": None}
    assert o.disallowed_tools == ["Bash", "Write", "Edit", "NotebookEdit", "Task", "Skill"]
    assert o.allowed_tools == [MCP_PREFIX + "*", "mcp__screenpipe__*"]
    assert o.permission_mode == "default"
    assert o.can_use_tool is cb
    assert o.resume == "r1"
    assert o.mcp_servers == {"assistant": "S",
                             "screenpipe": _expected_screenpipe()}
    # SDK는 options.env를 os.environ 위에 덮으므로 빈 값으로 덮어야 키가 빠진다
    assert not o.env.get("ANTHROPIC_API_KEY")
    assert o.max_turns is None and o.model is None


def test_claude_env_blanks_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("SOMETHING", "1")
    env = config.claude_env()
    assert env["ANTHROPIC_API_KEY"] == ""
    assert env["SOMETHING"] == "1"


def test_harness_has_tool_names():
    for name in ("mcp__screenpipe__activity-summary", "search-content", "frame-context",
                 "recent_tasks", "search_tasks", "get_task", "set_task_title", "get_schedule", "AskUserQuestion"):
        assert name in HARNESS
    assert agent.HARNESS.startswith("#")


async def test_concurrent_waits_are_serialized():
    events = FakeEvents()
    run = AgentRun(1, events)
    first = asyncio.ensure_future(run.can_use_tool("WebFetch", {}, ToolPermissionContext()))
    second = asyncio.ensure_future(run.can_use_tool("WebSearch", {}, ToolPermissionContext()))
    await until(lambda: run.waiting)
    for _ in range(5):
        await asyncio.sleep(0)
    assert events.of("question") == [("WebFetch 사용을 허용할까요?", ["허용", "거부"])]
    await run.say("허용")
    assert isinstance(await first, PermissionResultAllow)
    await until(lambda: run.waiting)
    assert events.of("question")[1] == ("WebSearch 사용을 허용할까요?", ["허용", "거부"])
    await run.say("아니")
    res = await second
    assert isinstance(res, PermissionResultDeny) and res.message == "아니"


async def test_stop_releases_all_queued_waits():
    client = FakeClient([init(), result()], asyncio.Event())
    events = FakeEvents()
    run = AgentRun(1, events, make_client=client)
    task = asyncio.ensure_future(run.run("처음", None))
    await until(lambda: client.queries)
    perm = asyncio.ensure_future(run.can_use_tool("WebFetch", {}, ToolPermissionContext()))
    conf = asyncio.ensure_future(run.confirm("proposal", "등록할까요?", {}))
    await until(lambda: run.waiting)
    await run.stop()
    res = await asyncio.wait_for(perm, 1)
    assert isinstance(res, PermissionResultDeny) and res.interrupt is True
    assert await asyncio.wait_for(conf, 1) == "거부"
    await asyncio.wait_for(task, 1)
    assert events.of("confirm_request") == []
    assert events.of("finished") == []


async def test_stop_during_ask_user_question_denies_with_interrupt():
    run = AgentRun(1, FakeEvents())
    tool_input = {"questions": [{"question": QUESTION, "options": [{"label": "열기"}]}]}
    pending = asyncio.ensure_future(run.can_use_tool("AskUserQuestion", tool_input, ToolPermissionContext()))
    await until(lambda: run.waiting)
    await run.stop()
    res = await pending
    assert isinstance(res, PermissionResultDeny) and res.interrupt is True


async def test_stop_during_connect_disconnects_client():
    started = asyncio.Event()
    release = asyncio.Event()

    class Slow(FakeClient):
        async def connect(self):
            started.set()
            await release.wait()

    client = Slow([result()])
    events = FakeEvents()
    run = AgentRun(1, events, make_client=client)
    task = asyncio.ensure_future(run.run("처음", None))
    await started.wait()
    await run.stop()
    release.set()
    await task
    assert client.queries == []
    assert client.disconnected >= 1
    assert events.of("finished") == []
