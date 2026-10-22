import pytest
import sqlite3

from backend.store import Store


def test_session_and_entries_roundtrip():
    s = Store(None)
    t = s.create_session("user", "휴지 주문")
    assert t["id"] == 1 and t["state"] == "working" and t["seen"] is False
    s.add_entry(1, "question", "결제할까요?", choices=["예", "아니오"])
    e = s.entries(1)
    assert e[0]["choices"] == ["예", "아니오"] and e[0]["kind"] == "question"
    u = s.update_session(1, state="waiting", seen=True, claude_session_id="s1")
    assert (u["state"], u["seen"], u["claude_session_id"], u["source"]) == ("waiting", True, "s1", "user")
    with pytest.raises(ValueError):  # 세션 종류는 만들 때 정해지고 바뀌지 않는다 (0035)
        s.update_session(1, source="schedule")
    assert s.get_session(99) is None


def test_alerts_order_and_filter():
    s = Store(None)
    for title, state, seen in [("d1", "done", False), ("seen", "done", True), ("f", "failed", False),
                               ("w", "waiting", True), ("d2", "done", False), ("run", "working", False)]:
        t = s.create_session("schedule", title)
        s.update_session(t["id"], state=state, seen=seen)
    items, pages = s.list_sessions(1, "alerts")
    assert [t["title"] for t in items] == ["w", "f", "d2", "d1"]
    assert pages == 1


def test_user_view_excludes_schedules_and_pages_by_4():
    s = Store(None)
    for i in range(5):
        s.create_session("user", f"u{i}")
    s.create_session("schedule", "sch")
    items, pages = s.list_sessions(1, "user")
    assert [t["title"] for t in items] == ["u4", "u3", "u2", "u1"] and pages == 2
    items2, _ = s.list_sessions(2, "user")
    assert [t["title"] for t in items2] == ["u0"]
    assert s.list_sessions(1, "alerts") == ([], 1) or s.list_sessions(1, "alerts")[0] == []
    assert len(s.recent_sessions(3)) == 3


def test_search_sessions_finds_entry_text():
    s = Store(None)
    a = s.create_session("user", "물건 사기")
    s.create_session("user", "다른 일")
    s.add_entry(a["id"], "result", "2만 원짜리 A 제품")
    assert [t["id"] for t in s.search_sessions("A 제품", None, None, 5)] == [a["id"]]
    assert s.search_sessions("A 제품", "2999-01-01", None, 5) == []
    assert [t["id"] for t in s.search_sessions("물건", None, None, 5)] == [a["id"]]


def test_schedule_roundtrip_and_settings_default():
    s = Store(None)
    t = s.create_session("schedule", "아침 뉴스")
    rule = {"repeat": "weekly", "time": "09:00", "weekday": 0}
    sc = s.create_schedule(t["id"], "아침 뉴스", rule, "뉴스 요약")
    assert sc["rule"] == rule and sc["enabled"] is True and sc["last_run_at"] is None
    s.update_schedule(t["id"], enabled=False, last_result="ok")
    assert s.get_schedule(t["id"])["enabled"] is False
    assert s.get_schedule(t["id"])["last_result"] == "ok"
    assert s.list_schedules(1) == ([s.get_schedule(t["id"])], 1)
    assert len(s.all_schedules()) == 1
    assert s.get_setting("permission_mode", "default") == "default"
    s.set_setting("permission_mode", "plan")
    assert s.get_setting("permission_mode", "default") == "plan"


def test_persists_to_file(tmp_path):
    p = tmp_path / "a.db"
    Store(p).create_session("user", "x")
    assert Store(p).get_session(1)["title"] == "x"


def test_sessions_in_states():
    s = Store(None)
    for title, state in [("w", "working"), ("d", "done"), ("q", "waiting")]:
        t = s.create_session("user", title)
        s.update_session(t["id"], state=state)
    assert [t["title"] for t in s.sessions_in_states("working", "waiting")] == ["w", "q"]


def test_chat_session_not_in_lists():
    s = Store(None)
    assert s.chat_session() is None
    chat = s.create_session("chat", "대화")
    s.update_session(chat["id"], state="failed", seen=False)  # 앱이 꺼져 고아 처리된 대화도 알림에 넣지 않는다
    u = s.create_session("user", "일")
    s.update_session(u["id"], state="done", seen=False)
    assert s.chat_session()["id"] == chat["id"]
    assert [t["id"] for t in s.list_sessions(1, "user")[0]] == [u["id"]]
    assert [t["id"] for t in s.list_sessions(1, "alerts")[0]] == [u["id"]]
    s.update_session(chat["id"], state="waiting")
    assert [t["id"] for t in s.list_sessions(1, "alerts")[0]] == [u["id"]]


def test_migrates_old_task_schema(tmp_path):
    """옛 스키마(tasks, task_id, task_text)의 기록이 새 이름으로 옮겨지고 검색도 된다 (0034)."""
    p = tmp_path / "old.db"
    db = sqlite3.connect(p)
    db.executescript("""
CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, title TEXT NOT NULL,
    state TEXT NOT NULL, seen INTEGER NOT NULL DEFAULT 0, session_id TEXT, created_at TEXT NOT NULL);
CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL REFERENCES tasks(id),
    at TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, choices TEXT, data TEXT);
CREATE INDEX entries_task ON entries(task_id);
CREATE TABLE schedules (task_id INTEGER PRIMARY KEY REFERENCES tasks(id), name TEXT NOT NULL, rule TEXT NOT NULL,
    instruction TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, last_run_at TEXT, last_result TEXT);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE VIRTUAL TABLE task_text USING fts5(task_id UNINDEXED, text);
INSERT INTO tasks VALUES (1, 'schedule', '아침 뉴스', 'done', 1, 's1', '2026-10-01T09:00:00+09:00');
INSERT INTO tasks VALUES (2, 'user', '회의 자료', 'done', 1, NULL, '2026-10-01T10:00:00+09:00');
INSERT INTO entries VALUES (1, 1, '2026-10-01T09:00:00+09:00', 'result', '오늘의 주요 뉴스', NULL, NULL);
INSERT INTO entries VALUES (2, 1, '2026-10-01T09:01:00+09:00', 'chip', '회의 자료', NULL, '{"task_id": 2}');
INSERT INTO schedules VALUES (1, '아침 뉴스', '{"repeat": "daily", "time": "09:00"}', '뉴스 요약', 1, NULL, NULL);
INSERT INTO task_text VALUES (1, '아침 뉴스'), (1, '오늘의 주요 뉴스');
""")
    db.close()
    s = Store(p)
    session = s.get_session(1)
    assert (session["title"], session["claude_session_id"]) == ("아침 뉴스", "s1")
    assert [e["session_id"] for e in s.entries(1)] == [1, 1]
    assert s.entries(1)[1]["data"] == {"session_id": 2}
    assert s.get_schedule(1)["session_id"] == 1
    assert [x["id"] for x in s.search_sessions("주요", None, None, 5)] == [1]
    assert [x["id"] for x in s.search_sessions("회의", None, None, 5)] == [2, 1]
    assert s.create_session("user", "새 일")["id"] == 3
    assert Store(p).get_session(1)["title"] == "아침 뉴스"  # 다시 열어도 그대로
