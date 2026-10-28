"""Conflict detection, free-slot search and venue ranking.

Both the booking form's live check and the AI assistant go through analyze(), so every
suggestion a user sees has been checked against the real calendar.
"""

from psycopg import Connection

from .db import venue_dict
from .timeutil import add_days, from_minutes, now_campus, stamp, to_minutes, weekday

ACTIVE = "status IN ('approved', 'pending')"
SLOT_STEP = 30  # minutes


def get_venue(conn: Connection, venue_id: int) -> dict | None:
    return venue_dict(conn.execute("SELECT * FROM venues WHERE id = %s", (venue_id,)).fetchone())


def active_venues(conn: Connection) -> list[dict]:
    return [venue_dict(r) for r in conn.execute("SELECT * FROM venues WHERE active ORDER BY capacity")]


def find_conflicts(conn, venue_id: int, start_ts: str, end_ts: str, exclude_id: int = 0) -> list[dict]:
    rows = conn.execute(
        f"""SELECT id, title, start_ts, end_ts, status, organizer FROM bookings
            WHERE venue_id = %s AND {ACTIVE} AND id != %s AND start_ts < %s AND end_ts > %s
            ORDER BY start_ts""",
        (venue_id, exclude_id, end_ts, start_ts),
    )
    return [dict(r) for r in rows]


def _busy_intervals(conn, venue_id: int, day: str) -> list[tuple[int, int]]:
    rows = conn.execute(
        f"""SELECT start_ts, end_ts FROM bookings
            WHERE venue_id = %s AND {ACTIVE} AND start_ts < %s AND end_ts > %s ORDER BY start_ts""",
        (venue_id, stamp(add_days(day, 1), "00:00"), stamp(day, "00:00")),
    )
    out = []
    for r in rows:
        s = 0 if r["start_ts"][:10] < day else to_minutes(r["start_ts"][11:])
        e = 24 * 60 if r["end_ts"][:10] > day else to_minutes(r["end_ts"][11:])
        out.append((s, e))
    return out


