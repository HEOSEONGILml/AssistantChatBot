import asyncio
import sys

from claude_agent_sdk import (AssistantMessage, PermissionResultAllow, PermissionResultDeny, RateLimitEvent,
                              RateLimitInfo, ResultMessage, SystemMessage, TextBlock, ToolPermissionContext,
                              ToolResultBlock, UserMessage)
from claude_agent_sdk.types import StreamEvent

from backend import agent, config
from backend.agent import HARNESS, AgentRun, activity_of, build_options
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
    """정해 둔 메시지를 흘려보낸다. gate가 있으면 그 Event가 켜질 때까지 마지막 메시지를 붙잡는다.
    메시지 자리에 Event를 두면 그 Event가 켜질 때까지 다음 메시지를 보내지 않는다 (끊으면 끝난다)."""

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
            wait = m if isinstance(m, asyncio.Event) else (
                self.gate if self.gate is not None and i == len(self.messages) - 1 else None)
            if wait is not None:
                gate = asyncio.ensure_future(wait.wait())
                closed = asyncio.ensure_future(self.closed.wait())
                await asyncio.wait([gate, closed], return_when=asyncio.FIRST_COMPLETED)
                gate.cancel(), closed.cancel()
                if self.closed.is_set():
                    return
            if not isinstance(m, asyncio.Event):
                yield m


def text(t):
    return AssistantMessage(content=[TextBlock(text=t)], model="m")


def result(t="다 했어요", is_error=False):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=is_error,
                         num_turns=1, session_id="s1", result=t)


def init():
    return SystemMessage(subtype="init", data={"session_id": "s1"})


def replay(t):
    """replay-user-messages로 Claude Code가 다시 보내는 사용자 말 (그 말을 처리하기 시작했다는 뜻)."""
    return UserMessage(content=t, uuid="u-" + t)


def tool_result():
    return UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="ok")], uuid="u-tool",
                       tool_use_result={"stdout": "ok"})


async def until(cond):
    for _ in range(200):
        if cond():
            return
        await asyncio.sleep(0)
    raise AssertionError("조건이 끝내 맞지 않았다")


async def test_text_becomes_progress_and_result_finishes():
    raw = {"status": "allowed", "unifiedWindows": {"five_hour": {"utilization": 0.3, "resetsAt": 100}}}
    limit = RateLimitEvent(rate_limit_info=RateLimitInfo(status="allowed", resets_at=100,
                                                         rate_limit_type="five_hour", utilization=0.3, raw=raw),
                           uuid="u", session_id="s1")
    client = FakeClient([init(), text("검색 중"), limit, result("찾았어요")])
    events = FakeEvents()
    run = AgentRun(7, events, make_client=client)
    await run.run("이어폰 찾아 줘", "OPTS")
    assert client.options == "OPTS"
    assert client.queries == ["이어폰 찾아 줘"]
    assert events.of("claude_session") == [("s1",)]
    assert events.of("progress") == [("검색 중",)]
    assert events.of("rate_limit") == [({"type": "five_hour", "utilization": 0.3, "resets_at": 100, "raw": raw},)]
    assert events.of("finished") == [("찾았어요", False)]
    assert client.disconnected == 1


async def test_last_text_same_as_result_is_not_progress():
    client = FakeClient([init(), text("검색 중"), text("찾았어요"), result("찾았어요")])
    events = FakeEvents()
    await AgentRun(7, events, make_client=client).run("이어폰 찾아 줘", None)
    assert events.of("progress") == [("검색 중",)]
    assert events.of("finished") == [("찾았어요", False)]


