"""Email sign-in, restricted to college addresses (@nmamit.in and @nitte.edu.in).

Anyone who enters an address on an allowed domain is signed in. Ownership of the mailbox is not
verified, so treat identities as self-declared (see README → "How sign-in works").
"""

import hashlib
import os
import re
import secrets
import time

from fastapi import Depends, HTTPException, Request, Response
from psycopg import Connection

from .db import get_db

ALLOWED_DOMAINS = [d.strip().lower() for d in os.getenv("ALLOWED_DOMAINS", "nmamit.in,nitte.edu.in").split(",") if d.strip()]
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
IS_PROD = os.getenv("ENV") == "production"

COOKIE = "nb_session"
SESSION_SECONDS = 7 * 86400
EMAIL_RE = re.compile(r"[a-z0-9][a-z0-9._%+-]{0,63}@([a-z0-9-]+(?:\.[a-z0-9-]+)+)")


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def domains_text(joiner: str = " or ") -> str:
    return joiner.join("@" + d for d in ALLOWED_DOMAINS)


def allowed_email(email: str) -> str | None:
    """Normalised address if it is on an allowed domain (exact match, so x@evil-nmamit.in is refused)."""
    email = (email or "").strip().lower()
    m = EMAIL_RE.fullmatch(email)
    return email if m and m.group(1) in ALLOWED_DOMAINS else None


def _name_from_email(email: str) -> str:
    local = email.split("@")[0]
    parts = [p for p in re.split(r"[._-]+", local) if p]
    return " ".join(p[:1].upper() + p[1:] for p in parts) or local


def public_user(u) -> dict | None:
    if not u:
        return None
    return {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"], "department": u["department"]}


def _upsert_user(conn: Connection, email: str, name: str | None = None):
    role = "admin" if email in ADMIN_EMAILS else "member"
    existing = conn.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()
    if existing:
        # Keep roles in sync with ADMIN_EMAILS on every sign-in so the env var stays the source of truth.
        new_role = role if ADMIN_EMAILS else existing["role"]
        conn.execute("UPDATE users SET role = %s, name = %s WHERE id = %s", (new_role, name or existing["name"], existing["id"]))
        return conn.execute("SELECT * FROM users WHERE id = %s", (existing["id"],)).fetchone()
    return conn.execute(
        "INSERT INTO users (email, name, role) VALUES (%s, %s, %s) RETURNING *",
        (email, name or _name_from_email(email), role),
    ).fetchone()


def _start_session(conn, response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
                 (_sha256(token), user_id, time.time() + SESSION_SECONDS))
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="lax", secure=IS_PROD, path="/")


# ---------- dependencies ----------

def optional_user(request: Request, conn: Connection = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    return conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = %s AND s.expires_at > %s",
        (_sha256(token), time.time()),
    ).fetchone()


def current_user(user=Depends(optional_user)):
    if not user:
        raise HTTPException(401, "Please sign in.")
    return user


def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admins only.")
    return user


# ---------- sign-in ----------

def email_sign_in(conn, response: Response, email: str, name: str = "") -> dict:
    normalised = allowed_email(email)
    if not normalised:
        raise HTTPException(400, f"Use your college email address ({domains_text()}).")
    name = re.sub(r"\s+", " ", name or "").strip()[:80]
    user = _upsert_user(conn, normalised, name or None)
    _start_session(conn, response, user["id"])
    return {"user": public_user(user)}


def logout(conn, request: Request, response: Response) -> dict:
    token = request.cookies.get(COOKIE)
    if token:
        conn.execute("DELETE FROM sessions WHERE token = %s", (_sha256(token),))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


def purge_expired(conn) -> None:
    conn.execute("DELETE FROM sessions WHERE expires_at < %s", (time.time(),))
