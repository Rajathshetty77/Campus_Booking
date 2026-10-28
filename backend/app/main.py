import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # before modules that read env at import

from fastapi import Depends, FastAPI, HTTPException, Request, Response  # noqa: E402
from fastapi.responses import JSONResponse, PlainTextResponse  # noqa: E402
from psycopg import Connection  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from . import auth  # noqa: E402
from .ai import EVENT_TYPES, ai_status, assistant, probe_ai  # noqa: E402
from .db import close_pool, connection, get_db, init_db, venue_dict  # noqa: E402
from .scheduler import analyze, get_venue  # noqa: E402
from .timeutil import add_days, is_valid_date, is_valid_time, now_campus, stamp  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with connection() as conn:
        auth.purge_expired(conn)
        if auth.bootstrap_admin(conn):
            print(f"Admin account is configured for {auth.INITIAL_ADMIN_EMAIL}.", flush=True)
        elif auth.INITIAL_ADMIN_EMAIL in auth.ADMIN_EMAILS:
            print("Set ADMIN_INITIAL_PASSWORD in backend/.env to bootstrap the initial admin account.", flush=True)
    status = await probe_ai()
    print(f"AI assistant: {'Claude (' + status['model'] + ')' if status['enabled'] else 'rule-based fallback (' + str(status['reason']) + ')'}", flush=True)
    if not auth.ADMIN_EMAILS:
        print("Tip: set ADMIN_EMAILS in backend/.env to give an account admin rights.", flush=True)
    yield
    close_pool()


app = FastAPI(title="NMAMIT Campus Booking API", lifespan=lifespan)

DB = Depends(get_db)
USER = Depends(auth.current_user)
ADMIN = Depends(auth.admin_user)


@app.exception_handler(HTTPException)
async def http_error(_req: Request, exc: HTTPException):
    body = exc.detail if isinstance(exc.detail, dict) else {"error": exc.detail}
    return JSONResponse(body, status_code=exc.status_code)


# ---------- auth ----------

class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class RegisterIn(LoginIn):
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=80)


@app.get("/api/config")
def config(conn: Connection = DB, user=Depends(auth.optional_user)):
    return {
        "allowedDomains": auth.ALLOWED_DOMAINS,
        "ai": ai_status(),
        "eventTypes": EVENT_TYPES,
        "today": now_campus()[0],
        "user": auth.public_user(user),
    }


@app.post("/api/auth/register", status_code=201)
def register(body: RegisterIn, response: Response, conn: Connection = DB):
    return auth.register(conn, response, body.email, body.password, body.name)


@app.post("/api/auth/login")
def login(body: LoginIn, response: Response, conn: Connection = DB):
    return auth.password_sign_in(conn, response, body.email, body.password)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, conn: Connection = DB):
    return auth.logout(conn, request, response)


@app.get("/api/me")
def me(user=USER):
    return {"user": auth.public_user(user)}


# ---------- venues ----------

class VenueIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    block: str = ""
    type: str = "Room"
    capacity: int = Field(ge=1, le=100000)
    features: list[str] = []
    color: str = "#64748b"
    requires_approval: bool = True
    open_time: str = "08:00"
    close_time: str = "20:00"
    active: bool = True

    def clean(self) -> tuple:
        if not is_valid_time(self.open_time) or not is_valid_time(self.close_time) or self.open_time >= self.close_time:
            raise HTTPException(400, "Opening time must be before closing time.")
        color = self.color if re.fullmatch(r"#[0-9a-fA-F]{6}", self.color) else "#64748b"
        features = [f.strip() for f in self.features if f.strip()]
        return (self.name.strip(), self.block.strip(), self.type.strip() or "Room", self.capacity, Jsonb(features),
                color, self.requires_approval, self.open_time, self.close_time, self.active)


@app.get("/api/venues")
def list_venues(all: int = 0, conn: Connection = DB, user=USER):
    show_all = all == 1 and user["role"] == "admin"
    rows = conn.execute(f"SELECT * FROM venues {'' if show_all else 'WHERE active'} ORDER BY name")
    return [venue_dict(r) for r in rows]


@app.post("/api/venues", status_code=201)
def create_venue(body: VenueIn, conn: Connection = DB, _admin=ADMIN):
    row = conn.execute(
        """INSERT INTO venues (name, block, type, capacity, features, color, requires_approval, open_time, close_time, active)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""", body.clean()).fetchone()
    return venue_dict(row)


@app.put("/api/venues/{venue_id}")
def update_venue(venue_id: int, body: VenueIn, conn: Connection = DB, _admin=ADMIN):
    row = conn.execute(
        """UPDATE venues SET name = %s, block = %s, type = %s, capacity = %s, features = %s, color = %s,
           requires_approval = %s, open_time = %s, close_time = %s, active = %s WHERE id = %s RETURNING *""",
        (*body.clean(), venue_id)).fetchone()
    if not row:
        raise HTTPException(404, "Venue not found.")
    return venue_dict(row)


