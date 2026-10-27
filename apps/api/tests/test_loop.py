from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.errors import PermanentToolError, TransientToolError
from app.models import Document, Goal, Message, PlanStep, WorkflowEvent
from app.seed import seed_workspace
from app.tools import WorkspaceTools


class RecordingTools(WorkspaceTools):
    def __init__(self):
        super().__init__()
        self.counts = Counter()
        self.order = []

    def call(self, name, args, *, db, context):
        self.counts[name] += 1
        self.order.append(name)
        return super().call(name, args, db=db, context=context)


class FlakyGitHub(RecordingTools):
    def __init__(self):
        super().__init__()
        self.failures_left = 2

    def call(self, name, args, *, db, context):
        if name == "github.list_items" and self.failures_left:
            self.failures_left -= 1
            self.counts[name] += 1
            self.order.append(name)
            raise TransientToolError("timeout talking to GitHub")
        return super().call(name, args, db=db, context=context)


class NotionDown(RecordingTools):
    def call(self, name, args, *, db, context):
        if name == "notion.search":
            self.counts[name] += 1
            self.order.append(name)
            raise PermanentToolError("Notion MCP rejected the token")
        return super().call(name, args, db=db, context=context)


def _goal(db, title, description=""):
    goal = Goal(title=title, description=description, status="idle")
    db.add(goal)
    db.commit()
    return goal.id


def _events(db, run_id):
    return list(db.scalars(select(WorkflowEvent).where(WorkflowEvent.run_id == run_id).order_by(WorkflowEvent.id)).all())


def test_design_review_respects_dependencies_and_compacts(sessions, make_loop):
    db = sessions()
    seed_workspace(db)
    goal_id = _goal(
        db,
        "Design review prep",
        "Prepare a briefing for tomorrow's design review and draft follow-up tasks.",
    )
    db.close()
    tools = RecordingTools()
    loop, _cache, _tools = make_loop(tools, compact_after=3)
    run = loop.execute(goal_id)
    assert run.status == "completed"
    assert run.compacted_context.startswith("Memory of completed steps:")
    assert tools.order[0] == "retrieval.search"
    assert tools.order[-1] == "agent.synthesize"
    assert tools.order.index("retrieval.search") < tools.order.index("calendar.list_events")
    db = sessions()
    kinds = {event.kind for event in _events(db, run.id)}
    assert {"plan", "tool_call", "checkpoint", "reflection", "compact"} <= kinds
    doc = db.scalar(select(Document).where(Document.external_id == f"briefing:{goal_id}:{run.id}"))
    assert doc is not None
    assert "Design review" in doc.content
    assert "Navigation proposal" in doc.content
    db.close()


def test_resume_does_not_repeat_a_finished_step(sessions, make_loop):
    db = sessions()
    seed_workspace(db)
    goal_id = _goal(db, "Design review prep", "Prepare a briefing for tomorrow's design review and draft follow-up tasks.")
    db.close()
    tools = RecordingTools()
    loop, cache, _tools = make_loop(tools)
    paused = loop.execute(goal_id, stop_after="calendar")
    assert paused.status == "paused"
    calendar_calls = tools.counts["calendar.list_events"]
    assert calendar_calls == 1
    db = sessions()
    step = db.scalar(select(PlanStep).where(PlanStep.plan_id == paused.plan_id, PlanStep.key == "calendar"))
    step.status = "pending"
    db.commit()
    db.close()
    cache.clear()
    resumed = loop.execute(goal_id, resume=True)
    assert resumed.status == "completed"
    assert tools.counts["calendar.list_events"] == calendar_calls
    db = sessions()
    reused = [
        event
        for event in _events(db, resumed.id)
        if event.kind == "checkpoint" and event.step_key == "calendar" and "not called again" in event.message
    ]
    assert reused
    db.close()


