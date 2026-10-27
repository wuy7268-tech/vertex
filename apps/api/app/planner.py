import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.llm import parse_json_object
from app.timeutil import TZ, as_utc

_MEETING = re.compile(
    r"schedule\s+(?:a\s+)?(?:meeting\s+)?(?:called\s+|titled\s+)?[\"']([^\"']+)[\"']\s+tomorrow\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
    re.I,
)


@dataclass
class PlannedStep:
    key: str
    title: str
    tool_name: str
    tool_args: dict
    depends_on: list[str]
    cacheable: bool = True
    status: str = "pending"
    preset: str | None = None
    order_index: int = 0


@dataclass
class Planner:
    clock: object
    llm: object | None = None
    tool_names: list[str] = field(default_factory=list)
    last_source: str = "heuristic"

    def plan(self, text: str, now: datetime | None = None) -> list[PlannedStep]:
        moment = now or self.clock.now()
        steps = self._heuristic(text, moment)
        self.last_source = "heuristic"
        if self.llm and getattr(self.llm, "enabled", False) and self.tool_names:
            alternative = self._from_model(text, moment)
            if alternative and _valid(alternative, set(self.tool_names)):
                steps = alternative
                self.last_source = "llm"
        for index, step in enumerate(steps):
            step.order_index = index
        return steps

    def revise(self, steps, hint: dict, now: datetime) -> list[PlannedStep]:
        drafts = [_copy_step(step) for step in steps]
        broaden_key = hint.get("broaden")
        if broaden_key:
            original = next(step for step in drafts if step.key == broaden_key)
            new_key = f"{broaden_key}_broad"
            if not any(step.key == new_key for step in drafts):
                broad = PlannedStep(
                    key=new_key,
                    title=f"{original.title} (broader)",
                    tool_name=original.tool_name,
                    tool_args=_broaden_args(original.tool_name, original.tool_args, now),
                    depends_on=list(original.depends_on),
                    cacheable=original.cacheable,
                )
                index = next(i for i, step in enumerate(drafts) if step.key == broaden_key)
                drafts.insert(index + 1, broad)
                for step in drafts:
                    step.depends_on = [new_key if dep == broaden_key else dep for dep in step.depends_on]
        skip_key = hint.get("skip")
        if skip_key:
            for step in drafts:
                if step.key == skip_key:
                    step.preset = "skipped"
        skipped = {step.key for step in drafts if step.preset == "skipped"}
        for step in drafts:
            step.depends_on = [dep for dep in step.depends_on if dep not in skipped]
        rest = [step for step in drafts if step.key != "synthesize"]
        synth = [step for step in drafts if step.key == "synthesize"]
        drafts = rest + synth
        for index, step in enumerate(drafts):
            step.order_index = index
        return drafts

    def _heuristic(self, text: str, now: datetime) -> list[PlannedStep]:
        reads, synthesize, meeting = select_channels(text)
        local = as_utc(now).astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        steps = [
            PlannedStep(
                key="retrieve",
                title="Retrieve related workspace context",
                tool_name="retrieval.search",
                tool_args={"query": " ".join(text.split())[:240], "limit": 6},
                depends_on=[],
            )
        ]
        catalog = {
            "calendar": (
                "Read the calendar",
                "calendar.list_events",
                {"start": local.isoformat(), "end": (local + timedelta(days=7)).isoformat()},
            ),
            "inbox": (
                "Read email",
                "gmail.list_messages",
                {"query": "unread" if re.search(r"\bunread\b", text.lower()) else "recent", "limit": 8},
            ),
            "docs": ("Search Drive", "drive.list_files", {"query": _keywords(text), "limit": 6}),
            "github": ("Read GitHub", "github.list_items", {"state": "open", "limit": 8}),
            "notion": ("Search Notion", "notion.search", {"query": _keywords(text), "limit": 5}),
            "tasks": ("Read open tasks", "tasks.list", {"status": "open", "limit": 8}),
        }
        read_keys = []
        for name in reads:
            title, tool_name, args = catalog[name]
            steps.append(
                PlannedStep(
                    key=name,
                    title=title,
                    tool_name=tool_name,
                    tool_args=args,
                    depends_on=["retrieve"],
                )
            )
            read_keys.append(name)
        if meeting:
            title, hour, minute = meeting
            start = (local + timedelta(days=1)).replace(hour=hour, minute=minute)
            end = start + timedelta(minutes=45)
            steps.append(
                PlannedStep(
                    key="schedule_event",
                    title=f"Schedule {title}",
                    tool_name="calendar.create_event",
                    tool_args={
                        "title": title,
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "description": "Scheduled by Vertex from a goal.",
                    },
                    depends_on=["calendar"] if "calendar" in read_keys else ["retrieve"],
                    cacheable=False,
                )
            )
            read_keys.append("schedule_event")
        if synthesize:
            steps.append(
                PlannedStep(
                    key="synthesize",
                    title="Draft the briefing and follow-up tasks",
                    tool_name="agent.synthesize",
                    tool_args={"goal": " ".join(text.split())[:500]},
                    depends_on=read_keys,
                    cacheable=False,
                )
            )
        return steps

    def _from_model(self, text: str, now: datetime) -> list[PlannedStep] | None:
        system = (
            "You plan tool calls for a workspace agent. Return JSON only: "
            '{"steps":[{"key":"","title":"","tool_name":"","tool_args":{},"depends_on":[]}]} . '
            "Use only the provided tools. Keep reads parallel under a retrieve step. "
            "Writes and synthesis depend on the reads they need."
        )
        user = f"Tools: {', '.join(self.tool_names)}\nNow: {as_utc(now).isoformat()}\nGoal: {text}"
        completed = self.llm.complete(system, user)
        if not completed:
            return None
        raw, _hit = completed
        parsed = parse_json_object(raw)
        if not parsed or not isinstance(parsed.get("steps"), list):
            return None
        steps = []
        for item in parsed["steps"]:
            if not isinstance(item, dict):
                return None
            steps.append(
                PlannedStep(
                    key=str(item.get("key") or ""),
                    title=str(item.get("title") or item.get("key") or "Step"),
                    tool_name=str(item.get("tool_name") or ""),
                    tool_args=item.get("tool_args") if isinstance(item.get("tool_args"), dict) else {},
                    depends_on=[str(dep) for dep in item.get("depends_on") or []],
                    cacheable=not str(item.get("tool_name") or "").startswith(("agent.", "calendar.create", "tasks.")),
                )
            )
        return steps