# ---------- bookings / common calendar ----------

BOOKING_SELECT = """
  SELECT b.*, v.name AS venue_name, v.color AS venue_color, u.name AS booked_by, u.email AS booked_by_email
  FROM bookings b JOIN venues v ON v.id = b.venue_id JOIN users u ON u.id = b.user_id"""


def shape_booking(b, viewer) -> dict:
    mine = b["user_id"] == viewer["id"]
    return {
        "id": b["id"], "title": b["title"], "description": b["description"], "event_type": b["event_type"],
        "organizer": b["organizer"], "venue_id": b["venue_id"], "venue_name": b["venue_name"],
        "venue_color": b["venue_color"], "start": b["start_ts"], "end": b["end_ts"], "attendees": b["attendees"],
        "status": b["status"], "admin_note": b["admin_note"], "booked_by": b["booked_by"],
        "booked_by_email": b["booked_by_email"], "created_at": b["created_at"], "mine": mine,
        "can_cancel": (mine or viewer["role"] == "admin") and b["status"] in ("pending", "approved"),
    }


@app.get("/api/bookings")
def calendar(start: str, end: str, conn: Connection = DB, user=USER):
    """The common calendar: every approved and pending booking in a date range, visible to all signed-in users."""
    if not (is_valid_date(start) and is_valid_date(end)):
        raise HTTPException(400, "start and end must be YYYY-MM-DD.")
    rows = conn.execute(
        f"""{BOOKING_SELECT} WHERE b.status IN ('approved', 'pending') AND b.start_ts < %s AND b.end_ts > %s
            ORDER BY b.start_ts""", (stamp(end, "23:59"), stamp(start, "00:00")))
    return [shape_booking(b, user) for b in rows]


@app.get("/api/bookings/mine")
def my_bookings(conn: Connection = DB, user=USER):
    rows = conn.execute(f"{BOOKING_SELECT} WHERE b.user_id = %s ORDER BY b.start_ts DESC LIMIT 200", (user["id"],))
    return [shape_booking(b, user) for b in rows]


@app.get("/api/bookings/pending")
def pending(conn: Connection = DB, admin=ADMIN):
    today, now = now_campus()
    rows = conn.execute(f"{BOOKING_SELECT} WHERE b.status = 'pending' AND b.end_ts > %s ORDER BY b.start_ts", (stamp(today, now),)).fetchall()
    out = []
    for b in rows:
        clashes = analyze(conn, venue_id=b["venue_id"], date=b["start_ts"][:10], start_time=b["start_ts"][11:],
                          end_time=b["end_ts"][11:], exclude_id=b["id"])["conflicts"]
        out.append({**shape_booking(b, admin), "clashes": clashes})
    return out


class CheckIn(BaseModel):
    venue_id: int = 0
    date: str = ""
    start_time: str = ""
    end_time: str = ""
    attendees: int = 0
    exclude_id: int = 0


class BookingIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    event_type: str = "Other"
    organizer: str = Field(default="", max_length=120)
    venue_id: int
    date: str
    start_time: str
    end_time: str
    attendees: int = Field(default=0, ge=0, le=100000)


@app.post("/api/check")
def check(body: CheckIn, conn: Connection = DB, _user=USER):
    """Live availability check used by the booking form while the user fills it in."""
    if body.date and not is_valid_date(body.date) or body.start_time and not is_valid_time(body.start_time) \
            or body.end_time and not is_valid_time(body.end_time):
        return {"ok": False, "problems": ["Enter a valid date and time."], "warnings": [], "conflicts": [],
                "alternatives": {"same_venue": [], "other_venues": [], "other_days": []}, "recommended_venues": []}
    return analyze(conn, **body.model_dump())


