import hashlib
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mcp import HTTPMCPClient
from app.models import CalendarEvent, Document, GitHubItem, Integration, Message, Task
from app.retrieval import index_record, search
from app.timeutil import TZ, as_utc, long_stamp, parse_dt, short_when, utcnow


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    ttl: int
    cacheable: bool
    namespace: str


SPECS: tuple[ToolSpec, ...] = (
    ToolSpec("retrieval.search", "Semantic search across mail, docs, calendar, GitHub, and tasks", 30, True, "retrieval"),
    ToolSpec("calendar.list_events", "List Google Calendar events in a window", 60, True, "calendar"),
    ToolSpec("calendar.create_event", "Create a Google Calendar event", 0, False, "calendar"),
    ToolSpec("gmail.list_messages", "List Gmail messages", 60, True, "gmail"),
    ToolSpec("gmail.get_message", "Read one Gmail message", 120, True, "gmail"),
    ToolSpec("drive.list_files", "Search Google Drive files", 60, True, "drive"),
    ToolSpec("drive.get_file", "Read one Google Drive file", 120, True, "drive"),
    ToolSpec("github.list_items", "List GitHub issues and pull requests", 60, True, "github"),
    ToolSpec("github.get_item", "Read one GitHub issue or pull request", 120, True, "github"),
    ToolSpec("notion.search", "Search Notion pages", 60, True, "notion"),
    ToolSpec("notion.get_page", "Read one Notion page", 120, True, "notion"),
    ToolSpec("tasks.list", "List workspace tasks", 30, True, "tasks"),
    ToolSpec("tasks.create", "Create a workspace task", 0, False, "tasks"),
    ToolSpec("tasks.complete", "Mark a workspace task done", 0, False, "tasks"),
    ToolSpec("agent.synthesize", "Write a briefing and draft follow-up tasks from prior steps", 0, False, "agent"),
)

SPEC_BY_NAME = {spec.name: spec for spec in SPECS}

INTEGRATIONS = (
    {
        "provider": "google_calendar",
        "label": "Google Calendar",
        "blurb": "Agenda, meetings, and events the agent can read or schedule.",
        "prefix": "calendar.",
    },
    {
        "provider": "gmail",
        "label": "Gmail",
        "blurb": "Inbox threads the agent reads when a goal mentions mail.",
        "prefix": "gmail.",
    },
    {
        "provider": "drive",
        "label": "Google Drive",
        "blurb": "Documents the agent searches and cites in briefings.",
        "prefix": "drive.",
    },
    {
        "provider": "github",
        "label": "GitHub",
        "blurb": "Issues and pull requests the agent turns into review tasks.",
        "prefix": "github.",
    },
    {
        "provider": "notion",
        "label": "Notion",
        "blurb": "Notes and wiki pages included in workspace search.",
        "prefix": "notion.",
    },
)


def provider_for(tool_name: str) -> str | None:
    for item in INTEGRATIONS:
        if tool_name.startswith(item["prefix"]):
            return item["provider"]
    return None


def summarize_result(name: str, result: dict) -> str:
    if name == "agent.synthesize":
        return result.get("summary") or "Filed a briefing."
    items = result.get("items") or []
    if not items:
        return "No records."
    labels = []
    for item in items[:4]:
        labels.append(item.get("title") or item.get("subject") or item.get("name") or "record")
    extra = f" (+{len(items) - 4})" if len(items) > 4 else ""
    return f"{len(items)} records: {', '.join(labels)}{extra}"


