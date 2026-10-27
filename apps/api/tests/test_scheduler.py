from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import Goal, WorkflowRun
from app.scheduler import Scheduler
from app.timeutil import SystemClock
from app.tools import WorkspaceTools


class CountingTools(WorkspaceTools):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def call(self, name, args, *, db, context):
        self.calls += 1
        return super().call(name, args, db=db, context=context)


def test_scheduler_runs_a_due_goal_once_per_window(sessions, make_loop):
    now = datetime(2026, 10, 27, 14, 5, tzinfo=timezone.utc)
    tools = CountingTools()
    loop, _cache, _tools = make_loop(tools)
    loop.clock = SystemClock()
    db = sessions()
    db.add(
        Goal(
            title="Morning briefing",
            description="Prepare a briefing for today and draft follow-up tasks.",
            status="idle",
            schedule="daily@08:00",
            next_run_at=now - timedelta(minutes=1),
        )
    )
    db.commit()
    db.close()
    scheduler = Scheduler(sessions, loop, SystemClock())
    scheduler.tick(now)
    after = tools.calls
    assert after > 0
    db = sessions()
    assert db.scalar(select(func.count()).select_from(WorkflowRun)) == 1
    goal = db.scalar(select(Goal))
    goal.next_run_at = now - timedelta(minutes=1)
    db.commit()
    db.close()
    scheduler.tick(now)
    assert tools.calls == after
    db = sessions()
    assert db.scalar(select(func.count()).select_from(WorkflowRun)) == 1
    db.close()
