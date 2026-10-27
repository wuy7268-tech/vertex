from datetime import datetime, timezone

from app.schedule import next_run, schedule_label, window_key


def test_next_daily_and_weekly_run_in_eastern_time():
    now = datetime(2026, 10, 27, 14, 5, tzinfo=timezone.utc)
    assert next_run("daily@08:00", now) == datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
    # Nov 2 2026 is after the DST fallback, so 9:00 ET is 14:00 UTC.
    assert next_run("weekly@mon@09:00", now) == datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)
    assert next_run("30 8 * * *", now) == datetime(2026, 10, 28, 12, 30, tzinfo=timezone.utc)
    assert next_run("0 9 * * 1", now) == datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)
    assert window_key("daily@08:00", now) == "2026-10-27"
    assert window_key("weekly@mon@09:00", now) == "2026-W44"
    assert schedule_label("daily@08:00") == "Daily · 8:00 AM ET"
    assert schedule_label(None) == "Manual"
