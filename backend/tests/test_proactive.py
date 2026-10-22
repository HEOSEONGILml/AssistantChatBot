import asyncio
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import clients, proactive
from backend.clients import Jev, ScreenHistory
from backend.proactive import Proactive
from tests.test_core import FakeAuth, make

NOW = datetime(2026, 10, 22, 6, 0, 0, tzinfo=timezone.utc)


def _db(tmp_path, rows):
    path = tmp_path / "db.sqlite"
    con = sqlite3.connect(path)
    con.execute("create table frames(timestamp text, app_name text, window_name text, full_text text, accessibility_text text)")
    for ago, app, win, full, acc in rows:
        ts = (NOW - ago).strftime("%Y-%m-%dT%H:%M:%S") + ".358785400+00:00"  # screenpipe는 소수 9자리
        con.execute("insert into frames values (?,?,?,?,?)", (ts, app, win, full, acc))
    con.commit()
    con.close()
    return path


def test_history_reads_recent_and_skips_own_app(tmp_path):
    m = timedelta(minutes=1)
    path = _db(tmp_path, [
        (6 * m, "chrome.exe", "old", "너무 오래됨", None),
        (4 * m, "chrome.exe", "검색", "OCR 글", "접근성 글"),
        (3 * m, "app.exe", "강아지", "내 창", None),
        (2 * m, None, None, "다른 모니터 OCR", None),  # 포커스 없는 모니터는 앱 이름이 없다 (2026-10-22 확인)
        (1 * m, "EXCEL.EXE", "매출.xlsx", None, "접근성만"),
    ])
    frames = ScreenHistory(path).recent(NOW - 5 * m)
    assert [(f["app"], f["window"], f["text"]) for f in frames] == [
        ("chrome.exe", "검색", "OCR 글"), ("EXCEL.EXE", "매출.xlsx", "접근성만")]
    assert frames[1]["at"] == NOW - m


def test_history_missing_db_returns_empty(tmp_path):
    assert ScreenHistory(tmp_path / "none.sqlite").recent(NOW) == []
    bad = tmp_path / "bad.sqlite"
    bad.write_text("not a db")
    assert ScreenHistory(bad).recent(NOW) == []


def _frame(i, text="가" * 500):
    return {"at": NOW - timedelta(seconds=30 * (30 - i)), "app": "chrome.exe", "window": f"창{i}", "text": text}


def test_summarize_budget():
    out = proactive.summarize([_frame(i) for i in range(30)], [], NOW)
    lines = out.split("\n")
    assert len(out) <= 2000
    assert lines[-1] == "최근 [괜찮아]: 없음"
    assert "창29" in lines[-2]
    assert all(len(l) < 300 + 60 for l in lines[:-1])
    assert "가" * 300 in lines[-2] and "가" * 301 not in lines[-2]


def test_summarize_declines():
    out = proactive.summarize([], [(datetime(2026, 10, 22, 15, 42), "EXCEL.EXE", "매출.xlsx")], datetime(2026, 10, 22, 16, 0))
    assert out.split("\n")[-1] == "최근 [괜찮아]: 15:42 EXCEL.EXE · 매출.xlsx"
    old = proactive.summarize([], [(datetime(2026, 10, 22, 14, 0), "A", "b")], datetime(2026, 10, 22, 16, 0))
    assert old.endswith("최근 [괜찮아]: 없음")


@pytest.mark.parametrize("need,declined,expected", [(0.96, 0.12, True), (0.96, 0.65, False), (0.93, 0.19, True), (0.07, 0.11, False), (0.69, 0.0, False)])
def test_should_nudge(need, declined, expected):
    assert proactive.should_nudge({"working": need, "declined_same": declined}) is expected


def _jev(response):
    def post(key, body):
        if isinstance(response, Exception):
            raise response
        return response
    return Jev(post=post)


async def test_jev_failure_returns_none():
    q = proactive.QUESTIONS
    assert await _jev(OSError("x")).ask("k", "s", q) is None
    assert await _jev((401, {})).ask("k", "s", q) is None
    assert await _jev((200, {"detail": "x"})).ask("k", "s", q) is None
    assert await _jev((200, {"answers": {"working": {"type": "noul"}}})).ask("k", "s", q) is None


