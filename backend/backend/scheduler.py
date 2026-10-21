"""스케줄러: 1분마다 깨어 실행할 때가 된 스케줄을 App에 시킨다.
앱이 꺼져 있던 동안의 실행은 따라잡지 않는다 (시작 시각 이전은 보지 않는다)."""
import asyncio
import logging
from datetime import datetime

from .schedule_rule import next_run

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, store, app, clock=lambda: datetime.now().astimezone()):
        self._store = store
        self._app = app
        self._clock = clock
        self._seen = clock()  # 마지막으로 본 시각. 이 뒤의 실행만 센다

    async def tick(self) -> None:
        now = self._clock()
        after, self._seen = self._seen, now
        for s in self._store.all_schedules():
            if not s["enabled"] or next_run(s["rule"], after) > now:
                continue
            if self._store.get_task(s["task_id"])["state"] in ("working", "waiting"):
                log.info("스케줄 %d: 아직 실행 중이라 이번 실행을 건너뜀", s["task_id"])
                continue
            try:
                await self._app.run_schedule(s["task_id"], now)
            except Exception as e:
                log.exception("스케줄 %d: 실행 시작 실패 (%s)", s["task_id"], type(e).__name__)

    async def run_forever(self, interval_s: float = 60) -> None:
        while True:
            await asyncio.sleep(interval_s)
            await self.tick()
