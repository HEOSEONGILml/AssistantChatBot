"""작업 관리: 화면 메시지마다 메서드 하나. 작업 하나 = Claude Code 세션 하나를 백그라운드로 돌리고,
세션에서 일어난 일을 대화 줄·상태로 저장해 화면에 보낸다. 전송 방식과 화면을 모른다."""
import asyncio
import logging
from collections import deque
from datetime import datetime
from typing import Awaitable, Callable, Protocol

from .agent import AgentRun, build_options
from .schedule_rule import label, next_run, validate
from .store import Store
from .tools import backend_server, edit_text

log = logging.getLogger(__name__)

Emit = Callable[[dict], Awaitable[None]]

PERMISSION_MODES = ("default", "acceptEdits", "plan", "auto", "bypassPermissions")
VIEWS = ("user", "alerts")
TITLE_LEN = 30
PROPOSAL_CHOICES = ["등록", "고치기"]
CHAT_TITLE = "대화"


class Auth(Protocol):
    async def logged_in(self) -> bool: ...
    async def login(self) -> bool: ...


def _now() -> datetime:
    return datetime.now().astimezone()


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


class _Events:
    """작업 하나의 RunEvents. 세션 이벤트를 저장하고 화면에 알린다."""

    def __init__(self, app: "App", task_id: int):
        self._app = app
        self._id = task_id
        self.confirming = False  # 등록 확인을 기다리는 중 ([고치기] 양식의 값을 답으로 넘길 때)

    def progress(self, text: str) -> None:
        self._app._entry(self._id, "progress", text)

    def question(self, text: str, choices: list[str]) -> None:
        self._app._entry(self._id, "question", text, choices=choices)
        self._app._set(self._id, state="waiting")

    def confirm_request(self, kind: str, text: str, data: dict) -> None:
        self.confirming = True
        self._app._entry(self._id, kind, text, choices=PROPOSAL_CHOICES, data=data)
        self._app._set(self._id, state="waiting")

    def answered(self) -> None:
        self.confirming = False
        self._app._set(self._id, state="working")

    def task_changed(self) -> None:
        self._app._set(self._id)

    def entry_added(self, entry: dict) -> None:
        self._app._post({"type": "entry", "task_id": self._id, "entry": entry})

    def schedule_changed(self) -> None:
        schedule = self._app._store.get_schedule(self._id)
        if schedule is not None:
            self._app._post({"type": "schedule", "schedule": self._app._schedule_view(schedule)})

    async def start_task(self, text: str) -> dict | None:
        return await self._app._new_task(text)

    def finished(self, result_text: str, is_error: bool) -> None:
        self._app._finish(self._id, result_text, is_error)

    def session(self, session_id: str) -> None:
        self._app._store.update_task(self._id, session_id=session_id)

    def rate_limit(self, info: dict) -> None:
        kind = info.get("type")
        if kind is None:
            log.warning("작업 %d: 종류 없는 사용량 이벤트를 버림", self._id)
            return
        self._app._limits[kind] = {**info, "received_at": _iso(_now())}
        self._app._post(self._app._usage())


