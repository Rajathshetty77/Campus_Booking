"""AI booking assistant.

Claude reads a natural-language request ("seminar hall for 80 people next Friday 2-4pm") plus a
snapshot of the shared calendar, answers availability questions, and returns a structured booking
draft. The server then runs that draft through scheduler.analyze(), so conflicts and alternatives
are always checked against the database rather than trusted from the model.

Without Claude credentials (or if a call fails) a rule-based parser takes over.
"""

import json
import logging
import os
import re

import anthropic

from .scheduler import active_venues, analyze, availability_snapshot
from .timeutil import add_days, from_minutes, is_valid_date, now_campus, to_minutes, weekday

log = logging.getLogger("ai")

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
EVENT_TYPES = ["Workshop", "Seminar", "Guest Lecture", "Meeting", "Cultural", "Sports",
               "Orientation", "Placement", "Exam", "Club Activity", "Other"]
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

_client: anthropic.AsyncAnthropic | None = None
_disabled_reason: str | None = "disabled by AI_DISABLED" if os.getenv("AI_DISABLED") == "true" else None
if not _disabled_reason:
    # Resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN or an `ant auth login` profile.
    _client = anthropic.AsyncAnthropic()


def ai_status() -> dict:
    enabled = _client is not None and _disabled_reason is None
    return {"enabled": enabled, "model": MODEL if enabled else None, "reason": _disabled_reason}


async def probe_ai() -> dict:
    """Cheap startup probe (no tokens spent) so the UI shows the right mode from the first request."""
    global _disabled_reason
    if _client is None or _disabled_reason:
        return ai_status()
    try:
        await _client.models.retrieve(MODEL)
    except anthropic.APIConnectionError:
        pass  # offline right now; try again on first use
    except anthropic.APIStatusError as e:
        _disabled_reason = f"Claude API error {e.status_code}"
    except Exception:  # the SDK raises a plain error when no credentials can be resolved
        _disabled_reason = "no Claude credentials configured"
    return ai_status()


# Strict structured-output schema. Every field is required; "" / 0 mean "unknown",
# which keeps the schema simple and avoids nullable unions.
DRAFT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reply", "intent", "draft"],
    "properties": {
        "reply": {"type": "string", "description": "Short, friendly answer to show the user (max ~80 words). Plain text."},
        "intent": {"type": "string", "enum": ["book", "query", "other"]},
        "draft": {
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "event_type", "organizer", "description", "venue_id", "date",
                         "start_time", "end_time", "attendees", "features"],
            "properties": {
                "title": {"type": "string"},
                "event_type": {"type": "string", "enum": [*EVENT_TYPES, ""]},
                "organizer": {"type": "string"},
                "description": {"type": "string"},
                "venue_id": {"type": "integer", "description": "0 if no venue chosen yet"},
                "date": {"type": "string", "description": "YYYY-MM-DD or empty"},
                "start_time": {"type": "string", "description": "HH:MM 24h or empty"},
                "end_time": {"type": "string", "description": "HH:MM 24h or empty"},
                "attendees": {"type": "integer", "description": "0 if unknown"},
                "features": {"type": "array", "items": {"type": "string"}, "description": "Facilities asked for, e.g. projector"},
            },
        },
    },
}


