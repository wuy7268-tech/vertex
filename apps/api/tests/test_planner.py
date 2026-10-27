from datetime import datetime, timezone

from app.planner import Planner, select_channels
from app.timeutil import SystemClock


def test_briefing_plan_tracks_dependencies():
    planner = Planner(SystemClock())
    steps = planner.plan("Prepare a briefing for tomorrow's design review and draft follow-up tasks")
    by_key = {step.key: step for step in steps}
    assert {"retrieve", "calendar", "inbox", "docs", "github", "notion", "tasks", "synthesize"} <= set(by_key)
    assert by_key["retrieve"].depends_on == []
    for key in ("calendar", "inbox", "docs", "github", "notion", "tasks"):
        assert by_key[key].depends_on == ["retrieve"]
    assert set(by_key["synthesize"].depends_on) >= {"calendar", "inbox", "docs", "github", "notion", "tasks"}


def test_github_digest_stays_narrow():
    steps = Planner(SystemClock()).plan(
        "Weekly GitHub digest\nSummarize open GitHub pull requests and issues and draft review tasks."
    )
    keys = {step.key for step in steps}
    assert keys == {"retrieve", "github", "synthesize"}
    github = next(step for step in steps if step.key == "github")
    assert github.depends_on == ["retrieve"]
    assert next(step for step in steps if step.key == "synthesize").depends_on == ["github"]


def test_schedule_meeting_step_uses_the_requested_hour():
    now = datetime(2026, 10, 27, 15, tzinfo=timezone.utc)
    steps = Planner(SystemClock()).plan('Schedule a meeting called "Launch checklist" tomorrow at 3pm', now)
    event = next(step for step in steps if step.key == "schedule_event")
    assert event.tool_name == "calendar.create_event"
    assert event.cacheable is False
    start = datetime.fromisoformat(event.tool_args["start"])
    assert start.astimezone(start.tzinfo).hour == 15 or start.hour == 15


def test_revise_rewires_dependencies_and_skips_failures():
    planner = Planner(SystemClock())
    steps = planner.plan("Prepare a briefing and draft follow-up tasks")
    for step in steps:
        step.status = "succeeded" if step.key in {"retrieve", "inbox"} else "pending"
    revised = planner.revise(steps, {"broaden": "inbox"}, datetime(2026, 10, 27, tzinfo=timezone.utc))
    by_key = {step.key: step for step in revised}
    assert "inbox_broad" in by_key
    assert by_key["inbox_broad"].tool_args["query"] == "recent"
    assert "inbox" not in by_key["synthesize"].depends_on
    assert "inbox_broad" in by_key["synthesize"].depends_on
    keys = set(by_key)
    for step in revised:
        assert set(step.depends_on) <= keys

    for step in revised:
        step.status = "failed" if step.key == "notion" else step.preset or step.status
    skipped = planner.revise(revised, {"skip": "notion"}, datetime(2026, 10, 27, tzinfo=timezone.utc))
    notion = next(step for step in skipped if step.key == "notion")
    assert notion.preset == "skipped"
    assert all("notion" not in step.depends_on for step in skipped)


def test_channel_selection_for_a_calendar_question():
    reads, synthesize, _meeting = select_channels("What's on my calendar tomorrow?")
    assert reads == ["calendar"]
    assert synthesize is False
