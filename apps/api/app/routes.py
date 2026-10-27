from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CalendarEvent,
    Document,
    GitHubItem,
    Goal,
    Integration,
    Message,
    Plan,
    PlanStep,
    StepResult,
    Task,
    WorkflowEvent,
    WorkflowRun,
)
from app.retrieval import reindex, search
from app.runtime import SessionLocal, agent, cache
from app.schedule import next_run, schedule_label
from app.timeutil import TZ, as_utc, iso, utcnow
from app.tools import INTEGRATIONS, SPECS, provider_for

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    description: str = ""
    priority: str = "medium"
    due_at: str | None = None


class TaskPatch(BaseModel):
    status: str | None = None
    title: str | None = None
    priority: str | None = None


class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    description: str = ""
    schedule: str | None = None


class IntegrationIn(BaseModel):
    mode: str
    mcp_url: str | None = None


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"ok": True, "database": "up", "cache": cache.kind}


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    running = db.scalars(select(Goal).where(Goal.status == "running")).all()
    return {
        "unread": db.scalar(select(func.count()).select_from(Message).where(Message.unread.is_(True))) or 0,
        "open_tasks": db.scalar(select(func.count()).select_from(Task).where(Task.status != "done")) or 0,
        "open_prs": db.scalar(
            select(func.count()).select_from(GitHubItem).where(GitHubItem.kind == "pr", GitHubItem.state == "open")
        )
        or 0,
        "running": bool(running),
        "running_goals": [{"id": goal.id, "title": goal.title} for goal in running],
    }


@router.get("/today")
def today(db: Session = Depends(get_db)):
    now = utcnow()
    start = now.astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=2)
    events = db.scalars(
        select(CalendarEvent)
        .where(CalendarEvent.start_at < end, CalendarEvent.end_at > start)
        .order_by(CalendarEvent.start_at)
    ).all()
    tasks = [task for task in db.scalars(select(Task).where(Task.status != "done")).all()]
    tasks.sort(key=lambda task: ({"high": 0, "medium": 1, "low": 2}.get(task.priority, 3), task.due_at or now + timedelta(days=365)))
    unread = db.scalars(select(Message).where(Message.unread.is_(True)).order_by(Message.received_at.desc()).limit(6)).all()
    pulls = db.scalars(
        select(GitHubItem).where(GitHubItem.kind == "pr", GitHubItem.state == "open").order_by(GitHubItem.updated_at.desc())
    ).all()
    briefing = db.scalar(select(Document).where(Document.source == "agent").order_by(Document.id.desc()))
    return {
        "now": iso(now),
        "events": [_event(row) for row in events],
        "tasks": [_task(row) for row in tasks[:8]],
        "unread": [_message(row) for row in unread],
        "pulls": [_github(row) for row in pulls],
        "goals": [_goal(db, row) for row in db.scalars(select(Goal).order_by(Goal.id)).all()],
        "briefing": _document(briefing, full=True) if briefing else None,
    }


@router.get("/tasks")
def list_tasks(status: str = "open", db: Session = Depends(get_db)):
    stmt = select(Task).order_by(Task.updated_at.desc())
    if status == "open":
        stmt = stmt.where(Task.status != "done")
    elif status != "all":
        stmt = stmt.where(Task.status == status)
    rows = list(db.scalars(stmt).all())
    rows.sort(key=lambda task: ({"high": 0, "medium": 1, "low": 2}.get(task.priority, 3), task.id))
    return {"tasks": [_task(row) for row in rows]}


@router.post("/tasks")
def create_task(body: TaskIn, db: Session = Depends(get_db)):
    if body.priority not in {"low", "medium", "high"}:
        raise HTTPException(400, "Priority must be low, medium, or high")
    task = Task(
        title=body.title.strip(),
        description=body.description,
        priority=body.priority,
        status="todo",
        due_at=_parse_optional(body.due_at),
        source="local",
    )
    db.add(task)
    db.commit()
    cache.incr("gen:tasks")
    return _task(task)


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, body: TaskPatch, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    if body.status is not None:
        if body.status not in {"todo", "in_progress", "done"}:
            raise HTTPException(400, "Unknown task status")
        task.status = body.status
    if body.title is not None:
        task.title = body.title.strip()
    if body.priority is not None:
        if body.priority not in {"low", "medium", "high"}:
            raise HTTPException(400, "Priority must be low, medium, or high")
        task.priority = body.priority
    task.updated_at = utcnow()
    db.commit()
    cache.incr("gen:tasks")
    return _task(task)


