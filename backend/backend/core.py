"""세션 관리: 화면 메시지마다 메서드 하나. 세션 하나 = Claude Code 세션 하나를 백그라운드로 돌리고,
Claude Code 세션에서 일어난 일을 대화 줄·상태로 저장해 화면에 보낸다. 전송 방식과 화면을 모른다."""
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
# 먼저 말 걸기 (docs/superpowers/specs/2026-10-22-proactive-help-design.md)
NUDGE_TEXT = "도움이 필요해?"
NUDGE_CHOICES = ["도와줘", "괜찮아"]
HELP_PROMPT = ("[먼저 말 걸기] 사용자가 {app} · {window}에서 막힌 것 같아 도움을 청했다. "
               "최근 화면 기록을 찾아보고 의견이나 해결 방법을 두세 문장으로 짧게 말해.")


class Auth(Protocol):
    async def logged_in(self) -> bool: ...
    async def login(self) -> bool: ...
    async def logout(self) -> None: ...


class Recorder(Protocol):
    async def start(self) -> None: ...
    def stop(self) -> None: ...


class Proactive(Protocol):
    """먼저 말 걸기의 판단 고리 (proactive.Proactive). 만들 때 App.proactive에 자기를 붙인다."""
    def current_task(self) -> tuple[str, str] | None: ...
    def decline(self, at: datetime, app: str, window: str) -> None: ...


def _now() -> datetime:
    return datetime.now().astimezone()


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


class _Events:
    """세션 하나의 RunEvents. Claude Code 세션 이벤트를 저장하고 화면에 알린다."""

    def __init__(self, app: "App", session_id: int):
        self._app = app
        self._id = session_id
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

    def session_changed(self) -> None:
        self._app._set(self._id)

    def entry_added(self, entry: dict) -> None:
        self._app._post({"type": "entry", "session_id": self._id, "entry": entry})

    def schedule_changed(self) -> None:
        schedule = self._app._store.get_schedule(self._id)
        if schedule is not None:
            self._app._post({"type": "schedule", "schedule": self._app._schedule_view(schedule)})

    async def start_session(self, source: str, fields: dict) -> dict | None:
        return await self._app._new_session(source, fields)

    def finished(self, result_text: str, is_error: bool) -> None:
        self._app._finish(self._id, result_text, is_error)

    def activity(self, kind: str, text: str) -> None:
        """지금 하는 일. 대화 기록에 남기지 않고 바로 보낸다."""
        if self._app._store.get_session(self._id) is not None:
            self._app._post({"type": "activity", "session_id": self._id, "kind": kind, "text": text})

    def claude_session(self, claude_session_id: str) -> None:
        self._app._store.update_session(self._id, claude_session_id=claude_session_id)

    def rate_limit(self, info: dict) -> None:
        kind = info.get("type")
        if kind is None:
            log.warning("세션 %d: 종류 없는 사용량 이벤트를 버림", self._id)
            return
        self._app._limits[kind] = {**info, "received_at": _iso(_now())}
        self._app._post(self._app._usage())


