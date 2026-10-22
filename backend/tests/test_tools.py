import asyncio
import json

import pytest

from backend.store import Store
from backend.tools import MCP_PREFIX, backend_server, build_tools

RULE = {"repeat": "daily", "time": "09:00"}


class FakeCtx:
    def __init__(self, session_id, answer="등록", store=None):
        self.session_id = session_id
        self.started = []
        self.logged_in = True
        self.answer = answer
        self.store = store
        self.confirms = []
        self.notified = []
        self.added = []
        self.schedule_changes = 0
        self.saved_before_confirm = None

    async def confirm(self, kind, text, data):
        self.saved_before_confirm = self.store.get_schedule(self.session_id) if self.store else None
        self.confirms.append((kind, text, data))
        return self.answer

    def notify(self, session):
        self.notified.append(session)

    def entry_added(self, entry):
        self.added.append(entry)

    def schedule_changed(self):
        self.schedule_changes += 1

    async def start_session(self, source, fields):
        if not self.logged_in:
            return None
        self.started.append((source, fields))
        if source == "user":
            return self.store.create_session("user", fields["text"][:30])
        session = self.store.create_session("schedule", fields["name"])
        self.store.create_schedule(session["id"], fields["name"], fields["rule"], fields["instruction"])
        return session


@pytest.fixture
def setup():
    store = Store(None)
    session = store.create_session("user", "임시")

    def make(answer="등록"):
        ctx = FakeCtx(session["id"], answer, store)
        tools = {t.name: t for t in build_tools(store, ctx)}
        return store, ctx, tools, session["id"]

    return make


def payload(result):
    return json.loads(result["content"][0]["text"])


def test_server_and_prefix(setup):
    store, ctx, tools, _ = setup()
    assert MCP_PREFIX == "mcp__backend__"
    assert set(tools) == {"recent_sessions", "search_sessions", "get_session", "get_schedule",
                          "set_session_title", "create_session", "update_schedule"}
    assert backend_server(store, ctx)["name"] == "backend"


async def test_search_sessions_returns_matches(setup):
    store, ctx, tools, tid = setup()
    store.update_session(tid, title="견적서 정리")
    other = store.create_session("user", "점심 메뉴")
    res = await tools["search_sessions"].handler({"query": "견적서"})
    assert [t["id"] for t in payload(res)] == [tid]
    assert other["id"] not in [t["id"] for t in payload(res)]


async def test_recent_and_get_session(setup):
    store, ctx, tools, tid = setup()
    assert payload(await tools["recent_sessions"].handler({}))[0]["id"] == tid
    store.add_entry(tid, "user", "안녕")
    got = payload(await tools["get_session"].handler({"session_id": tid}))
    assert got["session"]["id"] == tid and got["entries"][0]["text"] == "안녕"
    assert (await tools["get_session"].handler({"session_id": 999}))["is_error"]


async def test_get_schedule_missing_is_error(setup):
    _, _, tools, _ = setup()
    assert (await tools["get_schedule"].handler({}))["is_error"]


async def test_set_session_title_notifies(setup):
    store, ctx, tools, tid = setup()
    await tools["set_session_title"].handler({"title": "새 제목"})
    assert store.get_session(tid)["title"] == "새 제목"
    assert ctx.notified[0]["title"] == "새 제목"


async def test_create_session_schedule_confirms_then_makes_new_session(setup):
    store, ctx, tools, tid = setup("등록")
    res = await tools["create_session"].handler(
        {"source": "schedule", "name": "아침", "rule": RULE, "instruction": "메일 요약"})
    assert not res.get("is_error")
    kind, text, data = ctx.confirms[0]
    assert kind == "proposal" and text == "이렇게 등록할까요?"
    assert data["label"] == "매일 09:00" and data["first_run"]
    new = payload(res)
    assert new["session_id"] != tid and new["source"] == "schedule"
    sch = store.get_schedule(new["session_id"])
    assert sch["name"] == "아침" and sch["instruction"] == "메일 요약"
    # 지금 세션은 그대로다
    assert store.get_session(tid)["source"] == "user" and store.get_schedule(tid) is None
    [chip] = store.entries(tid)
    assert (chip["kind"], chip["text"], chip["data"]) == (
        "chip", "아침", {"session_id": new["session_id"], "source": "schedule"})
    assert ctx.added == [chip]


async def test_create_session_schedule_with_edited_values(setup):
    store, ctx, tools, tid = setup({"name": "저녁", "rule": {"repeat": "weekdays", "time": "18:00"},
                                    "instruction": "정리"})
    res = await tools["create_session"].handler(
        {"source": "schedule", "name": "아침", "rule": RULE, "instruction": "메일 요약"})
    sch = store.get_schedule(payload(res)["session_id"])
    assert sch["name"] == "저녁" and sch["rule"]["repeat"] == "weekdays" and sch["instruction"] == "정리"


async def test_create_session_schedule_declined_makes_nothing(setup):
    store, ctx, tools, tid = setup("아니 9시 말고 10시")
    res = await tools["create_session"].handler(
        {"source": "schedule", "name": "아침", "rule": RULE, "instruction": "x"})
    assert ctx.started == [] and store.entries(tid) == []
    assert "아니 9시 말고 10시" in res["content"][0]["text"]


async def test_create_session_schedule_rejects_bad_rule(setup):
    store, ctx, tools, tid = setup()
    for rule in ({"repeat": "daily", "time": "25:00"}, "매일"):
        res = await tools["create_session"].handler({"source": "schedule", "name": "a", "rule": rule, "instruction": "x"})
        assert res["is_error"]
    assert ctx.confirms == [] and ctx.started == []