async def test_held_text_is_sent_when_session_ends_without_result():
    client = FakeClient([init(), text("검색 중")])
    events = FakeEvents()
    await AgentRun(7, events, make_client=client).run("요청", None)
    assert events.of("progress") == [("검색 중",)]
    [(_, is_error)] = events.of("finished")
    assert is_error is True


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
    assert run.session_id == 3
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
    assert events.of("session_changed") == [()]
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

    o = build_options(permission_mode="default", can_use_tool=cb, mcp_servers={"backend": "S"}, resume="r1")
    assert o.system_prompt == {"type": "preset", "preset": "claude_code", "append": HARNESS}
    assert o.setting_sources == []
    assert o.cwd == config.work_dir()
    # 덧붙인 말이 처리됐는지 알려고 사용자 말을 다시 받는다 (스펙 5.1)
    assert o.extra_args == {"chrome": None, "replay-user-messages": None}
    assert o.disallowed_tools == []  # Claude Code 기본 도구를 끄지 않는다 (0036)
    assert o.allowed_tools == ["mcp__backend__*", "mcp__screenpipe__*"]
    assert o.permission_mode == "default"
    assert o.can_use_tool is cb
    assert o.resume == "r1"
    assert o.mcp_servers == {"backend": "S",
                             "screenpipe": _expected_screenpipe()}
    # SDK는 options.env를 os.environ 위에 덮으므로 빈 값으로 덮어야 키가 빠진다
    assert not o.env.get("ANTHROPIC_API_KEY")
    assert o.max_turns is None and o.model is None
    assert o.include_partial_messages is True  # 지금 하는 일(activity)을 StreamEvent로 받는다


def test_claude_env_blanks_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("SOMETHING", "1")
    env = config.claude_env()
    assert env["ANTHROPIC_API_KEY"] == ""
    assert env["SOMETHING"] == "1"


def test_harness_has_tool_names():
    for name in ("mcp__screenpipe__activity-summary", "search-content", "frame-context",
                 "recent_sessions", "search_sessions", "get_session", "set_session_title", "get_schedule", "AskUserQuestion"):
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


def stream(event):
    return StreamEvent(uuid="u", session_id="s1", event=event)


def block_start(block):
    return stream({"type": "content_block_start", "index": 0, "content_block": block})


def tool(name):
    return block_start({"type": "tool_use", "id": "t", "name": name, "input": {}})


