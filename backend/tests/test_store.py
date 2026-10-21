from backend.store import Store


def test_task_and_entries_roundtrip():
    s = Store(None)
    t = s.create_task("user", "휴지 주문")
    assert t["id"] == 1 and t["state"] == "working" and t["seen"] is False
    s.add_entry(1, "question", "결제할까요?", choices=["예", "아니오"])
    e = s.entries(1)
    assert e[0]["choices"] == ["예", "아니오"] and e[0]["kind"] == "question"
    u = s.update_task(1, state="waiting", seen=True, session_id="s1", source="schedule")
    assert (u["state"], u["seen"], u["session_id"], u["source"]) == ("waiting", True, "s1", "schedule")
    assert s.get_task(99) is None


def test_alerts_order_and_filter():
    s = Store(None)
    for title, state, seen in [("d1", "done", False), ("seen", "done", True), ("f", "failed", False),
                               ("w", "waiting", True), ("d2", "done", False), ("run", "working", False)]:
        t = s.create_task("schedule", title)
        s.update_task(t["id"], state=state, seen=seen)
    items, pages = s.list_tasks(1, "alerts")
    assert [t["title"] for t in items] == ["w", "f", "d2", "d1"]
    assert pages == 1


def test_user_view_excludes_schedules_and_pages_by_4():
    s = Store(None)
    for i in range(5):
        s.create_task("user", f"u{i}")
    s.create_task("schedule", "sch")
    items, pages = s.list_tasks(1, "user")
    assert [t["title"] for t in items] == ["u4", "u3", "u2", "u1"] and pages == 2
    items2, _ = s.list_tasks(2, "user")
    assert [t["title"] for t in items2] == ["u0"]
    assert s.list_tasks(1, "alerts") == ([], 1) or s.list_tasks(1, "alerts")[0] == []
    assert len(s.recent_tasks(3)) == 3


def test_search_tasks_finds_entry_text():
    s = Store(None)
    a = s.create_task("user", "물건 사기")
    s.create_task("user", "다른 일")
    s.add_entry(a["id"], "result", "2만 원짜리 A 제품")
    assert [t["id"] for t in s.search_tasks("A 제품", None, None, 5)] == [a["id"]]
    assert s.search_tasks("A 제품", "2999-01-01", None, 5) == []
    assert [t["id"] for t in s.search_tasks("물건", None, None, 5)] == [a["id"]]


def test_schedule_roundtrip_and_settings_default():
    s = Store(None)
    t = s.create_task("schedule", "아침 뉴스")
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
    Store(p).create_task("user", "x")
    assert Store(p).get_task(1)["title"] == "x"


def test_tasks_in_states():
    s = Store(None)
    for title, state in [("w", "working"), ("d", "done"), ("q", "waiting")]:
        t = s.create_task("user", title)
        s.update_task(t["id"], state=state)
    assert [t["title"] for t in s.tasks_in_states("working", "waiting")] == ["w", "q"]
