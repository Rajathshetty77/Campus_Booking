# AI Prompts Log — NMAMIT Campus Booking System

**Problem Statement (Question 3):**
> "Design a website that allows a NMAMIT user (`nmamit.in` & `nitte.edu.in`) to book events and locations by observing a common calendar. [AI Based]"

---

## Prompt 1: Core Architecture, Domain Auth & Shared Calendar Setup
**Prompt given by us:**
> We need to build a full-stack web application for our college (NMAMIT) where students and faculty can view a common shared calendar and book campus venues like seminar halls, labs, and auditoriums. 

> Here are the main requirements from our faculty:
> 1. Only users with `@nmamit.in` and `@nitte.edu.in` emails should be allowed to register and log in. Passwords should be hashed securely (using `scrypt`), and sessions should use `HttpOnly` cookies.
> 2. We want a separate `backend/` folder using Python FastAPI and PostgreSQL (we are using Supabase), and a `frontend/` folder using Next.js (App Router, TypeScript, and clean custom CSS with light/dark mode).
> 3. Use Next.js rewrites in `next.config.ts` to proxy `/api/*` calls to FastAPI on port 8000 so session cookies stay first-party.
> 4. Pre-seed real NMAMIT campus locations like Sadananda Open Air Auditorium, Sambhram Auditorium, and Seminar Halls with capacities, opening/closing hours, and equipment tags (projector, AC, sound system).
> 5. Build a common calendar with 3 views: Month view, Week view (where overlapping events sit side-by-side in lanes), and a Day-by-Venue column view where clicking a free 30-minute slot opens the booking modal.

---

## Prompt 2: Conflict Detection, Race Condition Locking & 3-Way Alternatives
**Prompt given by us:**
> Right now, if two club coordinators try to book the same auditorium at the exact same time, both bookings might go through. Also, when a slot is already taken, the user shouldn't just get an error—they should get smart suggestions for free slots.

> Please help us implement `backend/app/scheduler.py` and update the booking endpoints in `main.py`:
> 1. Store timestamps as IST wall-clock strings (`YYYY-MM-DD HH:MM`) with `COLLATE "C"` so string comparisons can check overlaps directly.
> 2. When creating or approving a booking, use PostgreSQL pessimistic row locking (`SELECT id FROM venues WHERE id = %s FOR UPDATE`) inside a `with conn.transaction():` block so two simultaneous requests for the same venue cannot double-book it.
> 3. Create a live `/api/check` endpoint that runs as the user types in the booking modal (debounced by 350ms). It should check operating hours, past dates, seating capacity limits, under-utilization warnings (<15% capacity in large halls), and clashes.
> 4. If there is a conflict, return 3 types of alternatives:
>    - `same_venue`: nearest free time windows in the same hall on that day
>    - `other_venues`: other campus halls free at that exact time that fit the attendee count and required features
>    - `other_days`: the same hall and time slot over the next 7 days

---

## Prompt 3: Dual-Engine AI Booking Assistant (Claude + Offline Regex Fallback)
**Prompt given by us:**
> Since this is an AI-based campus booking system, we want a chat drawer where a user can type natural sentences like *"Seminar hall for 80 people next Friday 2-4pm for an AI workshop"* or ask *"Which halls are free tomorrow afternoon?"*

> Please implement `backend/app/ai.py` and `frontend/src/components/Assistant.tsx` with these rules:
> 1. Use Anthropic Claude (`claude-opus-5-5`) with a strict JSON schema (`DRAFT_SCHEMA`) and prompt caching so it extracts `intent` (`book`, `query`, or `other`), `title`, `event_type`, `venue_id`, `date`, `start_time`, `end_time`, `attendees`, and `features`.
> 2. **Important:** If we don't have an `ANTHROPIC_API_KEY` set in `.env` or if the internet is down during our lab evaluation, the app must NOT crash. Build a deterministic rule-based regex parser as a fallback that parses Indian date formats (`DD/MM/YYYY`), relative days (`tomorrow`, `next Tuesday`), time ranges (`2-4pm`), headcount, and venue names offline.
> 3. For safety, the AI should never insert a booking directly into the database. Pass the AI's extracted draft through `scheduler.analyze()` first, and show a verification card in the chat with conflict warnings and one-click alternative pills so the user can review and confirm it.

---

## Prompt 4: Admin Approval Portal, Utilisation Stats & .ics Export
**Prompt given by us:**
> Major venues at NMAMIT require approval from an administrator before the booking is finalized, while smaller rooms can be auto-approved. 

> Please add:
> 1. An Admin Portal (`AdminView.tsx`) visible only to emails listed in `ADMIN_EMAILS` (like `admin@nmamit.in`).
> 2. A Pending Approvals queue that automatically highlights if a pending request clashes with another event, allowing one-click Approve or Reject (with a rejection note shown to the student).
> 3. Venue management (add/edit venues, capacities, operating hours, and toggle `requires_approval`) plus a 7-day venue utilisation bar chart (`/api/stats`).
> 4. In the "My Bookings" tab (`/mine`), let users cancel their bookings and download an RFC-5545 `.ics` calendar file (`GET /api/bookings/{id}/ics`) with `Asia/Kolkata` timezone headers for Google Calendar.

---

## Prompt 5: Debugging Local `.venv`, Supabase Pooler & Vercel/Render Deployment
**Prompt given by us:**
> While setting up on a second Windows laptop and deploying the frontend to Vercel and backend to Render, we ran into a few errors:
> 1. `Fatal error in launcher: Unable to create process` when running `pip install` from a zipped `.venv` folder.
> 2. `psycopg_pool.PoolTimeout: pool initialization incomplete` and `invalid connection option "DATABASE_URL"` when connecting to Supabase Session Pooler.
> 3. `Request failed (502)` on the live Vercel deployment (`https://campus-booking-one.vercel.app/`).

> Help us fix the hardcoded `.venv` issue, properly URL-encode special characters (`$` to `%24`) in the Supabase `DATABASE_URL`, and configure the `BACKEND_URL` environment variable for the Next.js production rewrite proxy.