def delta(t):
    return stream({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": t}})


def test_activity_of_blocks_and_tools():
    assert activity_of({"type": "thinking", "thinking": ""}) == ("thinking", "생각하는 중")
    assert activity_of({"type": "text", "text": ""}) == ("writing", "답 쓰는 중")
    names = {
        "mcp__screenpipe__search-content": "화면 기록에서 찾는 중",
        "mcp__claude-in-chrome__navigate": "크롬에서 작업하는 중",
        MCP_PREFIX + "search_sessions": "지난 작업 찾는 중",
        "WebSearch": "웹에서 검색하는 중",
        "WebFetch": "웹 페이지 읽는 중",
        "Bash": "명령 실행하는 중",
        "Read": "파일 읽는 중", "Glob": "파일 읽는 중", "Grep": "파일 읽는 중",
        "Write": "파일 고치는 중", "Edit": "파일 고치는 중", "NotebookEdit": "파일 고치는 중",
        "Task": "다른 에이전트에게 맡기는 중", "Agent": "다른 에이전트에게 맡기는 중",
        "TodoWrite": "도구 쓰는 중",
    }
    for name, text in names.items():
        assert activity_of({"type": "tool_use", "name": name}) == ("tool", text), name
    assert activity_of({"type": "tool_use", "name": "AskUserQuestion"}) is None  # 질문 줄이 대신 보인다
    assert activity_of({"type": "redacted_thinking"}) is None


async def test_activity_only_on_block_start():
    """글자 조각(delta)마다 보내지 않고, 하는 일이 바뀔 때만 보낸다."""
    client = FakeClient([
        init(),
        block_start({"type": "thinking", "thinking": ""}), stream({"type": "content_block_delta", "index": 0,
                                                                   "delta": {"type": "thinking_delta", "thinking": "음"}}),
        block_start({"type": "text", "text": ""}), delta("찾"), delta("아"), delta("볼게요"),
        tool("Read"), tool("Grep"),  # 같은 글이면 다시 보내지 않는다
        tool("Bash"),
        tool("AskUserQuestion"),  # 보내지 않는다
        block_start({"type": "text", "text": ""}),
        stream({"type": "message_stop"}),
        result("찾았어요"),
    ])
    events = FakeEvents()
    await AgentRun(7, events, make_client=client).run("요청", None)
    assert events.of("activity") == [("thinking", "생각하는 중"), ("writing", "답 쓰는 중"),
                                     ("tool", "파일 읽는 중"), ("tool", "명령 실행하는 중"),
                                     ("writing", "답 쓰는 중")]
    assert events.of("finished") == [("찾았어요", False)]


async def test_activity_repeats_after_question():
    """질문이 준비 중 줄을 지우므로, 답한 뒤에는 앞과 같은 일도 다시 보낸다."""
    events = FakeEvents()
    run = AgentRun(1, events)
    run._handle(block_start({"type": "text", "text": ""}))
    pending = asyncio.ensure_future(run.can_use_tool("WebFetch", {}, ToolPermissionContext()))
    await until(lambda: run.waiting)
    await run.say("허용")
    await pending
    run._handle(block_start({"type": "text", "text": ""}))
    assert events.of("activity") == [("writing", "답 쓰는 중"), ("writing", "답 쓰는 중")]


async def test_no_activity_after_stop():
    events = FakeEvents()
    run = AgentRun(1, events)
    await run.stop()
    run._handle(tool("Bash"))
    assert events.of("activity") == []


async def test_init_sends_mcp_status():
    servers = [{"name": "screenpipe", "status": "connected", "source": "dynamic"}]
    client = FakeClient([SystemMessage(subtype="init", data={"session_id": "s1", "mcp_servers": servers}), result()])
    events = FakeEvents()
    await AgentRun(1, events, make_client=client).run("처음", None)
    assert events.of("mcp_status") == [(servers,)]


async def test_init_without_mcp_servers_passes_none():
    """모양 검사는 App.mcp_status가 한다. agent는 받은 그대로 넘긴다."""
    events = FakeEvents()
    await AgentRun(1, events, make_client=FakeClient([init(), result()])).run("처음", None)
    assert events.of("mcp_status") == [(None,)]


async def test_fetch_mcp_status_reads_and_disconnects():
    class Status(FakeClient):
        async def get_mcp_status(self):
            return {"mcpServers": [{"name": "screenpipe", "status": "connected"}]}

    client = Status([])
    assert await agent.fetch_mcp_status("OPTS", make_client=client) == [{"name": "screenpipe", "status": "connected"}]
    assert client.options == "OPTS" and client.queries == [] and client.disconnected == 1


async def test_startup_probe_times_out(monkeypatch):
    """연결이 매달리면 시간 제한 뒤 포기하고 끊는다 (Review Focus 4)."""
    monkeypatch.setattr(agent, "PROBE_TIMEOUT", 0.01)

    class Hang(FakeClient):
        async def connect(self):
            await asyncio.Event().wait()

    client = Hang([])
    try:
        await agent.fetch_mcp_status("OPTS", make_client=client)
    except TimeoutError:
        pass
    else:
        raise AssertionError("시간 제한이 걸리지 않았다")
    assert client.disconnected == 1


def test_probe_timeout_is_ten_seconds():
    assert agent.PROBE_TIMEOUT == 10


class Polled(FakeClient):
    """get_mcp_status가 부를 때마다 statuses의 다음 값을 돌려준다 (끝나면 마지막 값을 되풀이)."""

    def __init__(self, statuses):
        super().__init__([])
        self.statuses = statuses
        self.reads = 0

    async def get_mcp_status(self):
        s = self.statuses[min(self.reads, len(self.statuses) - 1)]
        self.reads += 1
        return {"mcpServers": [{"name": "screenpipe", "status": s}]}


async def test_fetch_mcp_status_polls_while_pending(monkeypatch):
    monkeypatch.setattr(agent, "PROBE_POLL", 0)
    client = Polled(["pending", "pending", "connected"])
    assert await agent.fetch_mcp_status("OPTS", make_client=client) == [{"name": "screenpipe", "status": "connected"}]
    assert client.reads == 3 and client.disconnected == 1


async def test_fetch_mcp_status_returns_last_read_at_timeout(monkeypatch):
    monkeypatch.setattr(agent, "PROBE_POLL", 0.001)
    monkeypatch.setattr(agent, "PROBE_TIMEOUT", 0.05)
    client = Polled(["pending"])
    assert await agent.fetch_mcp_status("OPTS", make_client=client) == [{"name": "screenpipe", "status": "pending"}]
    assert client.reads >= 2 and client.disconnected == 1


async def test_fetch_mcp_status_does_not_hang_on_disconnect(monkeypatch):
    monkeypatch.setattr(agent, "DISCONNECT_TIMEOUT", 0.01)

    class HangOnClose(Polled):
        async def disconnect(self):
            self.disconnected += 1
            await asyncio.Event().wait()

    client = HangOnClose(["connected"])
    result = await asyncio.wait_for(agent.fetch_mcp_status("OPTS", make_client=client), 1)
    assert result == [{"name": "screenpipe", "status": "connected"}] and client.disconnected == 1


def test_probe_poll_and_disconnect_limits():
    assert agent.PROBE_POLL == 1 and agent.DISCONNECT_TIMEOUT == 5


# --- 연속 메시지 (보수 계획 Task 2, 2026-10-23 실측) ---

async def test_queued_followup_gets_its_own_result():
    """글로만 답하는 중에 덧붙이면 첫 차례가 끝난 뒤 다음 차례가 따로 온다. 다음 차례 결과까지 받는다 (Review Focus 2)."""
    step = asyncio.Event()
    writing = {"type": "text", "text": ""}
    client = FakeClient([init(), replay("처음"), block_start(writing), text("고양이 이야기"), step, tool_result(),
                         result("고양이 이야기"), init(), replay("개도"), block_start(writing), text("개도 넣었어요"),
                         result("고양이와 개"), asyncio.Event()])
    events = FakeEvents()
    run = AgentRun(1, events, make_client=client)
    task = asyncio.ensure_future(run.run("처음", None))
    await until(lambda: client.queries == ["처음"])
    await run.say("개도")
    step.set()
    await asyncio.wait_for(task, 1)
    assert events.of("turn_result") == [("고양이 이야기", False)]
    assert events.of("progress") == [("개도 넣었어요",)]
    assert events.of("finished") == [("고양이와 개", False)]
    assert client.disconnected == 1
    # 화면은 result 줄에서 준비 중 줄을 지운다. 다음 차례의 같은 일도 다시 보낸다
    order = [c[0] for c in events.calls if c[0] in ("activity", "turn_result", "finished")]
    assert order == ["activity", "turn_result", "activity", "finished"]


async def test_run_failure_after_held_result_finishes_with_it(monkeypatch):
    """결과를 쥐고 다음 차례를 기다리다 실행이 깨지면 받은 답으로 끝낸다."""
    monkeypatch.setattr(agent, "FOLLOWUP_GRACE", 100)
    step = asyncio.Event()

    class Broken(FakeClient):
        async def receive_messages(self):
            async for m in super().receive_messages():
                yield m
            raise RuntimeError("CLI 출력")
    client = Broken([init(), replay("처음"), step, result("했어요")])
    events = FakeEvents()
    run = AgentRun(1, events, make_client=client)
    task = asyncio.ensure_future(run.run("처음", None))
    await until(lambda: client.queries == ["처음"])
    await run.say("이것도")
    step.set()
    await asyncio.wait_for(task, 1)
    assert events.of("finished") == [("했어요", False)]


async def test_grace_is_a_deadline_from_result(monkeypatch):
    """결과 뒤 다른 메시지(사용량 등)가 와도 기다림이 늘지 않는다."""
    monkeypatch.setattr(agent, "FOLLOWUP_GRACE", 0.1)
    step = asyncio.Event()

    class Trickle(FakeClient):
        async def receive_messages(self):
            async for m in super().receive_messages():
                yield m
            while True:  # 다음 차례는 오지 않고 0.05초마다 다른 메시지만 온다
                await asyncio.sleep(0.05)
                yield stream({"type": "message_stop"})
    client = Trickle([init(), replay("처음"), step, result("했어요")])
    events = FakeEvents()
    run = AgentRun(1, events, make_client=client)
    task = asyncio.ensure_future(run.run("처음", None))
    await until(lambda: client.queries == ["처음"])
    await run.say("이것도")
    step.set()
    await asyncio.wait_for(task, 1)
    assert events.of("finished") == [("했어요", False)]


async def test_merged_followup_finishes_at_its_result(monkeypatch):
    """도구를 쓰는 중에 덧붙이면 같은 차례에 합쳐져 결과가 하나다. 다음 차례를 기다리지 않는다 (Review Focus 1)."""
    monkeypatch.setattr(agent, "FOLLOWUP_GRACE", 100)
    step = asyncio.Event()
    client = FakeClient([init(), replay("처음"), step, tool_result(), replay("이것도"), result("둘 다 했어요"),
                         asyncio.Event()])
    events = FakeEvents()
    run = AgentRun(1, events, make_client=client)
    task = asyncio.ensure_future(run.run("처음", None))
    await until(lambda: client.queries == ["처음"])
    await run.say("이것도")
    step.set()
    await asyncio.wait_for(task, 1)
    assert events.of("turn_result") == []
    assert events.of("finished") == [("둘 다 했어요", False)]


async def test_followup_without_next_turn_finishes_after_grace(monkeypatch):
    """처리됐다는 신호도 다음 차례도 오지 않으면 기다리는 시간 뒤 그 결과로 끝낸다 (Review Focus 1)."""
    monkeypatch.setattr(agent, "FOLLOWUP_GRACE", 0.05)
    step = asyncio.Event()
    client = FakeClient([init(), replay("처음"), step, result("했어요"), asyncio.Event()])
    events = FakeEvents()
    run = AgentRun(1, events, make_client=client)
    task = asyncio.ensure_future(run.run("처음", None))
    await until(lambda: client.queries == ["처음"])
    await run.say("이것도")
    step.set()
    await asyncio.wait_for(task, 1)
    assert events.of("turn_result") == []
    assert events.of("finished") == [("했어요", False)]
    assert client.disconnected == 1


async def test_no_followup_finishes_at_result(monkeypatch):
    """덧붙인 말이 없으면 지금처럼 결과에서 바로 끝낸다."""
    monkeypatch.setattr(agent, "FOLLOWUP_GRACE", 100)
    client = FakeClient([init(), replay("처음"), result("했어요"), asyncio.Event()])
    events = FakeEvents()
    await asyncio.wait_for(AgentRun(1, events, make_client=client).run("처음", None), 1)
    assert events.of("finished") == [("했어요", False)]


async def test_stop_while_waiting_next_turn_does_not_wait(monkeypatch):
    """다음 차례를 기다리는 중에 멈추면 기다리지 않고 끝난다. 멈춘 세션에는 결과를 쓰지 않는다."""
    monkeypatch.setattr(agent, "FOLLOWUP_GRACE", 100)
    step = asyncio.Event()
    client = FakeClient([init(), replay("처음"), step, result("했어요"), asyncio.Event()])
    events = FakeEvents()
    run = AgentRun(1, events, make_client=client)
    task = asyncio.ensure_future(run.run("처음", None))
    await until(lambda: client.queries == ["처음"])
    await run.say("이것도")
    step.set()
    await until(lambda: run._pending_result is not None)
    await run.stop()
    await asyncio.wait_for(task, 1)
    assert events.of("finished") == [] and events.of("turn_result") == []