class App:
    def __init__(self, store: Store, emit: Emit, auth: Auth, new_run=AgentRun):
        self._store = store
        self._emit = emit
        self._auth = auth
        self._new_run = new_run
        self._runs: dict[int, tuple[AgentRun, _Events, asyncio.Task]] = {}
        self._limits: dict[str, dict] = {}  # 한도 종류별 마지막 값
        # 세션 이벤트는 동기 콜백이라 보낼 메시지를 줄 세워 순서대로 보낸다
        self._outbox: deque[dict] = deque()
        self._sender: asyncio.Task | None = None
        self._logging_in = False  # 로그인 창이 떠 있는 동안 또 띄우지 않는다

    # --- 화면 메시지 ---
    async def connected(self, on: bool) -> None:
        if on:
            await self._send({"type": "status", "logged_in": await self._auth.logged_in()})
            chat = self._store.chat_task()
            if chat is not None:
                await self._send({"type": "task", "task": chat})

    async def login(self) -> None:
        if self._logging_in:
            log.info("로그인이 이미 진행 중이라 무시함")
            return
        self._logging_in = True
        try:
            ok = await self._auth.login()
        finally:
            self._logging_in = False
        await self._send({"type": "status", "logged_in": ok})

    async def request(self, text: str) -> None:
        await self._new_task(text)

    async def add_schedule(self, name: str, rule: dict, instruction: str) -> None:
        """양식으로 바로 저장한다 (확인 없음). 세션은 첫 실행 때 연다."""
        if not self._valid_rule(rule):
            return
        task = self._store.create_task("schedule", name)
        task = self._store.update_task(task["id"], state="done", seen=True)
        schedule = self._store.create_schedule(task["id"], name, rule, instruction)
        self._post({"type": "task", "task": task})
        await self._send({"type": "schedule", "schedule": self._schedule_view(schedule)})

    async def say(self, task_id: int, text: str) -> None:
        task = self._store.get_task(task_id)
        if task is None:
            log.warning("없는 작업에 말함: %d", task_id)
            return
        if not await self._logged_in():
            return
        self._entry(task_id, "user", text)
        if task_id in self._runs and task["state"] in ("working", "waiting"):
            await self._runs[task_id][0].say(text)
        else:
            # 끝나거나 멈춘 작업에 다시 말하면 그 세션을 이어 되묻는다 (끝나는 중인 세션은 버린다)
            self._set(task_id, state="working")
            self._start(task_id, text, resume=task["session_id"])
        await self._flush()

    async def stop(self, task_id: int) -> None:
        if task_id not in self._runs:
            log.warning("돌고 있지 않은 작업을 멈추려 함: %d", task_id)
            return
        run = self._runs[task_id][0]
        self._set(task_id, state="stopped")
        await run.stop()
        await self._flush()

    async def seen(self, task_id: int) -> None:
        if self._store.get_task(task_id) is None:
            return
        self._set(task_id, seen=True)
        await self._flush()

    async def list_tasks(self, page: int, view: str) -> None:
        if view not in VIEWS:
            log.warning("모르는 목록: %s", view)
            return
        items, pages = self._store.list_tasks(page, view)
        await self._send({"type": "tasks", "view": view, "page": page, "pages": pages, "items": items})

    async def get_task(self, task_id: int) -> None:
        task = self._store.get_task(task_id)
        if task is None:
            log.warning("없는 작업을 열려 함: %d", task_id)
            return
        schedule = self._store.get_schedule(task_id)
        await self._send({"type": "task_detail", "task": task, "entries": self._store.entries(task_id),
                          "schedule": self._schedule_view(schedule) if schedule else None})

    async def list_schedules(self, page: int) -> None:
        schedules, pages = self._store.list_schedules(page)
        items = []
        for s in schedules:
            v = self._schedule_view(s)
            if self._store.get_task(s["task_id"])["state"] in ("working", "waiting"):
                state = "running"
            else:
                state = "next" if s["enabled"] else "off"
            items.append({k: v[k] for k in ("task_id", "name", "label", "next_run")} | {"state": state})
        await self._send({"type": "schedules", "page": page, "pages": pages, "items": items})

    async def set_schedule(self, task_id: int, name: str, rule: dict, instruction: str) -> None:
        if not self._valid_rule(rule):
            return
        values = {"name": name, "rule": rule, "instruction": instruction}
        held = self._runs.get(task_id)
        if held and held[1].confirming:
            # 등록 확인의 [고치기]: 저장은 기다리던 도구가 한다. 사용자 답이라 user 줄을 남긴다 (지시는 길어 뺀다)
            self._entry(task_id, "user", f"고쳐서 등록: {name} ({label(rule)})")
            held[0].answer(values)
            await self._flush()
            return
        current = self._store.get_schedule(task_id)
        if current is None:
            log.warning("스케줄이 없는 작업을 고치려 함: %d", task_id)
            return
        text = edit_text(current, values)
        if text is None:
            return
        schedule = self._store.update_schedule(task_id, **values)
        self._entry(task_id, "edit", text)
        self._post({"type": "schedule", "schedule": self._schedule_view(schedule)})
        await self._flush()

    async def set_schedule_enabled(self, task_id: int, enabled: bool) -> None:
        if self._store.get_schedule(task_id) is None:
            log.warning("스케줄이 없는 작업을 켜고 끄려 함: %d", task_id)
            return
        schedule = self._store.update_schedule(task_id, enabled=enabled)
        await self._send({"type": "schedule", "schedule": self._schedule_view(schedule)})

    async def run_schedule(self, task_id: int, now: datetime) -> None:
        """스케줄 한 번 실행. 세션이 있으면 이어가고 없으면 새로 연다. 끝나면 last_run_at·last_result
        (끝난 작업의 상태 done/failed/stopped)를 기록하고 schedule 메시지를 보낸다."""
        task = self._store.get_task(task_id)
        if task is None or self._store.get_schedule(task_id) is None:
            log.warning("없는 스케줄을 실행하려 함: %d", task_id)
            return
        if task["state"] in ("working", "waiting"):
            log.info("스케줄 %d: 아직 실행 중이라 건너뜀", task_id)
            return
        if not await self._auth.logged_in():
            log.warning("스케줄 %d: 로그아웃 상태라 이번 실행을 건너뜀", task_id)
            return
        when = f"{now:%m/%d} ({'월화수목금토일'[now.weekday()]}) {now:%H:%M}"
        self._entry(task_id, "run", f"{when} 실행")
        self._set(task_id, state="working")
        if self._start(task_id, f"[스케줄 실행 · {when}] get_schedule로 지금 작업 지시서를 읽고 그대로 한 번 실행해.",
                       resume=task["session_id"]):
            self._runs[task_id][2].add_done_callback(lambda _: self._schedule_ran(task_id, now))
        await self._flush()

    def _schedule_ran(self, task_id: int, now: datetime) -> None:
        if task_id in self._runs:
            # 끝난 실행은 _drive가 이미 뺐다. 남아 있으면 멈춘 뒤 새로 시작한 실행이 도는 중이다
            log.info("스케줄 %d: 새 실행이 도는 중이라 지난 실행 결과를 기록하지 않음", task_id)
            return
        task = self._store.get_task(task_id)
        if task is None or self._store.get_schedule(task_id) is None:
            log.warning("스케줄 %d: 끝났지만 작업이나 스케줄이 없어 결과를 기록하지 않음", task_id)
            return
        schedule = self._store.update_schedule(task_id, last_run_at=_iso(now), last_result=task["state"])
        self._post({"type": "schedule", "schedule": self._schedule_view(schedule)})

    async def get_settings(self) -> None:
        await self._send({"type": "settings", "permission_mode": self._permission_mode()})

    async def set_permission_mode(self, mode: str) -> None:
        if mode not in PERMISSION_MODES:
            log.warning("모르는 권한 모드: %s", mode)
            return
        self._store.set_setting("permission_mode", mode)
        await self.get_settings()

    async def get_usage(self) -> None:
        await self._send(self._usage())

    async def startup(self) -> None:
        """앱이 꺼지며 끊긴 세션의 작업을 실패로 닫는다. 대화 작업이 없으면 만든다 (하나뿐, 0033).
        대화 작업이 실패로 닫혀도 다음 say가 저장된 세션을 이어 쓴다."""
        for task in self._store.tasks_in_states("working", "waiting"):
            self._store.add_entry(task["id"], "failure", "앱이 꺼져서 멈췄어요")
            self._store.update_task(task["id"], state="failed", seen=False)
        if self._store.chat_task() is None:
            chat = self._store.create_task("chat", CHAT_TITLE)
            self._store.update_task(chat["id"], state="done", seen=True)

    # --- 세션 ---
    async def _new_task(self, text: str) -> dict | None:
        """사용자 작업을 만들어 돌린다 (작업 탭 입력칸, 대화의 create_task). 로그아웃이면 None."""
        if not await self._logged_in():
            return None
        task = self._store.create_task("user", text[:TITLE_LEN])
        self._post({"type": "task", "task": task})
        self._entry(task["id"], "user", text)
        self._start(task["id"], text, resume=None)
        await self._flush()
        return self._store.get_task(task["id"])

    async def _logged_in(self) -> bool:
        """로그아웃이면 status를 다시 보내 화면이 로그인 요청을 띄우게 한다."""
        if await self._auth.logged_in():
            return True
        await self._send({"type": "status", "logged_in": False})
        return False

    def _start(self, task_id: int, prompt: str, resume: str | None) -> bool:
        """세션을 띄운다. 준비하다 실패하면 작업을 실패로 끝내고 False."""
        events = _Events(self, task_id)
        try:
            run = self._new_run(task_id, events)
            options = build_options(permission_mode=self._permission_mode(), can_use_tool=run.can_use_tool,
                                    mcp_servers={"assistant": backend_server(self._store, run)}, resume=resume)
        except Exception as e:
            log.error("작업 %d: 세션을 준비하지 못했다 (%s)", task_id, type(e).__name__)
            self._finish(task_id, "작업을 실행하지 못했어요", True)
            return False
        job = asyncio.create_task(self._drive(task_id, run, prompt, options))
        self._runs[task_id] = (run, events, job)
        log.info("작업 %d: 세션 시작 (이어가기 %s)", task_id, resume is not None)
        return True

    async def _drive(self, task_id: int, run, prompt: str, options) -> None:
        try:
            await run.run(prompt, options)
        except Exception as e:
            log.error("작업 %d: 세션이 예외로 끝났다 (%s)", task_id, type(e).__name__)  # 트레이스백엔 사용자 내용이 섞일 수 있다
            if self._store.get_task(task_id)["state"] in ("working", "waiting"):  # 이미 끝났으면 실패 줄을 또 쓰지 않는다
                self._finish(task_id, "작업을 실행하지 못했어요", True)
        finally:
            if self._runs.get(task_id, (None,))[0] is run:
                del self._runs[task_id]

    def _finish(self, task_id: int, text: str, is_error: bool) -> None:
        if self._store.get_task(task_id)["state"] == "stopped":
            return  # 멈춘 뒤 늦게 온 끝은 버린다
        self._entry(task_id, "failure" if is_error else "result", text)
        self._set(task_id, state="failed" if is_error else "done", seen=False)

    # --- 저장과 알림 ---
    def _entry(self, task_id: int, kind: str, text: str, **extra) -> None:
        entry = self._store.add_entry(task_id, kind, text, **extra)
        self._post({"type": "entry", "task_id": task_id, "entry": entry})

    def _set(self, task_id: int, **fields) -> None:
        self._post({"type": "task", "task": self._store.update_task(task_id, **fields)})

    @staticmethod
    def _valid_rule(rule) -> bool:
        try:
            validate(rule)
        except (ValueError, TypeError, AttributeError) as e:
            log.warning("잘못된 스케줄 규칙 (%s)", type(e).__name__)
            return False
        return True

    def _permission_mode(self) -> str:
        return self._store.get_setting("permission_mode", "default")

    def _usage(self) -> dict:
        return {"type": "usage", "limits": [
            {k: v.get(k) for k in ("type", "utilization", "resets_at", "received_at")} for v in self._limits.values()]}

    def _schedule_view(self, s: dict) -> dict:
        return {**{k: s[k] for k in ("task_id", "name", "rule", "instruction", "enabled", "last_run_at",
                                     "last_result")},
                "label": label(s["rule"]),
                "next_run": _iso(next_run(s["rule"], _now())) if s["enabled"] else None}

    # --- 보내기: 한 줄로 순서대로 ---
    def _post(self, msg: dict) -> None:
        self._outbox.append(msg)
        if self._sender is None or self._sender.done():
            self._sender = asyncio.create_task(self._drain())

    async def _send(self, msg: dict) -> None:
        self._post(msg)
        await self._flush()

    async def _flush(self) -> None:
        """줄 선 메시지가 다 나갈 때까지 기다린다. 부른 쪽이 취소돼도 보내기는 멈추지 않는다."""
        if self._sender is not None:
            await asyncio.shield(self._sender)

    async def _drain(self) -> None:
        while self._outbox:
            msg = self._outbox.popleft()
            try:
                await self._emit(msg)
            except Exception as e:
                log.warning("메시지 보내기 실패: %s (%s)", msg["type"], type(e).__name__)
