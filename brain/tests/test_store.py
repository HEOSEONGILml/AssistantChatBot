import sqlite3

import pytest

from brain.store import Event, Store, StoreError


def test_memory_store_events():
    s = Store(None)
    s.add(Event(1.0, "user", "message", {"text": "안녕"}))
    s.add(Event(2.0, "dog", "dog", {"utterance": "멍!"}))
    assert [e.kind for e in s.recent(5)] == ["message", "dog"]
    assert s.recent(1) == [Event(2.0, "dog", "dog", {"utterance": "멍!"})]
    s.clear_events()
    assert s.recent(5) == []


def test_persists_events_and_dog(tmp_path):
    db = tmp_path / "brain.db"
    s = Store(db)
    s.add(Event(1.0, "user", "poke", {}))
    s.save_dog({"mood": {"분노": 0.4}})
    again = Store(db)
    assert again.recent(5) == [Event(1.0, "user", "poke", {})]
    assert again.load_dog() == {"mood": {"분노": 0.4}}


def test_no_dog_yet(tmp_path):
    assert Store(tmp_path / "brain.db").load_dog() is None
    assert Store(None).load_dog() is None


def test_clear_keeps_dog(tmp_path):
    s = Store(tmp_path / "brain.db")
    s.save_dog({"a": 1})
    s.add(Event(1.0, "user", "poke", {}))
    s.clear_events()
    assert Store(tmp_path / "brain.db").recent(5) == []
    assert Store(tmp_path / "brain.db").load_dog() == {"a": 1}


def test_unopenable_db_keeps_events_in_memory_but_refuses_dog(tmp_path):
    s = Store(tmp_path / "no-such-dir" / "brain.db")
    s.add(Event(1.0, "user", "poke", {}))
    assert len(s.recent(5)) == 1
    with pytest.raises(StoreError):
        s.load_dog()  # 저장된 강아지가 있는지 모르므로 새로 태어나게 하면 안 된다


def test_broken_dog_row_raises(tmp_path):
    db = tmp_path / "brain.db"
    Store(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO dog (id, json) VALUES (1, 'not json')")
    con.commit()
    con.close()
    with pytest.raises(StoreError):
        Store(db).load_dog()


def test_import_v1_history_once(tmp_path):
    old = tmp_path / "history.db"
    con = sqlite3.connect(old)
    con.execute("CREATE TABLE messages (ts REAL NOT NULL, speaker TEXT NOT NULL, text TEXT NOT NULL)")
    con.executemany("INSERT INTO messages VALUES (?, ?, ?)", [(1.0, "user", "안녕"), (2.0, "dog", "멍!")])
    con.commit()
    con.close()
    s = Store(tmp_path / "brain.db")
    assert s.import_v1(old) == 2
    assert s.recent(5) == [Event(1.0, "user", "message", {"text": "안녕"}), Event(2.0, "dog", "dog", {"utterance": "멍!"})]
    assert s.import_v1(old) == 0  # 이벤트가 이미 있으면 옮기지 않는다


def test_import_v1_happens_only_once_even_after_clear(tmp_path):
    # 리뷰 지적: 기록을 지운 뒤 다시 켜면 v1 대화가 되살아났다
    old = tmp_path / "history.db"
    con = sqlite3.connect(old)
    con.execute("CREATE TABLE messages (ts REAL NOT NULL, speaker TEXT NOT NULL, text TEXT NOT NULL)")
    con.execute("INSERT INTO messages VALUES (1.0, 'user', '안녕')")
    con.commit()
    con.close()
    s = Store(tmp_path / "brain.db")
    assert s.import_v1(old) == 1
    s.clear_events()
    assert Store(tmp_path / "brain.db").import_v1(old) == 0
    assert Store(tmp_path / "brain.db").recent(5) == []
