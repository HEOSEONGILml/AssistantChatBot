from datetime import datetime, timedelta, timezone

from backend.scheduler import Scheduler
from backend.store import Store

KST = timezone(timedelta(hours=9))
RULE = {"repeat": "daily", "time": "18:00"}


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class FakeApp:
    def __init__(self):
        self.calls = []

    async def run_schedule(self, task_id, now):
        self.calls.append((task_id, now))


def setup(start, rule=RULE, enabled=True, state="done"):
    store = Store(None)
    task = store.create_task("schedule", "메일")
    store.update_task(task["id"], state=state)
    store.create_schedule(task["id"], "메일", rule, "요약")
    if not enabled:
        store.update_schedule(task["id"], enabled=False)
    clock = Clock(start)
    app = FakeApp()
    return Scheduler(store, app, clock), clock, app


async def test_due_schedule_runs_once():
    s, clock, app = setup(datetime(2026, 10, 22, 17, 59, tzinfo=KST))
    await s.tick()
    assert app.calls == []
    clock.t = datetime(2026, 10, 22, 18, 0, 30, tzinfo=KST)
    await s.tick()
    await s.tick()
    assert app.calls == [(1, clock.t)]


async def test_missed_while_off_is_skipped():
    s, clock, app = setup(datetime(2026, 10, 22, 19, 0, tzinfo=KST))  # 18:00은 시작 전
    clock.t = datetime(2026, 10, 22, 19, 1, tzinfo=KST)
    await s.tick()
    assert app.calls == []


async def test_running_schedule_skips_this_time():
    s, clock, app = setup(datetime(2026, 10, 22, 17, 59, tzinfo=KST), state="working")
    clock.t = datetime(2026, 10, 22, 18, 1, tzinfo=KST)
    await s.tick()
    assert app.calls == []
    clock.t = datetime(2026, 10, 22, 18, 2, tzinfo=KST)  # 건너뛴 실행은 다시 시도하지 않는다
    await s.tick()
    assert app.calls == []


async def test_disabled_schedule_never_runs():
    s, clock, app = setup(datetime(2026, 10, 22, 17, 59, tzinfo=KST), enabled=False)
    clock.t = datetime(2026, 10, 22, 18, 1, tzinfo=KST)
    await s.tick()
    assert app.calls == []


async def test_gap_from_sleep_skips_missed_run_but_next_day_runs():
    s, clock, app = setup(datetime(2026, 10, 22, 17, 59, tzinfo=KST))
    clock.t = datetime(2026, 10, 22, 19, 0, tzinfo=KST)  # 절전 후 복귀
    await s.tick()
    assert app.calls == []
    clock.t = datetime(2026, 10, 23, 17, 59, tzinfo=KST)  # 하루 뒤도 한 번 벌어짐
    await s.tick()
    clock.t = datetime(2026, 10, 23, 18, 0, 30, tzinfo=KST)
    await s.tick()
    assert app.calls == [(1, clock.t)]


async def test_missing_task_does_not_abort_tick():
    s, clock, app = setup(datetime(2026, 10, 22, 17, 59, tzinfo=KST))
    s._store._db.execute("PRAGMA foreign_keys = OFF")
    s._store._db.execute("DELETE FROM tasks WHERE id = 1")
    clock.t = datetime(2026, 10, 22, 18, 0, 30, tzinfo=KST)
    await s.tick()
    assert app.calls == []