@router.get("/calendar")
def calendar(db: Session = Depends(get_db)):
    now = utcnow().astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now + timedelta(days=7)
    rows = db.scalars(
        select(CalendarEvent).where(CalendarEvent.start_at < end, CalendarEvent.end_at > now).order_by(CalendarEvent.start_at)
    ).all()
    return {"events": [_event(row) for row in rows]}


@router.get("/inbox")
def inbox(db: Session = Depends(get_db)):
    rows = db.scalars(select(Message).order_by(Message.received_at.desc())).all()
    return {"messages": [_message(row) for row in rows]}


@router.get("/inbox/{message_id}")
def message_detail(message_id: int, db: Session = Depends(get_db)):
    row = db.get(Message, message_id)
    if row is None:
        raise HTTPException(404, "Message not found")
    if row.unread:
        row.unread = False
        db.commit()
        cache.incr("gen:gmail")
    return _message(row, full=True)


@router.get("/documents")
def documents(source: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Document).order_by(Document.updated_at.desc())
    if source:
        stmt = stmt.where(Document.source == source)
    return {"documents": [_document(row) for row in db.scalars(stmt).all()]}


@router.get("/documents/{document_id}")
def document_detail(document_id: int, db: Session = Depends(get_db)):
    row = db.get(Document, document_id)
    if row is None:
        raise HTTPException(404, "Document not found")
    return _document(row, full=True)


@router.get("/github")
def github(db: Session = Depends(get_db)):
    rows = db.scalars(select(GitHubItem).order_by(GitHubItem.state, GitHubItem.updated_at.desc())).all()
    return {"items": [_github(row, full=True) for row in rows]}


@router.get("/search")
def search_workspace(q: str = "", db: Session = Depends(get_db)):
    query = q.strip()
    if len(query) < 2:
        return {"query": query, "results": []}
    return {"query": query, "results": search(db, query, limit=12)}


@router.get("/goals")
def list_goals(db: Session = Depends(get_db)):
    rows = db.scalars(select(Goal).order_by(Goal.id)).all()
    return {"goals": [_goal(db, row) for row in rows]}


@router.post("/goals")
def create_goal(body: GoalIn, db: Session = Depends(get_db)):
    schedule = (body.schedule or "").strip() or None
    nxt = None
    if schedule:
        try:
            nxt = next_run(schedule, utcnow())
        except (ValueError, KeyError) as exc:
            raise HTTPException(400, f"Unsupported schedule: {schedule}") from exc
    goal = Goal(
        title=body.title.strip(),
        description=body.description.strip(),
        schedule=schedule,
        status="idle",
        next_run_at=nxt,
    )
    db.add(goal)
    db.commit()
    return _goal(db, goal)


@router.get("/goals/{goal_id}")
def goal_detail(goal_id: int, run: int | None = None, db: Session = Depends(get_db)):
    return _goal_detail(db, goal_id, run)


@router.post("/goals/{goal_id}/run")
def run_goal(goal_id: int, resume: bool = False, db: Session = Depends(get_db)):
    if db.get(Goal, goal_id) is None:
        raise HTTPException(404, "Goal not found")
    try:
        agent.execute(goal_id, resume=resume)
    except KeyError as exc:
        raise HTTPException(404, "Goal not found") from exc
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _goal_detail(db, goal_id)