class WorkspaceTools:
    def __init__(self, llm=None):
        self.llm = llm

    def names(self) -> list[str]:
        return [spec.name for spec in SPECS]

    def call(self, name: str, args: dict, *, db: Session, context: dict) -> dict:
        handler = {
            "retrieval.search": self._search,
            "calendar.list_events": self._calendar_list,
            "calendar.create_event": self._calendar_create,
            "gmail.list_messages": self._gmail_list,
            "gmail.get_message": self._gmail_get,
            "drive.list_files": self._docs_list,
            "drive.get_file": self._docs_get,
            "github.list_items": self._github_list,
            "github.get_item": self._github_get,
            "notion.search": self._notion_search,
            "notion.get_page": self._notion_get,
            "tasks.list": self._tasks_list,
            "tasks.create": self._tasks_create,
            "tasks.complete": self._tasks_complete,
            "agent.synthesize": self._synthesize,
        }.get(name)
        if handler is None:
            from app.errors import PermanentToolError

            raise PermanentToolError(f"Unknown tool {name}")
        if name == "agent.synthesize":
            return handler(db, args, context)
        return handler(db, args)

    def _search(self, db: Session, args: dict) -> dict:
        items = search(db, args.get("query") or "", int(args.get("limit") or 6))
        return {"items": items, "count": len(items)}

    def _calendar_list(self, db: Session, args: dict) -> dict:
        start = parse_dt(args["start"]) if args.get("start") else utcnow() - timedelta(days=1)
        end = parse_dt(args["end"]) if args.get("end") else start + timedelta(days=7)
        rows = db.scalars(
            select(CalendarEvent)
            .where(CalendarEvent.start_at < end, CalendarEvent.end_at > start)
            .order_by(CalendarEvent.start_at)
        ).all()
        items = [_event_item(row) for row in rows]
        return {"items": items, "count": len(items)}

    def _calendar_create(self, db: Session, args: dict) -> dict:
        title = (args.get("title") or "Untitled").strip()
        start = parse_dt(args["start"])
        end = parse_dt(args["end"]) if args.get("end") else start + timedelta(minutes=45)
        external_id = "sched:" + hashlib.sha256(f"{title}|{start.isoformat()}".encode()).hexdigest()[:16]
        existing = db.scalar(select(CalendarEvent).where(CalendarEvent.external_id == external_id))
        if existing is None:
            existing = CalendarEvent(
                external_id=external_id,
                title=title,
                description=args.get("description") or "",
                start_at=start,
                end_at=end,
                location=args.get("location") or "",
                attendees=args.get("attendees") or [],
                source="google_calendar",
            )
            db.add(existing)
            db.flush()
            index_record(
                db,
                origin="google_calendar",
                source_type="calendar",
                source_id=existing.id,
                title=existing.title,
                text=f"{existing.title} {existing.description}",
            )
        item = _event_item(existing)
        return {"items": [item], "count": 1, "invalidate": ["calendar", "retrieval"], "summary": f"Scheduled {title}."}

    def _gmail_list(self, db: Session, args: dict) -> dict:
        query = (args.get("query") or "recent").lower()
        limit = int(args.get("limit") or 8)
        stmt = select(Message).order_by(Message.received_at.desc())
        if query == "unread":
            stmt = stmt.where(Message.unread.is_(True))
        rows = db.scalars(stmt.limit(limit)).all()
        items = [_mail_item(row) for row in rows]
        return {"items": items, "count": len(items)}

    def _gmail_get(self, db: Session, args: dict) -> dict:
        row = db.get(Message, int(args["id"]))
        if row is None:
            from app.errors import PermanentToolError

            raise PermanentToolError(f"No message {args.get('id')}")
        item = _mail_item(row, full=True)
        return {"items": [item], "count": 1}

    def _docs_list(self, db: Session, args: dict) -> dict:
        return _doc_query(db, "drive", args)

    def _docs_get(self, db: Session, args: dict) -> dict:
        return _doc_get(db, int(args["id"]), "drive")

    def _notion_search(self, db: Session, args: dict) -> dict:
        return _doc_query(db, "notion", args)

    def _notion_get(self, db: Session, args: dict) -> dict:
        return _doc_get(db, int(args["id"]), "notion")

    def _github_list(self, db: Session, args: dict) -> dict:
        state = args.get("state") or "open"
        limit = int(args.get("limit") or 8)
        stmt = select(GitHubItem).order_by(GitHubItem.updated_at.desc())
        if state != "all":
            stmt = stmt.where(GitHubItem.state == state)
        rows = db.scalars(stmt.limit(limit)).all()
        items = [_github_item(row) for row in rows]
        return {"items": items, "count": len(items)}

    def _github_get(self, db: Session, args: dict) -> dict:
        row = db.get(GitHubItem, int(args["id"]))
        if row is None:
            from app.errors import PermanentToolError

            raise PermanentToolError(f"No GitHub item {args.get('id')}")
        return {"items": [_github_item(row, full=True)], "count": 1}

    def _tasks_list(self, db: Session, args: dict) -> dict:
        status = args.get("status") or "open"
        stmt = select(Task).order_by(Task.updated_at.desc())
        if status == "open":
            stmt = stmt.where(Task.status != "done")
        elif status != "all":
            stmt = stmt.where(Task.status == status)
        rows = db.scalars(stmt.limit(int(args.get("limit") or 8))).all()
        items = [_task_item(row) for row in rows]
        return {"items": items, "count": len(items)}

    def _tasks_create(self, db: Session, args: dict) -> dict:
        title = (args.get("title") or "Untitled task").strip()
        ref = args.get("source_ref")
        if ref:
            existing = db.scalar(select(Task).where(Task.source_ref == ref))
            if existing:
                return {"items": [_task_item(existing)], "count": 1, "invalidate": []}
        task = Task(
            title=title,
            description=args.get("description") or "",
            status="todo",
            priority=args.get("priority") or "medium",
            due_at=parse_dt(args["due_at"]) if args.get("due_at") else None,
            source=args.get("source") or "agent",
            source_ref=ref,
            goal_id=args.get("goal_id"),
        )
        db.add(task)
        db.flush()
        index_record(db, origin="task", source_type="task", source_id=task.id, title=task.title, text=task.description)
        return {"items": [_task_item(task)], "count": 1, "invalidate": ["tasks", "retrieval"]}

    def _tasks_complete(self, db: Session, args: dict) -> dict:
        task = db.get(Task, int(args["id"]))
        if task is None:
            from app.errors import PermanentToolError

            raise PermanentToolError(f"No task {args.get('id')}")
        task.status = "done"
        task.updated_at = utcnow()
        return {"items": [_task_item(task)], "count": 1, "invalidate": ["tasks"]}

    def _synthesize(self, db: Session, args: dict, context: dict) -> dict:
        steps = context.get("steps") or {}
        goal_id = context["goal_id"]
        run_id = context["run_id"]
        now = context.get("now") or utcnow()
        external_id = f"briefing:{goal_id}:{run_id}"
        existing = db.scalar(select(Document).where(Document.external_id == external_id))
        if existing:
            return {
                "items": [],
                "count": 0,
                "document_id": existing.id,
                "summary": "Briefing already filed.",
                "invalidate": [],
            }
        emails = _prefer(steps, "inbox")
        events = _prefer(steps, "calendar")
        docs = _prefer(steps, "docs")
        github = _prefer(steps, "github")
        notion = _prefer(steps, "notion")
        tasks = _prefer(steps, "tasks")
        related = (steps.get("retrieve") or {}).get("items") or []
        created = _draft_tasks(db, emails, events, github, goal_id, run_id, now)
        body = _briefing(args.get("goal") or "Briefing", now, events, emails, docs, github, notion, tasks, related, created)
        llm_cache_hit = False
        if self.llm and getattr(self.llm, "enabled", False):
            completed = self.llm.complete(
                "Rewrite this workspace briefing as concise prose. Use only the records given. Do not invent meetings, mail, or tasks.",
                body,
            )
            if completed:
                body, llm_cache_hit = completed
        raw_goal = (args.get("goal") or "Workspace").strip()
        short = raw_goal.split(" Prepare ")[0].split(" prepare ")[0].strip()
        if len(short) > 72:
            short = short[:72].rsplit(" ", 1)[0]
        title = f"Briefing · {short}"
        doc = Document(
            external_id=external_id,
            source="agent",
            title=title,
            content=body,
            url="",
            updated_at=now,
        )
        db.add(doc)
        db.flush()
        doc.url = f"/docs/{doc.id}"
        index_record(db, origin="agent", source_type="document", source_id=doc.id, title=doc.title, text=doc.content)
        if not created:
            summary = "Filed a briefing."
        elif len(created) == 1:
            summary = "Filed a briefing and 1 follow-up task."
        else:
            summary = f"Filed a briefing and {len(created)} follow-up tasks."
        if llm_cache_hit:
            summary += " Reused a cached model response."
        return {
            "items": created,
            "count": len(created),
            "document_id": doc.id,
            "summary": summary,
            "llm_cache_hit": llm_cache_hit,
            "invalidate": ["docs", "tasks", "retrieval"],
        }


