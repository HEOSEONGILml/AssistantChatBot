"""에이전트가 쓰는 백엔드 MCP 도구. 작업 기록 검색과 스케줄 등록·수정을 맡는다."""
import json
from datetime import datetime
from typing import Protocol

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool

from .schedule_rule import label, next_run, validate
from .store import Store

MCP_PREFIX = "mcp__assistant__"


class TaskContext(Protocol):
    """도구가 지금 작업과 이야기하는 통로. 제안 줄과 상태는 confirm이 남긴다."""

    task_id: int

    async def confirm(self, kind: str, text: str, data: dict) -> str | dict: ...

    def notify(self, task: dict) -> None: ...


def _ok(value) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}


def _text(text: str, is_error: bool = False) -> dict:
    result = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["is_error"] = True
    return result


def _proposal(name: str, rule: dict, instruction: str) -> dict:
    first_run = next_run(rule, datetime.now().astimezone()).isoformat(timespec="seconds")
    return {"name": name, "rule": rule, "label": label(rule), "instruction": instruction, "first_run": first_run}


def _confirmed(answer: dict, fallback: dict) -> dict:
    """[고치기]로 저장된 값을 쓰되, 빠진 칸은 제안 값으로 채운다."""
    return {k: answer.get(k, fallback[k]) for k in ("name", "rule", "instruction")}


def build_tools(store: Store, ctx: TaskContext) -> list[SdkMcpTool]:
    @tool("recent_tasks", "최근 작업 목록 (최신순).", {"type": "object", "properties": {
        "limit": {"type": "integer", "description": "개수 (기본 10)"}}})
    async def recent_tasks(args):
        return _ok(store.recent_tasks(args.get("limit", 10)))

    @tool("search_tasks", "작업 제목과 대화 글을 검색한다. since·until은 날짜(YYYY-MM-DD)나 ISO 시각.", {
        "type": "object",
        "properties": {"query": {"type": "string"}, "since": {"type": "string"},
                       "until": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["query"]})
    async def search_tasks(args):
        return _ok(store.search_tasks(args["query"], args.get("since"), args.get("until"), args.get("limit", 10)))

    @tool("get_task", "작업 하나와 그 대화 줄을 본다.", {"task_id": int})
    async def get_task(args):
        task = store.get_task(args["task_id"])
        if task is None:
            return _text("그런 작업이 없다", True)
        return _ok({"task": task, "entries": store.entries(task["id"])})

    @tool("get_schedule", "이 작업의 스케줄 지시서를 본다.", {})
    async def get_schedule(args):
        schedule = store.get_schedule(ctx.task_id)
        if schedule is None:
            return _text("이 작업에는 스케줄이 없다", True)
        return _ok(schedule)

    @tool("set_task_title", "이 작업의 제목을 정한다.", {"title": str})
    async def set_task_title(args):
        ctx.notify(store.update_task(ctx.task_id, title=args["title"]))
        return _ok({"ok": True})

    @tool("create_schedule",
          "이 작업을 반복 스케줄로 등록한다. 사용자 확인을 거친다. "
          "rule: {repeat: daily|weekdays|weekly|monthly, time: 'HH:MM', weekday: 0-6(월=0), day: 1-31}",
          {"type": "object",
           "properties": {"name": {"type": "string"}, "rule": {"type": "object"}, "instruction": {"type": "string"}},
           "required": ["name", "rule", "instruction"]})
    async def create_schedule(args):
        try:
            validate(args["rule"])
        except ValueError as e:
            return _text(str(e), True)
        proposal = _proposal(args["name"], args["rule"], args["instruction"])
        answer = await ctx.confirm("proposal", "이렇게 등록할까요?", proposal)
        if isinstance(answer, dict):
            values = _confirmed(answer, proposal)
        elif answer in ("등록", "예"):
            values = _confirmed({}, proposal)
        else:
            return _text(f"등록하지 않았다. 사용자 답: {answer}")
        try:
            validate(values["rule"])
        except ValueError as e:
            return _text(str(e), True)
        store.create_schedule(ctx.task_id, values["name"], values["rule"], values["instruction"])
        ctx.notify(store.update_task(ctx.task_id, source="schedule"))
        return _ok({"ok": True, "saved": values})

    @tool("update_schedule", "이 작업의 스케줄을 고친다 (바뀐 칸만). 사용자 확인을 거친다.",
          {"type": "object",
           "properties": {"name": {"type": "string"}, "rule": {"type": "object"}, "instruction": {"type": "string"}}})
    async def update_schedule(args):
        current = store.get_schedule(ctx.task_id)
        if current is None:
            return _text("이 작업에는 스케줄이 없다", True)
        changes = {k: args[k] for k in ("name", "rule", "instruction") if k in args}
        if not changes:
            return _text("바꿀 내용이 없다", True)
        if "rule" in changes:
            try:
                validate(changes["rule"])
            except ValueError as e:
                return _text(str(e), True)
        merged = {**{k: current[k] for k in ("name", "rule", "instruction")}, **changes}
        proposal = _proposal(**merged) | {"changed": sorted(changes)}
        answer = await ctx.confirm("proposal", "이렇게 고칠까요?", proposal)
        if isinstance(answer, dict):
            values = _confirmed(answer, merged)
        elif answer in ("등록", "예"):
            values = merged
        else:
            return _text(f"고치지 않았다. 사용자 답: {answer}")
        try:
            validate(values["rule"])
        except ValueError as e:
            return _text(str(e), True)
        store.update_schedule(ctx.task_id, **values)
        fields = [k for k in ("name", "rule", "instruction") if values[k] != current[k]]
        names = {"name": "이름", "rule": "반복", "instruction": "지시"}
        store.add_entry(ctx.task_id, "edit", "작업 지시서를 고쳤어요: " + ", ".join(names[k] for k in fields))
        return _ok({"ok": True, "saved": values})

    return [recent_tasks, search_tasks, get_task, get_schedule, set_task_title, create_schedule, update_schedule]


def backend_server(store: Store, ctx: TaskContext):
    return create_sdk_mcp_server(name="assistant", tools=build_tools(store, ctx))
