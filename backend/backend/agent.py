"""Claude Code 세션 하나를 돌린다 (세션 하나에 Claude Code 세션 하나, 0029·0034). 질문·권한 요청은 Future 하나로 사용자 답을 기다린다."""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Protocol

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, PermissionResultAllow,
                              PermissionResultDeny, RateLimitEvent, ResultMessage, SystemMessage, TextBlock,
                              ToolPermissionContext, UserMessage)
from claude_agent_sdk.types import StreamEvent

from . import config
from .tools import MCP_PREFIX

log = logging.getLogger(__name__)

HARNESS = (Path(__file__).with_name("harness.md")).read_text(encoding="utf-8")

# 윈도 네이티브의 Claude Code는 npx(.cmd)를 직접 못 띄워 cmd /c로 감싼다.
SCREENPIPE = ({"command": "cmd", "args": ["/c", "npx", "-y", "screenpipe-mcp@latest"]}
              if sys.platform == "win32"
              else {"command": "npx", "args": ["-y", "screenpipe-mcp@latest"]})
STOP_ANSWER = "거부"
PROBE_TIMEOUT = 10  # 초. 시작 때 MCP 상태 읽기가 매달리면 포기한다 (계획 2026-10-22-mcp-list Review Focus 4)
PROBE_POLL = 1  # 초. 연결 중(pending)인 MCP가 있으면 이 간격으로 다시 읽는다 (잠정값)
DISCONNECT_TIMEOUT = 5  # 초. 끊기가 매달려도 시작 때 읽기를 끝낸다 (잠정값)
# 초. 결과 뒤 처리 안 된 덧붙인 말이 있을 때 다음 차례를 기다리는 시간. 결과를 받은 때부터 잰다
# (잠정값. 2026-10-23 실측에서 다음 차례는 0.1초 안에 시작했다)
FOLLOWUP_GRACE = 3

# 도구 이름 -> 준비 중 줄의 글. 앞부분이 맞으면 그 글이다 (context 정한 값 표)
_TOOL_PREFIX_TEXT = (("mcp__screenpipe__", "화면 기록에서 찾는 중"),
                     ("mcp__claude-in-chrome__", "크롬에서 작업하는 중"),
                     (MCP_PREFIX, "지난 작업 찾는 중"))
_TOOL_TEXT = {"WebSearch": "웹에서 검색하는 중", "WebFetch": "웹 페이지 읽는 중", "Bash": "명령 실행하는 중",
              "Read": "파일 읽는 중", "Glob": "파일 읽는 중", "Grep": "파일 읽는 중",
              "Write": "파일 고치는 중", "Edit": "파일 고치는 중", "NotebookEdit": "파일 고치는 중",
              "Task": "다른 에이전트에게 맡기는 중", "Agent": "다른 에이전트에게 맡기는 중"}


def activity_of(block: dict) -> tuple[str, str] | None:
    """content_block_start의 블록 -> (kind, text). 보내지 않을 블록이면 None.
    AskUserQuestion은 질문 줄이 대신 보이므로 보내지 않는다."""
    kind = block.get("type")
    if kind == "thinking":
        return "thinking", "생각하는 중"
    if kind == "text":
        return "writing", "답 쓰는 중"
    if kind != "tool_use":
        return None
    name = block.get("name", "")
    if name == "AskUserQuestion":
        return None
    for prefix, text in _TOOL_PREFIX_TEXT:
        if name.startswith(prefix):
            return "tool", text
    return "tool", _TOOL_TEXT.get(name, "도구 쓰는 중")


