"""두뇌 핵심: 화면이 보낸 Signal을 받아 Reaction을 낸다. 전송 방식과 화면을 모른다 (두뇌 스펙 2·4·5절)."""
import asyncio
import logging
import time
from datetime import datetime
from typing import Awaitable, Callable

from .clients import AuthError, CallError, Jev, Talker
from .memory import History
from .persona import dialogue_prompt, system_instruction, trim_line
from .questions import ACTIONS, EMOTIONS, SITUATIONS, jev_state
from .tuning import Tuning

log = logging.getLogger(__name__)

Emit = Callable[[dict], Awaitable[None]]
MakeClients = Callable[[dict[str, str | None]], tuple[Jev, Talker]]


class Brain:
    def __init__(self, *, emit: Emit, make_clients: MakeClients, history: History,
                 clock: Callable[[], float] = time.time, tuning: Tuning = Tuning()):
        self._emit = emit
        self._make_clients = make_clients
        self._history = history
        self._clock = clock
        self._t = tuning
        self._jev: Jev | None = None
        self._talker: Talker | None = None
        self._ai = "no_keys"                  # ok / no_keys / bad_key
        self._connected = False
        self._in_house = False                # 화면이 따로 알리기 전에는 집 밖, 사용자 있음으로 본다
        self._away = False
        self._house_away_s: float | None = None
        self._typing = ""
        self._typing_at_call = ""             # 마지막 타이핑 판단 때의 글. 새 글자 수(K)를 여기서부터 센다
        self._last_typing_at: float | None = None
        self._typing_pending = False          # 마지막 타이핑 판단 뒤로 글이 바뀌었는가
        self._emotion = "calm"
        self._action = "none"
        self._consecutive = 0                 # 사용자 입력 없이 강아지가 연달아 말한 횟수
        self._unread = False
        self._failures = 0                    # Jev 연속 실패 횟수 (조용함 주기 백오프)
        self._last_call_at = clock()
        self._last_interaction_at = float("-inf")
        self._due: str | None = None          # 다음 tick에 바로 할 판단 (강아지가 방금 말함)
        self._task: asyncio.Task | None = None
        self._phase: str | None = None        # 진행 중인 판단의 단계: judging / speaking
        self._situation: str | None = None    # 진행 중인 판단의 상황

    # ---- 화면 연결과 설정 ----

    async def connected(self, on: bool) -> None:
        self._connected = on
        if on:
            await self._emit({"type": "status", "ai": self._ai})
        else:
            self._cancel()

    async def set_keys(self, keys: dict[str, str | None]) -> None:
        await self._close_clients()
        if all(keys.get(name) for name in ("typesafe", "gemini")):
            self._jev, self._talker = self._make_clients(keys)
            await self._set_ai("ok")
        else:
            await self._set_ai("no_keys")

    async def clear_history(self) -> None:
        self._history.clear()

    async def aclose(self) -> None:
        self._cancel()
        await self._close_clients()

    # ---- 신호 ----

    async def handle(self, signal: dict) -> None:
        kind = signal.get("kind")
        now = self._clock()
        if kind == "typing":
            self._typing = str(signal.get("text", ""))
            self._last_typing_at = now
            self._typing_pending = True
            if abs(len(self._typing) - len(self._typing_at_call)) >= self._t.typing_chars:
                self._start("typing")
        elif kind == "sent":
            text = str(signal.get("text", "")).strip()
            if not text:
                return
            self._history.add("user", text, now)
            self._typing, self._typing_at_call, self._typing_pending = "", "", False
            self._consecutive = 0
            self._due = None
            self._start("sent", cancel=True)
        elif kind == "house":
            if signal.get("inside"):
                self._in_house = True
                self._due = None
                self._cancel()  # 만들던 대사도 버린다
            elif self._in_house:  # 이미 집 밖인 줄 알면(다시 연결할 때 화면이 다시 알림) 판단하지 않는다
                self._in_house = False
                self._house_away_s = float(signal.get("awayMs", 0)) / 1000
                self._start("house_out")
        elif kind == "bubble_seen":
            self._unread = False
        elif kind == "user_away":
            self._away = True
        elif kind == "user_return":
            if self._away:
                self._away = False
                self._start("user_return")
        elif kind == "interaction":
            situation = f"interaction:{signal.get('type')}"
            if situation not in SITUATIONS:
                log.warning("모르는 상호작용: %s", signal.get("type"))
                return
            if now - self._last_interaction_at < self._t.interaction_min_gap_s:
                return
            if self._start(situation):
                self._last_interaction_at = now
        else:
            log.warning("모르는 signal 종류: %s", kind)

    # ---- 스케줄러 ----

    async def tick(self) -> None:
        """주기적으로 불러 시간에 따른 트리거(타이핑 멈춤, 방금 말함, 조용함)를 확인한다."""
        now = self._clock()
        if (self._typing_pending and self._last_typing_at is not None
                and now - self._last_typing_at >= self._t.typing_pause_s):
            self._start("typing")  # 대사를 만드는 중이면 건너뛰고 다음 tick에 다시 본다
        if self._due and self._start(self._due):
            self._due = None
        base = self._t.quiet_away_s if self._away else self._t.quiet_active_s
        period = max(base, min(base * 2 ** min(self._failures, 10), self._t.backoff_max_s))
        if now - self._last_call_at >= period:
            self._start("quiet")

    async def run_ticker(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(self._t.tick_s)

    async def drain(self) -> None:
        """진행 중인 판단이 끝날 때까지 기다린다 (테스트·종료용)."""
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)

    # ---- 판단 ----

    def _busy(self) -> bool:
        return self._task is not None and not self._task.done()

    def _cancel(self) -> None:
        if self._busy():
            self._task.cancel()
        self._task = None
        self._phase = None

    def _start(self, situation: str, cancel: bool = False) -> bool:
        if not self._connected or self._in_house or self._ai != "ok":
            return False
        if situation == "typing" and not self._typing.strip():
            self._typing_pending = False  # 다 지웠으면 타이핑 판단을 하지 않는다
            return False
        if self._busy():
            # 타이핑은 Jev 단계의 판단만 새 글로 바꾼다. 보낸 말에 대한 답은 버리지 않는다 (스펙 5절 3)
            if cancel or (situation == "typing" and self._phase == "judging" and self._situation != "sent"):
                self._cancel()
            else:
                return False
        if situation == "typing":
            self._typing_pending = False
            self._typing_at_call = self._typing
        self._last_call_at = self._clock()
        self._phase = "judging"
        self._situation = situation
        self._task = asyncio.create_task(self._run(situation))
        return True

    async def _run(self, situation: str) -> None:
        try:
            await self._judge_and_speak(situation)
        finally:
            if asyncio.current_task() is self._task:
                self._phase = None

    async def _judge_and_speak(self, situation: str) -> None:
        assert self._jev is not None and self._talker is not None
        now = self._clock()
        last = self._history.last_ts()
        state = jev_state(
            situation=situation, now=datetime.fromtimestamp(now), typing=self._typing,
            recent=self._history.recent(self._t.recent_n),
            since_last_s=None if last is None else now - last,
            unread=self._unread, emotion=self._emotion, consecutive=self._consecutive,
            house_away_s=self._house_away_s if situation == "house_out" else None)
        try:
            j = await self._jev.judge(state)
        except AuthError:
            await self._set_ai("bad_key")
            return
        except CallError as e:
            self._failures += 1
            log.warning("Jev 실패(%s). 연속 %d번", e, self._failures)
            return
        self._failures = 0

        reaction: dict = {}
        if j.emotion in EMOTIONS and j.emotion != self._emotion:
            self._emotion = reaction["emotion"] = j.emotion
        action = j.action if j.action in ACTIONS else "none"
        if action != "none" and action != self._action:
            reaction["action"] = action
        self._action = action
        if reaction:
            await self._emit({"type": "reaction", **reaction})

        if j.speak < self._t.speak_threshold or self._consecutive >= self._t.max_consecutive:
            return  # 무응답 (감정·행동 반응은 이미 보냈다)
        self._phase = "speaking"
        prompt = dialogue_prompt(
            situation=SITUATIONS[situation], emotion=EMOTIONS[self._emotion], action=ACTIONS[action],
            recent=self._history.recent(self._t.recent_n), typing=self._typing if situation == "typing" else "")
        try:
            line = trim_line(await self._talker.say(system_instruction(), prompt))
        except AuthError:
            await self._set_ai("bad_key")
            return
        except CallError as e:
            log.warning("Gemini 실패(%s). 대사 없이 넘어간다", e)
            return
        if not line:
            return
        await self._emit({"type": "reaction", "utterance": line})
        self._history.add("dog", line, self._clock())
        self._consecutive += 1
        self._unread = True
        self._due = "just_spoke"

    async def _set_ai(self, ai: str) -> None:
        if ai == self._ai:
            return
        self._ai = ai
        # 판단 도중(Jev·Gemini 키 오류)이면 그 판단은 곧 끝나므로 자기 자신은 취소하지 않는다
        if ai != "ok" and asyncio.current_task() is not self._task:
            self._cancel()
        if self._connected:
            await self._emit({"type": "status", "ai": ai})

    async def _close_clients(self) -> None:
        for c in (self._jev, self._talker):
            if c is None:
                continue
            try:
                await c.aclose()
            except Exception:
                log.exception("클라이언트 닫기 실패")
        self._jev = self._talker = None