@app.post("/api/bookings", status_code=201)
def create_booking(body: BookingIn, conn: Connection = DB, user=USER):
    if not body.title.strip():
        raise HTTPException(400, "Give the event a title.")
    if not (is_valid_date(body.date) and is_valid_time(body.start_time) and is_valid_time(body.end_time)):
        raise HTTPException(400, "Enter a valid date and start/end time.")
    venue = get_venue(conn, body.venue_id)
    if not venue or not venue["active"]:
        raise HTTPException(400, "Choose a valid venue.")

    # Locking the venue row serialises bookings per venue, so two people can't both pass the check for the same slot.
    with conn.transaction():
        conn.execute("SELECT id FROM venues WHERE id = %s FOR UPDATE", (venue["id"],))
        result = analyze(conn, **body.model_dump())
        if not result["ok"]:
            raise HTTPException(409, {"error": " ".join(result["problems"]), "analysis": result})
        status = "approved" if user["role"] == "admin" or not venue["requires_approval"] else "pending"
        new_id = conn.execute(
            """INSERT INTO bookings (title, description, event_type, organizer, venue_id, user_id, start_ts, end_ts, attendees, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (body.title.strip(), body.description.strip(), body.event_type if body.event_type in EVENT_TYPES else "Other",
             body.organizer.strip(), body.venue_id, user["id"], stamp(body.date, body.start_time),
             stamp(body.date, body.end_time), body.attendees, status)).fetchone()["id"]
    return shape_booking(conn.execute(f"{BOOKING_SELECT} WHERE b.id = %s", (new_id,)).fetchone(), user)


@app.post("/api/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, conn: Connection = DB, user=USER):
    b = conn.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,)).fetchone()
    if not b:
        raise HTTPException(404, "Booking not found.")
    if b["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "You can only cancel your own bookings.")
    if b["status"] not in ("pending", "approved"):
        raise HTTPException(400, f"Booking is already {b['status']}.")
    conn.execute("UPDATE bookings SET status = 'cancelled', updated_at = now() WHERE id = %s", (booking_id,))
    return {"ok": True}


class DecisionIn(BaseModel):
    decision: str
    note: str = Field(default="", max_length=500)


@app.post("/api/bookings/{booking_id}/decision")
def decide(booking_id: int, body: DecisionIn, conn: Connection = DB, _admin=ADMIN):
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be approved or rejected.")
    with conn.transaction():
        b = conn.execute("SELECT * FROM bookings WHERE id = %s FOR UPDATE", (booking_id,)).fetchone()
        if not b:
            raise HTTPException(404, "Booking not found.")
        if b["status"] != "pending":
            raise HTTPException(400, f"Booking is already {b['status']}.")
        if body.decision == "approved":
            conn.execute("SELECT id FROM venues WHERE id = %s FOR UPDATE", (b["venue_id"],))
            clash = conn.execute(
                """SELECT title FROM bookings WHERE venue_id = %s AND status = 'approved' AND id != %s
                   AND start_ts < %s AND end_ts > %s""", (b["venue_id"], b["id"], b["end_ts"], b["start_ts"])).fetchone()
            if clash:
                raise HTTPException(409, f'Cannot approve: overlaps approved booking "{clash["title"]}".')
        conn.execute("UPDATE bookings SET status = %s, admin_note = %s, updated_at = now() WHERE id = %s",
                     (body.decision, body.note.strip(), booking_id))
    return {"ok": True}


@app.get("/api/bookings/{booking_id}/ics")
def booking_ics(booking_id: int, conn: Connection = DB, _user=USER):
    """One booking as an .ics file for Google Calendar / Outlook."""
    b = conn.execute(f"{BOOKING_SELECT} WHERE b.id = %s", (booking_id,)).fetchone()
    if not b:
        raise HTTPException(404, "Booking not found.")

    def fmt(ts: str) -> str:
        return ts.replace("-", "").replace(":", "").replace(" ", "T") + "00"

    def esc(s: str) -> str:
        return re.sub(r"([,;\\])", r"\\\1", str(s)).replace("\n", "\\n")

    ics = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//NMAMIT Campus Booking//EN", "BEGIN:VEVENT",
        f"UID:booking-{b['id']}@campus-booking",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;TZID=Asia/Kolkata:{fmt(b['start_ts'])}", f"DTEND;TZID=Asia/Kolkata:{fmt(b['end_ts'])}",
        f"SUMMARY:{esc(b['title'])}", f"LOCATION:{esc(b['venue_name'])}",
        f"DESCRIPTION:{esc(b['event_type'] + ' · ' + b['organizer'] + chr(10) + b['description'])}",
        "END:VEVENT", "END:VCALENDAR",
    ])
    return PlainTextResponse(ics, media_type="text/calendar",
                             headers={"Content-Disposition": f'attachment; filename="booking-{b["id"]}.ics"'})


# ---------- AI assistant ----------

class AssistantIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[dict] = []


@app.post("/api/ai/assistant")
async def ai_assistant(body: AssistantIn, conn: Connection = DB, user=USER):
    return await assistant(conn, body.message.strip(), body.history, user)


# ---------- admin stats ----------

@app.get("/api/stats")
def stats(conn: Connection = DB, _admin=ADMIN):
    today, _ = now_campus()
    counts = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, COUNT(*) AS n FROM bookings WHERE end_ts >= %s GROUP BY status", (stamp(today, "00:00"),))}
    utilisation = [dict(r) for r in conn.execute(
        """SELECT v.id, v.name, v.color,
                  ROUND(COALESCE(SUM(EXTRACT(EPOCH FROM b.end_ts::timestamp - b.start_ts::timestamp)) / 3600, 0)::numeric, 1)::float8 AS hours
           FROM venues v LEFT JOIN bookings b ON b.venue_id = v.id AND b.status = 'approved'
             AND b.start_ts >= %s AND b.start_ts < %s
           WHERE v.active GROUP BY v.id ORDER BY hours DESC""",
        (stamp(today, "00:00"), stamp(add_days(today, 7), "00:00")))]
    return {"counts": counts, "utilisation": utilisation}
