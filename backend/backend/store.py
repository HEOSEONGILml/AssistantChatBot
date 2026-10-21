"""작업 기록 저장소 (SQLite). 작업·대화 줄·스케줄·설정을 한 파일에 둔다."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

PAGE_SIZE = 4  # 목록 한 쪽은 4줄 (디자인)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    state TEXT NOT NULL,
    seen INTEGER NOT NULL DEFAULT 0,
    session_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    choices TEXT,
    data TEXT
);
CREATE INDEX IF NOT EXISTS entries_task ON entries(task_id);
CREATE TABLE IF NOT EXISTS schedules (
    task_id INTEGER PRIMARY KEY REFERENCES tasks(id),
    name TEXT NOT NULL,
    rule TEXT NOT NULL,
    instruction TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    last_result TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS task_text USING fts5(task_id UNINDEXED, text);
"""

_TASK_FIELDS = {"title", "state", "seen", "session_id", "source"}
_SCHEDULE_FIELDS = {"name", "rule", "instruction", "enabled", "last_run_at", "last_result"}
# 알림 순서: 답 기다림 -> 실패 -> 완료
_ALERT_ORDER = "CASE state WHEN 'waiting' THEN 0 WHEN 'failed' THEN 1 ELSE 2 END, id DESC"
_ALERT_WHERE = "state = 'waiting' OR (state IN ('done','failed') AND seen = 0)"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _task(row: sqlite3.Row) -> dict:
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
        self._db.executescript(_SCHEMA)

    # --- 작업 ---
    def create_task(self, source: str, title: str) -> dict:
        with self._db:
            cur = self._db.execute(
                "INSERT INTO tasks (source, title, state, seen, created_at) VALUES (?, ?, 'working', 0, ?)",
                (source, title, _now()),
            )
            self._reindex(cur.lastrowid)
        return self.get_task(cur.lastrowid)

    def update_task(self, task_id: int, **fields) -> dict:
        bad = set(fields) - _TASK_FIELDS
        if bad:
            raise ValueError(f"고칠 수 없는 필드: {sorted(bad)}")
        if "seen" in fields:
            fields["seen"] = int(fields["seen"])
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            with self._db:
                self._db.execute(f"UPDATE tasks SET {sets} WHERE id = ?", (*fields.values(), task_id))
                if "title" in fields:
                    self._reindex(task_id)
        return self.get_task(task_id)

    def get_task(self, task_id: int) -> dict | None:
        row = self._db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _task(row) if row else None

    def list_tasks(self, page: int, view: str) -> tuple[list[dict], int]:
        if view == "user":
            where, order = "source = 'user'", "id DESC"
        elif view == "alerts":
            where, order = _ALERT_WHERE, _ALERT_ORDER
        else:
            raise ValueError(f"모르는 목록: {view}")
        total = self._db.execute(f"SELECT COUNT(*) FROM tasks WHERE {where}").fetchone()[0]
        rows = self._db.execute(
            f"SELECT * FROM tasks WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
            (PAGE_SIZE, (max(page, 1) - 1) * PAGE_SIZE),
        ).fetchall()
        return [_task(r) for r in rows], _pages(total)

    def recent_tasks(self, limit: int) -> list[dict]:
        rows = self._db.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [_task(r) for r in rows]

    def search_tasks(self, query: str, since: str | None, until: str | None, limit: int) -> list[dict]:
        # 단어마다 앞부분 일치(조사 붙은 한국어 대응), 모두 들어 있어야 한다
        terms = [t.replace('"', "") for t in query.split()]
        terms = [t for t in terms if t]
        if not terms:
            return []
        match = " ".join(f'"{t}"*' for t in terms)
        sql = "SELECT * FROM tasks WHERE id IN (SELECT task_id FROM task_text WHERE task_text MATCH ?)"
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
        return [_task(r) for r in self._db.execute(sql, args).fetchall()]

    # --- 대화 줄 ---
    def add_entry(self, task_id: int, kind: str, text: str,
                  choices: list[str] | None = None, data: dict | None = None) -> dict:
        with self._db:
            cur = self._db.execute(
                "INSERT INTO entries (task_id, at, kind, text, choices, data) VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, _now(), kind, text,
                 json.dumps(choices, ensure_ascii=False) if choices is not None else None,
                 json.dumps(data, ensure_ascii=False) if data is not None else None),
            )
            self._db.execute("INSERT INTO task_text (task_id, text) VALUES (?, ?)", (task_id, text))
        return _entry(self._db.execute("SELECT * FROM entries WHERE id = ?", (cur.lastrowid,)).fetchone())

    def entries(self, task_id: int) -> list[dict]:
        rows = self._db.execute("SELECT * FROM entries WHERE task_id = ? ORDER BY id", (task_id,)).fetchall()
        return [_entry(r) for r in rows]

    def _reindex(self, task_id: int) -> None:
        """검색 글을 제목과 대화 글로 다시 채운다 (제목이 바뀔 수 있어서)."""
        self._db.execute("DELETE FROM task_text WHERE task_id = ?", (task_id,))
        self._db.execute("INSERT INTO task_text (task_id, text) SELECT id, title FROM tasks WHERE id = ?", (task_id,))
        self._db.execute("INSERT INTO task_text (task_id, text) SELECT task_id, text FROM entries WHERE task_id = ?",
                         (task_id,))

    # --- 스케줄 ---
    def create_schedule(self, task_id: int, name: str, rule: dict, instruction: str) -> dict:
        with self._db:
            self._db.execute(
                "INSERT INTO schedules (task_id, name, rule, instruction, enabled) VALUES (?, ?, ?, ?, 1)",
                (task_id, name, json.dumps(rule), instruction),
            )
        return self.get_schedule(task_id)

    def update_schedule(self, task_id: int, **fields) -> dict:
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
                self._db.execute(f"UPDATE schedules SET {sets} WHERE task_id = ?", (*fields.values(), task_id))
        return self.get_schedule(task_id)

    def get_schedule(self, task_id: int) -> dict | None:
        row = self._db.execute("SELECT * FROM schedules WHERE task_id = ?", (task_id,)).fetchone()
        return _schedule(row) if row else None

    def list_schedules(self, page: int) -> tuple[list[dict], int]:
        total = self._db.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
        rows = self._db.execute(
            "SELECT * FROM schedules ORDER BY task_id DESC LIMIT ? OFFSET ?",
            (PAGE_SIZE, (max(page, 1) - 1) * PAGE_SIZE),
        ).fetchall()
        return [_schedule(r) for r in rows], _pages(total)

    def all_schedules(self) -> list[dict]:
        return [_schedule(r) for r in self._db.execute("SELECT * FROM schedules ORDER BY task_id").fetchall()]

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