def _system_prompt(venues: list[dict]) -> str:
    lines = "\n".join(
        f"- {v['id']} | {v['name']} | {v['block']} | {v['type']} | {v['capacity']} seats | "
        f"{', '.join(v['features'])} | {v['open_time']}-{v['close_time']} | {'approval' if v['requires_approval'] else 'instant'}"
        for v in venues
    )
    return f"""You are the booking assistant for NMAMIT (Nitte), helping students and staff book campus venues for events.
All times are campus local time (IST), 24-hour HH:MM.

Venues (id | name | block | type | capacity | features | opening hours | needs approval):
{lines}

How to respond:
- intent "book" when the user wants to reserve something; fill the draft with everything you can infer. Resolve relative dates ("next Friday", "tomorrow") against today's date given in the message. If they give a start but no end, assume a sensible duration for the event type (meetings 1h, talks/seminars 2h, workshops 3h).
- If they did not name a venue, pick the best-fitting free venue: enough seats, the facilities they mention, not wildly oversized, and no clash in the calendar snapshot.
- intent "query" for questions about availability or what is happening; answer from the calendar snapshot. Leave draft fields empty/0 unless the answer naturally implies a booking.
- intent "other" for anything unrelated to campus bookings; politely steer back.
- Never claim a booking has been made — the user confirms it in the form. Mention clashes you can see in the snapshot.
- Unknown text fields are "", unknown numbers are 0, features is [] when none are mentioned."""


def _calendar_context(conn) -> str:
    today, now = now_campus()
    rows = availability_snapshot(conn, today, 21)
    lines = "\n".join(f"{b['start_ts']}–{b['end_ts'][11:]} | {b['venue']} | {b['title']} ({b['event_type']}, {b['status']})" for b in rows)
    return f"Today is {DAY_NAMES[weekday(today)]} {today}, current time {now}.\nBooked/pending slots for the next 3 weeks:\n{lines or '(none)'}"