def free_windows(conn, venue: dict, day: str, duration: int) -> list[tuple[int, int]]:
    """Free windows of at least `duration` minutes for one venue on one date."""
    today, now = now_campus()
    if day < today:
        return []
    open_m = to_minutes(venue["open_time"])
    close_m = to_minutes(venue["close_time"])
    if day == today:
        open_m = max(open_m, -(-(to_minutes(now) + 1) // SLOT_STEP) * SLOT_STEP)

    windows, cursor = [], open_m
    for s, e in _busy_intervals(conn, venue["id"], day):
        if s - cursor >= duration:
            windows.append((cursor, s))
        cursor = max(cursor, e)
    if close_m - cursor >= duration:
        windows.append((cursor, close_m))
    return windows


def _slots_for(conn, venue: dict, day: str, duration: int, preferred_start: int) -> list[int]:
    """Candidate start slots inside free windows, ranked by distance from the preferred time."""
    out = []
    for ws, we in free_windows(conn, venue, day, duration):
        s = -(-ws // SLOT_STEP) * SLOT_STEP
        while s + duration <= we:
            out.append(s)
            s += SLOT_STEP
    return sorted(out, key=lambda s: abs(s - preferred_start))


def venue_fit(venue: dict, attendees: int = 0, wanted: list[str] | None = None) -> int | None:
    """Score how well a venue suits an event. Higher is better; None means unsuitable."""
    if attendees and venue["capacity"] < attendees:
        return None
    score = 100
    if attendees:  # prefer rooms that are well-filled, not cavernous
        score -= round((1 - attendees / venue["capacity"]) * 40)
    have = [f.lower() for f in venue["features"]]
    for f in wanted or []:
        score += 10 if any(f.lower() in h for h in have) else -15
    return score


def recommend_venues(conn, attendees: int = 0, features: list[str] | None = None, limit: int = 3) -> list[dict]:
    scored = [(v, venue_fit(v, attendees, features)) for v in active_venues(conn)]
    scored = sorted([x for x in scored if x[1] is not None], key=lambda x: -x[1])[:limit]
    return [{"venue_id": v["id"], "name": v["name"], "capacity": v["capacity"], "score": s} for v, s in scored]


def analyze(conn, venue_id=0, date="", start_time="", end_time="", attendees=0, features=None, exclude_id=0, **_ignored) -> dict:
    """Full availability analysis for a requested booking:
    problems (blocking), warnings (non-blocking) and ranked alternatives."""
    features = features or []
    attendees = int(attendees or 0)
    result = {
        "ok": False, "problems": [], "warnings": [], "conflicts": [],
        "alternatives": {"same_venue": [], "other_venues": [], "other_days": []},
        "recommended_venues": [],
    }
    venue = get_venue(conn, int(venue_id or 0)) if venue_id else None
    if not venue or not venue["active"]:
        result["problems"].append("Choose a venue.")
        result["recommended_venues"] = recommend_venues(conn, attendees, features)
        return result
    if not (date and start_time and end_time):
        result["problems"].append("Choose a date and time.")
        return result

    start, end = to_minutes(start_time), to_minutes(end_time)
    duration = end - start
    today, now = now_campus()
    problems, warnings = result["problems"], result["warnings"]

    if duration <= 0:
        problems.append("End time must be after start time.")
    if date < today or (date == today and start_time <= now):
        problems.append("That time is in the past.")
    if start < to_minutes(venue["open_time"]) or end > to_minutes(venue["close_time"]):
        problems.append(f"{venue['name']} is open {venue['open_time']}–{venue['close_time']}.")
    if attendees and attendees > venue["capacity"]:
        problems.append(f"{venue['name']} seats {venue['capacity']}; you expect {attendees}.")
    elif attendees and attendees < venue["capacity"] * 0.15 and venue["capacity"] > 100:
        warnings.append(f"{venue['name']} ({venue['capacity']} seats) is much larger than {attendees} attendees need.")
    if weekday(date) == 0:
        warnings.append("That date is a Sunday — confirm the campus is open.")

    if duration > 0:
        result["conflicts"] = find_conflicts(conn, venue["id"], stamp(date, start_time), stamp(date, end_time), exclude_id)
        if result["conflicts"]:
            c = result["conflicts"][0]
            problems.append(f'Clashes with "{c["title"]}" ({c["start_ts"][11:]}–{c["end_ts"][11:]}, {c["status"]}).')

    result["ok"] = not problems
    if result["ok"] or duration <= 0:
        if venue["requires_approval"]:
            warnings.append(f"{venue['name']} bookings need admin approval.")
        if attendees:
            result["recommended_venues"] = recommend_venues(conn, attendees, features)
        return result

    alts = result["alternatives"]
    # Same venue, nearby times.
    for s in _slots_for(conn, venue, date, duration, start)[:4]:
        alts["same_venue"].append({"venue_id": venue["id"], "venue": venue["name"], "date": date,
                                   "start_time": from_minutes(s), "end_time": from_minutes(s + duration)})
    # Same time, other suitable venues.
    for v in active_venues(conn):
        score = venue_fit(v, attendees, features)
        if v["id"] == venue["id"] or score is None:
            continue
        if start < to_minutes(v["open_time"]) or end > to_minutes(v["close_time"]):
            continue
        if find_conflicts(conn, v["id"], stamp(date, start_time), stamp(date, end_time)):
            continue
        alts["other_venues"].append({"venue_id": v["id"], "venue": v["name"], "capacity": v["capacity"],
                                     "date": date, "start_time": start_time, "end_time": end_time, "score": score})
    alts["other_venues"] = sorted(alts["other_venues"], key=lambda a: -a["score"])[:3]
    # Same venue and time, following days.
    for d in range(1, 8):
        if len(alts["other_days"]) >= 3:
            break
        day = add_days(date, d)
        slots = _slots_for(conn, venue, day, duration, start)
        if slots and slots[0] == start:
            alts["other_days"].append({"venue_id": venue["id"], "venue": venue["name"], "date": day,
                                       "start_time": start_time, "end_time": end_time})
    return result


def availability_snapshot(conn, from_date: str, days: int) -> list[dict]:
    """Compact list of upcoming bookings, used as context for the AI assistant."""
    rows = conn.execute(
        f"""SELECT b.title, b.event_type, b.status, b.start_ts, b.end_ts, v.name AS venue
            FROM bookings b JOIN venues v ON v.id = b.venue_id
            WHERE b.{ACTIVE} AND b.start_ts >= %s AND b.start_ts < %s ORDER BY b.start_ts""",
        (stamp(from_date, "00:00"), stamp(add_days(from_date, days), "00:00")),
    )
    return [dict(r) for r in rows]