class ToolRouter:
    def __init__(self, workspace: WorkspaceTools):
        self.workspace = workspace

    def names(self) -> list[str]:
        return [spec.name for spec in SPECS]

    def call(self, name: str, args: dict, *, db: Session, context: dict) -> dict:
        provider = provider_for(name)
        if provider:
            integration = db.scalar(select(Integration).where(Integration.provider == provider))
            if integration and integration.mode == "mcp" and integration.mcp_url:
                return HTTPMCPClient(integration.mcp_url).call(name, args)
        return self.workspace.call(name, args, db=db, context=context)


def _draft_tasks(db, emails, events, github, goal_id, run_id, now) -> list[dict]:
    created: list[dict] = []
    horizon = as_utc(now) + timedelta(hours=36)
    due = (as_utc(now).astimezone(TZ) + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)

    def add(title: str, description: str, priority: str, due_at, ref: str) -> None:
        if len(created) >= 8:
            return
        if db.scalar(select(Task).where(Task.source_ref == ref)):
            return
        duplicate = db.scalar(select(Task).where(Task.title == title, Task.status != "done"))
        if duplicate:
            return
        task = Task(
            title=title,
            description=description,
            status="todo",
            priority=priority,
            due_at=as_utc(due_at) if due_at else None,
            source="agent",
            source_ref=ref,
            goal_id=goal_id,
        )
        db.add(task)
        db.flush()
        index_record(db, origin="task", source_type="task", source_id=task.id, title=task.title, text=description)
        created.append(_task_item(task))

    for message in emails:
        sender = (message.get("sender") or "").lower()
        email = (message.get("email") or "").lower()
        if not message.get("unread"):
            continue
        if "github" in sender or "noreply" in email or "no-reply" in email:
            continue
        add(
            f"Reply to {message.get('sender')}: {message.get('subject')}",
            message.get("snippet") or "",
            "high",
            due,
            f"run:{run_id}:mail:{message.get('id')}",
        )
    for item in github:
        if item.get("state") != "open":
            continue
        kind = item.get("kind")
        if kind == "pr":
            add(
                f"Review {item.get('repo')}#{item.get('number')}: {item.get('title')}",
                item.get("excerpt") or "",
                "high",
                due,
                f"run:{run_id}:gh:{item.get('id')}",
            )
        elif kind == "issue":
            add(
                f"Triage {item.get('repo')}#{item.get('number')}: {item.get('title')}",
                item.get("excerpt") or "",
                "medium",
                due,
                f"run:{run_id}:gh:{item.get('id')}",
            )
    for event in events:
        title = event.get("title") or ""
        if any(word in title.lower() for word in ("standup", "focus")):
            continue
        start = parse_dt(event["start"]) if event.get("start") else None
        if start is None or start > horizon or start < as_utc(now):
            continue
        add(
            f"Prepare for {title}",
            event.get("excerpt") or "",
            "high",
            start,
            f"run:{run_id}:cal:{event.get('id')}",
        )
    return created