async def _ask_claude(conn, message: str, history: list, user) -> dict:
    messages = []
    for h in history[-8:]:
        if isinstance(h, dict) and h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str) and h["content"].strip():
            messages.append({"role": h["role"], "content": h["content"][:2000]})
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    messages.append({
        "role": "user",
        "content": f"{_calendar_context(conn)}\n\nRequester: {user['name']} <{user['email']}>\n\nRequest: {message}",
    })

    response = await _client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": DRAFT_SCHEMA}},
        system=[{"type": "text", "text": _system_prompt(active_venues(conn)), "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    )
    if response.stop_reason == "refusal":
        return {"reply": "I can't help with that request, but I can help you find and book campus venues.", "intent": "other", "draft": None}
    text = "".join(b.text for b in response.content if b.type == "text")
    parsed = json.loads(text)
    if parsed["intent"] == "other":
        parsed["draft"] = None
    return parsed


# ---------- rule-based fallback ----------

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
DAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
DEFAULT_MINUTES = {"Meeting": 60, "Workshop": 180, "Seminar": 120, "Guest Lecture": 120, "Exam": 180, "Sports": 180, "Cultural": 180}
TYPE_PATTERNS = [
    (r"workshop|hands[- ]on|bootcamp", "Workshop"), (r"seminar|talk|webinar", "Seminar"),
    (r"guest lecture|lecture|keynote", "Guest Lecture"), (r"meeting|review|discussion|interview", "Meeting"),
    (r"cultural|dance|music|rehearsal|fest", "Cultural"), (r"sports|match|tournament|badminton|cricket", "Sports"),
    (r"orientation|induction", "Orientation"), (r"placement|recruit|drive", "Placement"),
    (r"exam|test|quiz", "Exam"), (r"club", "Club Activity"),
]
KNOWN_FEATURES = ["projector", "sound system", "stage", "ac", "computers", "video conferencing", "whiteboard", "recording"]


def _parse_date(t: str, today: str) -> str:
    if re.search(r"\bday after tomorrow\b", t):
        return add_days(today, 2)
    if re.search(r"\btomorrow\b", t):
        return add_days(today, 1)
    if re.search(r"\btoday\b|\btonight\b", t):
        return today
    if m := re.search(r"\b\d{4}-\d{2}-\d{2}\b", t):
        return m.group(0) if is_valid_date(m.group(0)) else ""
    if m := re.search(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", t):  # Indian DD/MM order
        y = m.group(3) or today[:4]
        y = "20" + y if len(y) == 2 else y
        d = f"{y}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        if is_valid_date(d):
            return f"{int(y) + 1}{d[4:]}" if d < today and not m.group(3) else d
    mon = "|".join(MONTHS)
    if m := re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({mon})[a-z]*|\b({mon})[a-z]*\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", t):
        day = int(m.group(1) or m.group(4))
        month = MONTHS.index(m.group(2) or m.group(3)) + 1
        d = f"{today[:4]}-{month:02d}-{day:02d}"
        if is_valid_date(d) and d < today:
            d = f"{int(today[:4]) + 1}{d[4:]}"
        if is_valid_date(d):
            return d
    if m := re.search(rf"\b(?:next\s+|this\s+|on\s+)?({'|'.join(DAYS)})\b", t):
        diff = (DAYS.index(m.group(1)) - weekday(today)) % 7
        return add_days(today, diff or 7)  # "Friday" said on a Friday means next week
    return ""


def _to24(h, mins, ampm: str) -> str:
    h, mins = int(h), int(mins or 0)
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    if not ampm and 1 <= h <= 7:
        h += 12  # "from 2 to 4" on a campus almost always means afternoon
    if h > 23 or mins > 59:
        return ""
    return from_minutes(h * 60 + mins)


def _parse_times(t: str) -> tuple[str, str, int]:
    t = re.sub(r"\bnoon\b", "12pm", t)
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:-|–|to|till|until)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t)
    if m and (m.group(3) or m.group(6) or m.group(2) or m.group(5) or re.search(r"\b(from|between)\b", t)):
        end_ampm = m.group(6) or ""
        start_ampm = m.group(3) or ("pm" if end_ampm == "pm" and int(m.group(1)) <= int(m.group(4)) else end_ampm)
        return _to24(m.group(1), m.group(2), start_ampm), _to24(m.group(4), m.group(5), end_ampm), 0

    m = re.search(r"\b(?:at|from|@)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b|\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
    start = _to24(m.group(1) or m.group(4), m.group(2) or m.group(5), m.group(3) or m.group(6) or "") if m else ""
    duration = 0
    if d := re.search(r"\bfor\s+(\d+(?:\.\d+)?|an?|one|two|three|four)\s*(hours?|hrs?|h|minutes?|mins?)\b", t):
        n = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4}.get(d.group(1)) or float(d.group(1))
        duration = int(n if d.group(2).startswith("m") else n * 60)
    if not start:
        for word, default in (("morning", "10:00"), ("afternoon", "14:00"), ("evening", "17:00")):
            if re.search(rf"\b{word}\b", t):
                return default, "", duration
    return start, "", duration


def _rule_based(message: str, venues: list[dict]) -> dict:
    today, _ = now_campus()
    t = message.lower()
    is_query = bool(re.search(r"\b(free|available|availability|vacant|what'?s on|anything|schedule)\b", t)) \
        and not re.search(r"\b(book|reserve|need|want)\b", t)

    date = _parse_date(t, today)
    start, end, duration = _parse_times(t)
    event_type = next((name for pat, name in TYPE_PATTERNS if re.search(pat, t)), "")
    m = re.search(r"\b(\d{1,4})\s*(?:people|persons|participants|students|attendees|members|pax|guests|seats)\b", t)
    attendees = int(m.group(1)) if m else 0
    features = [f if f != "ac" else "AC" for f in KNOWN_FEATURES if re.search(rf"\b{re.escape(f)}\b", t)]

    venue = None
    for v in venues:
        name = v["name"].lower()
        words = [w for w in name.split() if len(w) > 3]
        if name in t or (words and all(w in t for w in words)):
            venue = v
            break
    if not venue:
        type_hits = [v for v in venues if v["type"].lower() in t
                     or (v["type"] == "Lab" and re.search(r"\blab\b", t))
                     or (v["type"] == "Auditorium" and "auditorium" in t)]
        venue = next((v for v in type_hits if not attendees or v["capacity"] >= attendees), None)

    if start and not end:
        mins = duration or DEFAULT_MINUTES.get(event_type, 120)
        end = from_minutes(min(to_minutes(start) + mins, 23 * 60 + 59))

    title = ""
    if q := re.search(r"[\"“]([^\"”]{4,80})[\"”]", message):
        title = q.group(1)
    elif q := re.search(r"\b(?:for|called|titled|named)\s+(?:an?\s+|the\s+)?([a-z][\w &:+-]{3,60}?)(?=\s+(?:on|at|in|from|next|this|tomorrow|today|with|for)\b|[,.]|$)", message, re.I):
        title = q.group(1)[0].upper() + q.group(1)[1:]
    title = title or event_type

    return {
        "intent": "query" if is_query else "book",
        "reply": "",
        "draft": {"title": title, "event_type": event_type, "organizer": "", "description": "",
                  "venue_id": venue["id"] if venue else 0, "date": date, "start_time": start,
                  "end_time": end, "attendees": attendees, "features": features},
    }


def _describe_query(conn, draft: dict, venues: list[dict]) -> str:
    date = draft.get("date") or now_campus()[0]
    if draft.get("venue_id"):
        pool = [v for v in venues if v["id"] == draft["venue_id"]]
    else:
        pool = [v for v in venues if not draft.get("attendees") or v["capacity"] >= draft["attendees"]]
    lines = []
    for v in pool[:6]:
        s, e = draft.get("start_time"), draft.get("end_time")
        res = analyze(conn, venue_id=v["id"], date=date, start_time=s or v["open_time"], end_time=e or v["close_time"])
        if s and e:
            lines.append(f"{v['name']}: {'busy' if res['conflicts'] else 'free'} {s}–{e}")
        else:
            busy = [f"{c['start_ts'][11:]}–{c['end_ts'][11:]}" for c in res["conflicts"]]
            lines.append(f"{v['name']}: {'busy ' + ', '.join(busy) if busy else 'free all day'}")
    return f"Availability on {date}:\n" + "\n".join(lines)


# ---------- entry point ----------

async def assistant(conn, message: str, history: list, user) -> dict:
    global _disabled_reason
    venues = active_venues(conn)
    out, source = None, "rules"
    if _client is not None and not _disabled_reason:
        try:
            out = await _ask_claude(conn, message, history, user)
            source = "claude"
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            _disabled_reason = "Claude credentials were rejected"
        except (anthropic.APIError, json.JSONDecodeError) as e:
            log.warning("Claude call failed, using rule-based parser: %s", e)
        except Exception as e:  # missing credentials surface as a plain error from the SDK
            _disabled_reason = "no Claude credentials configured"
            log.warning("Claude unavailable: %s", e)
    if out is None:
        out = _rule_based(message, venues)

    draft = out.get("draft")
    analysis = None
    if draft and (draft.get("venue_id") or draft.get("date") or draft.get("start_time") or draft.get("attendees")):
        analysis = analyze(conn, **draft)
        # No venue named: pick the best fit that is actually free at the requested time.
        if out["intent"] == "book" and not draft.get("venue_id") and draft.get("date") and draft.get("start_time") and draft.get("end_time"):
            for rec in analysis["recommended_venues"]:
                a = analyze(conn, **{**draft, "venue_id": rec["venue_id"]})
                if a["ok"]:
                    draft["venue_id"], analysis = rec["venue_id"], a
                    break

    if not out.get("reply"):
        if out["intent"] == "query":
            out["reply"] = _describe_query(conn, draft or {}, venues)
        elif analysis and analysis["ok"]:
            name = next((v["name"] for v in venues if v["id"] == draft["venue_id"]), "The venue")
            out["reply"] = f"{name} is free then. Review the draft and confirm."
        elif analysis:
            out["reply"] = "I've drafted this, but: " + " ".join(analysis["problems"])
        else:
            out["reply"] = 'Tell me what you want to book, e.g. "Seminar hall for 80 people next Friday 2–4pm for an AI workshop".'
    return {**out, "analysis": analysis, "source": source}
