from datetime import datetime, timedelta, timezone

from app.timeutil import TZ, as_utc

_DOW = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def schedule_label(schedule: str | None) -> str:
    if not schedule:
        return "Manual"
    if schedule.startswith("daily@"):
        return f"Daily · {_pretty_hm(schedule.split('@', 1)[1])} ET"
    if schedule.startswith("weekly@"):
        _, dow, hm = schedule.split("@")
        return f"Weekly · {dow.title()} {_pretty_hm(hm)} ET"
    return schedule


def window_key(schedule: str, now: datetime) -> str:
    local = as_utc(now).astimezone(TZ)
    if schedule.startswith("weekly@") or _is_weekly_cron(schedule):
        year, week, _ = local.isocalendar()
        return f"{year}-W{week:02d}"
    return local.date().isoformat()


def next_run(schedule: str, now: datetime) -> datetime:
    local = as_utc(now).astimezone(TZ)
    if schedule.startswith("daily@"):
        hour, minute = _hm(schedule.split("@", 1)[1])
        candidate = _next_daily(local, hour, minute)
    elif schedule.startswith("weekly@"):
        _, dow, hm = schedule.split("@")
        hour, minute = _hm(hm)
        candidate = _next_weekday(local, _DOW[dow.lower()], hour, minute)
    else:
        candidate = _next_cron(schedule, local)
    return candidate.astimezone(timezone.utc)


def _next_daily(local: datetime, hour: int, minute: int) -> datetime:
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate


def _next_weekday(local: datetime, weekday: int, hour: int, minute: int) -> datetime:
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta = (weekday - candidate.weekday()) % 7
    candidate += timedelta(days=delta)
    if candidate <= local:
        candidate += timedelta(days=7)
    return candidate


def _next_cron(expr: str, local: datetime) -> datetime:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"Unsupported schedule: {expr}")
    minute_s, hour_s, dom, month, dow = parts
    if dom != "*" or month != "*":
        raise ValueError("Only daily or weekday cron expressions are supported")
    hour, minute = int(hour_s), int(minute_s)
    if dow == "*":
        return _next_daily(local, hour, minute)
    target = int(dow)  # 0 = Sunday
    python_weekday = (target - 1) % 7
    return _next_weekday(local, python_weekday, hour, minute)


def _is_weekly_cron(schedule: str) -> bool:
    parts = schedule.split()
    return len(parts) == 5 and parts[2] == "*" and parts[3] == "*" and parts[4] != "*"


def _hm(value: str) -> tuple[int, int]:
    hour_s, minute_s = value.split(":")
    return int(hour_s), int(minute_s)


def _pretty_hm(value: str) -> str:
    hour, minute = _hm(value)
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{minute:02d} {suffix}"
