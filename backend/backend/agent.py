"""Claude Code 세션 하나를 돌린다 (작업 하나 = 세션 하나, 0029). 질문·권한 요청은 Future 하나로 사용자 답을 기다린다."""
import asyncio
import logging
from pathlib import Path
from typing import Protocol

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, PermissionResultAllow,
                              PermissionResultDeny, RateLimitEvent, ResultMessage, SystemMessage, TextBlock,
                              ToolPermissionContext)

from . import config
from .tools import MCP_PREFIX

log = logging.getLogger(__name__)

HARNESS = (Path(__file__).with_name("harness.md")).read_text(encoding="utf-8")

SCREENPIPE = {"command": "npx", "args": ["-y", "screenpipe-mcp@latest"]}
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
    """세션에서 일어난 일을 앱(작업 관리)에 알린다."""

    def progress(self, text: str) -> None: ...
    def question(self, text: str, choices: list[str]) -> None: ...
    def confirm_request(self, kind: str, text: str, data: dict) -> None: ...
    def answered(self) -> None: ...
    def task_changed(self) -> None: ...
    def finished(self, result_text: str, is_error: bool) -> None: ...
    def session(self, session_id: str) -> None: ...
    def rate_limit(self, info: dict) -> None: ...


class AgentRun:
    """세션 하나. 도구의 TaskContext 노릇도 한다 (confirm은 질문과 같은 기다림을 쓴다)."""

    def __init__(self, task_id: int, events: RunEvents, make_client=ClaudeSDKClient):
        self.task_id = task_id
        self._events = events
        self._make_client = make_client
        self._client = None
        self._answer: asyncio.Future | None = None
        self._stopped = False

    @property
    def waiting(self) -> bool:
        return self._answer is not None and not self._answer.done()

    async def run(self, prompt: str, options) -> None:
        """끝(ResultMessage)까지 돌린다. 멈춘 경우엔 finished를 부르지 않는다 (앱이 멈춤으로 둔다)."""
        try:
            self._client = self._make_client(options=options)
            await self._client.connect()
            if self._stopped:
                return
            await self._client.query(prompt)
            async for m in self._client.receive_messages():
                if self._handle(m):
                    return
            if not self._stopped:
                log.warning("작업 %d: 결과 없이 세션이 끝났다", self.task_id)
                self._events.finished("결과 없이 끝났어요", True)
        except Exception as e:
            if self._stopped:
                return
            log.exception("작업 %d: Claude Code 실행 실패 (%s)", self.task_id, type(e).__name__)
            self._events.finished("Claude Code를 실행하지 못했어요", True)
        finally:
            await self._close()

    def _handle(self, m) -> bool:
        """메시지 하나를 이벤트로. 끝이면 True."""
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, TextBlock) and b.text.strip():
                    self._events.progress(b.text)
        elif isinstance(m, SystemMessage) and m.subtype == "init":
            self._events.session(m.data["session_id"])
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
            for q in tool_input.get("questions", []):
                self._events.question(q["question"], [o["label"] for o in q.get("options", [])])
                answers[q["question"]] = await self._wait()
                if self._stopped:
                    return PermissionResultDeny(message=STOP_ANSWER, interrupt=True)
            return PermissionResultAllow(updated_input={**tool_input, "answers": answers})
        self._events.question(ctx.title or f"{tool_name} 사용을 허용할까요?", ["허용", "거부"])
        answer = await self._wait()
        if answer == "허용":
            return PermissionResultAllow()
        return PermissionResultDeny(message=str(answer))

    async def confirm(self, kind: str, text: str, data: dict) -> str | dict:
        self._events.confirm_request(kind, text, data)
        return await self._wait()

    def notify(self, task: dict) -> None:
        self._events.task_changed()

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
            log.warning("작업 %d: 세션이 없어 덧붙이지 못했다", self.task_id)

    async def stop(self) -> None:
        self._stopped = True
        self.answer(STOP_ANSWER)
        if self._client is not None:
            try:
                await self._client.interrupt()
            except Exception as e:
                log.warning("작업 %d: 멈춤 요청 실패 (%s)", self.task_id, type(e).__name__)
        await self._close()

    async def _wait(self) -> str | dict:
        self._answer = asyncio.get_running_loop().create_future()
        try:
            value = await self._answer
        finally:
            self._answer = None
        if not self._stopped:
            self._events.answered()
        return value

    async def _close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
            except Exception as e:
                log.warning("작업 %d: 연결 끊기 실패 (%s)", self.task_id, type(e).__name__)