@router.get("/integrations")
def list_integrations(db: Session = Depends(get_db)):
    rows = {row.provider: row for row in db.scalars(select(Integration)).all()}
    payload = []
    for item in INTEGRATIONS:
        row = rows.get(item["provider"])
        tools = [
            {"name": spec.name, "description": spec.description}
            for spec in SPECS
            if provider_for(spec.name) == item["provider"]
        ]
        payload.append(
            {
                "provider": item["provider"],
                "label": item["label"],
                "blurb": item["blurb"],
                "status": row.status if row else "disconnected",
                "mode": row.mode if row else "builtin",
                "mcp_url": row.mcp_url if row else None,
                "last_synced_at": iso(row.last_synced_at) if row else None,
                "tools": tools,
            }
        )
    return {"integrations": payload}


@router.put("/integrations/{provider}")
def update_integration(provider: str, body: IntegrationIn, db: Session = Depends(get_db)):
    known = {item["provider"] for item in INTEGRATIONS}
    if provider not in known:
        raise HTTPException(404, "Unknown connector")
    if body.mode not in {"builtin", "mcp"}:
        raise HTTPException(400, "Mode must be builtin or mcp")
    if body.mode == "mcp" and not (body.mcp_url or "").strip():
        raise HTTPException(400, "A remote MCP URL is required")
    row = db.scalar(select(Integration).where(Integration.provider == provider))
    if row is None:
        label = next(item["label"] for item in INTEGRATIONS if item["provider"] == provider)
        row = Integration(provider=provider, label=label)
        db.add(row)
    row.mode = body.mode
    row.mcp_url = body.mcp_url.strip() if body.mcp_url else None
    row.status = "connected"
    db.commit()
    return {"provider": row.provider, "mode": row.mode, "mcp_url": row.mcp_url, "status": row.status}


@router.post("/integrations/{provider}/sync")
def sync_integration(provider: str, db: Session = Depends(get_db)):
    row = db.scalar(select(Integration).where(Integration.provider == provider))
    if row is None:
        raise HTTPException(404, "Unknown connector")
    catalog = None
    if row.mode == "mcp" and row.mcp_url:
        from app.mcp import HTTPMCPClient

        try:
            catalog = HTTPMCPClient(row.mcp_url).list_tools()
        except Exception as exc:
            raise HTTPException(502, f"MCP sync failed: {exc}") from exc
        row.catalog = catalog if isinstance(catalog, dict) else {"result": catalog}
    else:
        reindex(db)
        cache.incr("gen:retrieval")
    row.last_synced_at = utcnow()
    row.status = "connected"
    db.commit()
    return {"provider": provider, "last_synced_at": iso(row.last_synced_at), "mode": row.mode}


def _goal_detail(db: Session, goal_id: int, run_id: int | None = None) -> dict:
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(404, "Goal not found")
    runs = db.scalars(select(WorkflowRun).where(WorkflowRun.goal_id == goal.id).order_by(WorkflowRun.id.desc())).all()
    selected = next((item for item in runs if item.id == run_id), None) if run_id else (runs[0] if runs else None)
    return {
        "goal": _goal(db, goal),
        "runs": [_run_summary(item) for item in runs],
        "run": _run_detail(db, selected) if selected else None,
    }


def _run_detail(db: Session, run: WorkflowRun) -> dict:
    plans = db.scalars(select(Plan).where(Plan.run_id == run.id).order_by(Plan.version)).all()
    results = {
        row.step_key: row
        for row in db.scalars(select(StepResult).where(StepResult.run_id == run.id)).all()
    }
    events = db.scalars(select(WorkflowEvent).where(WorkflowEvent.run_id == run.id).order_by(WorkflowEvent.id)).all()
    docs = db.scalars(select(Document).where(Document.external_id == f"briefing:{run.goal_id}:{run.id}")).all()
    tasks = db.scalars(select(Task).where(Task.source_ref.like(f"run:{run.id}:%"))).all()
    return {
        "id": run.id,
        "status": run.status,
        "idempotency_key": run.idempotency_key,
        "compacted_context": run.compacted_context,
        "replan_count": run.replan_count,
        "error": run.error,
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
        "plans": [_plan(db, plan, results) for plan in plans],
        "events": [_event_row(row) for row in events],
        "artifacts": {"documents": [_document(row) for row in docs], "tasks": [_task(row) for row in tasks]},
    }