async def test_create_session_from_schedule_session(setup):
    """종류와 상관없이 어느 세션에서든 만든다: 스케줄 세션에서 스케줄·작업을 만든다."""
    store, ctx, tools, tid = setup("등록")
    store.create_schedule(tid, "아침", RULE, "i")
    a = await tools["create_session"].handler({"source": "schedule", "name": "저녁", "rule": RULE, "instruction": "x"})
    b = await tools["create_session"].handler({"source": "user", "text": "회의 자료 모아 줘"})
    assert not a.get("is_error") and not b.get("is_error")
    assert [e["data"]["source"] for e in store.entries(tid) if e["kind"] == "chip"] == ["schedule", "user"]


async def test_create_session_missing_fields_or_chat_is_error(setup):
    store, ctx, tools, tid = setup()
    for args in ({"source": "user"}, {"source": "schedule", "name": "a"}, {"source": "chat", "text": "x"}, {"text": "x"}):
        assert (await tools["create_session"].handler(args))["is_error"]
    assert ctx.started == [] and ctx.confirms == []


async def test_update_schedule_leaves_edit_entry(setup):
    store, ctx, tools, tid = setup("등록")
    store.create_schedule(tid, "아침", RULE, "메일 요약")
    res = await tools["update_schedule"].handler({"instruction": "메일과 일정 요약"})
    assert not res.get("is_error")
    assert ctx.confirms[0][1] == "이렇게 고칠까요?"
    assert store.get_schedule(tid)["instruction"] == "메일과 일정 요약"
    assert store.get_schedule(tid)["name"] == "아침"
    edits = [e for e in store.entries(tid) if e["kind"] == "edit"]
    assert edits and edits[0]["text"].startswith("작업 지시서를 고쳤어요:")
    assert ctx.added == edits and ctx.schedule_changes == 1  # 수정 줄과 스케줄을 화면에 보낸다


async def test_update_schedule_declined_or_missing(setup):
    store, ctx, tools, tid = setup("아니")
    assert (await tools["update_schedule"].handler({"name": "x"}))["is_error"]  # 스케줄 없음
    store.create_schedule(tid, "아침", RULE, "i")
    await tools["update_schedule"].handler({"name": "x"})
    assert store.get_schedule(tid)["name"] == "아침"
    assert [e for e in store.entries(tid) if e["kind"] == "edit"] == []
    assert ctx.added == [] and ctx.schedule_changes == 0


async def test_non_dict_rule_is_error(setup):
    store, ctx, tools, tid = setup()
    store.create_schedule(tid, "아침", RULE, "i")
    res = await tools["update_schedule"].handler({"rule": "매일"})
    assert res["is_error"] and ctx.confirms == []


async def test_update_schedule_no_change_writes_nothing(setup):
    store, ctx, tools, tid = setup("등록")
    store.create_schedule(tid, "아침", RULE, "i")
    res = await tools["update_schedule"].handler({"name": "아침"})
    assert not res.get("is_error") and "바뀐 내용이 없" in res["content"][0]["text"]
    assert [e for e in store.entries(tid) if e["kind"] == "edit"] == []


async def test_create_session_user_starts_task_and_leaves_chip(setup):
    store, ctx, tools, tid = setup()
    res = await tools["create_session"].handler({"source": "user", "text": "다음 주 회의 자료 모아 줘"})
    assert not res.get("is_error")
    new = payload(res)
    assert ctx.started == [("user", {"text": "다음 주 회의 자료 모아 줘"})]
    assert new["session_id"] != tid and new["title"] == "다음 주 회의 자료 모아 줘"
    [chip] = store.entries(tid)
    assert (chip["kind"], chip["text"], chip["data"]) == (
        "chip", "다음 주 회의 자료 모아 줘", {"session_id": new["session_id"], "source": "user"})
    assert ctx.added == [chip]
    assert store.entries(new["session_id"]) == []  # 칩은 지금 세션에만 남는다


async def test_create_session_when_logged_out_is_error(setup):
    store, ctx, tools, tid = setup()
    ctx.logged_in = False
    res = await tools["create_session"].handler({"source": "user", "text": "일"})
    assert res["is_error"]
    assert store.entries(tid) == [] and ctx.added == []


async def test_set_session_title_refused_in_chat():
    store = Store(None)
    chat = store.create_session("chat", "대화")
    ctx = FakeCtx(chat["id"], store=store)
    tools = {t.name: t for t in build_tools(store, ctx)}
    res = await tools["set_session_title"].handler({"title": "회의 자료"})
    assert res["is_error"]
    assert store.get_session(chat["id"])["title"] == "대화" and ctx.notified == []


async def test_create_session_deleted_during_start_leaves_no_chip(setup):
    store, ctx, tools, tid = setup()
    gate = asyncio.Event()
    start = ctx.start_session

    async def gated(source, fields):
        await gate.wait()
        return await start(source, fields)

    ctx.start_session = gated
    job = asyncio.create_task(tools["create_session"].handler({"source": "user", "text": "일"}))
    await asyncio.sleep(0)
    store.delete_session(tid)  # 기다리는 사이 이 세션이 지워진다
    gate.set()
    await job
    assert store.entries(tid) == [] and ctx.added == []


async def test_update_schedule_deleted_during_confirm_leaves_no_edit(setup):
    store, ctx, tools, tid = setup()
    store.create_schedule(tid, "저녁", RULE, "요약")
    confirm = ctx.confirm

    async def deleting(kind, text, data):
        answer = await confirm(kind, text, data)
        store.delete_session(tid)
        return answer

    ctx.confirm = deleting
    await tools["update_schedule"].handler({"name": "아침"})
    assert store.entries(tid) == [] and ctx.added == []
