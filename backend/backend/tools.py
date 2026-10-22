"""에이전트가 쓰는 백엔드 MCP 도구. 세션 조회, 새 세션 만들기, 지금 세션의 제목·스케줄 고치기를 맡는다."""
import json
from datetime import datetime
from typing import Protocol

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool

from .schedule_rule import label, next_run, validate
from .store import Store

MCP_NAME = "backend"  # 파이썬 백엔드 MCP의 서버 이름
MCP_PREFIX = f"mcp__{MCP_NAME}__"


class SessionContext(Protocol):
    """도구가 지금 세션과 이야기하는 통로. 제안 줄과 상태는 confirm이 남긴다.
    도구가 저장한 줄·스케줄은 entry_added·schedule_changed로 화면에 알린다."""

    session_id: int

    async def confirm(self, kind: str, text: str, data: dict) -> str | dict: ...

    def notify(self, session: dict) -> None: ...

    def entry_added(self, entry: dict) -> None: ...

    def schedule_changed(self) -> None: ...

    async def start_session(self, source: str, fields: dict) -> dict | None:
        """새 세션을 만든다. 작업(user)은 바로 돌리고, 스케줄(schedule)은 첫 실행 때 돈다.
        로그아웃이면 만들지 않고 None."""


def _ok(value) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}


def _text(text: str, is_error: bool = False) -> dict:
    result = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["is_error"] = True
    return result


def _invalid(rule) -> str | None:
    """규칙이 틀리면 이유를, 맞으면 None을. dict가 아닌 값도 같은 오류로 다룬다."""
    try:
        validate(rule)
    except (ValueError, TypeError, AttributeError) as e:
        return str(e) or "규칙 모양이 틀렸다"
    return None


def _proposal(name: str, rule: dict, instruction: str) -> dict:
    first_run = next_run(rule, datetime.now().astimezone()).isoformat(timespec="seconds")
    return {"name": name, "rule": rule, "label": label(rule), "instruction": instruction, "first_run": first_run}


def _confirmed(answer: dict, fallback: dict) -> dict:
    """[고치기]로 저장된 값을 쓰되, 빠진 칸은 제안 값으로 채운다."""
    return {k: answer.get(k, fallback[k]) for k in ("name", "rule", "instruction")}


def edit_text(current: dict, values: dict) -> str | None:
    """지시서 수정 줄의 글. 바뀐 칸이 없으면 None. 대화 도구와 수정 양식이 함께 쓴다."""
    names = {"name": "이름", "rule": "반복", "instruction": "지시"}
    fields = [names[k] for k in names if values[k] != current[k]]
    return "작업 지시서를 고쳤어요: " + ", ".join(fields) if fields else None


