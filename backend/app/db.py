"""Postgres access (hosted on Supabase).

The backend connects straight to the Supabase database with the connection string in DATABASE_URL.
Connections run in autocommit mode; code that must check-then-write atomically wraps itself in
`with conn.transaction():` and takes row locks (SELECT … FOR UPDATE).
"""

import os
from pathlib import Path

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .timeutil import add_days, now_campus, stamp

SCHEMA = (Path(__file__).resolve().parent / "schema.sql").read_text(encoding="utf-8")

_pool: ConnectionPool | None = None


def open_pool() -> None:
    global _pool
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Put your Supabase connection string in backend/.env (see README).")
    _pool = ConnectionPool(
        url,
        min_size=1,
        max_size=int(os.getenv("DB_POOL_SIZE", "5")),
        # prepare_threshold=None: no server-side prepared statements, so Supabase's transaction pooler works too.
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": None},
        check=ConnectionPool.check_connection,  # the pooler drops idle connections; test before handing one out
        open=True,
    )
    _pool.wait(timeout=30)


def close_pool() -> None:
    if _pool is not None:
        _pool.close()


def connection():
    """Borrow a pooled connection: `with connection() as conn: ...`"""
    if _pool is None:
        raise RuntimeError("Database pool is not open.")
    return _pool.connection()


def get_db():
    """FastAPI dependency: one pooled connection per request."""
    with connection() as conn:
        yield conn


def venue_dict(row) -> dict | None:
    return dict(row) if row else None


def init_db() -> None:
    open_pool()
    with connection() as conn:
        conn.execute(SCHEMA)
        _seed(conn)


def _seed(conn: Connection) -> None:
    """Sample data so the shared calendar is not empty on first run.
    Venue names are placeholders — admins can rename them or add real ones from the Admin page."""
    with conn.transaction():
        conn.execute("LOCK TABLE venues IN EXCLUSIVE MODE")  # two workers starting at once must not both seed
        if conn.execute("SELECT COUNT(*) AS n FROM venues").fetchone()["n"]:
            return

        venues = [
            ("Main Auditorium", "Admin Block", "Auditorium", 600, ["projector", "sound system", "stage", "AC", "recording"], "#4f46e5", True, "08:00", "21:00"),
            ("Seminar Hall A", "CSE Block", "Seminar Hall", 150, ["projector", "sound system", "AC"], "#0891b2", True, "08:00", "20:00"),
            ("Seminar Hall B", "ECE Block", "Seminar Hall", 120, ["projector", "sound system", "AC"], "#059669", True, "08:00", "20:00"),
            ("Conference Room", "Admin Block", "Conference Room", 30, ["projector", "video conferencing", "AC"], "#d97706", True, "09:00", "18:00"),
            ("Computer Lab 1", "CSE Block", "Lab", 70, ["computers", "projector", "AC"], "#dc2626", False, "08:00", "19:00"),
            ("Open Air Theatre", "Central Campus", "Outdoor", 1000, ["stage", "sound system"], "#7c3aed", True, "07:00", "22:00"),
            ("Library Discussion Room", "Central Library", "Discussion Room", 15, ["whiteboard", "display"], "#db2777", False, "08:00", "20:00"),
            ("Indoor Sports Hall", "Sports Complex", "Sports", 200, ["badminton courts", "sound system"], "#65a30d", True, "06:00", "21:00"),
        ]
        venue_ids = []
        for v in venues:
            venue_ids.append(conn.execute(
                """INSERT INTO venues (name, block, type, capacity, features, color, requires_approval, open_time, close_time)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (v[0], v[1], v[2], v[3], Jsonb(v[4]), v[5], v[6], v[7], v[8]),
            ).fetchone()["id"])
        demo_id = conn.execute(
            """INSERT INTO users (email, name, role, department) VALUES (%s, %s, 'member', %s)
               ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING id""",
            ("events.coordinator@nmamit.in", "Events Coordinator", "Student Affairs"),
        ).fetchone()["id"]

        today, _ = now_campus()
        samples = [
            (0, "10:00", "12:00", 1, "Orientation: First-Year Students", "Orientation", "Student Affairs", 450, "approved"),
            (0, "14:00", "16:00", 2, "Guest Lecture: Generative AI in Practice", "Guest Lecture", "Dept. of CSE", 120, "approved"),
            (1, "09:30", "11:00", 4, "IQAC Review Meeting", "Meeting", "IQAC", 20, "approved"),
            (1, "13:00", "17:00", 5, "Hackathon Warm-up: Git & APIs", "Workshop", "Coding Club", 60, "approved"),
            (2, "15:00", "17:30", 3, "IEEE Student Branch Talk", "Seminar", "IEEE SB", 90, "pending"),
            (3, "17:00", "20:00", 6, "Cultural Night Rehearsal", "Cultural", "Cultural Committee", 150, "approved"),
            (4, "10:00", "13:00", 1, "Placement Pre-Talk", "Placement", "Training & Placement Cell", 400, "approved"),
            (5, "08:00", "11:00", 8, "Inter-Department Badminton", "Sports", "Sports Council", 80, "pending"),
        ]
        for day, s, e, venue, title, etype, org, att, status in samples:
            d = add_days(today, day)
            conn.execute(
                """INSERT INTO bookings (title, event_type, organizer, venue_id, user_id, start_ts, end_ts, attendees, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (title, etype, org, venue_ids[venue - 1], demo_id, stamp(d, s), stamp(d, e), att, status),
            )
