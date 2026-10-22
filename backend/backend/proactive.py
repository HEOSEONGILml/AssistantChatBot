"""먼저 말 걸기: 화면 기록 줄이기, Jev 질문 정의, 배지 조건, 30초마다 도는 판단 고리. 질문과 임계값은 여기에만 둔다 (CLAUDE.md 4절)."""
import asyncio
import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

BUDGET = 2000       # 글자. 2천 토큰을 한글 기준 약 2,000자로 근사 (잠정)
TEXT_LIMIT = 300    # 프레임마다 글 앞 300자
DECLINE_WINDOW = timedelta(hours=1)
DECLINE_MAX = 10    # 거절 줄에 넣는 최근 [괜찮아] 수. 거절이 많아도 화면 기록 줄이 밀려나지 않게 (잠정)
HISTORY_WINDOW = timedelta(minutes=5)  # 판단에 넣는 화면 기록
BADGE_TIME = timedelta(minutes=5)      # 배지가 떠 있는 시간
NONE_DECLINED = "최근 [괜찮아]: 없음"

# 작업 화면이면 뜬다. 같은 창에서 [괜찮아]라고 했으면 그 창에서는 띄우지 않는다 (사용자, 2026-10-22).
# 한 문장에 둘을 섞으면 판단이 흐려져 둘로 나눴다 (2026-10-22 실측, docs/superpowers/specs/2026-10-22-proactive-help-design.md 4절)
QUESTIONS = {
    "working": {
        "type": "noul",
        "instructions": "화면 기록을 보면 사용자가 지금 작업 화면(문서·코드·표·기획·업무 도구 등)에서 일하고 있다. 영상·음악·쇼핑·SNS·게임 화면이면 아니다",
    },
    "declined_same": {
        "type": "noul",
        "instructions": "마지막 줄 '최근 [괜찮아]' 목록에, 화면 기록의 가장 최근 줄과 앱 이름과 창 제목이 같은 항목이 있다. 목록이 '없음'이면 아니다",
    },
}

WORKING_MIN = 0.7        # 잠정값. 실측은 작업 화면 0.89~0.97, 영상·쇼핑 0.07~0.11
DECLINED_SAME_MIN = 0.5  # 잠정값. 실측은 거절 없음 0.06~0.12, 같은 창 거절 0.65~0.83, 다른 창 거절 0.19


def should_nudge(answers: dict[str, float]) -> bool:
    return answers["working"] >= WORKING_MIN and answers["declined_same"] < DECLINED_SAME_MIN


def _local(dt: datetime) -> datetime:
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def summarize(frames: list[dict], declines: list[tuple[datetime, str, str]], now: datetime) -> str:
    """화면 기록을 Jev에 줄 글로 줄인다. 오래된 것부터 한 줄씩, 예산이 모자라면 오래된 줄을 버린다. 끝 줄은 거절 내역(새 것 10개까지)."""
    shown = [d for d in declines if _local(now) - DECLINE_WINDOW <= _local(d[0]) <= _local(now)][-DECLINE_MAX:]
    tail = ("최근 [괜찮아]: " + ", ".join(f"{_local(at):%H:%M} {app} · {win}" for at, app, win in shown)) if shown else NONE_DECLINED
    room = BUDGET - len(tail)
    lines: list[str] = []
    for f in reversed(frames):  # 새 것부터 채운다
        text = " ".join(f["text"].split())[:TEXT_LIMIT]
        line = f"{_local(f['at']):%H:%M:%S} {f['app']} · {f['window']} {text}".rstrip()
        room -= len(line) + 1
        if room < 0:
            break
        lines.append(line)
    return "\n".join([*reversed(lines), tail])


class Proactive:
    """판단 고리. 쉬는 때(로그아웃, 화면 기록 꺼짐, Jev 키 없음, 배지가 떠 있음, 대화 중)가 아니면 화면 기록을 Jev에 묻고 배지를 켠다.
    만들 때 app.proactive에 자기를 붙인다 ([괜찮아]·배지 누름이 거절 내역과 지금 작업을 쓴다)."""

    def __init__(self, store, app, history, jev, clock=lambda: datetime.now().astimezone()):
        self._store = store
        self._app = app
        self._history = history
        self._jev = jev
        self._clock = clock
        self._declines: list[tuple[datetime, str, str]] = []  # 메모리에만 둔다 (재시작하면 비움)
        self._task: tuple[str, str] | None = None
        self._badge_at: datetime | None = None
        app.proactive = self

    def current_task(self) -> tuple[str, str] | None:
        """마지막 판단의 가장 최근 프레임 (앱, 창 제목)."""
        return self._task

    def decline(self, at: datetime, app: str, window: str) -> None:
        self._declines = [d for d in self._declines if _local(at) - _local(d[0]) <= DECLINE_WINDOW]
        self._declines.append((at, app, window))

    async def tick(self) -> None:
        now = self._clock()
        if self._app.nudge_active:
            if self._badge_at is not None and now - self._badge_at > BADGE_TIME:
                await self._app.set_nudge(False)
            return
        if self._app.logged_in is False:
            return  # 화면에 보낸 마지막 로그인 상태로 본다. CLI는 배지를 켜기 직전에만 부른다
        if self._app.chatting():
            return  # 대화 중에는 판단하지 않는다 (사용자, 2026-10-22)
        key = self._app.jev_key()
        if not key or not self._app.recording_enabled():
            return
        frames = await asyncio.to_thread(self._history.recent, now - HISTORY_WINDOW)
        if not frames:
            return  # 기록이 없거나 DB를 못 읽음
        self._task = (frames[-1]["app"], frames[-1]["window"])
        answers = await self._jev.ask(key, summarize(frames, self._declines, now), QUESTIONS)
        if answers is None or not should_nudge(answers):
            return
        log.info("배지 조건 맞음 (working %.2f, declined_same %.2f)", answers["working"], answers["declined_same"])
        self._badge_at = now
        await self._app.set_nudge(True)

    async def run_forever(self, interval_s: float = 30) -> None:
        while True:
            await asyncio.sleep(interval_s)
            try:
                await self.tick()
            except Exception as e:
                log.error("먼저 말 걸기 판단 실패: %s", type(e).__name__)  # 내용은 쓰지 않는다
