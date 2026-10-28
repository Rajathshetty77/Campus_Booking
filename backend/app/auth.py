"""Password authentication restricted to the configured college email domains."""

import hashlib
import hmac
import os
import re
import secrets
import time

from fastapi import Depends, HTTPException, Request, Response
from psycopg import Connection

from .db import get_db

ALLOWED_DOMAINS = [d.strip().lower() for d in os.getenv("ALLOWED_DOMAINS", "nmamit.in,nitte.edu.in").split(",") if d.strip()]
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "admin@nmamit.in").split(",") if e.strip()}
INITIAL_ADMIN_EMAIL = os.getenv("ADMIN_INITIAL_EMAIL", "admin@nmamit.in").strip().lower()
ADMIN_INITIAL_PASSWORD = os.getenv("ADMIN_INITIAL_PASSWORD", "")
IS_PROD = os.getenv("ENV") == "production"

COOKIE = "nb_session"
SESSION_SECONDS = 7 * 86400
EMAIL_RE = re.compile(r"[a-z0-9][a-z0-9._%+-]{0,63}@([a-z0-9-]+(?:\.[a-z0-9-]+)+)")
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_KEY_LENGTH = 64


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


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_KEY_LENGTH,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${key.hex()}"


def _verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, n, r, p, salt_hex, key_hex = encoded.split("$")
        if algorithm != "scrypt":
            return False
        expected = bytes.fromhex(key_hex)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def bootstrap_admin(conn: Connection) -> bool:
    """Create the configured initial admin, without resetting an existing password."""
    if INITIAL_ADMIN_EMAIL not in ADMIN_EMAILS:
        raise RuntimeError("ADMIN_INITIAL_EMAIL must also be listed in ADMIN_EMAILS.")
    if not allowed_email(INITIAL_ADMIN_EMAIL):
        raise RuntimeError("ADMIN_INITIAL_EMAIL must use a domain listed in ALLOWED_DOMAINS.")
    if not ADMIN_INITIAL_PASSWORD:
        existing = conn.execute(
            "SELECT password_hash FROM users WHERE email = %s",
            (INITIAL_ADMIN_EMAIL,),
        ).fetchone()
        return bool(existing and existing["password_hash"])
    if len(ADMIN_INITIAL_PASSWORD) < 8 or len(ADMIN_INITIAL_PASSWORD) > 128:
        raise RuntimeError("ADMIN_INITIAL_PASSWORD must be between 8 and 128 characters.")

    conn.execute(
        """INSERT INTO users (email, name, role, password_hash)
           VALUES (%s, %s, 'admin', %s)
           ON CONFLICT (email) DO UPDATE SET
             role = 'admin',
             password_hash = COALESCE(users.password_hash, EXCLUDED.password_hash)""",
        (INITIAL_ADMIN_EMAIL, "Admin", _password_hash(ADMIN_INITIAL_PASSWORD)),
    )
    return True


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


# ---------- registration and sign-in ----------

def register(conn: Connection, response: Response, email: str, password: str, name: str = "") -> dict:
    normalised = allowed_email(email)
    if not normalised:
        raise HTTPException(400, f"Register with a college email address ({domains_text()}).")
    if normalised in ADMIN_EMAILS:
        raise HTTPException(403, "Administrator accounts are provisioned by the server.")
    if len(password) < 8 or len(password) > 128:
        raise HTTPException(400, "Password must be between 8 and 128 characters.")

    name = re.sub(r"\s+", " ", name or "").strip()[:80]
    role = "member"
    password_hash = _password_hash(password)
    user = conn.execute(
        """UPDATE users SET password_hash = %s,
             name = CASE WHEN %s <> '' THEN %s ELSE name END, role = %s
           WHERE email = %s AND password_hash IS NULL RETURNING *""",
        (password_hash, name, name, role, normalised),
    ).fetchone()
    if not user:
        user = conn.execute(
            """INSERT INTO users (email, name, role, password_hash)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (email) DO NOTHING RETURNING *""",
            (normalised, name or _name_from_email(normalised), role, password_hash),
        ).fetchone()
    if not user:
        raise HTTPException(409, "An account already exists for this email. Sign in instead.")
    _start_session(conn, response, user["id"])
    return {"user": public_user(user)}


def password_sign_in(conn: Connection, response: Response, email: str, password: str) -> dict:
    normalised = allowed_email(email)
    if not normalised:
        raise HTTPException(400, f"Use a college email address ({domains_text()}).")
    user = conn.execute("SELECT * FROM users WHERE email = %s", (normalised,)).fetchone()
    if not user or not _verify_password(password, user["password_hash"]):
        raise HTTPException(401, "Incorrect email or password.")

    # Keep configured admin addresses authoritative, while preserving existing roles if unset.
    role = ("admin" if normalised in ADMIN_EMAILS else "member") if ADMIN_EMAILS else user["role"]
    if user["role"] != role:
        conn.execute("UPDATE users SET role = %s WHERE id = %s", (role, user["id"]))
        user["role"] = role
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
