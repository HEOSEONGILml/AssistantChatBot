"""이벤트 기록과 강아지 상태 (두뇌 스펙 v2 11절). 이벤트 쓰기가 실패하면 메모리로 계속한다.
강아지 상태를 읽지 못하면 StoreError: 저장된 성격이 있는지 모르는 채 새로 태어나게 하지 않기 위해서다."""
import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

MEM_KEEP = 500  # 메모리에 들고 있는 최근 이벤트 수. tuning.recent_events보다 넉넉하게


@dataclass(frozen=True)
class Event:
    ts: float
    source: str   # user: 사용자가 한 일 / screen: 화면이 알린 상황 / dog: 강아지가 한 일
    kind: str
    data: dict


class StoreError(Exception):
    """강아지 상태를 읽지 못했다."""


class Store:
    def __init__(self, path: Path | None):
        self._mem: list[Event] = []
        self._dog: dict | None = None
        self._db: sqlite3.Connection | None = None
        self._failed = False
        if path is None:
            return
        try:
            self._db = sqlite3.connect(path)
            self._db.execute("CREATE TABLE IF NOT EXISTS events (ts REAL NOT NULL, source TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL)")
            self._db.execute("CREATE TABLE IF NOT EXISTS dog (id INTEGER PRIMARY KEY CHECK (id = 1), json TEXT NOT NULL)")
            self._db.commit()
            rows = self._db.execute("SELECT ts, source, kind, data FROM events ORDER BY rowid DESC LIMIT ?", (MEM_KEEP,)).fetchall()
            self._mem = [Event(r[0], r[1], r[2], json.loads(r[3])) for r in reversed(rows)]
        except (sqlite3.Error, ValueError):
            log.exception("기록 저장소를 열지 못해 메모리로 계속한다")
            self._db, self._failed = None, True

    def _write(self, sql: str, args: tuple = ()) -> None:
        assert self._db is not None
        self._db.execute(sql, args)
        self._db.commit()

    def add(self, ev: Event) -> None:
        self._mem.append(ev)
        del self._mem[:-MEM_KEEP]
        if self._db is None:
            return
        try:
            self._write("INSERT INTO events (ts, source, kind, data) VALUES (?, ?, ?, ?)",
                        (ev.ts, ev.source, ev.kind, json.dumps(ev.data, ensure_ascii=False)))
        except sqlite3.Error:
            log.exception("이벤트 기록 쓰기 실패. 메모리로 계속한다")  # 대화 내용은 로그에 쓰지 않는다

    def recent(self, n: int) -> list[Event]:
        return self._mem[-n:] if n > 0 else []

    def clear_events(self) -> None:
        self._mem.clear()
        if self._db is None:
            return
        try:
            self._write("DELETE FROM events")
        except sqlite3.Error:
            log.exception("이벤트 기록 삭제 실패")

    def load_dog(self) -> dict | None:
        if self._failed:
            raise StoreError("저장소를 열지 못했다")
        if self._db is None:
            return self._dog
        try:
            row = self._db.execute("SELECT json FROM dog WHERE id = 1").fetchone()
            return json.loads(row[0]) if row else None
        except (sqlite3.Error, ValueError) as e:
            raise StoreError("강아지 상태 읽기 실패") from e

    def save_dog(self, data: dict) -> None:
        self._dog = data
        if self._db is None:
            return
        try:
            self._write("INSERT OR REPLACE INTO dog (id, json) VALUES (1, ?)", (json.dumps(data, ensure_ascii=False),))
        except sqlite3.Error:
            log.exception("강아지 상태 쓰기 실패")

    def import_v1(self, history_path: Path) -> int:
        """v1 대화 기록(history.db)을 이벤트로 옮긴다. 이벤트가 이미 있으면 하지 않는다."""
        if self._mem or not history_path.exists():
            return 0
        try:
            con = sqlite3.connect(history_path)
            rows = con.execute("SELECT ts, speaker, text FROM messages ORDER BY rowid").fetchall()
            con.close()
        except sqlite3.Error:
            log.exception("v1 대화 기록을 읽지 못했다")
            return 0
        for ts, who, text in rows:
            self.add(Event(ts, "user", "message", {"text": text}) if who == "user" else Event(ts, "dog", "dog", {"utterance": text}))
        return len(rows)