async def test_jev_parses_noul():
    resp = (200, {"answers": {"working": {"type": "noul", "noul": 0.87}, "declined_same": {"type": "noul", "noul": 0.1}}})
    assert await _jev(resp).ask("k", "s", proactive.QUESTIONS) == {"working": 0.87, "declined_same": 0.1}


def _env_key():
    env = Path(__file__).resolve().parents[2] / ".env"
    try:
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


@pytest.mark.skipif(not _env_key(), reason="루트 .env에 TYPESAFE_API_KEY 없음")
async def test_jev_live():
    state = "10:00:00 Code.exe · main.py def add(a, b): return a + b\n10:02:00 Code.exe · test_main.py 2 passed\n최근 [괜찮아]: 없음"
    answers = await Jev().ask(_env_key(), state, proactive.QUESTIONS)
    assert answers is not None and answers["working"] >= 0.7 and answers["declined_same"] < 0.5


# --- 판단 고리 ---
@pytest.fixture
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))


class FakeHistory:
    def __init__(self, frames):
        self.frames = frames

    def recent(self, since):
        return self.frames


class FakeJev:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []  # (키, 글)

    async def ask(self, key, state, questions):
        assert questions is proactive.QUESTIONS
        self.calls.append((key, state))
        return self.answers


class Clock:
    def __init__(self):
        self.now = datetime.now().astimezone()

    def __call__(self):
        return self.now


HELPS = {"working": 0.89, "declined_same": 0.23}


async def loop(answers=HELPS, key="k", logged_in=True, frames=None):
    app, store, out, runs = make(FakeAuth(logged_in))
    await app.startup()
    if key:
        await app.set_jev_key(key)
    clock = Clock()
    if frames is None:
        frames = [{"at": clock.now - timedelta(seconds=10), "app": "EXCEL.EXE", "window": "매출.xlsx", "text": "#REF!"}]
    jev = FakeJev(answers)
    p = Proactive(store, app, FakeHistory(frames), jev, clock)
    out.clear()
    return p, app, store, out, jev, clock


def nudges(out):
    return [m for m in out if m["type"] == "nudge"]


async def test_tick_nudges_when_jev_says_so(appdata):
    p, app, store, out, jev, clock = await loop()
    await p.tick()
    assert nudges(out) == [{"type": "nudge", "active": True}]
    assert jev.calls[0][0] == "k" and "EXCEL.EXE · 매출.xlsx #REF!" in jev.calls[0][1]
    assert p.current_task() == ("EXCEL.EXE", "매출.xlsx")
    await p.tick()  # 배지가 떠 있으면 쉰다
    assert len(jev.calls) == 1 and nudges(out) == [{"type": "nudge", "active": True}]


async def test_tick_no_nudge_below_threshold(appdata):
    p, app, store, out, jev, clock = await loop(answers={"working": 0.19, "declined_same": 0.27})
    await p.tick()
    assert len(jev.calls) == 1 and nudges(out) == []


async def test_tick_rests(appdata):
    p, app, store, out, jev, clock = await loop(key="")
    await p.tick()
    assert jev.calls == []
    p, app, store, out, jev, clock = await loop()
    await app.set_recording(False)
    await p.tick()
    assert jev.calls == []
    p, app, store, out, jev, clock = await loop(frames=[])  # 기록이 없거나 DB를 못 읽음
    await p.tick()
    assert jev.calls == [] and p.current_task() is None
    p, app, store, out, jev, clock = await loop()
    await app.set_nudge(True)
    await p.tick()
    assert jev.calls == []


async def test_tick_logged_out_judges_but_no_badge(appdata):
    p, app, store, out, jev, clock = await loop(logged_in=False)
    await p.tick()
    assert len(jev.calls) == 1 and nudges(out) == [] and app.nudge_active is False


async def test_tick_survives_jev_failure(appdata, caplog):
    p, app, store, out, jev, clock = await loop(answers=None, key="secret-jev-key")
    await p.tick()
    assert nudges(out) == [] and app.nudge_active is False
    # 진짜 Jev 클라이언트가 실패해도 키·글은 로그에 없다
    p._jev = Jev(post=lambda key, body: (_ for _ in ()).throw(TimeoutError()))
    await p.tick()
    assert nudges(out) == []
    assert "Jev 호출 실패: TimeoutError" in caplog.text
    assert "secret-jev-key" not in caplog.text and "#REF!" not in caplog.text


