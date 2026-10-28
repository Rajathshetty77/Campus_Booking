# NMAMIT Campus Booking System

> **A high-performance, real-time campus venue reservation and scheduling platform with an intelligent AI booking assistant, multi-view calendar, pessimistic concurrency control, and administrative approval workflows.**

---

## Table of Contents

- [1. Overview](#1-overview)
- [2. System Architecture](#2-system-architecture)
- [3. Key Features](#3-key-features)
  - [Interactive Multi-View Calendar](#interactive-multi-view-calendar)
  - [Live Reactive Availability & Conflict Engine](#live-reactive-availability--conflict-engine)
  - [Intelligent 3-Way Alternative Slot Recommendations](#intelligent-3-way-alternative-slot-recommendations)
  - [Dual-Engine AI Booking Assistant](#dual-engine-ai-booking-assistant)
  - [Administrative Approval & Venue Management](#administrative-approval--venue-management)
  - [Personal Booking Dashboard & Calendar Export](#personal-booking-dashboard--calendar-export)
- [4. Database Architecture & Schema](#4-database-architecture--schema)
  - [Entity-Relationship Diagram (ERD)](#entity-relationship-diagram-erd)
  - [Data Model & Table Definitions](#data-model--table-definitions)
  - [Timezone & Lexical Collations](#timezone--lexical-collations)
  - [Row Level Security (RLS)](#row-level-security-rls)
- [5. Concurrency Control & Race Condition Prevention](#5-concurrency-control--race-condition-prevention)
- [6. AI Assistant Pipeline & Fallback Architecture](#6-ai-assistant-pipeline--fallback-architecture)
  - [Claude Opus Structured Output Engine](#claude-opus-structured-output-engine)
  - [Deterministic Rule-Based Regex Parser](#deterministic-rule-based-regex-parser)
  - [Post-Processing Database Verification](#post-processing-database-verification)
- [7. Complete REST API Reference](#7-complete-rest-api-reference)
  - [Authentication Endpoints](#authentication-endpoints)
  - [Venues Endpoints](#venues-endpoints)
  - [Bookings & Calendar Endpoints](#bookings--calendar-endpoints)
  - [Conflict & Availability Endpoints](#conflict--availability-endpoints)
  - [Administrative & Stats Endpoints](#administrative--stats-endpoints)
  - [AI Assistant Endpoint](#ai-assistant-endpoint)
- [8. Repository Structure & Code Map](#8-repository-structure--code-map)
- [9. Configuration & Environment Variables](#9-configuration--environment-variables)
- [10. Local Development Setup](#10-local-development-setup)
  - [Prerequisites](#prerequisites)
  - [1. Database Provisioning (Supabase Postgres)](#1-database-provisioning-supabase-postgres)
  - [2. Backend Setup (FastAPI)](#2-backend-setup-fastapi)
  - [3. Frontend Setup (Next.js)](#3-frontend-setup-nextjs)
- [11. Production Deployment & Security Best Practices](#11-production-deployment--security-best-practices)
- [12. Troubleshooting & FAQ](#12-troubleshooting--faq)

---

## 1. Overview

The **NMAMIT Campus Booking System** is an end-to-end web application tailored for educational institutions (specifically NMAMIT / Nitte Education Trust). It replaces disjointed, paper-based, or spreadsheet-driven venue booking with a unified, conflict-free digital system.

### Core Problems Solved
1. **Double-Bookings & Scheduling Clashes**: Eliminates conflicting reservations across seminar halls, auditoriums, conference rooms, labs, and sports complexes.
2. **Opaque Campus Availability**: Provides a single pane of glass across all campus venues with real-time views by month, week, or venue column.
3. **Friction in Request Creation**: Allows users to write conversational requests (e.g., *"Seminar hall for 120 people next Tuesday 2–5pm for a robotics symposium"*) which an AI assistant parses into valid booking parameters.
4. **Instant vs. Moderated Approvals**: Equips administrators with an approval queue showing automatic conflict alerts and allowing one-click decisions with rejection notes.

---

## 2. System Architecture

The platform uses a decoupled client-server architecture:
- **Client Tier**: Next.js 16 (App Router, React 19, TypeScript 5) providing server-side and client-side rendering with custom semantic CSS supporting both light and dark operating system themes.
- **Reverse Proxy**: Next.js rewrites forward all `/api/*` calls directly to the FastAPI backend. This ensures the browser only ever talks to port 3000, keeping authentication session cookies first-party (`SameSite=Lax`).
- **Application Tier**: FastAPI (Python 3.10+) running asynchronously on Uvicorn, with Pydantic v2 data models and connection pooling.
- **Persistence Tier**: Hosted PostgreSQL on Supabase, connected via `psycopg` (v3) using pooler connections in autocommit mode.
- **AI Intelligence Tier**: Anthropic Claude API (`claude-opus-5-5`) with prompt caching and structured outputs, supported by a deterministic fallback regex parser when offline or without credentials.

```mermaid
flowchart TD
    subgraph Browser["User Browser (Desktop / Mobile)"]
        UI["Next.js Web UI\n(Port 3000)"]
    end

    subgraph FrontendServer["Frontend Server (Next.js 16)"]
        Pages["App Router\n/calendar · /mine · /admin · /login"]
        Proxy["Next.js Rewrite Proxy\n/api/* -> http://127.0.0.1:8000/api/*"]
    end

    subgraph BackendServer["API Backend (FastAPI / Python 3.10+)"]
        Auth["Auth & Session Manager\n(HMAC/SHA-256 Token)"]
        Scheduler["Conflict & Availability Engine\n(scheduler.py)"]
        AIEngine["AI Assistant Router\n(ai.py)"]
        LockMgr["Pessimistic Locking Manager\n(SELECT ... FOR UPDATE)"]
    end

    subgraph ExternalServices["External Cloud & AI Services"]
        Supabase[("Supabase PostgreSQL\n(Tables: users, sessions, venues, bookings)")]
        Claude["Anthropic Claude API\n(claude-opus-5-5 / Structured JSON)"]
    end

    UI -->|Render UI & Navigate| Pages
    UI -->|Fetch /api/* (First-party Cookie)| Proxy
    Proxy -->|Forward HTTP /api/*| BackendServer
    BackendServer --> Auth
    BackendServer --> Scheduler
    BackendServer --> LockMgr
    BackendServer --> AIEngine
    AIEngine -->|Structured Prompt| Claude
    LockMgr -->|Pooled SQL Transactions| Supabase
    Scheduler -->|Overlap Queries (COLLATE 'C')| Supabase
```

### Technology Matrix

| Layer | Component | Version / Technology | Key Purpose |
|---|---|---|---|
| **Frontend Framework** | Next.js | 16.4.2 (App Router) | High-performance routing, SSR, proxying, and reactive views |
| **UI Library** | React | 19.3.0 | Modern declarative component model |
| **Language** | TypeScript | 5.x | Strict type contracts across APIs and UI components |
| **Styling** | Semantic CSS3 | Vanilla CSS Variables | Zero-dependency styling with native dark/light mode support |
| **Backend Framework** | FastAPI | >= 0.156 | High-speed asynchronous Python REST API with auto OpenAPI docs |
| **ASGI Server** | Uvicorn | >= 0.54 | Production ASGI server for asynchronous event loops |
| **Database Pooler** | psycopg-pool | >= 3.3 | Non-blocking database connection pooling with connection health checks |
| **Database Driver** | psycopg | >= 3.3 (binary) | Native PostgreSQL adapter supporting binary protocol and JSONB |
| **Database** | PostgreSQL | Supabase Hosted (15+) | Relational storage, ACID transactions, and Row Level Security |
| **LLM Engine** | Anthropic Claude | Claude Opus 5.5 | Natural-language query extraction with strict JSON schema |

---

## 3. Key Features

### Interactive Multi-View Calendar
The calendar supports three view modes suited for different operational needs:
1. **Month View**:
   - 42-day rolling month grid with day-of-week headers (Monday through Sunday).
   - Event chips showing venue color codes, start times, and titles.
   - Truncated overflow indicator (`+N more`) that opens the selected day.
   - Click-to-book on empty future date cells (defaults to 10:00 AM).
2. **Week View**:
   - 7-day multi-column timeline spanning operating hours (07:00 to 22:00).
   - **Side-by-Side Collision Layout**: Overlapping events are dynamically split into parallel horizontal lanes rather than obscuring each other.
   - Visual red hairline indicating the current time on the campus schedule.
3. **Day · by Venue View**:
   - Each column represents an individual campus venue (Auditorium, Seminar Hall, Lab, etc.).
   - Shaded out-of-bounds regions denoting operating hours when venues are closed.
   - Click any 30-minute block in any venue column to prefill the booking dialog with that venue and timestamp.
4. **Venue Filtering & Persistence**:
   - Sidebar venue list with color swatches and seating capacities.
   - Toggle individual venues on or off; preferences are persisted in browser `localStorage`.

### Live Reactive Availability & Conflict Engine
As users type in the booking modal, the client debounces input by 350ms and posts to `/api/check`:
- **Boundary Validation**: Ensures end time is after start time and times conform to 24-hour `HH:MM`.
- **Temporal Check**: Rejects timestamps in the past relative to campus local time (`Asia/Kolkata`).
- **Operating Hours**: Validates that requested slots fall completely within venue operating hours (e.g., `08:00`–`20:00`).
- **Seating Capacity Check**: Rejects requests where expected attendees exceed venue capacity.
- **Under-Utilization Warning**: Generates an advisory warning when a large venue (>100 capacity) is requested for fewer than 15% of its capacity.
- **Sunday Campus Alert**: Warns users when reserving slots on Sundays so campus facility staff can be notified.
- **Clash Detection**: Checks the database for overlapping bookings with `approved` or `pending` status.

### Intelligent 3-Way Alternative Slot Recommendations
When a slot has a conflict or falls outside operating hours, the engine automatically calculates alternatives:
1. **Same Venue, Nearby Free Times**: Finds the nearest available free windows in the same venue on the requested date.
2. **Other Suitable Venues**: Scans all active campus venues free at the requested time, scoring them based on capacity fit and matching facility requirements (e.g., projector, sound system, AC).
3. **Same Slot on Future Days**: Scans up to 7 days ahead for when the exact same venue and time slot are open.

Every suggestion includes a one-click button to automatically adopt the alternative in the booking form.

### Dual-Engine AI Booking Assistant
Users can schedule events by conversing in natural language. The assistant drawer handles both event creation and calendar queries:
- **Intelligent Intent Classification**:
  - `book`: Extracts event title, event type, date, start/end time, expected attendees, required facilities, and best venue.
  - `query`: Answers questions like *"Which halls are free tomorrow after 2 PM?"* using a live 3-week calendar snapshot.
  - `other`: Gracefully steers non-booking conversations back to campus scheduling.
- **Structured JSON Schema**: Prompts Claude Opus 5.5 using structured outputs (`DRAFT_SCHEMA`), preventing hallucinations and formatting errors.
- **Deterministic Rule-Based Fallback**: When no Anthropic API key is provided or the service is offline, a comprehensive regex and rule engine takes over, parsing Indian date formats (`DD/MM/YYYY`), relative days (`next Friday`), time intervals (`2 to 4pm`), and event keywords.
- **Zero-Direct-Write Safety**: The assistant never inserts bookings directly into the database. Instead, it generates a pre-verified draft card for the user to review and confirm.

### Administrative Approval & Venue Management
Users designated in `ADMIN_EMAILS` gain access to the dedicated **Admin** portal:
- **Pending Approval Queue**: Displays all bookings awaiting review with automated clash indicators highlighting conflicting events.
- **One-Click Decisions**: Approve or reject bookings. Rejections require a clear note explaining the reason, visible to the requester.
- **Venue Management**:
  - Create new venues or update existing locations.
  - Configure venue name, campus block, capacity, facility tags, hex accent colors, and opening/closing hours.
  - Toggle whether a venue requires administrative approval or supports instant confirmation.
  - Deactivate venues without deleting past historical booking records.
- **Venue Utilization Analytics**: Real-time aggregation of approved booked hours over the next 7 days per venue.

### Personal Booking Dashboard & Calendar Export
- **My Bookings Tab (`/mine`)**: Segregates reservations into **Upcoming** and **Past**.
- **Cancellation Workflow**: Users can cancel their own pending or approved bookings, immediately releasing the slot for others.
- **iCalendar (.ics) Export**: One-click download of RFC-5545 `.ics` files configured with `Asia/Kolkata` timezone headers, ready to import into Google Calendar, Microsoft Outlook, or Apple Calendar.

---

## 4. Database Architecture & Schema

The application connects to a Supabase-hosted PostgreSQL database. Database migrations and initial seed records are automatically executed on backend startup via [`backend/app/schema.sql`](backend/app/schema.sql).

### Entity-Relationship Diagram (ERD)

```mermaid
erDiagram
    users ||--o{ sessions : "has many"
    users ||--o{ bookings : "creates"
    venues ||--o{ bookings : "hosts"

    users {
        integer id PK
        text email UK "lower-case only"
        text name
        text role "member | admin"
        text department
        timestamptz created_at
    }

    sessions {
        text token PK "SHA-256 hash"
        integer user_id FK
        double_precision expires_at
    }

    venues {
        integer id PK
        text name
        text block
        text type
        integer capacity
        jsonb features "array of strings"
        text color "hex color string"
        boolean requires_approval
        text open_time "HH:MM"
        text close_time "HH:MM"
        boolean active
    }

    bookings {
        integer id PK
        text title
        text description
        text event_type
        text organizer
        integer venue_id FK
        integer user_id FK
        text start_ts "YYYY-MM-DD HH:MM (COLLATE C)"
        text end_ts "YYYY-MM-DD HH:MM (COLLATE C)"
        integer attendees
        text status "pending | approved | rejected | cancelled"
        text admin_note
        timestamptz created_at
        timestamptz updated_at
    }
```

### Data Model & Table Definitions

#### `users` Table
Stores registered college members and administrators.
```sql
CREATE TABLE IF NOT EXISTS users (
  id          integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  email       text NOT NULL UNIQUE CHECK (email = lower(email)),
  name        text NOT NULL,
  role        text NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'admin')),
  department  text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
```

#### `sessions` Table
Stores active user sessions with SHA-256 hashed tokens and expiration timestamps.
```sql
CREATE TABLE IF NOT EXISTS sessions (
  token       text PRIMARY KEY,
  user_id     integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at  double precision NOT NULL
);
```

#### `venues` Table
Contains campus locations, capacities, equipment tags, and scheduling rules.
```sql
CREATE TABLE IF NOT EXISTS venues (
  id                integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  name              text NOT NULL,
  block             text NOT NULL DEFAULT '',
  type              text NOT NULL,
  capacity          integer NOT NULL,
  features          jsonb NOT NULL DEFAULT '[]',
  color             text NOT NULL,
  requires_approval boolean NOT NULL DEFAULT true,
  open_time         text NOT NULL DEFAULT '07:00',
  close_time        text NOT NULL DEFAULT '21:00',
  active            boolean NOT NULL DEFAULT true
);
```

#### `bookings` Table
Main ledger of reservations, timeslots, and approval statuses.
```sql
CREATE TABLE IF NOT EXISTS bookings (
  id          integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  title       text NOT NULL,
  description text NOT NULL DEFAULT '',
  event_type  text NOT NULL,
  organizer   text NOT NULL DEFAULT '',
  venue_id    integer NOT NULL REFERENCES venues(id),
  user_id     integer NOT NULL REFERENCES users(id),
  start_ts    text COLLATE "C" NOT NULL,
  end_ts      text COLLATE "C" NOT NULL,
  attendees   integer NOT NULL DEFAULT 0,
  status      text NOT NULL DEFAULT 'pending'
              CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
  admin_note  text NOT NULL DEFAULT '',
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
```

### Timezone & Lexical Collations
Rather than storing booking intervals in UTC timestamp fields that necessitate complex runtime timezone offsets, timestamps are stored as **IST wall-clock strings** (`YYYY-MM-DD HH:MM`) with explicit PostgreSQL collation:
```sql
start_ts text COLLATE "C" NOT NULL,
end_ts   text COLLATE "C" NOT NULL
```
**Benefits**:
- String collation `COLLATE "C"` guarantees byte-wise lexical comparison.
- Overlap detection becomes a direct SQL string comparison:
  ```sql
  WHERE venue_id = %s AND status IN ('approved', 'pending')
    AND start_ts < %s AND end_ts > %s
  ```
- Fast, deterministic lookups indexable via composite B-tree index `idx_bookings_venue_time (venue_id, start_ts, end_ts)`.

### Row Level Security (RLS)
Supabase automatically exposes REST APIs backed by PostgREST using project API keys. To prevent unauthenticated access:
```sql
ALTER TABLE users    ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE venues   ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;
```
Because no permissive RLS policies are added, any request made through the Supabase public REST API with `anon` or `authenticated` keys is blocked. The FastAPI backend connects directly to PostgreSQL as the database owner, bypassing RLS.

---

## 5. Concurrency Control & Race Condition Prevention

In campus booking systems, two users frequently attempt to book the same popular venue (e.g., Auditorium) for the same time slot simultaneously. A naive `SELECT` followed by `INSERT` suffers from a classic race condition (Time-of-Check to Time-of-Use / TOCTOU).

### Pessimistic Row-Level Locking Architecture

```mermaid
sequenceDiagram
    autonumber
    actor UserA as Requester A
    actor UserB as Requester B
    participant API as FastAPI Backend
    participant DB as PostgreSQL Transaction

    UserA->>API: POST /api/bookings (Auditorium, 14:00-16:00)
    UserB->>API: POST /api/bookings (Auditorium, 14:00-16:00)
    
    rect rgb(240, 248, 255)
    Note over API,DB: Requester A transaction starts
    API->>DB: BEGIN TRANSACTION
    API->>DB: SELECT id FROM venues WHERE id = 1 FOR UPDATE
    Note over DB: Venue #1 locked by Requester A
    end

    rect rgb(255, 240, 240)
    Note over API,DB: Requester B transaction starts
    API->>DB: BEGIN TRANSACTION
    API->>DB: SELECT id FROM venues WHERE id = 1 FOR UPDATE
    Note over DB: Requester B WAITS on lock...
    end

    API->>DB: analyze() -> No conflicts detected
    API->>DB: INSERT INTO bookings (...) VALUES (...)
    API->>DB: COMMIT (Lock released)
    API-->>UserA: 201 Created (Booking Successful)

    rect rgb(255, 240, 240)
    Note over DB: Requester B acquires lock
    API->>DB: analyze() -> Conflicting with Requester A!
    API->>DB: ROLLBACK
    API-->>UserB: 409 Conflict (with alternative suggestions)
    end
```

### Locking Implementation Details
1. **Creation Lock**: In [`backend/app/main.py`](backend/app/main.py), booking creation wraps availability checking and insertion in a PostgreSQL transaction:
   ```python
   with conn.transaction():
       conn.execute("SELECT id FROM venues WHERE id = %s FOR UPDATE", (venue["id"],))
       result = analyze(conn, **body.model_dump())
       if not result["ok"]:
           raise HTTPException(409, {"error": " ".join(result["problems"]), "analysis": result})
       # Insert booking safely...
   ```
2. **Approval Double-Check**: When an admin approves a pending booking in [`backend/app/main.py`](backend/app/main.py), the venue row is locked and the system verifies that no other booking for the same slot was approved in the interim:
   ```python
   with conn.transaction():
       conn.execute("SELECT id FROM venues WHERE id = %s FOR UPDATE", (b["venue_id"],))
       clash = conn.execute(
           """SELECT title FROM bookings WHERE venue_id = %s AND status = 'approved' AND id != %s
              AND start_ts < %s AND end_ts > %s""", (b["venue_id"], b["id"], b["end_ts"], b["start_ts"])).fetchone()
       if clash:
           raise HTTPException(409, f'Cannot approve: overlaps approved booking "{clash["title"]}".')
       conn.execute("UPDATE bookings SET status = 'approved' ... WHERE id = %s", (booking_id,))
   ```

---

## 6. AI Assistant Pipeline & Fallback Architecture

The assistant located in [`backend/app/ai.py`](backend/app/ai.py) translates unstructured human messages into concrete, conflict-checked reservation drafts.

```mermaid
flowchart TD
    Req["User Prompt\n'Seminar hall for 80 people next Friday 2-4pm'"] --> CheckAuth{Claude API Key\nConfigured & Healthy?}
    
    CheckAuth -- Yes --> AskClaude["Ask Claude Opus 5.5\n(JSON Schema + Ephemeral Prompt Caching)"]
    CheckAuth -- No / Error --> RuleEngine["Deterministic Rule Engine\n(Regex Date/Time/Type Parser)"]
    
    AskClaude --> ParseDraft["Extracted JSON Draft\n(title, venue, date, start, end, attendees)"]
    RuleEngine --> ParseDraft

    ParseDraft --> Analyze["Run scheduler.analyze() against PostgreSQL"]
    Analyze --> CheckFit{Venue Specified\nby User?}
    
    CheckFit -- Yes --> CheckConflict["Check Conflicts & Operating Hours"]
    CheckFit -- No --> PickBest["Auto-select Best Matching\nFree Venue for Capacity"]
    
    PickBest --> CheckConflict
    CheckConflict --> OutputCard["Generate Assistant Response\n+ Structured Draft Card with Alternatives"]
    OutputCard --> Frontend["Render in Chat Drawer\nUser Reviews & Submits via Modal"]
```

### Claude Opus Structured Output Engine
When an Anthropic API key is provided, the backend queries Claude Opus 5.5 using structured outputs (`output_config={"format": {"type": "json_schema", "schema": DRAFT_SCHEMA}}`):
- **Ephemeral System Prompt Caching**: The active venue list and scheduling guidelines are cached at Anthropic's edge (`cache_control: {"type": "ephemeral"}`), slashing latency and token costs.
- **Dynamic Context Injection**: The backend injects campus local date and time alongside a 3-week snapshot of all approved and pending bookings.
- **Strict JSON Contract**: Forces fields (`title`, `event_type`, `organizer`, `description`, `venue_id`, `date`, `start_time`, `end_time`, `attendees`, `features`) to adhere to rigid types.

### Deterministic Rule-Based Regex Parser
If Claude is disabled (`AI_DISABLED=true`) or unconfigured, the system falls back to a rule-based parser:
- **Relative Dates**: Resolves phrases like `today`, `tonight`, `tomorrow`, `day after tomorrow`, and `next Friday` relative to Indian Standard Time.
- **Indian Date Formats**: Matches `DD/MM` and `DD/MM/YYYY` numeric patterns as well as month names (e.g., `15th Nov`, `Nov 15`).
- **Time Intervals**: Parses 12-hour and 24-hour ranges (e.g., `2-4pm`, `10:00 to 12:30`, `from 9 am till 11 am`). Defaults unqualified small integers (e.g., `from 2 to 4`) to afternoon hours.
- **Duration Parsing**: Converts natural duration phrases (e.g., `for 2 hours`, `for 90 mins`) into end times.
- **Fuzzy Venue Matching**: Scans venue names, blocks, and keywords (e.g., `Auditorium`, `Lab`, `Sports`) against user tokens.

### Post-Processing Database Verification
Crucially, **the AI never writes to the calendar**. Any draft produced by Claude or the rule-based engine is immediately passed into `scheduler.analyze()` to verify:
1. Does the venue exist and is it active?
2. Does the venue seat the requested attendee count?
3. Is the venue open during those hours?
4. Does the slot clash with any existing booking?

If conflicts exist, the assistant automatically attaches alternatives to the chat message so the user can resolve them with a single click.

---

## 7. Complete REST API Reference

All application endpoints are served under `/api/*` and return JSON responses. Interactive Swagger UI documentation is available at `http://localhost:8000/docs`.

### Authentication Endpoints

#### `GET /api/config`
Retrieves public application configuration, allowed domains, AI status, event types, and current user session.
- **Access**: Public
- **Response `200 OK`**:
  ```json
  {
    "allowedDomains": ["nmamit.in", "nitte.edu.in"],
    "ai": { "enabled": true, "model": "claude-opus-5-5", "reason": null },
    "eventTypes": ["Workshop", "Seminar", "Guest Lecture", "Meeting", "Cultural", "Sports", "Orientation", "Placement", "Exam", "Club Activity", "Other"],
    "today": "2026-10-28",
    "user": { "id": 1, "email": "events.coordinator@nmamit.in", "name": "Events Coordinator", "role": "member", "department": "Student Affairs" }
  }
  ```

#### `POST /api/auth/login`
Signs in an existing user with their college email address and password. Sets an `HttpOnly`, `SameSite=Lax` cookie named `nb_session`.
- **Access**: Public
- **Request Body**:
  ```json
  { "email": "rajath@nmamit.in", "password": "your-password" }
  ```
- **Response `200 OK`**:
  ```json
  {
    "user": { "id": 2, "email": "rajath@nmamit.in", "name": "Rajath K", "role": "member", "department": null }
  }
  ```
- **Error Codes**: `400 Bad Request` if the domain is not in `ALLOWED_DOMAINS`; `401 Unauthorized` for incorrect credentials.

#### `POST /api/auth/register`
Creates an account and signs in the new user. Registration is restricted to `ALLOWED_DOMAINS`; passwords must be 8–128 characters. Passwords are stored as scrypt hashes, not plaintext.
- **Access**: Public
- **Request Body**:
  ```json
  { "email": "rajath@nmamit.in", "name": "Rajath K", "password": "choose-a-password" }
  ```
- **Response `201 Created`**: Returns the user object and sets the session cookie.
- **Error Codes**: `400 Bad Request` for invalid input or disallowed email domain; `403 Forbidden` for an admin address reserved for server provisioning; `409 Conflict` if an account already exists.

Email addresses are not verified by email in this application. Restricting registration to college domains does not prove that the registrant owns that mailbox.

#### `POST /api/auth/logout`
Deletes the active session from the database and removes the session cookie.
- **Access**: Public
- **Response `200 OK`**: `{ "ok": true }`

#### `GET /api/me`
Fetches the profile of the currently signed-in user.
- **Access**: Signed-in user
- **Response `200 OK`**: `{ "user": { ... } }`
- **Error Codes**: `401 Unauthorized` if not signed in.

---

### Venues Endpoints

#### `GET /api/venues`
Lists campus venues.
- **Access**: Signed-in user
- **Query Parameters**:
  - `all` (integer, optional): If `1` and user is an admin, includes inactive venues.
- **Response `200 OK`**:
  ```json
  [
    {
      "id": 1,
      "name": "Sadananda Open Air Auditorium",
      "block": "B C Alva Sports Complex, Nitte",
      "type": "Auditorium",
      "capacity": 2500,
      "features": ["projector", "sound system", "stage", "recording"],
      "color": "#4f46e5",
      "requires_approval": true,
      "open_time": "08:00",
      "close_time": "21:00",
      "active": true
    }
  ]
  ```

#### `POST /api/venues`
Creates a new venue.
- **Access**: Admins only (`403 Forbidden` otherwise)
- **Request Body**:
  ```json
  {
    "name": "Mechanical Seminar Hall",
    "block": "Mech Block",
    "type": "Seminar Hall",
    "capacity": 100,
    "features": ["projector", "AC"],
    "color": "#059669",
    "requires_approval": true,
    "open_time": "08:30",
    "close_time": "18:00",
    "active": true
  }
  ```
- **Response `201 Created`**: Returns created venue object.

#### `PUT /api/venues/{venue_id}`
Updates an existing venue's parameters, capacity, or operating hours.
- **Access**: Admins only
- **Response `200 OK`**: Returns updated venue object.

---

### Bookings & Calendar Endpoints

#### `GET /api/bookings`
Retrieves all approved and pending reservations for a given date range to populate the shared calendar.
- **Access**: Signed-in user
- **Query Parameters**:
  - `start` (string, required): `YYYY-MM-DD`
  - `end` (string, required): `YYYY-MM-DD`
- **Response `200 OK`**:
  ```json
  [
    {
      "id": 14,
      "title": "Robotics Workshop",
      "description": "Hands-on ROS session",
      "event_type": "Workshop",
      "organizer": "Robotics Club",
      "venue_id": 2,
      "venue_name": "Sambhram Auditorium",
      "venue_color": "#0891b2",
      "start": "2026-10-30 14:00",
      "end": "2026-10-30 17:00",
      "attendees": 80,
      "status": "approved",
      "admin_note": "",
      "booked_by": "Rajath K",
      "booked_by_email": "rajath@nmamit.in",
      "created_at": "2026-10-28T08:00:00Z",
      "mine": true,
      "can_cancel": true
    }
  ]
  ```

#### `GET /api/bookings/mine`
Returns up to 200 historical and upcoming bookings belonging to the current user.
- **Access**: Signed-in user
- **Response `200 OK`**: Array of shaped booking objects.

#### `POST /api/bookings`
Creates a new booking reservation. If the venue does not require approval or the requester is an admin, the booking is instantly marked `approved`; otherwise it defaults to `pending`.
- **Access**: Signed-in user
- **Request Body**:
  ```json
  {
    "title": "Cloud Computing Seminar",
    "description": "Guest lecture by industry expert",
    "event_type": "Seminar",
    "organizer": "Dept. of CSE",
    "venue_id": 2,
    "date": "2026-10-31",
    "start_time": "10:00",
    "end_time": "12:00",
    "attendees": 90
  }
  ```
- **Response `201 Created`**: Returns created booking object.
- **Error Codes**: `409 Conflict` if the slot clashes with an existing booking, returning conflict details and alternative recommendations.

#### `POST /api/bookings/{booking_id}/cancel`
Cancels an existing booking. Can only be performed by the booking owner or an administrator.
- **Access**: Booking Owner or Admin
- **Response `200 OK`**: `{ "ok": true }`

#### `GET /api/bookings/{booking_id}/ics`
Generates and downloads an RFC-5545 compliant `.ics` calendar invitation for Google Calendar or Outlook.
- **Access**: Signed-in user
- **Response `200 OK`**: `text/calendar` attachment.

---

### Conflict & Availability Endpoints

#### `POST /api/check`
Performs a live availability check as the user modifies the booking form.
- **Access**: Signed-in user
- **Request Body**:
  ```json
  {
    "venue_id": 1,
    "date": "2026-10-30",
    "start_time": "10:00",
    "end_time": "12:00",
    "attendees": 500,
    "exclude_id": 0
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "ok": true,
    "problems": [],
    "warnings": ["Sadananda Open Air Auditorium bookings need admin approval."],
    "conflicts": [],
    "alternatives": { "same_venue": [], "other_venues": [], "other_days": [] },
    "recommended_venues": [
      { "venue_id": 1, "name": "Sadananda Open Air Auditorium", "capacity": 2500, "score": 93 }
    ]
  }
  ```

---

### Administrative & Stats Endpoints

#### `GET /api/bookings/pending`
Fetches all pending bookings with start times in the future, including detected clash conflicts.
- **Access**: Admins only
- **Response `200 OK`**: Array of pending bookings with nested `clashes` array.

#### `POST /api/bookings/{booking_id}/decision`
Records an administrative approval or rejection decision.
- **Access**: Admins only
- **Request Body**:
  ```json
  {
    "decision": "rejected",
    "note": "Venue scheduled for annual maintenance on that date."
  }
  ```
- **Response `200 OK`**: `{ "ok": true }`
- **Error Codes**: `409 Conflict` if approving would clash with another already-approved reservation.

#### `GET /api/stats`
Aggregates booking metrics and 7-day venue utilization.
- **Access**: Admins only
- **Response `200 OK`**:
  ```json
  {
    "counts": { "approved": 12, "pending": 3, "rejected": 1, "cancelled": 2 },
    "utilisation": [
      { "id": 1, "name": "Sadananda Open Air Auditorium", "color": "#4f46e5", "hours": 14.5 },
      { "id": 2, "name": "Sambhram Auditorium", "color": "#0891b2", "hours": 9.0 }
    ]
  }
  ```

---

### AI Assistant Endpoint

#### `POST /api/ai/assistant`
Interacts with the conversational AI assistant.
- **Access**: Signed-in user
- **Request Body**:
  ```json
  {
    "message": "Seminar hall for 80 people next Friday 2-4pm for an AI workshop",
    "history": [
      { "role": "user", "content": "Hello" },
      { "role": "assistant", "content": "How can I help you book a venue today?" }
    ]
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "reply": "Sambhram Auditorium is free then. Review the draft and confirm.",
    "intent": "book",
    "source": "claude",
    "draft": {
      "title": "AI Workshop",
      "event_type": "Workshop",
      "organizer": "",
      "description": "",
      "venue_id": 2,
      "date": "2026-10-30",
      "start_time": "14:00",
      "end_time": "16:00",
      "attendees": 80,
      "features": ["projector", "AC"]
    },
    "analysis": {
      "ok": true,
      "problems": [],
      "warnings": ["Sambhram Auditorium bookings need admin approval."],
      "conflicts": [],
      "alternatives": { "same_venue": [], "other_venues": [], "other_days": [] }
    }
  }
  ```

---

## 8. Repository Structure & Code Map

```
D:\Rajath_Task\
├── backend/                        # FastAPI application & database scripts
│   ├── .env.example                # Sample environment configuration template
│   ├── requirements.txt            # Python dependencies (FastAPI, psycopg, Anthropic)
│   └── app/
│       ├── __init__.py             # Package marker
│       ├── main.py                 # FastAPI endpoints, request schemas, lifecycle hooks
│       ├── auth.py                 # Session management, domain checks, cookie helpers
│       ├── db.py                   # Psycopg pooler initialization, database seed logic
│       ├── scheduler.py            # Conflict engine, free slot search, fit algorithms
│       ├── ai.py                   # Claude prompt engineering & regex fallback parser
│       ├── timeutil.py             # IST timezone utilities & string timestamp formatters
│       └── schema.sql              # PostgreSQL DDL tables, indexes, and RLS commands
│
├── frontend/                       # Next.js 16 Web Application
│   ├── package.json                # Frontend dependencies (Next 16, React 19, TypeScript)
│   ├── tsconfig.json               # TypeScript compiler options
│   ├── next.config.ts              # Next.js config & /api/* reverse-proxy rewrites
│   └── src/
│       ├── app/
│       │   ├── globals.css         # Custom semantic CSS design system & dark mode tokens
│       │   ├── layout.tsx          # Root HTML layout with Geist font definition
│       │   ├── login/
│       │   │   └── page.tsx        # Sign-in page with real-time domain feedback
│       │   └── (app)/
│       │       ├── layout.tsx      # Authenticated shell layout
│       │       ├── calendar/
│       │       │   └── page.tsx    # Calendar page route
│       │       ├── mine/
│       │       │   └── page.tsx    # Personal bookings page route
│       │       └── admin/
│       │           └── page.tsx    # Admin dashboard route
│       │
│       ├── components/
│       │   ├── AppShell.tsx        # Top navigation bar, auth context provider, toast alert
│       │   ├── Calendar.tsx        # Month grid & multi-lane week/day time grid views
│       │   ├── BookingDialog.tsx   # Interactive booking modal with live /api/check
│       │   ├── Assistant.tsx       # Conversational AI drawer & draft recommendation card
│       │   ├── EventDetails.tsx    # Booking inspection modal with cancellation & .ics
│       │   └── Modal.tsx           # Accessible dialog backdrop with focus trap & ESC listener
│       │
│       ├── views/
│       │   ├── CalendarView.tsx    # State management for calendar view modes & filters
│       │   ├── MyBookingsView.tsx  # Upcoming/past listing and cancellation actions
│       │   └── AdminView.tsx       # Pending approvals queue, venue CRUD, usage metrics
│       │
│       └── lib/
│           ├── api.ts              # Typed fetch wrapper with structured error handling
│           ├── dates.ts            # Campus time helpers, date math, range formatting
│           └── types.ts            # TypeScript interfaces for API payloads and entities
│
└── README.md                       # Comprehensive project documentation (this file)
```

---

## 9. Configuration & Environment Variables

All sensitive configuration is read from `backend/.env`. A template is provided in [`backend/.env.example`](backend/.env.example).

### Backend Variables (`backend/.env`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | String | *Required* | PostgreSQL connection string. Use Supabase IPv4 **Session pooler** (`port 5432`). |
| `DB_POOL_SIZE` | Integer | `5` | Maximum number of concurrent database connections in the psycopg pool. |
| `ADMIN_EMAILS` | String | `admin@nmamit.in` | Comma-separated list of emails granted administrative privileges upon login. |
| `ADMIN_INITIAL_EMAIL` | String | `admin@nmamit.in` | Email for the initial admin account created at startup. Must also be in `ADMIN_EMAILS` and use an allowed domain. |
| `ADMIN_INITIAL_PASSWORD` | String | *Required for initial admin setup* | Initial password used only when creating the admin or upgrading a passwordless record. Stored as a scrypt hash; it does not reset an existing password. Keep this value private. |
| `ALLOWED_DOMAINS` | String | `nmamit.in,nitte.edu.in` | Comma-separated list of allowed email domain suffixes. |
| `ANTHROPIC_API_KEY` | String | *Optional* | Anthropic API key to activate Claude Opus 5.5 natural language processing. |
| `ANTHROPIC_MODEL` | String | `claude-opus-5-5` | Model identifier for Anthropic Claude. |
| `AI_DISABLED` | Boolean | `false` | Set to `true` to force the assistant into rule-based offline parsing mode. |
| `ENV` | String | `development` | Environment mode. Set to `production` to enforce `Secure` HTTPS cookies. |

### Frontend Variables (`frontend/.env.local` or Environment)

| Variable | Type | Default | Description |
|---|---|---|---|
| `BACKEND_URL` | String | `http://127.0.0.1:8000` | Target URL used by Next.js rewrites to proxy `/api/*` calls. |

---

## 10. Local Development Setup

### Prerequisites
- **Python**: Version 3.10, 3.11, or 3.12 installed.
- **Node.js**: Version 20.x or 22.x LTS with `npm`.
- **Supabase Account**: Free account at [supabase.com](https://supabase.com).

---

### 1. Database Provisioning (Supabase Postgres)

1. Sign in to your [Supabase Dashboard](https://supabase.com/dashboard) and click **New project**.
2. Set a project name (e.g., `nmamit-campus-booking`) and database password.
3. Choose the **Mumbai (ap-south-1)** region to minimize latency to campus users.
4. Navigate to **Project Settings** → **Database** → **Connection Pooling** (or click the **Connect** button in the dashboard).
5. Select the **Session pooler** mode on **Port 5432** (essential for standard IPv4 network connectivity).
6. Copy the connection URI:
   ```
   postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
   ```
7. *Special Characters*: If your database password contains special characters (`@`, `#`, `$`, `/`), URL-encode them (e.g., `@` becomes `%40`, `#` becomes `%23`).

> [!NOTE]
> You do **not** need to manually execute SQL scripts in Supabase. On initial backend launch, [`backend/app/db.py`](backend/app/db.py) will automatically execute [`backend/app/schema.sql`](backend/app/schema.sql), populate sample venues and bookings if the tables are empty, and update untouched legacy sample venues to the current venue list while preserving their IDs and bookings.

---

### 2. Backend Setup (FastAPI)

Open a terminal and navigate to the `backend/` directory:

```bash
# Navigate to backend
cd backend

# Create Python virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (cmd.exe):
.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env from template
copy .env.example .env    # Windows
# cp .env.example .env    # Linux / macOS
```

Open `backend/.env` in your text editor and configure:
```ini
DATABASE_URL=postgresql://postgres.yourprojectid:yourpassword@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
ADMIN_EMAILS=admin@nmamit.in,coordinator@nitte.edu.in
ADMIN_INITIAL_EMAIL=admin@nmamit.in
ADMIN_INITIAL_PASSWORD=replace-with-a-private-password
ALLOWED_DOMAINS=nmamit.in,nitte.edu.in
ANTHROPIC_API_KEY=sk-ant-api03-...   # Optional (falls back to rule-based parser if omitted)
ENV=development
```

Start the FastAPI development server:
```bash
python -m uvicorn app.main:app --reload --port 8000
```
The API server will run at `http://localhost:8000`. You can inspect the interactive OpenAPI documentation at `http://localhost:8000/docs`.

---

### 3. Frontend Setup (Next.js)

Open a separate terminal window and navigate to the `frontend/` directory:

```bash
# Navigate to frontend
cd frontend

# Install npm packages
npm install

# Start Next.js development server
npm run dev
```

Open `http://localhost:3000` in your web browser.

#### Signing In
- Register with an email matching an allowed college domain, then sign in using that email and password.
- The initial admin account is bootstrapped from `ADMIN_INITIAL_EMAIL` and `ADMIN_INITIAL_PASSWORD` when the backend starts. If its account already has a password, later startup runs will not reset it.
- If you sign in using an address listed in `ADMIN_EMAILS`, the **Admin** navigation tab will appear automatically.

---

## 11. Production Deployment & Security Best Practices

### 1. Cookie & Session Security
- In production, ensure the backend runs behind HTTPS and set `ENV=production` in `backend/.env`.
- This ensures the `nb_session` cookie is marked with the `Secure` flag, preventing transmission over unencrypted HTTP.
- The cookie is configured with `HttpOnly=True` and `SameSite=Lax`, protecting against Cross-Site Scripting (XSS) and Cross-Site Request Forgery (CSRF).

### 2. Email Verification Hardening (Roadmap)
The current sign-in mechanism is designed for low-friction campus demos and trusted intranets; it validates domain format but does not send verification codes. For production campus deployment:
- **Email OTP / Magic Links**: Transmit a 6-digit one-time passcode to the user's campus mailbox via SMTP / Resend before issuing a session token.
- **Single Sign-On (SSO)**: Connect Next.js / FastAPI to Google Workspace for Education via OpenID Connect (OIDC) or SAML 2.0 to enforce institutional multi-factor authentication (MFA).

### 3. Production Frontend Build
To run the Next.js frontend in production mode:
```bash
cd frontend
npm run build
npm run start
```

### 4. Database Connection Pool Management
- When scaling backend worker processes (e.g., `uvicorn app.main:app --workers 4`), ensure the aggregate connections (`workers * DB_POOL_SIZE`) do not exceed Supabase's max connection quota.
- Setting `prepare_threshold=None` in `backend/app/db.py` allows seamless operation through transaction poolers like PgBouncer.

---

## 12. Troubleshooting & FAQ

### 1. Backend startup fails with `Tenant or user not found` or connection timeout
- **Cause**: Using the direct PostgreSQL connection instead of the session pooler, or IPv6 incompatibility on your local network.
- **Fix**: Open Supabase **Connect** settings, choose **Session pooler** mode on port **5432**, and confirm your network resolves the `aws-0-ap-south-1.pooler.supabase.com` hostname.

### 2. Backend startup fails with `password authentication failed`
- **Cause**: Special characters in the database password (such as `@`, `#`, `$`, `%`) that break URI parsing.
- **Fix**: URL-encode special characters in `DATABASE_URL` (e.g., `P@ssword!` becomes `P%40ssword%21`).

### 3. Frontend displays "Cannot reach the booking server. Is the backend running?"
- **Cause**: The FastAPI server on port 8000 is not running, or `BACKEND_URL` in Next.js points to an incorrect host.
- **Fix**: Verify that `http://localhost:8000/api/config` returns valid JSON in your browser.

### 4. How do I enable the Claude Opus AI assistant?
- **Fix**: Add a valid Anthropic API key to `backend/.env` under `ANTHROPIC_API_KEY=sk-ant-...` and restart the backend. If no key is provided, the application will display *"Offline mode: rule-based parsing"* and continue operating normally using the regex engine.

### 5. How do I grant an account Admin permissions?
- **Fix**: Add the user's email address to `ADMIN_EMAILS` in `backend/.env` (comma-separated if multiple, e.g. `ADMIN_EMAILS=admin@nmamit.in,dean@nmamit.in`). Next time that user signs in, their account role will be automatically synchronized to `admin`.

---

## License

Developed for NMAM Institute of Technology (NMAMIT), Nitte Deemed to be University. All rights reserved.