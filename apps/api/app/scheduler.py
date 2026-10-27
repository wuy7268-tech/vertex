import logging
import threading

from sqlalchemy import select

from app.models import Goal, WorkflowRun
from app.schedule import next_run, window_key

log = logging.getLogger("vertex.scheduler")


class Scheduler:
    def __init__(self, sessions, loop, clock):
        self.sessions = sessions
        self.loop = loop
        self.clock = clock
        self._stop = False
        self._event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._event.clear()
        self._thread = threading.Thread(target=self._run, name="vertex-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        self._event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop:
            try:
                self.tick()
            except Exception:
                log.exception("scheduler tick failed")
            if self._event.wait(3):
                return

    def tick(self, now=None) -> None:
        moment = now or self.clock.now()
        db = self.sessions()
        try:
            due = db.scalars(
                select(Goal).where(
                    Goal.schedule.is_not(None),
                    Goal.next_run_at.is_not(None),
                    Goal.next_run_at <= moment,
                )
            ).all()
            jobs = [(goal.id, goal.schedule) for goal in due]
        finally:
            db.close()
        for goal_id, schedule in jobs:
            if self._stop:
                return
            key = f"goal:{goal_id}:{window_key(schedule, moment)}"
            status = self._status_for_key(key)
            try:
                if status in (None,):
                    self.loop.execute(goal_id, idempotency_key=key)
                elif status in ("running", "paused"):
                    self.loop.execute(goal_id, resume=True)
            except Exception:
                log.exception("scheduled goal %s failed", goal_id)
            self._advance_next(goal_id, schedule, moment)

    def _status_for_key(self, key: str) -> str | None:
        db = self.sessions()
        try:
            existing = db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == key))
            return existing.status if existing else None
        finally:
            db.close()

    def _advance_next(self, goal_id: int, schedule: str, now) -> None:
        db = self.sessions()
        try:
            goal = db.get(Goal, goal_id)
            if goal is None:
                return
            goal.next_run_at = next_run(schedule, now)
            goal.last_run_at = now
            db.commit()
        finally:
            db.close()
