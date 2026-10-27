from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SystemClock:
    def now(self) -> datetime:
        return utcnow()


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_dt(value: str) -> datetime:
    return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def clock_time(value: datetime) -> str:
    local = as_utc(value).astimezone(TZ)
    hour = local.hour % 12 or 12
    suffix = "AM" if local.hour < 12 else "PM"
    return f"{hour}:{local.minute:02d} {suffix}"


def short_when(start: datetime, end: datetime) -> str:
    local = as_utc(start).astimezone(TZ)
    return f"{local.strftime('%a')} {clock_time(start)}–{clock_time(end)}"


def long_stamp(value: datetime) -> str:
    local = as_utc(value).astimezone(TZ)
    return f"{local.strftime('%A, %B')} {local.day} · {clock_time(value)} ET"


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return as_utc(value).isoformat()