async def test_run_forever_keeps_going_after_error(appdata):
    p, app, store, out, jev, clock = await loop()
    ticks = []

    async def boom():
        ticks.append(1)
        if len(ticks) == 3:
            raise asyncio.CancelledError
        raise RuntimeError("x")
    p.tick = boom
    with pytest.raises(asyncio.CancelledError):
        await p.run_forever(interval_s=0)
    assert len(ticks) == 3


async def test_badge_expires_after_5_minutes(appdata):
    p, app, store, out, jev, clock = await loop()
    await p.tick()
    clock.now += timedelta(minutes=4, seconds=59)
    await p.tick()
    assert nudges(out) == [{"type": "nudge", "active": True}]
    clock.now += timedelta(seconds=2)
    await p.tick()
    assert nudges(out) == [{"type": "nudge", "active": True}, {"type": "nudge", "active": False}]
    assert app.nudge_active is False and len(jev.calls) == 1
    await p.tick()  # 꺼진 뒤에는 다시 판단한다
    assert len(jev.calls) == 2


async def test_nudge_answer_decline_records(appdata):
    p, app, store, out, jev, clock = await loop()
    await p.tick()
    await app.nudge_open()
    await app.nudge_answer(False)
    clock.now += timedelta(seconds=30)  # 다음 판단
    jev.answers = {"working": 0.97, "declined_same": 0.65}  # 같은 창에서 거절했다고 본다 → 그 창에서는 배지 없음
    await p.tick()
    assert app.nudge_active is False
    assert re.fullmatch(r"최근 \[괜찮아\]: \d\d:\d\d EXCEL\.EXE · 매출\.xlsx", jev.calls[-1][1].split("\n")[-1])
    clock.now += timedelta(hours=1, minutes=1)  # 1시간이 지나면 넣지 않는다
    await p.tick()
    assert jev.calls[-1][1].endswith("최근 [괜찮아]: 없음")


async def test_tick_rests_when_logged_out(appdata):
    p, app, store, out, jev, clock = await loop(logged_in=False)
    await app.connected(True)  # status {logged_in: false}를 보냈다
    await p.tick()
    assert jev.calls == []
    await app.login()
    await p.tick()
    assert len(jev.calls) == 1
    await app.set_nudge(False)
    await app.logout()
    await p.tick()
    assert len(jev.calls) == 1


def test_summarize_keeps_newest_declines():
    now = datetime(2026, 10, 22, 16, 0)
    declines = [(now - timedelta(minutes=50 - i), f"앱{i}.exe", "창" * 100) for i in range(30)]
    frame = {"at": now - timedelta(seconds=10), "app": "EXCEL.EXE", "window": "매출.xlsx", "text": "#REF!"}
    out = proactive.summarize([frame], declines, now)
    tail = out.split("\n")[-1]
    assert tail.count("앱") == 10 and "앱29.exe" in tail and "앱19.exe" not in tail
    assert "EXCEL.EXE · 매출.xlsx #REF!" in out


async def test_tick_rests_while_nudge_unanswered(appdata):
    p, app, store, out, jev, clock = await loop()
    app.proactive = p
    await p.tick()
    await app.nudge_open()  # 배지는 꺼지고 "도움이 필요해?"가 답을 기다린다
    await p.tick()
    assert len(jev.calls) == 1
    await app.nudge_answer(False)
    await p.tick()
    assert len(jev.calls) == 2


async def test_tick_rests_while_chat_is_working_or_waiting(appdata):
    p, app, store, out, jev, clock = await loop()
    chat_id = store.chat_session()["id"]
    await app.say(chat_id, "안녕")  # working
    await p.tick()
    assert jev.calls == []
    run = app._runs[chat_id][0]
    run.events.question("어느 파일?", ["a", "b"])  # waiting
    await p.tick()
    assert jev.calls == []
    run.events.answered()
    run.events.finished("끝", False)
    run.end()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await p.tick()
    assert len(jev.calls) == 1
