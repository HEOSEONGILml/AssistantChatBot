"""Claude Code 세션 하나를 돌린다 (세션 하나에 Claude Code 세션 하나, 0029·0034). 질문·권한 요청은 Future 하나로 사용자 답을 기다린다."""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Protocol

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, PermissionResultAllow,
                              PermissionResultDeny, RateLimitEvent, ResultMessage, SystemMessage, TextBlock,
                              ToolPermissionContext)

from . import config
from .tools import MCP_PREFIX

log = logging.getLogger(__name__)

HARNESS = (Path(__file__).with_name("harness.md")).read_text(encoding="utf-8")

# 윈도 네이티브의 Claude Code는 npx(.cmd)를 직접 못 띄워 cmd /c로 감싼다.
SCREENPIPE = ({"command": "cmd", "args": ["/c", "npx", "-y", "screenpipe-mcp@latest"]}
              if sys.platform == "win32"
              else {"command": "npx", "args": ["-y", "screenpipe-mcp@latest"]})
STOP_ANSWER = "거부"


def build_options(*, permission_mode: str, can_use_tool, mcp_servers: dict, resume: str | None) -> ClaudeAgentOptions:
    """스펙 5.1 실행 옵션. 한도와 모델은 두지 않는다 (사용자)."""
    return ClaudeAgentOptions(
        system_prompt={"type": "preset", "preset": "claude_code", "append": HARNESS},
        setting_sources=[],
        cwd=config.work_dir(),
        extra_args={"chrome": None},
        disallowed_tools=["Bash", "Write", "Edit", "NotebookEdit", "Task", "Skill"],
        # 데이터 찾기 도구는 묻지 않는다
        allowed_tools=[MCP_PREFIX + "*", "mcp__screenpipe__*"],
        env=config.claude_env(),
        mcp_servers={**mcp_servers, "screenpipe": SCREENPIPE},
        permission_mode=permission_mode,
        can_use_tool=can_use_tool,
        resume=resume,
    )


class RunEvents(Protocol):
    """세션에서 일어난 일을 앱(세션 관리)에 알린다."""

    def progress(self, text: str) -> None: ...
    def question(self, text: str, choices: list[str]) -> None: ...
    def confirm_request(self, kind: str, text: str, data: dict) -> None: ...
    def answered(self) -> None: ...
    def session_changed(self) -> None: ...
    def entry_added(self, entry: dict) -> None: ...
    def schedule_changed(self) -> None: ...
    async def start_session(self, source: str, fields: dict) -> dict | None: ...
    def finished(self, result_text: str, is_error: bool) -> None: ...
    def claude_session(self, claude_session_id: str) -> None: ...
    def rate_limit(self, info: dict) -> None: ...


