"""세션 기록 저장소 (SQLite). 세션·대화 줄·스케줄·설정을 한 파일에 둔다."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

PAGE_SIZE = 4  # 목록 한 쪽은 4줄 (디자인)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    state TEXT NOT NULL,
    seen INTEGER NOT NULL DEFAULT 0,
    claude_session_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    choices TEXT,
    data TEXT
);
CREATE INDEX IF NOT EXISTS entries_session ON entries(session_id);
CREATE TABLE IF NOT EXISTS schedules (
    session_id INTEGER PRIMARY KEY REFERENCES sessions(id),
    name TEXT NOT NULL,
    rule TEXT NOT NULL,
    instruction TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    last_result TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS session_text USING fts5(session_id UNINDEXED, text);
"""

# 옛 이름(tasks, task_id, task_text)을 새 이름으로 옮긴다 (0034). 색인은 _SCHEMA로 새로 만들고 다시 채운다.
_MIGRATE_0034 = """
ALTER TABLE tasks RENAME COLUMN session_id TO claude_session_id;
ALTER TABLE tasks RENAME TO sessions;
ALTER TABLE entries RENAME COLUMN task_id TO session_id;
ALTER TABLE schedules RENAME COLUMN task_id TO session_id;
DROP INDEX IF EXISTS entries_task;
DROP TABLE IF EXISTS task_text;
UPDATE entries SET data = json_object('session_id', json_extract(data, '$.task_id'))
    WHERE kind = 'chip' AND json_extract(data, '$.task_id') IS NOT NULL;
"""

