"use client";

import { useEffect, useState } from "react";
import { useApp } from "@/components/AppShell";
import { StatusPill } from "@/components/EventDetails";
import { api } from "@/lib/api";
import { formatRange, nowCampus } from "@/lib/dates";
import type { Booking } from "@/lib/types";

export default function MyBookingsView() {
  const { refreshKey, bookingsChanged, openBooking, toast } = useApp();
  const [rows, setRows] = useState<Booking[] | null>(null);

  useEffect(() => {
    api<Booking[]>("/bookings/mine").then(setRows).catch(() => setRows([]));
  }, [refreshKey]);

  async function cancel(b: Booking) {
    if (!confirm(`Cancel "${b.title}"?`)) return;
    try {
      await api(`/bookings/${b.id}/cancel`, { method: "POST" });
      bookingsChanged();
      toast("Booking cancelled.");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not cancel.");
    }
  }

  const now = nowCampus();
  const nowTs = `${now.date} ${now.time}`;
  const upcoming = (rows ?? []).filter((b) => b.end >= nowTs).sort((a, b) => a.start.localeCompare(b.start));
  const past = (rows ?? []).filter((b) => b.end < nowTs);

  return (
    <div className="page">
      <div className="page-head">
        <h1>My bookings</h1>
        <button className="btn btn-primary" onClick={() => openBooking({})}>+ New booking</button>
      </div>
      {rows === null ? (
        <span className="spinner" aria-label="Loading" />
      ) : rows.length === 0 ? (
        <div className="empty">You haven&apos;t booked anything yet. Pick a free slot on the calendar, or ask the AI assistant.</div>
      ) : (
        <>
          <h2 className="section-title">Upcoming</h2>
          {upcoming.length ? <List rows={upcoming} onCancel={cancel} /> : <p className="muted">Nothing upcoming.</p>}
          {past.length > 0 && (
            <>
              <h2 className="section-title">Past</h2>
              <List rows={past} />
            </>
          )}
        </>
      )}
    </div>
  );
}

function List({ rows, onCancel }: { rows: Booking[]; onCancel?: (b: Booking) => void }) {
  return (
    <ul className="card-list">
      {rows.map((b) => (
        <li key={b.id} className="booking-card" style={{ "--c": b.venue_color } as React.CSSProperties}>
          <div className="booking-main">
            <div className="booking-title">{b.title} <StatusPill status={b.status} /></div>
            <div className="muted small">{formatRange(b.start, b.end)} · {b.venue_name}{b.organizer && ` · ${b.organizer}`}</div>
            {b.admin_note && <div className="small">Admin note: {b.admin_note}</div>}
          </div>
          <div className="booking-actions">
            {["approved", "pending"].includes(b.status) && <a className="btn btn-ghost btn-sm" href={`/api/bookings/${b.id}/ics`} download>.ics</a>}
            {onCancel && b.can_cancel && <button className="btn btn-ghost btn-sm" onClick={() => onCancel(b)}>Cancel</button>}
          </div>
        </li>
      ))}
    </ul>
  );
}