class AgentRun:
    """세션 하나. 도구의 SessionContext 노릇도 한다 (confirm은 질문과 같은 기다림을 쓴다)."""

    def __init__(self, session_id: int, events: RunEvents, make_client=ClaudeSDKClient):
        self.session_id = session_id
        self._events = events
        self._make_client = make_client
        self._client = None
        self._answer: asyncio.Future | None = None
        # SDK는 권한 요청·도구 호출을 따로 돌리므로 질문이 겹칠 수 있다. 한 번에 하나만 보이고 기다린다.
        self._ask_lock = asyncio.Lock()
        self._stopped = False

    @property
    def waiting(self) -> bool:
        return self._answer is not None and not self._answer.done()

    async def run(self, prompt: str, options) -> None:
        """끝(ResultMessage)까지 돌린다. 멈춘 경우엔 finished를 부르지 않는다 (앱이 멈춤으로 둔다)."""
        client = None
        try:
            # 지역 변수로도 쥐어, 연결 중 stop이 와도 이 클라이언트를 끝에 반드시 끊는다
            client = self._client = self._make_client(options=options)
            await client.connect()
            if self._stopped:
                return
            await client.query(prompt)
            async for m in client.receive_messages():
                if self._handle(m):
                    return
            if not self._stopped:
                log.warning("세션 %d: 결과 없이 세션이 끝났다", self.session_id)
                self._events.finished("결과 없이 끝났어요", True)
        except Exception as e:
            if self._stopped:
                return
            # SDK 오류 글·트레이스백에는 CLI 출력(사용자 내용)이 섞일 수 있어 종류만 남긴다
            log.error("세션 %d: Claude Code 실행 실패 (%s)", self.session_id, type(e).__name__)
            self._events.finished("Claude Code를 실행하지 못했어요", True)
        finally:
            self._client = None
            await self._disconnect(client)

    def _handle(self, m) -> bool:
        """메시지 하나를 이벤트로. 끝이면 True."""
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, TextBlock) and b.text.strip():
                    self._events.progress(b.text)
        elif isinstance(m, SystemMessage) and m.subtype == "init":
            self._events.claude_session(m.data["session_id"])
        elif isinstance(m, RateLimitEvent):
            i = m.rate_limit_info
            self._events.rate_limit({"type": i.rate_limit_type, "utilization": i.utilization,
                                     "resets_at": i.resets_at})
        elif isinstance(m, ResultMessage):
            self._events.finished(m.result or "", m.is_error)
            return True
        return False

    async def can_use_tool(self, tool_name: str, tool_input: dict, ctx: ToolPermissionContext):
        if tool_name == "AskUserQuestion":
            answers = {}
            async with self._ask_lock:  # 한 도구의 질문들은 이어서 묻는다
                for q in tool_input.get("questions", []):
                    answers[q["question"]] = await self._ask(
                        lambda: self._events.question(q["question"], [o["label"] for o in q.get("options", [])]))
                    if self._stopped:
                        return PermissionResultDeny(message=STOP_ANSWER, interrupt=True)
            return PermissionResultAllow(updated_input={**tool_input, "answers": answers})
        async with self._ask_lock:
            answer = await self._ask(
                lambda: self._events.question(ctx.title or f"{tool_name} 사용을 허용할까요?", ["허용", "거부"]))
        if self._stopped:
            return PermissionResultDeny(message=STOP_ANSWER, interrupt=True)
        if answer == "허용":
            return PermissionResultAllow()
        return PermissionResultDeny(message=str(answer))

    async def confirm(self, kind: str, text: str, data: dict) -> str | dict:
        async with self._ask_lock:
            return await self._ask(lambda: self._events.confirm_request(kind, text, data))

    def notify(self, session: dict) -> None:
        self._events.session_changed()

    def entry_added(self, entry: dict) -> None:
        self._events.entry_added(entry)

    def schedule_changed(self) -> None:
        self._events.schedule_changed()

    async def start_session(self, source: str, fields: dict) -> dict | None:
        return await self._events.start_session(source, fields)

    def answer(self, value: str | dict) -> None:
        """기다리는 답을 푼다. 앱이 [고치기] 폼의 dict를 넘길 때도 쓴다."""
        if self.waiting:
            self._answer.set_result(value)

    async def say(self, text: str) -> None:
        """질문을 기다리는 중이면 그 답으로, 아니면 진행 중인 세션에 덧붙인다."""
        if self.waiting:
            self.answer(text)
        elif self._client is not None and not self._stopped:
            await self._client.query(text)
        else:
            log.warning("세션 %d: 세션이 없어 덧붙이지 못했다", self.session_id)

    async def stop(self) -> None:
        """지금 질문은 "거부"로 풀고, 줄 서 있던 질문은 _ask에서 바로 "거부"로 끝난다."""
        self._stopped = True
        self.answer(STOP_ANSWER)
        client = self._client
        if client is not None:
            try:
                await client.interrupt()
            except Exception as e:
                log.warning("세션 %d: 멈춤 요청 실패 (%s)", self.session_id, type(e).__name__)
            await self._disconnect(client)

    async def _ask(self, emit) -> str | dict:
        """_ask_lock을 쥔 채로 부른다. 멈췄으면 묻지 않고 "거부"."""
        if self._stopped:
            return STOP_ANSWER
        emit()
        return await self._wait()

    async def _wait(self) -> str | dict:
        self._answer = asyncio.get_running_loop().create_future()
        try:
            value = await self._answer
        finally:
            self._answer = None
        if not self._stopped:
            self._events.answered()
        return value

    async def _disconnect(self, client) -> None:
        if client is not None:
            try:
                await client.disconnect()
            except Exception as e:
                log.warning("세션 %d: 연결 끊기 실패 (%s)", self.session_id, type(e).__name__)