def build_options(*, permission_mode: str, can_use_tool, mcp_servers: dict, resume: str | None) -> ClaudeAgentOptions:
    """스펙 5.1 실행 옵션. 한도와 모델은 두지 않는다 (사용자)."""
    return ClaudeAgentOptions(
        system_prompt={"type": "preset", "preset": "claude_code", "append": HARNESS},
        setting_sources=[],
        cwd=config.work_dir(),
        # replay-user-messages: 보낸 말을 처리하기 시작할 때 다시 받아, 덧붙인 말이 처리됐는지 안다
        extra_args={"chrome": None, "replay-user-messages": None},
        # 데이터 찾기 도구는 묻지 않는다
        allowed_tools=[MCP_PREFIX + "*", "mcp__screenpipe__*"],
        env=config.claude_env(),
        mcp_servers={**mcp_servers, "screenpipe": SCREENPIPE},
        permission_mode=permission_mode,
        can_use_tool=can_use_tool,
        resume=resume,
        include_partial_messages=True,  # 지금 하는 일(activity)을 StreamEvent로 받는다 (스펙 5.1)
    )


async def fetch_mcp_status(options, make_client=ClaudeSDKClient) -> list[dict]:
    """Claude Code를 질문 없이 붙여 MCP 상태 목록(mcpServers)만 읽고 끊는다 (모델 호출 없음).
    연결 중(pending)인 MCP가 있으면 PROBE_POLL마다 다시 읽는다. PROBE_TIMEOUT이 지나면 마지막으로 읽은 목록을,
    한 번도 못 읽었으면 TimeoutError. 어느 경우든 끊어 프로세스를 남기지 않는다."""
    client = make_client(options=options)
    last = None
    try:
        async with asyncio.timeout(PROBE_TIMEOUT):
            await client.connect()
            while True:
                last = (await client.get_mcp_status())["mcpServers"]
                if not any(isinstance(s, dict) and s.get("status") == "pending" for s in last):
                    return last
                await asyncio.sleep(PROBE_POLL)
    except TimeoutError:
        if last is None:
            raise
        return last
    finally:
        try:
            async with asyncio.timeout(DISCONNECT_TIMEOUT):
                await client.disconnect()
        except Exception as e:
            log.warning("MCP 상태 읽기: 연결 끊기 실패 (%s)", type(e).__name__)


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
    def turn_result(self, result_text: str, is_error: bool) -> None: ...
    def finished(self, result_text: str, is_error: bool) -> None: ...
    def claude_session(self, claude_session_id: str) -> None: ...
    def rate_limit(self, info: dict) -> None: ...
    def activity(self, kind: str, text: str) -> None: ...
    def mcp_status(self, servers) -> None: ...


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
        # 마지막 글은 최종 답(ResultMessage)과 같으므로, 다음 메시지가 올 때까지 진행으로 보내지 않고 쥔다
        self._held: str | None = None
        self._activity: tuple[str, str] | None = None  # 마지막으로 보낸 지금 하는 일
        # 덧붙인 말 (스펙 5.1 실행 끝내기): 보낸 말 수와 Claude Code가 처리하기 시작한(다시 보낸) 말 수
        self._sent = 0
        self._replayed = 0
        # 처리 안 된 덧붙인 말이 남아 다음 차례를 기다리는 동안 쥔 결과 (글, 오류인가)
        self._pending_result: tuple[str, bool] | None = None

    @property
    def waiting(self) -> bool:
        return self._answer is not None and not self._answer.done()

    async def run(self, prompt: str, options) -> None:
        """끝(마지막 차례의 ResultMessage)까지 돌린다. 멈춘 경우엔 finished를 부르지 않는다 (앱이 멈춤으로 둔다)."""
        client = None
        try:
            # 지역 변수로도 쥐어, 연결 중 stop이 와도 이 클라이언트를 끝에 반드시 끊는다
            client = self._client = self._make_client(options=options)
            await client.connect()
            if self._stopped:
                return
            self._sent += 1
            await client.query(prompt)
            messages = client.receive_messages()
            deadline = None  # 결과를 쥔 뒤 다음 차례를 기다릴 마감. 사이에 다른 메시지가 와도 늦추지 않는다
            while True:
                if self._pending_result is None:
                    deadline = None
                elif deadline is None:
                    deadline = asyncio.get_running_loop().time() + FOLLOWUP_GRACE
                try:
                    async with asyncio.timeout_at(deadline):  # None이면 마감 없음
                        m = await anext(messages)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    log.info("세션 %d: 덧붙인 말의 다음 차례가 오지 않아 끝낸다", self.session_id)
                    break
                if self._handle(m):
                    return
            if self._stopped:
                return
            if self._pending_result is not None:
                self._events.finished(*self._pending_result)
                return
            self._flush()
            log.warning("세션 %d: 결과 없이 세션이 끝났다", self.session_id)
            self._events.finished("결과 없이 끝났어요", True)
        except Exception as e:
            if self._stopped:
                return
            self._flush()
            # SDK 오류 글·트레이스백에는 CLI 출력(사용자 내용)이 섞일 수 있어 종류만 남긴다
            log.error("세션 %d: Claude Code 실행 실패 (%s)", self.session_id, type(e).__name__)
            if self._pending_result is not None:  # 앞 차례의 답은 받았으니 그것으로 끝낸다
                self._events.finished(*self._pending_result)
            else:
                self._events.finished("Claude Code를 실행하지 못했어요", True)
        finally:
            self._client = None
            await self._disconnect(client)

    def _handle(self, m) -> bool:
        """메시지 하나를 이벤트로. 끝이면 True."""
        if isinstance(m, StreamEvent):
            # 글자 조각(delta)은 보지 않고 블록이 시작될 때만 본다
            if m.event.get("type") == "content_block_start" and not self._stopped:
                now = activity_of(m.event.get("content_block", {}))
                if now is not None and now != self._activity:
                    self._activity = now
                    self._events.activity(*now)
        elif isinstance(m, AssistantMessage):
            for b in m.content:
                self._flush()
                if isinstance(b, TextBlock) and b.text.strip():
                    self._held = b.text
        elif isinstance(m, UserMessage):
            # 도구 결과와 Claude Code가 끼워 넣은 차례(origin이 human이 아님)는 우리가 보낸 말이 아니다
            if (isinstance(m.content, str) and m.tool_use_result is None and m.parent_tool_use_id is None
                    and (m.origin is None or m.origin.get("kind") == "human")):
                self._replayed += 1
                self._next_turn()
        elif isinstance(m, SystemMessage) and m.subtype == "init":
            self._next_turn()
            self._events.claude_session(m.data["session_id"])
            self._events.mcp_status(m.data.get("mcp_servers"))  # 모양 검사는 앱이 한다
        elif isinstance(m, RateLimitEvent):
            i = m.rate_limit_info
            # 풀린 칸은 창 하나뿐이고 utilization이 비어 올 수 있어, 창별 값이 다 든 원본(raw)도 넘긴다
            self._events.rate_limit({"type": i.rate_limit_type, "utilization": i.utilization,
                                     "resets_at": i.resets_at, "raw": i.raw})
        elif isinstance(m, ResultMessage):
            if self._held is not None and self._held.strip() != (m.result or "").strip():
                self._flush()
            self._held = None
            if self._replayed < self._sent and self._sent > 1:
                # 덧붙인 말이 아직 처리되지 않았다. 다음 차례가 오면 이 결과는 중간 결과가 된다
                self._pending_result = (m.result or "", m.is_error)
                return False
            self._events.finished(m.result or "", m.is_error)
            return True
        return False

    def _next_turn(self) -> None:
        """다음 차례가 시작됐다. 쥔 결과가 있으면 중간 결과로 보낸다."""
        if self._pending_result is not None:
            if not self._stopped:
                self._events.turn_result(*self._pending_result)
                self._activity = None  # 화면은 result 줄에서 준비 중 줄을 지우므로 같은 일도 다시 보낸다
            self._pending_result = None

    def _flush(self) -> None:
        if self._held is not None:
            self._events.progress(self._held)
            self._held = None

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
            self._sent += 1  # 결과가 오기 전에 세어야 처리 안 된 말로 본다
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
        self._activity = None  # 질문이 준비 중 줄을 지우므로 답한 뒤에는 같은 일도 다시 보낸다
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
