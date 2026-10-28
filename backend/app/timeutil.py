"""Campus-local time helpers.

Bookings are stored as IST wall-clock strings "YYYY-MM-DD HH:MM". That format sorts
lexically, so overlap checks are plain string comparisons in SQL.
"""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

CAMPUS_TZ = ZoneInfo("Asia/Kolkata")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def now_campus() -> tuple[str, str]:
    now = datetime.now(CAMPUS_TZ)
    return now.strftime("%Y-%m-%d"), now.strftime("%H:%M")


def to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def from_minutes(mins: int) -> str:
    return f"{mins // 60:02d}:{mins % 60:02d}"


def add_days(day: str, n: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=n)).isoformat()


def weekday(day: str) -> int:
    """0 = Sunday … 6 = Saturday (matches the JS convention the frontend uses)."""
    return (date.fromisoformat(day).weekday() + 1) % 7


def is_valid_date(day: str) -> bool:
    if not isinstance(day, str) or not DATE_RE.match(day):
        return False
    try:
        date.fromisoformat(day)
        return True
    except ValueError:
        return False


def is_valid_time(t: str) -> bool:
    return isinstance(t, str) and bool(TIME_RE.match(t))


def stamp(day: str, time: str) -> str:
    return f"{day} {time}"