def _briefing(goal, now, events, emails, docs, github, notion, tasks, related, created) -> str:
    short = goal.strip().split(" Prepare ")[0].split(" prepare ")[0].strip()
    lines = [
        "# Briefing",
        short,
        long_stamp(now),
        "",
    ]
    _section(lines, "Schedule", [_fmt_event(item) for item in events])
    _section(lines, "Inbox", [_fmt_mail(item) for item in emails])
    _section(lines, "Documents", [_fmt_doc(item) for item in docs])
    _section(lines, "GitHub", [_fmt_github(item) for item in github])
    _section(lines, "Notion", [_fmt_doc(item) for item in notion])
    _section(lines, "Open tasks", [f"- {item.get('title')} ({item.get('priority')})" for item in tasks])
    _section(lines, "Related", [f"- {item.get('title')} · {item.get('origin')}" for item in related[:5]])
    _section(lines, "Follow-ups drafted", [f"- {item.get('title')}" for item in created])
    if len(lines) <= 4:
        lines.append("Nothing in the workspace matched this goal.")
    return "\n".join(lines).strip() + "\n"


def _section(lines: list[str], title: str, rows: list[str]) -> None:
    rows = [row for row in rows if row]
    if not rows:
        return
    lines.append(f"## {title}")
    lines.extend(rows)
    lines.append("")


