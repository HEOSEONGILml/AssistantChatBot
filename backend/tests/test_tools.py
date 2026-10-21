import json

import pytest

from backend.store import Store
from backend.tools import MCP_PREFIX, backend_server, build_tools

RULE = {"repeat": "daily", "time": "09:00"}


class FakeCtx:
    def __init__(self, task_id, answer="등록", store=None):
        self.task_id = task_id
        self.answer = answer
        self.store = store
        self.confirms = []
        self.notified = []
        self.saved_before_confirm = None

    async def confirm(self, kind, text, data):
        self.saved_before_confirm = self.store.get_schedule(self.task_id) if self.store else None
        self.confirms.append((kind, text, data))
        return self.answer

    def notify(self, task):
        self.notified.append(task)


@pytest.fixture
def setup():
    store = Store(None)
    task = store.create_task("user", "임시")

    def make(answer="등록"):
        ctx = FakeCtx(task["id"], answer, store)
        tools = {t.name: t for t in build_tools(store, ctx)}
        return store, ctx, tools, task["id"]

    return make


def payload(result):
    return json.loads(result["content"][0]["text"])


def test_server_and_prefix(setup):
    store, ctx, tools, _ = setup()
    assert MCP_PREFIX == "mcp__assistant__"
    assert set(tools) == {"recent_tasks", "search_tasks", "get_task", "get_schedule",
                          "set_task_title", "create_schedule", "update_schedule"}
    assert backend_server(store, ctx)["name"] == "assistant"


async def test_search_tasks_returns_matches(setup):
    store, ctx, tools, tid = setup()
    store.update_task(tid, title="견적서 정리")
    other = store.create_task("user", "점심 메뉴")
    res = await tools["search_tasks"].handler({"query": "견적서"})
    assert [t["id"] for t in payload(res)] == [tid]
    assert other["id"] not in [t["id"] for t in payload(res)]


async def test_recent_and_get_task(setup):
    store, ctx, tools, tid = setup()
    assert payload(await tools["recent_tasks"].handler({}))[0]["id"] == tid
    store.add_entry(tid, "user", "안녕")
    got = payload(await tools["get_task"].handler({"task_id": tid}))
    assert got["task"]["id"] == tid and got["entries"][0]["text"] == "안녕"
    assert (await tools["get_task"].handler({"task_id": 999}))["is_error"]


async def test_get_schedule_missing_is_error(setup):
    _, _, tools, _ = setup()
    assert (await tools["get_schedule"].handler({}))["is_error"]


async def test_set_task_title_notifies(setup):
    store, ctx, tools, tid = setup()
    await tools["set_task_title"].handler({"title": "새 제목"})
    assert store.get_task(tid)["title"] == "새 제목"
    assert ctx.notified[0]["title"] == "새 제목"


async def test_create_schedule_waits_for_confirmation(setup):
    store, ctx, tools, tid = setup("등록")
    res = await tools["create_schedule"].handler({"name": "아침", "rule": RULE, "instruction": "메일 요약"})
    assert not res.get("is_error")
    assert ctx.saved_before_confirm is None
    kind, text, data = ctx.confirms[0]
    assert kind == "proposal" and text == "이렇게 등록할까요?"
    assert data["label"] == "매일 09:00" and data["first_run"]
    sch = store.get_schedule(tid)
    assert sch["name"] == "아침" and sch["instruction"] == "메일 요약"
    assert store.get_task(tid)["source"] == "schedule"
    assert ctx.notified


async def test_create_schedule_with_edited_values(setup):
    store, ctx, tools, tid = setup({"name": "저녁", "rule": {"repeat": "weekdays", "time": "18:00"},
                                    "instruction": "정리"})
    await tools["create_schedule"].handler({"name": "아침", "rule": RULE, "instruction": "메일 요약"})
    sch = store.get_schedule(tid)
    assert sch["name"] == "저녁" and sch["rule"]["repeat"] == "weekdays" and sch["instruction"] == "정리"


async def test_create_schedule_declined_saves_nothing(setup):
    store, ctx, tools, tid = setup("아니 9시 말고 10시")
    res = await tools["create_schedule"].handler({"name": "아침", "rule": RULE, "instruction": "x"})
    assert store.get_schedule(tid) is None
    assert store.get_task(tid)["source"] == "user"
    assert "아니 9시 말고 10시" in res["content"][0]["text"]


async def test_create_schedule_rejects_bad_rule(setup):
    store, ctx, tools, tid = setup()
    res = await tools["create_schedule"].handler(
        {"name": "a", "rule": {"repeat": "daily", "time": "25:00"}, "instruction": "x"})
    assert res["is_error"] and ctx.confirms == []


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


async def test_update_schedule_declined_or_missing(setup):
    store, ctx, tools, tid = setup("아니")
    assert (await tools["update_schedule"].handler({"name": "x"}))["is_error"]  # 스케줄 없음
    store.create_schedule(tid, "아침", RULE, "i")
    await tools["update_schedule"].handler({"name": "x"})
    assert store.get_schedule(tid)["name"] == "아침"
