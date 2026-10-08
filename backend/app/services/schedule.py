"""Schedule math: next run slots in the user's timezone, freshness windows."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models import Frequency

FREQUENCY_WINDOW: dict[str, timedelta] = {
    Frequency.hourly: timedelta(hours=1),
    Frequency.six_hours: timedelta(hours=6),
    Frequency.daily: timedelta(days=1),
    Frequency.weekly: timedelta(days=7),
}

# Value for the Google News `when:` operator.
GOOGLE_WHEN: dict[str, str] = {
    Frequency.hourly: "1h",
    Frequency.six_hours: "6h",
    Frequency.daily: "1d",
    Frequency.weekly: "7d",
}


def _slot_hours(frequency: str, send_hour: int) -> list[int]:
    if frequency == Frequency.hourly:
        return list(range(24))
    if frequency == Frequency.six_hours:
        return sorted((send_hour % 6) + 6 * k for k in range(4))
    return [send_hour]


def compute_next_run(
    frequency: str,
    send_hour: int,
    weekday: int,
    tz_name: str,
    after: datetime,
) -> datetime:
    """Return the first schedule slot strictly after `after`, as an aware UTC datetime.

    Slots are wall-clock hours in the user's timezone (DST-aware):
    hourly -> every hour, 6h -> every 6 hours aligned to send_hour,
    daily -> send_hour every day, weekly -> send_hour on `weekday` (0 = Monday).
    """
    if after.tzinfo is None:
        after = after.replace(tzinfo=UTC)
    tz = ZoneInfo(tz_name)
    local_after = after.astimezone(tz)
    hours = _slot_hours(frequency, send_hour)
    for day_offset in range(0, 9):
        day = local_after.date() + timedelta(days=day_offset)
        if frequency == Frequency.weekly and day.weekday() != weekday:
            continue
        for hour in hours:
            candidate = datetime.combine(day, time(hour), tzinfo=tz).astimezone(UTC)
            if candidate > after:
                return candidate
    raise ValueError("no schedule slot found")  # unreachable for valid input


def freshness_window(frequency: str) -> timedelta:
    return FREQUENCY_WINDOW.get(frequency, timedelta(days=1))