def _fmt_event(item: dict) -> str:
    people = ", ".join(item.get("attendees") or [])
    suffix = f" · {people}" if people else ""
    return f"- {item.get('when')} · {item.get('title')}{suffix}"


def _fmt_mail(item: dict) -> str:
    flag = "unread" if item.get("unread") else "read"
    return f"- {item.get('sender')} — {item.get('subject')} ({flag})"


def _fmt_doc(item: dict) -> str:
    excerpt = item.get("excerpt") or ""
    return f"- {item.get('title')}" + (f" — {excerpt}" if excerpt else "")


def _fmt_github(item: dict) -> str:
    return f"- {item.get('repo')}#{item.get('number')} {item.get('title')} ({item.get('state')} {item.get('kind')})"


def _prefer(steps: dict, key: str) -> list:
    broad = steps.get(f"{key}_broad") or {}
    if broad.get("items"):
        return broad["items"]
    return (steps.get(key) or {}).get("items") or []


def _doc_query(db: Session, source: str, args: dict) -> dict:
    query = (args.get("query") or "").lower().strip()
    limit = int(args.get("limit") or 6)
    rows = db.scalars(select(Document).where(Document.source == source).order_by(Document.updated_at.desc())).all()
    if query:
        words = [word for word in query.split() if word]
        rows = [row for row in rows if all(word in f"{row.title} {row.content}".lower() for word in words)] or [
            row for row in rows if any(word in f"{row.title} {row.content}".lower() for word in words)
        ]
    items = [_doc_item(row) for row in rows[:limit]]
    return {"items": items, "count": len(items)}


def _doc_get(db: Session, doc_id: int, source: str) -> dict:
    row = db.get(Document, doc_id)
    if row is None or row.source != source:
        from app.errors import PermanentToolError

        raise PermanentToolError(f"No {source} document {doc_id}")
    return {"items": [_doc_item(row, full=True)], "count": 1}


def _event_item(row: CalendarEvent) -> dict:
    when = short_when(row.start_at, row.end_at)
    return {
        "id": row.id,
        "title": row.title,
        "start": as_utc(row.start_at).isoformat(),
        "end": as_utc(row.end_at).isoformat(),
        "when": when,
        "location": row.location,
        "attendees": [person.get("name") for person in (row.attendees or []) if person.get("name")],
        "excerpt": (row.description or "")[:180],
    }


def _mail_item(row: Message, full: bool = False) -> dict:
    item = {
        "id": row.id,
        "sender": row.sender_name,
        "email": row.sender_email,
        "subject": row.subject,
        "snippet": row.snippet,
        "received_at": as_utc(row.received_at).isoformat(),
        "unread": row.unread,
    }
    if full:
        item["body"] = row.body
    return item


def _doc_item(row: Document, full: bool = False) -> dict:
    item = {
        "id": row.id,
        "title": row.title,
        "source": row.source,
        "excerpt": " ".join((row.content or "").split())[:180],
        "url": row.url,
    }
    if full:
        item["content"] = row.content
    return item


def _github_item(row: GitHubItem, full: bool = False) -> dict:
    item = {
        "id": row.id,
        "kind": row.kind,
        "repo": row.repo,
        "number": row.number,
        "title": row.title,
        "state": row.state,
        "author": row.author,
        "url": row.url,
        "excerpt": " ".join((row.body or "").split())[:180],
    }
    if full:
        item["body"] = row.body
    return item


def _task_item(row: Task) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "status": row.status,
        "priority": row.priority,
        "due_at": as_utc(row.due_at).isoformat() if row.due_at else None,
    }