_SESSION_FIELDS = {"title", "state", "seen", "claude_session_id"}  # source(종류)는 바뀌지 않는다 (0035)
_SCHEDULE_FIELDS = {"name", "rule", "instruction", "enabled", "last_run_at", "last_result"}
# 알림 순서: 답 기다림 -> 실패 -> 완료
_ALERT_ORDER = "CASE state WHEN 'waiting' THEN 0 WHEN 'failed' THEN 1 ELSE 2 END, id DESC"
# 대화 탭의 대화 세션은 알림에 넣지 않는다 (0030 수정: 대화 탭)
_ALERT_WHERE = "source != 'chat' AND (state = 'waiting' OR (state IN ('done','failed') AND seen = 0))"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _session(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["seen"] = bool(d["seen"])
    return d


def _entry(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["choices"] = json.loads(d["choices"]) if d["choices"] is not None else None
    d["data"] = json.loads(d["data"]) if d["data"] is not None else None
    return d


def _schedule(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["rule"] = json.loads(d["rule"])
    d["enabled"] = bool(d["enabled"])
    return d


def _pages(total: int) -> int:
    return max(1, -(-total // PAGE_SIZE))


class Store:
    def __init__(self, path: Path | None):
        self._db = sqlite3.connect(str(path) if path else ":memory:")
        self._db.row_factory = sqlite3.Row
        tables = {r[0] for r in self._db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "tasks" in tables and "sessions" not in tables:
            self._db.executescript("BEGIN;" + _MIGRATE_0034 + _SCHEMA)  # 한 트랜잭션: 실패하면 옛 DB 그대로
            with self._db:
                for (session_id,) in self._db.execute("SELECT id FROM sessions").fetchall():
                    self._reindex(session_id)
        else:
            self._db.executescript(_SCHEMA)

    # --- 세션 ---
    def create_session(self, source: str, title: str) -> dict:
        with self._db:
            cur = self._db.execute(
                "INSERT INTO sessions (source, title, state, seen, created_at) VALUES (?, ?, 'working', 0, ?)",
                (source, title, _now()),
            )
            self._reindex(cur.lastrowid)
        return self.get_session(cur.lastrowid)

    def update_session(self, session_id: int, **fields) -> dict:
        bad = set(fields) - _SESSION_FIELDS
        if bad:
            raise ValueError(f"고칠 수 없는 필드: {sorted(bad)}")
        if "seen" in fields:
            fields["seen"] = int(fields["seen"])
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            with self._db:
                self._db.execute(f"UPDATE sessions SET {sets} WHERE id = ?", (*fields.values(), session_id))
                if "title" in fields:
                    self._reindex(session_id)
        return self.get_session(session_id)

    def get_session(self, session_id: int) -> dict | None:
        row = self._db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return _session(row) if row else None

    def chat_session(self) -> dict | None:
        """대화 탭의 대화 세션 (하나뿐이다). 아직 없으면 None."""
        row = self._db.execute("SELECT * FROM sessions WHERE source = 'chat' ORDER BY id LIMIT 1").fetchone()
        return _session(row) if row else None

    def list_sessions(self, page: int, view: str) -> tuple[list[dict], int]:
        if view == "user":
            where, order = "source = 'user'", "id DESC"
        elif view == "alerts":
            where, order = _ALERT_WHERE, _ALERT_ORDER
        else:
            raise ValueError(f"모르는 목록: {view}")
        total = self._db.execute(f"SELECT COUNT(*) FROM sessions WHERE {where}").fetchone()[0]
        rows = self._db.execute(
            f"SELECT * FROM sessions WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
            (PAGE_SIZE, (max(page, 1) - 1) * PAGE_SIZE),
        ).fetchall()
        return [_session(r) for r in rows], _pages(total)

    def sessions_in_states(self, *states: str) -> list[dict]:
        marks = ", ".join("?" for _ in states)
        rows = self._db.execute(f"SELECT * FROM sessions WHERE state IN ({marks}) ORDER BY id", states).fetchall()
        return [_session(r) for r in rows]

    def recent_sessions(self, limit: int) -> list[dict]:
        rows = self._db.execute("SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [_session(r) for r in rows]

    def search_sessions(self, query: str, since: str | None, until: str | None, limit: int) -> list[dict]:
        # 단어마다 앞부분 일치(조사 붙은 한국어 대응), 모두 들어 있어야 한다
        terms = [t.replace('"', "") for t in query.split()]
        terms = [t for t in terms if t]
        if not terms:
            return []
        match = " ".join(f'"{t}"*' for t in terms)
        sql = "SELECT * FROM sessions WHERE id IN (SELECT session_id FROM session_text WHERE session_text MATCH ?)"
        args: list = [match]
        # 날짜만 줘도 되도록 준 글자 수만큼만 비교한다
        if since:
            sql += " AND substr(created_at, 1, ?) >= ?"
            args += [len(since), since]
        if until:
            sql += " AND substr(created_at, 1, ?) <= ?"
            args += [len(until), until]
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [_session(r) for r in self._db.execute(sql, args).fetchall()]

    # --- 대화 줄 ---
    def add_entry(self, session_id: int, kind: str, text: str,
                  choices: list[str] | None = None, data: dict | None = None) -> dict:
        with self._db:
            cur = self._db.execute(
                "INSERT INTO entries (session_id, at, kind, text, choices, data) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, _now(), kind, text,
                 json.dumps(choices, ensure_ascii=False) if choices is not None else None,
                 json.dumps(data, ensure_ascii=False) if data is not None else None),
            )
            self._db.execute("INSERT INTO session_text (session_id, text) VALUES (?, ?)", (session_id, text))
        return _entry(self._db.execute("SELECT * FROM entries WHERE id = ?", (cur.lastrowid,)).fetchone())

    def entries(self, session_id: int) -> list[dict]:
        rows = self._db.execute("SELECT * FROM entries WHERE session_id = ? ORDER BY id", (session_id,)).fetchall()
        return [_entry(r) for r in rows]

    def _reindex(self, session_id: int) -> None:
        """검색 글을 제목과 대화 글로 다시 채운다 (제목이 바뀔 수 있어서)."""
        self._db.execute("DELETE FROM session_text WHERE session_id = ?", (session_id,))
        self._db.execute("INSERT INTO session_text (session_id, text) SELECT id, title FROM sessions WHERE id = ?", (session_id,))
        self._db.execute("INSERT INTO session_text (session_id, text) SELECT session_id, text FROM entries WHERE session_id = ?",
                         (session_id,))

    # --- 스케줄 ---
    def create_schedule(self, session_id: int, name: str, rule: dict, instruction: str) -> dict:
        with self._db:
            self._db.execute(
                "INSERT INTO schedules (session_id, name, rule, instruction, enabled) VALUES (?, ?, ?, ?, 1)",
                (session_id, name, json.dumps(rule), instruction),
            )
        return self.get_schedule(session_id)

    def update_schedule(self, session_id: int, **fields) -> dict:
        bad = set(fields) - _SCHEDULE_FIELDS
        if bad:
            raise ValueError(f"고칠 수 없는 필드: {sorted(bad)}")
        if "rule" in fields:
            fields["rule"] = json.dumps(fields["rule"])
        if "enabled" in fields:
            fields["enabled"] = int(fields["enabled"])
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            with self._db:
                self._db.execute(f"UPDATE schedules SET {sets} WHERE session_id = ?", (*fields.values(), session_id))
        return self.get_schedule(session_id)

    def get_schedule(self, session_id: int) -> dict | None:
        row = self._db.execute("SELECT * FROM schedules WHERE session_id = ?", (session_id,)).fetchone()
        return _schedule(row) if row else None

    def list_schedules(self, page: int) -> tuple[list[dict], int]:
        total = self._db.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
        rows = self._db.execute(
            "SELECT * FROM schedules ORDER BY session_id DESC LIMIT ? OFFSET ?",
            (PAGE_SIZE, (max(page, 1) - 1) * PAGE_SIZE),
        ).fetchall()
        return [_schedule(r) for r in rows], _pages(total)

    def all_schedules(self) -> list[dict]:
        return [_schedule(r) for r in self._db.execute("SELECT * FROM schedules ORDER BY session_id").fetchall()]

    # --- 설정 ---
    def get_setting(self, key: str, default: str) -> str:
        row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
