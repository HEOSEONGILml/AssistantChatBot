import sqlite3

from brain.memory import History


def test_memory_only_history():
    h = History(None)
    assert h.recent(5) == [] and h.last_ts() is None
    h.add("user", "안녕", 1.0)
    h.add("dog", "멍!", 2.0)
    assert h.recent(5) == [(1.0, "user", "안녕"), (2.0, "dog", "멍!")]
    assert h.recent(1) == [(2.0, "dog", "멍!")]
    assert h.last_ts() == 2.0


def test_persists_across_instances(tmp_path):
    db = tmp_path / "history.db"
    h = History(db)
    h.add("user", "산책 가자", 10.0)
    assert History(db).recent(5) == [(10.0, "user", "산책 가자")]


def test_clear_removes_everything(tmp_path):
    db = tmp_path / "history.db"
    h = History(db)
    h.add("user", "a", 1.0)
    h.clear()
    assert h.recent(5) == [] and h.last_ts() is None
    assert History(db).recent(5) == []


def test_unopenable_db_falls_back_to_memory(tmp_path):
    bad = tmp_path / "no-such-dir" / "history.db"
    h = History(bad)
    h.add("user", "그래도 기억해", 1.0)
    assert h.recent(1) == [(1.0, "user", "그래도 기억해")]


def test_write_failure_keeps_memory(tmp_path, monkeypatch):
    h = History(tmp_path / "history.db")
    def broken(*a, **k):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(h, "_write", broken)
    h.add("user", "메모리에는 남는다", 1.0)
    assert h.recent(1) == [(1.0, "user", "메모리에는 남는다")]