def build_tools(store: Store, ctx: SessionContext) -> list[SdkMcpTool]:
    def leave_entry(kind, text, data=None):
        """이 세션에 대화 줄을 남긴다. 기다리는 사이 세션이 지워졌으면 남기지 않는다."""
        if store.get_session(ctx.session_id) is None:
            return
        ctx.entry_added(store.add_entry(ctx.session_id, kind, text, data=data))

    @tool("recent_sessions", "최근 세션 목록 (최신순).", {"type": "object", "properties": {
        "limit": {"type": "integer", "description": "개수 (기본 10)"}}})
    async def recent_sessions(args):
        return _ok(store.recent_sessions(args.get("limit", 10)))

    @tool("search_sessions", "세션 제목과 대화 글을 검색한다. since·until은 날짜(YYYY-MM-DD)나 ISO 시각.", {
        "type": "object",
        "properties": {"query": {"type": "string"}, "since": {"type": "string"},
                       "until": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["query"]})
    async def search_sessions(args):
        return _ok(store.search_sessions(args["query"], args.get("since"), args.get("until"), args.get("limit", 10)))

    @tool("get_session", "세션 하나와 그 대화 줄을 본다.", {"session_id": int})
    async def get_session(args):
        session = store.get_session(args["session_id"])
        if session is None:
            return _text("그런 세션이 없다", True)
        return _ok({"session": session, "entries": store.entries(session["id"])})

    @tool("get_schedule", "이 세션의 스케줄 지시서를 본다.", {})
    async def get_schedule(args):
        schedule = store.get_schedule(ctx.session_id)
        if schedule is None:
            return _text("이 세션에는 스케줄이 없다", True)
        return _ok(schedule)

    @tool("set_session_title", "이 세션의 제목을 정한다.", {"title": str})
    async def set_session_title(args):
        if store.get_session(ctx.session_id)["source"] == "chat":
            return _text("대화 탭의 제목은 바꾸지 않는다", True)
        ctx.notify(store.update_session(ctx.session_id, title=args["title"]))
        return _ok({"ok": True})

    @tool("create_session",
          "새 세션을 만들고 지금 세션에 칩 줄로 잇는다. 어느 세션에서든 쓴다. "
          "source=user(작업): text에 맡긴 일을 사용자 말 그대로, 맥락이 빠졌으면 채워서 적는다. 바로 돈다. "
          "source=schedule(스케줄): name, rule, instruction. 사용자 확인을 거친다. 정한 시각에 돈다. "
          "rule: {repeat: daily|weekdays|weekly|monthly, time: 'HH:MM', weekday: 0-6(월=0), day: 1-31}",
          {"type": "object",
           "properties": {"source": {"type": "string", "enum": ["user", "schedule"]}, "text": {"type": "string"},
                          "name": {"type": "string"}, "rule": {"type": "object"}, "instruction": {"type": "string"}},
           "required": ["source"]})
    async def create_session(args):
        source = args.get("source")
        if source == "user":
            if not isinstance(args.get("text"), str) or not args["text"]:
                return _text("작업에는 text가 필요하다", True)
            fields = {"text": args["text"]}
        elif source == "schedule":
            if not all(isinstance(args.get(k), str) for k in ("name", "instruction")):
                return _text("스케줄에는 name, rule, instruction이 필요하다", True)
            if (err := _invalid(args.get("rule"))):
                return _text(err, True)
            proposal = _proposal(args["name"], args["rule"], args["instruction"])
            answer = await ctx.confirm("proposal", "이렇게 등록할까요?", proposal)
            if isinstance(answer, dict):
                fields = _confirmed(answer, proposal)
            elif answer in ("등록", "예"):
                fields = _confirmed({}, proposal)
            else:
                return _text(f"등록하지 않았다. 사용자 답: {answer}")
            if (err := _invalid(fields["rule"])):
                return _text(err, True)
        else:
            return _text("source는 user나 schedule이다 (대화 세션은 하나뿐이다)", True)
        session = await ctx.start_session(source, fields)
        if session is None:
            return _text("로그아웃 상태라 세션을 만들지 못했다", True)
        leave_entry("chip", session["title"], data={"session_id": session["id"], "source": source})
        return _ok({"session_id": session["id"], "source": source, "title": session["title"]})

    @tool("update_schedule", "이 세션의 스케줄을 고친다 (바뀐 칸만). 사용자 확인을 거친다.",
          {"type": "object",
           "properties": {"name": {"type": "string"}, "rule": {"type": "object"}, "instruction": {"type": "string"}}})
    async def update_schedule(args):
        current = store.get_schedule(ctx.session_id)
        if current is None:
            return _text("이 세션에는 스케줄이 없다", True)
        changes = {k: args[k] for k in ("name", "rule", "instruction") if k in args}
        if not changes:
            return _text("바꿀 내용이 없다", True)
        if "rule" in changes:
            if (err := _invalid(changes["rule"])):
                return _text(err, True)
        merged = {**{k: current[k] for k in ("name", "rule", "instruction")}, **changes}
        proposal = _proposal(**merged) | {"changed": sorted(changes)}
        answer = await ctx.confirm("proposal", "이렇게 고칠까요?", proposal)
        if isinstance(answer, dict):
            values = _confirmed(answer, merged)
        elif answer in ("등록", "예"):
            values = merged
        else:
            return _text(f"고치지 않았다. 사용자 답: {answer}")
        if (err := _invalid(values["rule"])):
            return _text(err, True)
        if all(values[k] == current[k] for k in values):
            return _text("바뀐 내용이 없어 저장하지 않았다")
        store.update_schedule(ctx.session_id, **values)
        leave_entry("edit", edit_text(current, values))
        ctx.schedule_changed()
        return _ok({"ok": True, "saved": values})

    return [recent_sessions, search_sessions, get_session, get_schedule, set_session_title, create_session,
            update_schedule]


def backend_server(store: Store, ctx: SessionContext):
    return create_sdk_mcp_server(name=MCP_NAME, tools=build_tools(store, ctx))