def test_transient_failures_retry_the_same_step(sessions, make_loop):
    db = sessions()
    seed_workspace(db)
    goal_id = _goal(db, "Weekly GitHub digest", "Summarize open GitHub pull requests and issues and draft review tasks.")
    db.close()
    tools = FlakyGitHub()
    loop, _cache, _tools = make_loop(tools)
    run = loop.execute(goal_id)
    assert run.status == "completed"
    assert tools.counts["github.list_items"] == 3
    db = sessions()
    retries = [event for event in _events(db, run.id) if event.kind == "retry" and event.step_key == "github"]
    assert len(retries) == 2
    doc = db.scalar(select(Document).where(Document.source == "agent"))
    assert doc is not None
    assert "142" in doc.content
    db.close()


def test_permanent_failure_skips_the_step_and_continues(sessions, make_loop):
    db = sessions()
    seed_workspace(db)
    goal_id = _goal(db, "Design review prep", "Prepare a briefing for tomorrow's design review and draft follow-up tasks.")
    db.close()
    tools = NotionDown()
    loop, _cache, _tools = make_loop(tools)
    run = loop.execute(goal_id)
    assert run.status == "completed"
    assert run.replan_count >= 1
    db = sessions()
    notion = db.scalar(select(PlanStep).where(PlanStep.plan_id == run.plan_id, PlanStep.key == "notion"))
    assert notion.status == "skipped"
    assert any(event.kind == "replan" for event in _events(db, run.id))
    db.close()


def test_empty_inbox_replans_with_a_broader_query(sessions, make_loop):
    db = sessions()
    db.add(
        Message(
            external_id="mail-1",
            sender_name="Omar Farouk",
            sender_email="omar@vertex.dev",
            subject="Retro notes from Omar",
            snippet="The retry bug is still open.",
            body="The retry bug is still open. Please look before standup.",
            received_at=datetime.now(timezone.utc) - timedelta(hours=5),
            unread=False,
        )
    )
    goal_id = _goal(db, "Check unread email and draft follow-up tasks")
    db.close()
    loop, _cache, _tools = make_loop()
    run = loop.execute(goal_id)
    assert run.status == "completed"
    db = sessions()
    assert any(event.kind == "replan" and event.step_key == "inbox" for event in _events(db, run.id))
    doc = db.scalar(select(Document).where(Document.external_id == f"briefing:{goal_id}:{run.id}"))
    assert doc is not None
    assert "Retro notes from Omar" in doc.content
    broad = db.scalar(select(PlanStep).where(PlanStep.plan_id == run.plan_id, PlanStep.key == "inbox_broad"))
    assert broad is not None
    assert broad.status == "succeeded"
    db.close()


def test_cached_reads_are_not_called_twice(sessions, make_loop):
    db = sessions()
    seed_workspace(db)
    first = _goal(db, "What's on my calendar tomorrow?")
    second = _goal(db, "What's on my calendar tomorrow?")
    db.close()
    tools = RecordingTools()
    loop, _cache, _tools = make_loop(tools)
    assert loop.execute(first).status == "completed"
    assert loop.execute(second).status == "completed"
    assert tools.counts["calendar.list_events"] == 1
    db = sessions()
    hits = db.scalars(select(WorkflowEvent).where(WorkflowEvent.kind == "cache_hit", WorkflowEvent.step_key == "calendar")).all()
    assert hits
    db.close()


def test_schedule_meeting_creates_one_event(sessions, make_loop):
    db = sessions()
    goal_id = _goal(db, 'Schedule a meeting called "Launch checklist" tomorrow at 3pm')
    db.close()
    loop, _cache, _tools = make_loop()
    run = loop.execute(goal_id)
    assert run.status == "completed"
    db = sessions()
    from app.models import CalendarEvent
    from app.timeutil import TZ, as_utc

    event = db.scalar(select(CalendarEvent).where(CalendarEvent.title == "Launch checklist"))
    assert event is not None
    assert as_utc(event.start_at).astimezone(TZ).hour == 15
    db.close()
