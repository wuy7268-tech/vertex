from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CalendarEvent, Document, GitHubItem, Goal, Integration, Message, Task
from app.retrieval import reindex
from app.schedule import next_run
from app.timeutil import TZ, as_utc, utcnow
from app.tools import INTEGRATIONS


def seed_workspace(db: Session, *, now: datetime | None = None) -> bool:
    if db.scalar(select(Goal.id)):
        return False
    moment = as_utc(now or utcnow())

    for item in INTEGRATIONS:
        db.add(
            Integration(
                provider=item["provider"],
                label=item["label"],
                status="connected",
                mode="builtin",
                last_synced_at=moment,
            )
        )

    briefing = Goal(
        title="Morning briefing",
        description="Prepare a briefing for today: calendar, unread email, open reviews, and follow-up tasks.",
        status="idle",
        schedule="daily@08:00",
        next_run_at=moment - timedelta(minutes=1),
        created_at=moment,
        updated_at=moment,
    )
    review = Goal(
        title="Design review prep",
        description="Prepare a briefing for tomorrow's design review and draft follow-up tasks.",
        status="idle",
        created_at=moment,
        updated_at=moment,
    )
    digest = Goal(
        title="Weekly GitHub digest",
        description="Summarize open GitHub pull requests and issues and draft review tasks.",
        status="idle",
        schedule="weekly@mon@09:00",
        next_run_at=next_run("weekly@mon@09:00", moment),
        created_at=moment,
        updated_at=moment,
    )
    db.add_all([briefing, review, digest])

    def span(days: int, hour: int, minute: int, duration: int = 60):
        local_now = moment.astimezone(TZ)
        day = (local_now + timedelta(days=days)).date()
        start = datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)
        end = start + timedelta(minutes=duration)
        return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

    standup_start, standup_end = span(0, 9, 30, 15)
    focus_start, focus_end = span(0, 13, 0, 60)
    review_start, review_end = span(1, 10, 0, 60)
    one_start, one_end = span(1, 15, 30, 30)
    demo_start, demo_end = span(3, 11, 0, 60)
    people = {
        "maya": {"name": "Maya Chen", "email": "maya@vertex.dev"},
        "omar": {"name": "Omar Farouk", "email": "omar@vertex.dev"},
        "priya": {"name": "Priya Shah", "email": "priya@vertex.dev"},
        "leo": {"name": "Leo Martins", "email": "leo@vertex.dev"},
    }
    db.add_all(
        [
            CalendarEvent(
                external_id="cal-standup",
                title="Team standup",
                description="Short sync on what is blocked.",
                start_at=standup_start,
                end_at=standup_end,
                location="Ithaca office",
                attendees=[people["maya"], people["omar"], people["priya"], people["leo"]],
            ),
            CalendarEvent(
                external_id="cal-focus",
                title="Focus: agent loop",
                description="Deep work on replanning and context compaction.",
                start_at=focus_start,
                end_at=focus_end,
                location="Ithaca office",
                attendees=[],
            ),
            CalendarEvent(
                external_id="cal-design-review",
                title="Design review",
                description="Review the navigation proposal and decide what ships in Friday's demo.",
                start_at=review_start,
                end_at=review_end,
                location="Ithaca office · room 2",
                attendees=[people["maya"], people["omar"]],
            ),
            CalendarEvent(
                external_id="cal-one-on-one",
                title="1:1 with Priya",
                description="Hiring pipeline and the design engineer loop.",
                start_at=one_start,
                end_at=one_end,
                location="Video",
                attendees=[people["priya"]],
            ),
            CalendarEvent(
                external_id="cal-demo",
                title="Demo dry run",
                description="Walk the morning briefing and a resumed agent run.",
                start_at=demo_start,
                end_at=demo_end,
                location="Ithaca office",
                attendees=[people["maya"], people["omar"], people["priya"], people["leo"]],
            ),
        ]
    )

    def mail(external_id, sender, email, subject, body, hours_ago, unread, labels):
        received = moment - timedelta(hours=hours_ago)
        return Message(
            external_id=external_id,
            thread_id=external_id,
            sender_name=sender,
            sender_email=email,
            recipients=[{"name": "Vertex", "email": "work@vertex.dev"}],
            subject=subject,
            snippet=" ".join(body.split())[:160],
            body=body,
            received_at=received,
            unread=unread,
            labels=labels,
        )

    db.add_all(
        [
            mail(
                "mail-maya-nav",
                "Maya Chen",
                "maya@vertex.dev",
                "Navigation proposal for the design review",
                "The pre-read for tomorrow's design review is the navigation proposal. "
                "I want a decision on the left rail, the agent panel, and which empty states we show in the demo. "
                "Please skim it before we sit down — the open question is whether Goals stays in the rail or moves into Today.",
                2,
                True,
                ["inbox", "important"],
            ),
            mail(
                "mail-omar-retry",
                "Omar Farouk",
                "omar@vertex.dev",
                "Retry notes from the retro",
                "From yesterday's retro: a failed GitHub call was starting the whole plan over. "
                "The next run should keep the checkpoint and retry that step with the same idempotency key. "
                "I left the reproduction on issue 138.",
                20,
                True,
                ["inbox"],
            ),
            mail(
                "mail-github-142",
                "GitHub",
                "noreply@github.com",
                "Review requested: vertex#142 Compact agent context",
                "Leo Martins requested your review on vertex-labs/vertex #142. "
                "The change folds old tool results into a short memory after the event log grows.",
                3,
                True,
                ["inbox", "github"],
            ),
            mail(
                "mail-priya",
                "Priya Shah",
                "priya@vertex.dev",
                "Design engineer loop",
                "Sharing the loop for the design engineer role. No action before our 1:1 — I want your read on the portfolio exercise.",
                26,
                False,
                ["inbox"],
            ),
            mail(
                "mail-leo-cache",
                "Leo Martins",
                "leo@vertex.dev",
                "Redis notes for tool caching",
                "Cache key is the tool name, the arguments, and a generation counter. Writes bump the generation so a stale list is not reused. "
                "Identical LLM prompts should hit the same cache.",
                70,
                False,
                ["inbox"],
            ),
        ]
    )

    db.add_all(
        [
            Document(
                external_id="drive-nav",
                source="drive",
                title="Navigation proposal",
                content=(
                    "Navigation proposal for the Vertex workspace. The left rail keeps Today, Tasks, Calendar, "
                    "Inbox, Documents, GitHub, Goals, and Integrations. Today opens on the next meetings, unread mail, "
                    "and the latest agent briefing. Goals is the control surface for the agent: each goal shows its plan, "
                    "dependencies, retries, and the compacted memory. Open question for the design review: does the agent "
                    "panel live on Today, or only inside a goal? Recommendation: a quiet status in the rail, and the full "
                    "trace on the goal. Friday's demo should run the design-review prep live and show a resume after a pause."
                ),
                url="https://drive.google.com/file/d/navigation-proposal",
                updated_at=moment - timedelta(days=1),
            ),
            Document(
                external_id="drive-roadmap",
                source="drive",
                title="Q4 roadmap",
                content=(
                    "Q4 is the agent loop, scheduled morning briefings, and the five connectors: Google Calendar, Gmail, "
                    "Drive, GitHub, and Notion. Semantic search over the workspace is the retrieval step in front of every plan. "
                    "We are not building a second inbox. Vertex reads the systems people already use and writes tasks back."
                ),
                url="https://drive.google.com/file/d/q4-roadmap",
                updated_at=moment - timedelta(days=4),
            ),
            Document(
                external_id="drive-loop",
                source="drive",
                title="Agent loop design notes",
                content=(
                    "A run plans, calls tools, reflects, and replans. Finished steps stay finished. "
                    "The idempotency key is the run, the step, and the arguments. Context compaction replaces raw payloads "
                    "with a short memory once the log gets long. Scheduled goals use a window key so a restart does not run the same morning twice."
                ),
                url="https://drive.google.com/file/d/agent-loop-notes",
                updated_at=moment - timedelta(days=2),
            ),
            Document(
                external_id="notion-principles",
                source="notion",
                title="Design principles",
                content=(
                    "Vertex should feel like a desk, not a chatbot. Show the work the agent did: the plan, the tools, "
                    "the cache hits, the retries. Never hide a failure behind a spinner. Prefer one strong accent and real type."
                ),
                url="https://www.notion.so/vertex/design-principles",
                updated_at=moment - timedelta(days=6),
            ),
            Document(
                external_id="notion-mcp",
                source="notion",
                title="MCP integration checklist",
                content=(
                    "Each connector speaks MCP tools/list and tools/call over HTTP. Built-in servers mirror Calendar, "
                    "Gmail, Drive, GitHub, and Notion for local use. Pointing a connector at a remote MCP URL replaces the built-in tools for that provider."
                ),
                url="https://www.notion.so/vertex/mcp-checklist",
                updated_at=moment - timedelta(days=3),
            ),
        ]
    )

    db.add_all(
        [
            GitHubItem(
                external_id="gh-142",
                kind="pr",
                repo="vertex-labs/vertex",
                number=142,
                title="Compact agent context after tool results",
                body="After the event log passes the threshold, store a short memory of completed steps and stop feeding raw payloads back into planning.",
                state="open",
                author="leo",
                url="https://github.com/vertex-labs/vertex/pull/142",
                updated_at=moment - timedelta(hours=5),
            ),
            GitHubItem(
                external_id="gh-138",
                kind="pr",
                repo="vertex-labs/vertex",
                number=138,
                title="Idempotent step retries",
                body="Retry a failed step with the same idempotency key. A resume must not call a tool whose checkpoint already succeeded.",
                state="open",
                author="omar",
                url="https://github.com/vertex-labs/vertex/pull/138",
                updated_at=moment - timedelta(hours=18),
            ),
            GitHubItem(
                external_id="gh-129",
                kind="issue",
                repo="vertex-labs/vertex",
                number=129,
                title="Invalidate the tool cache when a write lands",
                body="List calls are cached in Redis. Creating an event has to bump the calendar generation so the next list is live.",
                state="open",
                author="priya",
                url="https://github.com/vertex-labs/vertex/issues/129",
                updated_at=moment - timedelta(days=2),
            ),
            GitHubItem(
                external_id="gh-121",
                kind="pr",
                repo="vertex-labs/vertex",
                number=121,
                title="Calendar MCP connector",
                body="Shipped the built-in calendar server and the HTTP MCP client.",
                state="closed",
                author="maya",
                url="https://github.com/vertex-labs/vertex/pull/121",
                updated_at=moment - timedelta(days=9),
            ),
        ]
    )

    review_due, _ = span(1, 9, 0, 30)
    db.add_all(
        [
            Task(
                title="Send the design review pre-read to Maya",
                description="She already mailed the navigation proposal. Confirm the doc link is the one in Drive.",
                status="todo",
                priority="high",
                due_at=review_due,
                source="local",
                created_at=moment,
                updated_at=moment,
            ),
            Task(
                title="Land the Redis cache change",
                description="Generation counters on write, TTL on reads.",
                status="in_progress",
                priority="medium",
                source="local",
                created_at=moment,
                updated_at=moment,
            ),
            Task(
                title="File the AWS invoice",
                description="Low priority. Not part of the design review.",
                status="todo",
                priority="low",
                source="local",
                created_at=moment,
                updated_at=moment,
            ),
        ]
    )
    db.flush()
    reindex(db)
    db.commit()
    return True