def select_channels(text: str) -> tuple[list[str], bool, tuple[str, int, int] | None]:
    lowered = text.lower()
    meeting = _meeting(text)
    if _has(lowered, "github") and _has(lowered, "digest"):
        return ["github"], True, meeting
    broad = _has(lowered, "brief", "briefing", "prepare", "prep") or "catch up" in lowered
    reads: list[str] = []

    def add(name: str) -> None:
        if name not in reads:
            reads.append(name)

    if broad or _has(lowered, "calendar", "meeting", "agenda", "tomorrow", "standup"):
        add("calendar")
    if broad or _has(lowered, "email", "inbox", "mail", "unread", "gmail"):
        add("inbox")
    if broad or _has(lowered, "document", "documents", "docs", "drive", "proposal") or "pre-read" in lowered:
        add("docs")
    if broad or _has(lowered, "github", "issue", "pr") or "pull request" in lowered:
        add("github")
    if broad or _has(lowered, "notion", "wiki"):
        add("notion")
    if broad or _has(lowered, "task", "tasks", "todo"):
        add("tasks")
    if not reads:
        reads = ["calendar", "inbox", "tasks"]
    synthesize = broad or _has(lowered, "digest", "draft", "todo", "task", "tasks") or "follow up" in lowered or "follow-up" in lowered
    if broad:
        for name in ("calendar", "inbox", "docs", "github", "notion", "tasks"):
            add(name)
    return reads, synthesize, meeting


def _meeting(text: str) -> tuple[str, int, int] | None:
    match = _MEETING.search(text)
    if not match:
        return None
    title, hour_s, minute_s, ampm = match.groups()
    hour = int(hour_s)
    minute = int(minute_s or 0)
    if ampm and ampm.lower() == "pm" and hour < 12:
        hour += 12
    if ampm and ampm.lower() == "am" and hour == 12:
        hour = 0
    return title.strip(), hour, minute


def _copy_step(step) -> PlannedStep:
    status = getattr(step, "status", "pending")
    preset = None
    if status == "succeeded":
        preset = "succeeded"
    elif status in ("skipped", "failed"):
        preset = "skipped"
    return PlannedStep(
        key=step.key,
        title=step.title,
        tool_name=step.tool_name,
        tool_args=dict(step.tool_args or {}),
        depends_on=list(step.depends_on or []),
        cacheable=bool(step.cacheable),
        status=status,
        preset=preset,
    )


def _broaden_args(tool_name: str, args: dict, now: datetime) -> dict:
    widened = dict(args)
    if tool_name == "gmail.list_messages":
        widened["query"] = "recent"
        widened["limit"] = 12
    elif tool_name == "drive.list_files":
        widened["query"] = ""
        widened["limit"] = 8
    elif tool_name == "github.list_items":
        widened["state"] = "all"
        widened["limit"] = 10
    elif tool_name == "notion.search":
        widened["query"] = ""
        widened["limit"] = 8
    elif tool_name == "calendar.list_events":
        local = as_utc(now).astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        widened["start"] = (local - timedelta(days=1)).isoformat()
        widened["end"] = (local + timedelta(days=14)).isoformat()
    return widened


def _keywords(text: str) -> str:
    stop = {
        "a", "an", "the", "for", "and", "or", "to", "of", "my", "me", "on", "in", "with",
        "prepare", "prep", "brief", "briefing", "draft", "follow", "up", "follow-up",
        "today", "tomorrow", "task", "tasks", "please", "from",
    }
    words = [word for word in re.findall(r"[a-z0-9']+", text.lower()) if word not in stop]
    return " ".join(words[:8])


def _has(text: str, *phrases: str) -> bool:
    for phrase in phrases:
        if " " in phrase or "-" in phrase:
            if phrase in text:
                return True
        elif re.search(rf"\b{re.escape(phrase)}\b", text):
            return True
    return False


def _valid(steps: list[PlannedStep], known: set[str]) -> bool:
    keys = [step.key for step in steps]
    if not keys or len(keys) != len(set(keys)):
        return False
    keyset = set(keys)
    graph = {}
    for step in steps:
        if step.tool_name not in known or not step.key:
            return False
        if any(dep not in keyset for dep in step.depends_on):
            return False
        graph[step.key] = step.depends_on
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(key: str) -> bool:
        if key in visiting:
            return False
        if key in visited:
            return True
        visiting.add(key)
        for dep in graph[key]:
            if not walk(dep):
                return False
        visiting.remove(key)
        visited.add(key)
        return True

    return all(walk(key) for key in keys)
