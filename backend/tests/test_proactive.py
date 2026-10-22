import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import clients, proactive
from backend.clients import Jev, ScreenHistory

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


@pytest.mark.parametrize("need,declined,expected", [(0.89, 0.23, True), (0.88, 0.80, False), (0.95, 0.80, True), (0.19, 0.27, False)])
def test_should_nudge(need, declined, expected):
    assert proactive.should_nudge({"need_help": need, "declined_same": declined}) is expected


def _jev(response):
    async def noop():
        pass

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
    assert await _jev((200, {"answers": {"need_help": {"type": "noul"}}})).ask("k", "s", q) is None


async def test_jev_parses_noul():
    resp = (200, {"answers": {"need_help": {"type": "noul", "noul": 0.87}, "declined_same": {"type": "noul", "noul": 0.1}}})
    assert await _jev(resp).ask("k", "s", proactive.QUESTIONS) == {"need_help": 0.87, "declined_same": 0.1}


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
    state = "10:00:00 EXCEL.EXE · 매출.xlsx 글: #REF! 오류 수식을 고치려 여러 번 다시 입력함. 같은 셀을 계속 고치고 있다. 오류가 안 없어진다.\n최근 [괜찮아]: 없음"
    answers = await Jev().ask(_env_key(), state, proactive.QUESTIONS)
    assert answers is not None and answers["need_help"] >= 0.7
