"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { formatRange } from "@/lib/dates";
import type { Booking } from "@/lib/types";
import { useApp } from "./AppShell";
import Modal from "./Modal";

export function StatusPill({ status }: { status: Booking["status"] }) {
  return <span className={`pill pill-${status}`}>{status === "pending" ? "pending approval" : status}</span>;
}

export default function EventDetails({ booking: b, onClose }: { booking: Booking; onClose: () => void }) {
  const { bookingsChanged, toast } = useApp();
  const [busy, setBusy] = useState(false);

  async function cancel() {
    if (!confirm(`Cancel "${b.title}"? This frees the venue for others.`)) return;
    setBusy(true);
    try {
      await api(`/bookings/${b.id}/cancel`, { method: "POST" });
      bookingsChanged();
      toast("Booking cancelled.");
      onClose();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not cancel.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={b.title} onClose={onClose} size="sm">
      <div className="details">
        <div className="details-row"><StatusPill status={b.status} /><span className="muted">{b.event_type}</span></div>
        <dl className="details-grid">
          <dt>When</dt><dd>{formatRange(b.start, b.end)}</dd>
          <dt>Where</dt><dd><span className="dot" style={{ background: b.venue_color }} /> {b.venue_name}</dd>
          {b.organizer && <><dt>Organiser</dt><dd>{b.organizer}</dd></>}
          {b.attendees > 0 && <><dt>Attendees</dt><dd>{b.attendees}</dd></>}
          <dt>Booked by</dt><dd>{b.booked_by} <span className="muted small">({b.booked_by_email})</span></dd>
          {b.admin_note && <><dt>Admin note</dt><dd>{b.admin_note}</dd></>}
        </dl>
        {b.description && <p className="details-desc">{b.description}</p>}
      </div>
      <div className="modal-foot">
        <a className="btn btn-ghost" href={`/api/bookings/${b.id}/ics`} download>Add to my calendar</a>
        {b.can_cancel && <button className="btn btn-danger" onClick={cancel} disabled={busy}>Cancel booking</button>}
      </div>
    </Modal>
  );
}