def _plan(db: Session, plan: Plan, results: dict) -> dict:
    steps = db.scalars(select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.order_index)).all()
    payload = []
    for step in steps:
        result = results.get(step.key)
        payload.append(
            {
                "id": step.id,
                "key": step.key,
                "title": step.title,
                "tool_name": step.tool_name,
                "tool_args": step.tool_args,
                "depends_on": step.depends_on or [],
                "status": step.status,
                "attempts": result.attempts if result else step.attempts,
                "cache_hit": bool(result and result.cache_hit),
                "summary": result.summary if result else "",
            }
        )
    _assign_waves(payload)
    return {"id": plan.id, "version": plan.version, "summary": plan.summary, "steps": payload}


def _assign_waves(steps: list[dict]) -> None:
    by_key = {step["key"]: step for step in steps}
    memo: dict[str, int] = {}

    def depth(key: str, trail: set[str]) -> int:
        if key in memo:
            return memo[key]
        if key in trail or key not in by_key:
            return 0
        deps = by_key[key]["depends_on"]
        if not deps:
            memo[key] = 0
            return 0
        memo[key] = 1 + max(depth(dep, trail | {key}) for dep in deps)
        return memo[key]

    for step in steps:
        step["wave"] = depth(step["key"], set())


def _goal(db: Session, goal: Goal) -> dict:
    latest = db.scalar(select(WorkflowRun).where(WorkflowRun.goal_id == goal.id).order_by(WorkflowRun.id.desc()))
    return {
        "id": goal.id,
        "title": goal.title,
        "description": goal.description,
        "status": goal.status,
        "schedule": goal.schedule,
        "schedule_label": schedule_label(goal.schedule),
        "next_run_at": iso(goal.next_run_at),
        "last_run_at": iso(goal.last_run_at),
        "latest_run": _run_summary(latest) if latest else None,
    }


def _run_summary(run: WorkflowRun) -> dict:
    return {
        "id": run.id,
        "status": run.status,
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
        "replan_count": run.replan_count,
        "error": run.error,
    }


def _task(row: Task) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "description": row.description,
        "status": row.status,
        "priority": row.priority,
        "due_at": iso(row.due_at),
        "source": row.source,
        "source_ref": row.source_ref,
        "goal_id": row.goal_id,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def _event(row: CalendarEvent) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "description": row.description,
        "start_at": iso(row.start_at),
        "end_at": iso(row.end_at),
        "location": row.location,
        "attendees": row.attendees or [],
        "source": row.source,
    }


def _message(row: Message, full: bool = False) -> dict:
    payload = {
        "id": row.id,
        "sender_name": row.sender_name,
        "sender_email": row.sender_email,
        "subject": row.subject,
        "snippet": row.snippet,
        "received_at": iso(row.received_at),
        "unread": row.unread,
        "labels": row.labels or [],
    }
    if full:
        payload["body"] = row.body
        payload["recipients"] = row.recipients or []
    return payload


def _document(row: Document, full: bool = False) -> dict:
    payload = {
        "id": row.id,
        "title": row.title,
        "source": row.source,
        "url": row.url,
        "updated_at": iso(row.updated_at),
        "excerpt": " ".join((row.content or "").split())[:220],
    }
    if full:
        payload["content"] = row.content
    return payload


def _github(row: GitHubItem, full: bool = False) -> dict:
    payload = {
        "id": row.id,
        "kind": row.kind,
        "repo": row.repo,
        "number": row.number,
        "title": row.title,
        "state": row.state,
        "author": row.author,
        "url": row.url,
        "updated_at": iso(row.updated_at),
    }
    if full:
        payload["body"] = row.body
    return payload


def _event_row(row: WorkflowEvent) -> dict:
    return {
        "id": row.id,
        "step_key": row.step_key,
        "kind": row.kind,
        "message": row.message,
        "payload": row.payload or {},
        "created_at": iso(row.created_at),
    }


def _parse_optional(value: str | None):
    if not value:
        return None
    from app.timeutil import parse_dt

    return parse_dt(value)