class App:
    def __init__(self, store: Store, emit: Emit, auth: Auth, recorder: Recorder, new_run=AgentRun):
        self._store = store
        self._emit = emit
        self._auth = auth
        self._recorder = recorder
        self._new_run = new_run
        self._runs: dict[int, tuple[AgentRun, _Events, asyncio.Task]] = {}
        self._limits: dict[str, dict] = {}  # 한도 종류별 마지막 값
        # 세션 이벤트는 동기 콜백이라 보낼 메시지를 줄 세워 순서대로 보낸다
        self._outbox: deque[dict] = deque()
        self._sender: asyncio.Task | None = None
        self._logging_in = False  # 로그인 창이 떠 있는 동안 또 띄우지 않는다
        self.proactive: Proactive | None = None
        self.nudge_active = False  # 먼저 말 걸기 배지가 떠 있다
        self.logged_in: bool | None = None  # 마지막으로 보낸 status의 로그인 상태 (보낸 적 없으면 None)
        # 질문·제안을 기다리는 대화 세션에 누른 [도와줘]: (세션 ID, 숨은 지시). 그 실행이 끝나면 이어 묻는다. 하나만 둔다
        self._help_later: tuple[int, str] | None = None

    # --- 화면 메시지 ---
    async def connected(self, on: bool) -> None:
        if on:
            await self._send({"type": "status", "logged_in": await self._auth.logged_in()})
            chat = self._store.chat_session()
            if chat is not None:
                await self._send({"type": "session", "session": chat})
            await self._send({"type": "nudge", "active": self.nudge_active})

    async def login(self) -> None:
        if self._logging_in:
            log.info("로그인이 이미 진행 중이라 무시함")
            return
        self._logging_in = True
        try:
            ok = await self._auth.login()
        except Exception as e:
            log.warning("로그인 실패: %s", type(e).__name__)  # 메시지에 사용자 정보가 있을 수 있어 종류만 적는다
            ok = False
        finally:
            self._logging_in = False
        await self._send({"type": "status", "logged_in": ok})

    async def logout(self) -> None:
        await self._auth.logout()
        await self._send({"type": "status", "logged_in": False})

    async def request(self, text: str) -> None:
        await self._new_task(text)

    async def add_schedule(self, name: str, rule: dict, instruction: str) -> None:
        """양식으로 바로 저장한다 (확인 없음). Claude Code 세션은 첫 실행 때 연다."""
        if not self._valid_rule(rule):
            return
        await self._new_schedule(name, rule, instruction)

    async def say(self, session_id: int, text: str, prompt: str | None = None) -> None:
        """text는 user 줄로 남긴다. prompt가 있으면 Claude에는 text 대신 prompt를 보낸다 (숨은 지시)."""
        session = self._store.get_session(session_id)
        if session is None:
            log.warning("없는 세션에 말함: %d", session_id)
            return
        if not await self._logged_in():
            return
        self._entry(session_id, "user", text)
        prompt = text if prompt is None else prompt
        if session_id in self._runs and session["state"] in ("working", "waiting"):
            await self._runs[session_id][0].say(prompt)
        else:
            # 끝나거나 멈춘 세션에 다시 말하면 그 Claude Code 세션을 이어 되묻는다 (끝나는 중인 세션은 버린다)
            self._set(session_id, state="working")
            self._start(session_id, prompt, resume=session["claude_session_id"])
        await self._flush()

    async def stop(self, session_id: int) -> None:
        if session_id not in self._runs:
            log.warning("돌고 있지 않은 세션을 멈추려 함: %d", session_id)
            return
        run = self._runs[session_id][0]
        self._drop_help_later(session_id)  # 사용자가 대화를 멈췄으니 미뤄 둔 [도와줘]도 버린다
        self._set(session_id, state="stopped")
        await run.stop()
        await self._flush()

    async def seen(self, session_id: int) -> None:
        if self._store.get_session(session_id) is None:
            return
        self._set(session_id, seen=True)
        await self._flush()

    async def list_sessions(self, page: int, view: str) -> None:
        if view not in VIEWS:
            log.warning("모르는 목록: %s", view)
            return
        items, pages = self._store.list_sessions(page, view)
        await self._send({"type": "sessions", "view": view, "page": page, "pages": pages, "items": items})

    async def get_session(self, session_id: int) -> None:
        session = self._store.get_session(session_id)
        if session is None:
            # 지운 세션의 칩을 눌렀을 때. 화면이 목록으로 돌아가게 지웠다고 답한다
            await self._send({"type": "session_deleted", "session_id": session_id})
            return
        schedule = self._store.get_schedule(session_id)
        await self._send({"type": "session_detail", "session": session, "entries": self._store.entries(session_id),
                          "schedule": self._schedule_view(schedule) if schedule else None})

    async def delete_session(self, session_id: int) -> None:
        """돌거나 답을 기다리면 먼저 멈추고 지운다. 대화 세션을 지우면 새 대화 세션을 만든다 (대화 세션은 늘 하나)."""
        session = self._store.get_session(session_id)
        if session is not None:
            # 멈추기를 기다리는 사이 실행이 끝나도 미뤄 둔 [도와줘]가 지울 세션에서 돌지 않게 먼저 버린다
            self._drop_help_later(session_id)
            held = self._runs.get(session_id)
            if held is not None:
                await held[0].stop()  # 기다리던 답은 "거부"로 풀고 Claude Code 세션을 끊는다
            self._store.delete_session(session_id)  # 뒤에 오는 이벤트는 세션이 없어 버려진다
            log.info("세션 %d: 지움", session_id)
        self._post({"type": "session_deleted", "session_id": session_id})
        if session is not None and session["source"] == "chat":
            self._post({"type": "session", "session": self._new_chat()})
        await self._flush()

    async def list_schedules(self, page: int) -> None:
        schedules, pages = self._store.list_schedules(page)
        items = []
        for s in schedules:
            v = self._schedule_view(s)
            if self._store.get_session(s["session_id"])["state"] in ("working", "waiting"):
                state = "running"
            else:
                state = "next" if s["enabled"] else "off"
            items.append({k: v[k] for k in ("session_id", "name", "label", "next_run")} | {"state": state})
        await self._send({"type": "schedules", "page": page, "pages": pages, "items": items})

    async def set_schedule(self, session_id: int, name: str, rule: dict, instruction: str) -> None:
        if not self._valid_rule(rule):
            return
        values = {"name": name, "rule": rule, "instruction": instruction}
        held = self._runs.get(session_id)
        if held and held[1].confirming:
            # 등록 확인의 [고치기]: 저장은 기다리던 도구가 한다. 사용자 답이라 user 줄을 남긴다 (지시는 길어 뺀다)
            self._entry(session_id, "user", f"고쳐서 등록: {name} ({label(rule)})")
            held[0].answer(values)
            await self._flush()
            return
        current = self._store.get_schedule(session_id)
        if current is None:
            log.warning("스케줄이 없는 세션을 고치려 함: %d", session_id)
            return
        text = edit_text(current, values)
        if text is None:
            return
        schedule = self._store.update_schedule(session_id, **values)
        self._entry(session_id, "edit", text)
        self._post({"type": "schedule", "schedule": self._schedule_view(schedule)})
        await self._flush()

    async def set_schedule_enabled(self, session_id: int, enabled: bool) -> None:
        if self._store.get_schedule(session_id) is None:
            log.warning("스케줄이 없는 세션을 켜고 끄려 함: %d", session_id)
            return
        schedule = self._store.update_schedule(session_id, enabled=enabled)
        await self._send({"type": "schedule", "schedule": self._schedule_view(schedule)})

    async def run_schedule(self, session_id: int, now: datetime) -> None:
        """스케줄 한 번 실행. Claude Code 세션이 있으면 이어가고 없으면 새로 연다. 끝나면 last_run_at·last_result
        (끝난 세션의 상태 done/failed/stopped)를 기록하고 schedule 메시지를 보낸다."""
        session = self._store.get_session(session_id)
        if session is None or self._store.get_schedule(session_id) is None:
            log.warning("없는 스케줄을 실행하려 함: %d", session_id)
            return
        if session["state"] in ("working", "waiting"):
            log.info("스케줄 %d: 아직 실행 중이라 건너뜀", session_id)
            return
        if not await self._auth.logged_in():
            log.warning("스케줄 %d: 로그아웃 상태라 이번 실행을 건너뜀", session_id)
            return
        when = f"{now:%m/%d} ({'월화수목금토일'[now.weekday()]}) {now:%H:%M}"
        self._entry(session_id, "run", f"{when} 실행")
        self._set(session_id, state="working")
        if self._start(session_id, f"[스케줄 실행 · {when}] get_schedule로 지금 작업 지시서를 읽고 그대로 한 번 실행해.",
                       resume=session["claude_session_id"]):
            self._runs[session_id][2].add_done_callback(lambda _: self._schedule_ran(session_id, now))
        await self._flush()

    def _schedule_ran(self, session_id: int, now: datetime) -> None:
        if session_id in self._runs:
            # 끝난 실행은 _drive가 이미 뺐다. 남아 있으면 멈춘 뒤 새로 시작한 실행이 도는 중이다
            log.info("스케줄 %d: 새 실행이 도는 중이라 지난 실행 결과를 기록하지 않음", session_id)
            return
        session = self._store.get_session(session_id)
        if session is None or self._store.get_schedule(session_id) is None:
            log.warning("스케줄 %d: 끝났지만 세션이나 스케줄이 없어 결과를 기록하지 않음", session_id)
            return
        schedule = self._store.update_schedule(session_id, last_run_at=_iso(now), last_result=session["state"])
        self._post({"type": "schedule", "schedule": self._schedule_view(schedule)})

    async def get_settings(self) -> None:
        await self._send({"type": "settings", "permission_mode": self._permission_mode(),
                          "recording": self.recording_enabled(), "jev_key_set": bool(self.jev_key())})

    async def set_permission_mode(self, mode: str) -> None:
        if mode not in PERMISSION_MODES:
            log.warning("모르는 권한 모드: %s", mode)
            return
        self._store.set_setting("permission_mode", mode)
        await self.get_settings()

    async def set_recording(self, enabled: bool) -> None:
        self._store.set_setting("recording", "on" if enabled else "off")
        if enabled:
            await self._recorder.start()
        else:
            self._recorder.stop()
        await self.get_settings()

    def recording_enabled(self) -> bool:
        return self._store.get_setting("recording", "on") == "on"

    async def set_jev_key(self, key: str) -> None:
        """빈 값이면 키를 지운다. 화면에는 키 원문을 다시 보내지 않는다 (jev_key_set만)."""
        self._store.set_setting("jev_key", key.strip())
        await self.get_settings()

    def jev_key(self) -> str:
        return self._store.get_setting("jev_key", "")

    # --- 먼저 말 걸기 ---
    async def set_nudge(self, active: bool) -> None:
        """배지를 켜고 끈다. 켜기 직전에만 로그인을 확인한다(CLI라 느려서 판단마다 하지 않는다)."""
        if active and not await self._auth.logged_in():
            log.info("로그아웃 상태라 배지를 켜지 않음")
            return
        self.nudge_active = active
        if active:
            log.info("배지 켬")
        await self._send({"type": "nudge", "active": active})

    async def nudge_open(self) -> None:
        """배지 누름: 대화 세션에 물음 줄을 남기고 배지를 끈다. 그새 배지가 꺼졌으면 무시한다."""
        task = self.proactive.current_task() if self.proactive else None
        if not self.nudge_active or task is None:
            log.info("배지가 꺼져 있어 배지 누름을 무시함")
            return
        chat = self._store.chat_session()
        if chat is None:
            chat = self._new_chat()
            self._post({"type": "session", "session": chat})
        self._entry(chat["id"], "nudge", NUDGE_TEXT, choices=NUDGE_CHOICES, data={"app": task[0], "window": task[1]})
        await self.set_nudge(False)

    async def nudge_answer(self, help: bool) -> None:
        """[도와줘]·[괜찮아]. 대화 세션의 마지막 nudge 줄 뒤에 user 줄이 없을 때만 받는다 (한 번만).
        [도와줘]는 대화 세션이 질문·제안의 답을 기다리는 중이면 그 답으로 쓰지 않고, 그 실행이 끝난 뒤 이어 묻는다."""
        chat = self._store.chat_session()
        nudge = self._unanswered_nudge(chat)
        if nudge is None:
            log.info("답할 nudge가 없어 무시함")
            return
        data = nudge["data"]
        if help:
            prompt = HELP_PROMPT.format(**data)
            if chat["state"] == "waiting" and chat["id"] in self._runs:
                if not await self._logged_in():
                    return
                self._entry(chat["id"], "user", NUDGE_CHOICES[0])
                self._help_later = (chat["id"], prompt)
                await self._flush()
                return
            await self.say(chat["id"], NUDGE_CHOICES[0], prompt=prompt)
            return
        self._entry(chat["id"], "user", NUDGE_CHOICES[1])
        if self.proactive:
            self.proactive.decline(_now(), data["app"], data["window"])
        await self._flush()

    def _unanswered_nudge(self, chat: dict | None) -> dict | None:
        """대화 세션의 마지막 nudge 줄. 그 뒤에 user 줄이 있으면(이미 답함) None."""
        entries = self._store.entries(chat["id"]) if chat else []
        last = next((i for i in range(len(entries) - 1, -1, -1) if entries[i]["kind"] == "nudge"), None)
        if last is None or any(e["kind"] == "user" for e in entries[last + 1:]):
            return None
        return entries[last]

    def chatting(self) -> bool:
        """대화 중: 답하지 않은 "도움이 필요해?"가 있거나 대화 세션이 답을 쓰거나 기다린다 (판단 고리가 쉰다)."""
        chat = self._store.chat_session()
        if chat is None:
            return False
        return chat["state"] in ("working", "waiting") or self._unanswered_nudge(chat) is not None

    async def get_usage(self) -> None:
        await self._send(self._usage())

    async def startup(self) -> None:
        """앱이 꺼지며 끊긴 세션을 실패로 닫는다 (대화 세션은 done으로만 되돌린다).
        대화 세션이 없으면 만든다 (하나뿐, 0033). 다음 say가 저장된 Claude Code 세션을 이어 쓴다. 화면 기록이 켜져 있으면 screenpipe를 띄운다."""
        for session in self._store.sessions_in_states("working", "waiting"):
            if session["source"] == "chat":
                self._store.update_session(session["id"], state="done")  # 대화는 실패로 알리지 않는다
                continue
            self._store.add_entry(session["id"], "failure", "앱이 꺼져서 멈췄어요")
            self._store.update_session(session["id"], state="failed", seen=False)
        if self._store.chat_session() is None:
            self._new_chat()
        if self.recording_enabled():
            await self._recorder.start()

    # --- 세션 ---
    def _new_chat(self) -> dict:
        """대화 세션을 만든다. 돌지 않고 첫 say를 기다린다."""
        chat = self._store.create_session("chat", CHAT_TITLE)
        return self._store.update_session(chat["id"], state="done", seen=True)

    async def _new_session(self, source: str, fields: dict) -> dict | None:
        """에이전트의 create_session. 어느 세션에서 불렀든 같은 길로 만든다."""
        if source == "user":
            return await self._new_task(fields["text"])
        return await self._new_schedule(fields["name"], fields["rule"], fields["instruction"])

    async def _new_schedule(self, name: str, rule: dict, instruction: str) -> dict:
        """스케줄 세션을 만든다. 돌지 않고 다음 실행 시각을 기다린다 (스케줄 탭 양식, create_session)."""
        session = self._store.create_session("schedule", name)
        session = self._store.update_session(session["id"], state="done", seen=True)
        schedule = self._store.create_schedule(session["id"], name, rule, instruction)
        self._post({"type": "session", "session": session})
        await self._send({"type": "schedule", "schedule": self._schedule_view(schedule)})
        return session

    async def _new_task(self, text: str) -> dict | None:
        """작업 세션을 만들어 돌린다 (작업 탭 입력칸, create_session). 로그아웃이면 None."""
        if not await self._logged_in():
            return None
        task = self._store.create_session("user", text[:TITLE_LEN])
        self._post({"type": "session", "session": task})
        self._entry(task["id"], "user", text)
        self._start(task["id"], text, resume=None)
        await self._flush()
        return self._store.get_session(task["id"])

    async def _logged_in(self) -> bool:
        """로그아웃이면 status를 다시 보내 화면이 로그인 요청을 띄우게 한다."""
        if await self._auth.logged_in():
            return True
        await self._send({"type": "status", "logged_in": False})
        return False

    def _start(self, session_id: int, prompt: str, resume: str | None) -> bool:
        """Claude Code 세션을 띄운다. 준비하다 실패하면 세션을 실패로 끝내고 False.
        로그인 확인을 기다리는 사이 세션이 지워졌으면 띄우지 않고 False."""
        if self._store.get_session(session_id) is None:
            log.info("세션 %d: 지워져서 Claude Code 세션을 띄우지 않음", session_id)
            return False
        events = _Events(self, session_id)
        try:
            run = self._new_run(session_id, events)
            options = build_options(permission_mode=self._permission_mode(), can_use_tool=run.can_use_tool,
                                    mcp_servers={"assistant": backend_server(self._store, run)}, resume=resume)
        except Exception as e:
            log.error("세션 %d: Claude Code 세션을 준비하지 못했다 (%s)", session_id, type(e).__name__)
            self._finish(session_id, "작업을 실행하지 못했어요", True)
            return False
        job = asyncio.create_task(self._drive(session_id, run, prompt, options))
        self._runs[session_id] = (run, events, job)
        log.info("세션 %d: Claude Code 세션 시작 (이어가기 %s)", session_id, resume is not None)
        return True

    async def _drive(self, session_id: int, run, prompt: str, options) -> None:
        try:
            await run.run(prompt, options)
        except Exception as e:
            log.error("세션 %d: Claude Code 세션이 예외로 끝났다 (%s)", session_id, type(e).__name__)  # 트레이스백엔 사용자 내용이 섞일 수 있다
            session = self._store.get_session(session_id)
            if session is not None and session["state"] in ("working", "waiting"):  # 이미 끝났거나 지웠으면 쓰지 않는다
                self._finish(session_id, "작업을 실행하지 못했어요", True)
        finally:
            if self._runs.get(session_id, (None,))[0] is run:
                del self._runs[session_id]
                self._start_help_later(session_id)

    def _drop_help_later(self, session_id: int) -> None:
        if self._help_later is not None and self._help_later[0] == session_id:
            self._help_later = None

    def _start_help_later(self, session_id: int) -> None:
        """미뤄 둔 [도와줘]를 끝난 세션에 이어 묻는다 (끝난 세션에 say처럼). 세션을 지웠으면 버린다."""
        if self._help_later is None or self._help_later[0] != session_id:
            return
        prompt = self._help_later[1]
        self._help_later = None
        session = self._store.get_session(session_id)
        if session is None:
            return
        self._set(session_id, state="working")
        self._start(session_id, prompt, resume=session["claude_session_id"])

    def _finish(self, session_id: int, text: str, is_error: bool) -> None:
        session = self._store.get_session(session_id)
        if session is None or session["state"] == "stopped":
            return  # 지우거나 멈춘 뒤 늦게 온 끝은 버린다
        self._entry(session_id, "failure" if is_error else "result", text)
        self._set(session_id, state="failed" if is_error else "done", seen=False)

    # --- 저장과 알림 (지운 세션에는 쓰지 않는다) ---
    def _entry(self, session_id: int, kind: str, text: str, **extra) -> None:
        if self._store.get_session(session_id) is None:
            return
        entry = self._store.add_entry(session_id, kind, text, **extra)
        self._post({"type": "entry", "session_id": session_id, "entry": entry})

    def _set(self, session_id: int, **fields) -> None:
        if self._store.get_session(session_id) is None:
            return
        self._post({"type": "session", "session": self._store.update_session(session_id, **fields)})

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
        return {**{k: s[k] for k in ("session_id", "name", "rule", "instruction", "enabled", "last_run_at",
                                     "last_result")},
                "label": label(s["rule"]),
                "next_run": _iso(next_run(s["rule"], _now())) if s["enabled"] else None}

    # --- 보내기: 한 줄로 순서대로 ---
    def _post(self, msg: dict) -> None:
        if msg["type"] == "status":
            self.logged_in = msg["logged_in"]
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
