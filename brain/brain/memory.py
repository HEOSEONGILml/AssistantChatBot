"""대화 기록 (두뇌 스펙 6절). 무기한 보관하고, 읽기·쓰기가 실패하면 메모리로 계속한다."""
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

MEM_KEEP = 200  # 메모리에 들고 있는 최근 대화 수. tuning.recent_n보다 넉넉하게


class History:
    def __init__(self, path: Path | None):
        self._mem: list[tuple[float, str, str]] = []
        self._db: sqlite3.Connection | None = None
        if path is None:
            return
        try:
            self._db = sqlite3.connect(path)
            self._db.execute("CREATE TABLE IF NOT EXISTS messages (ts REAL NOT NULL, speaker TEXT NOT NULL, text TEXT NOT NULL)")
            self._db.commit()
            rows = self._db.execute("SELECT ts, speaker, text FROM messages ORDER BY rowid DESC LIMIT ?", (MEM_KEEP,)).fetchall()
            self._mem = [(r[0], r[1], r[2]) for r in reversed(rows)]
        except sqlite3.Error:
            log.exception("대화 기록을 열지 못해 메모리로 계속한다")
            self._db = None

    def _write(self, sql: str, args: tuple = ()) -> None:
        assert self._db is not None
        self._db.execute(sql, args)
        self._db.commit()

    def add(self, speaker: str, text: str, ts: float) -> None:
        self._mem.append((ts, speaker, text))
        del self._mem[:-MEM_KEEP]
        if self._db is None:
            return
        try:
            self._write("INSERT INTO messages (ts, speaker, text) VALUES (?, ?, ?)", (ts, speaker, text))
        except sqlite3.Error:
            log.exception("대화 기록 쓰기 실패. 메모리로 계속한다")  # 대화 내용은 로그에 쓰지 않는다

    def recent(self, n: int) -> list[tuple[float, str, str]]:
        return self._mem[-n:] if n > 0 else []

    def last_ts(self) -> float | None:
        return self._mem[-1][0] if self._mem else None

    def clear(self) -> None:
        self._mem.clear()
        if self._db is None:
            return
        try:
            self._write("DELETE FROM messages")
        except sqlite3.Error:
            log.exception("대화 기록 삭제 실패")
