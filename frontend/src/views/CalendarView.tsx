"use client";

import { useEffect, useLayoutEffect, useMemo, useState } from "react";
import { useApp } from "@/components/AppShell";
import Calendar, { rangeFor, type View } from "@/components/Calendar";
import EventDetails from "@/components/EventDetails";
import { api } from "@/lib/api";
import { addDays, addMonths, formatDay, fromMinutes, nowCampus, startOfWeek, toMinutes } from "@/lib/dates";
import type { Booking } from "@/lib/types";

const HIDDEN_KEY = "nb.hiddenVenues";
const VIEW_KEY = "nb.view";

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null; // storage blocked: fall back to defaults
  }
}

export default function CalendarView() {
  const { venues, refreshKey, openBooking } = useApp();
  // This page only renders in the browser (AppShell waits for the session), so reading
  // per-browser preferences in the initialisers is safe.
  const [view, setView] = useState<View>(() => {
    const v = readStorage(VIEW_KEY);
    return v === "month" || v === "day" ? v : "week";
  });
  const [hidden, setHidden] = useState<Set<number>>(() => {
    try {
      return new Set(JSON.parse(readStorage(HIDDEN_KEY) || "[]"));
    } catch {
      return new Set();
    }
  });
  const [cursor, setCursor] = useState(() => nowCampus().date);
  const [loaded, setLoaded] = useState<{ key: string; rows: Booking[] }>({ key: "", rows: [] });
  const [selected, setSelected] = useState<Booking | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(VIEW_KEY, view);
      localStorage.setItem(HIDDEN_KEY, JSON.stringify([...hidden]));
    } catch {
      /* ignore */
    }
  }, [view, hidden]);

  // Transient overlays shouldn't reappear when the user navigates back to this page.
  useLayoutEffect(() => () => {
    setSelected(null);
    setSidebarOpen(false);
  }, []);

  const range = useMemo(() => rangeFor(view, cursor, startOfWeek(cursor)), [view, cursor]);

  const fetchKey = `${range.start}|${range.end}|${refreshKey}`;
  useEffect(() => {
    let cancelled = false;
    api<Booking[]>(`/bookings?start=${range.start}&end=${range.end}`)
      .catch(() => [] as Booking[])
      .then((rows) => !cancelled && setLoaded({ key: fetchKey, rows }));
    return () => {
      cancelled = true;
    };
  }, [range.start, range.end, fetchKey]);
  const loading = loaded.key !== fetchKey;
  const bookings = loaded.rows;

  const visibleVenues = venues.filter((v) => !hidden.has(v.id));
  const visibleBookings = bookings.filter((b) => !hidden.has(b.venue_id));

  function step(dir: -1 | 1) {
    setCursor((c) => (view === "month" ? addMonths(c, dir) : addDays(c, view === "week" ? 7 * dir : dir)));
  }

  function toggleVenue(id: number) {
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const title =
    view === "month"
      ? formatDay(cursor, { month: "long", year: "numeric" })
      : view === "week"
        ? `${formatDay(range.start, { day: "numeric", month: "short" })} – ${formatDay(range.end, { day: "numeric", month: "short", year: "numeric" })}`
        : formatDay(cursor, { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  return (
    <div className="calendar-page">
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <button className="btn btn-primary btn-block" onClick={() => openBooking({})}>+ New booking</button>
        <section className="side-section">
          <div className="side-head">
            <h2>Venues</h2>
            <button className="link" onClick={() => setHidden(hidden.size ? new Set() : new Set(venues.map((v) => v.id)))}>
              {hidden.size ? "Show all" : "Hide all"}
            </button>
          </div>
          <ul className="venue-list">
            {venues.map((v) => (
              <li key={v.id}>
                <label className="venue-item">
                  <input type="checkbox" checked={!hidden.has(v.id)} onChange={() => toggleVenue(v.id)} style={{ accentColor: v.color }} />
                  <span className="dot" style={{ background: v.color }} />
                  <span className="venue-name">{v.name}</span>
                  <span className="muted small">{v.capacity}</span>
                </label>
              </li>
            ))}
          </ul>
        </section>
        <section className="side-section legend">
          <h2>Status</h2>
          <div><span className="swatch swatch-approved" />Approved</div>
          <div><span className="swatch swatch-pending" />Pending approval</div>
          <div><span className="swatch swatch-closed" />Venue closed</div>
          <p className="muted small">Click an empty slot to book it. In <em>Day · by venue</em> view every column is one location.</p>
        </section>
      </aside>
      {sidebarOpen && <div className="sidebar-scrim" onClick={() => setSidebarOpen(false)} />}

      <section className="cal-wrap">
        <div className="cal-toolbar">
          <div className="cal-nav">
            <button className="icon-btn only-mobile" onClick={() => setSidebarOpen(true)} aria-label="Show venues">☰</button>
            <button className="btn btn-ghost" onClick={() => setCursor(nowCampus().date)}>Today</button>
            <button className="icon-btn" onClick={() => step(-1)} aria-label="Previous">‹</button>
            <button className="icon-btn" onClick={() => step(1)} aria-label="Next">›</button>
            <h1 className="cal-title">{title}</h1>
            {loading && <span className="spinner spinner-sm" aria-label="Loading" />}
          </div>
          <div className="seg" role="tablist" aria-label="Calendar view">
            {(["month", "week", "day"] as const).map((v) => (
              <button key={v} role="tab" aria-selected={view === v} className={view === v ? "on" : ""} onClick={() => setView(v)}>
                {v === "day" ? "Day · by venue" : v[0].toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div className="cal">
          <Calendar
            view={view}
            days={range.days}
            cursor={cursor}
            bookings={visibleBookings}
            venues={visibleVenues}
            onEvent={setSelected}
            onShowDay={(d) => {
              setCursor(d);
              setView("day");
            }}
            onSlot={(date, time, venueId) =>
              openBooking({ date, start_time: time, end_time: fromMinutes(Math.min(toMinutes(time) + 60, 23 * 60 + 45)), venue_id: venueId })
            }
          />
        </div>
      </section>

      {selected && <EventDetails booking={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
