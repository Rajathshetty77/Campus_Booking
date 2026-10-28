"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useApp } from "@/components/AppShell";
import Modal from "@/components/Modal";
import { api } from "@/lib/api";
import { formatRange } from "@/lib/dates";
import type { Booking, Venue } from "@/lib/types";

interface Stats {
  counts: Partial<Record<Booking["status"], number>>;
  utilisation: { id: number; name: string; color: string; hours: number }[];
}

export default function AdminView() {
  const { user, refreshKey, bookingsChanged, reloadVenues, toast } = useApp();
  const [pending, setPending] = useState<Booking[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [allVenues, setAllVenues] = useState<Venue[]>([]);
  const [editing, setEditing] = useState<Partial<Venue> | null>(null);

  const load = useCallback(() => {
    api<Booking[]>("/bookings/pending").then(setPending).catch(() => setPending([]));
    api<Stats>("/stats").then(setStats).catch(() => setStats(null));
    api<Venue[]>("/venues?all=1").then(setAllVenues).catch(() => setAllVenues([]));
  }, []);

  useEffect(() => {
    if (user.role === "admin") load();
  }, [user.role, load, refreshKey]);

  if (user.role !== "admin") return <div className="page"><div className="empty">Admins only.</div></div>;

  async function decide(b: Booking, decision: "approved" | "rejected") {
    let note = "";
    if (decision === "rejected") {
      const input = prompt(`Reason for rejecting "${b.title}" (shown to the requester):`, "");
      if (input === null) return;
      note = input;
    }
    try {
      await api(`/bookings/${b.id}/decision`, { body: { decision, note } });
      toast(decision === "approved" ? "Approved." : "Rejected.");
      bookingsChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed.");
    }
  }

  const c = stats?.counts ?? {};

  return (
    <div className="page">
      <div className="page-head"><h1>Admin</h1></div>

      <div className="stat-row">
        <Stat label="Pending approval" value={c.pending ?? 0} accent />
        <Stat label="Upcoming approved" value={c.approved ?? 0} />
        <Stat label="Rejected" value={c.rejected ?? 0} />
        <Stat label="Cancelled" value={c.cancelled ?? 0} />
      </div>

      <h2 className="section-title">Waiting for approval</h2>
      {pending === null ? (
        <span className="spinner" aria-label="Loading" />
      ) : pending.length === 0 ? (
        <p className="muted">Nothing waiting. 🎉</p>
      ) : (
        <ul className="card-list">
          {pending.map((b) => (
            <li key={b.id} className="booking-card" style={{ "--c": b.venue_color } as React.CSSProperties}>
              <div className="booking-main">
                <div className="booking-title">{b.title}</div>
                <div className="muted small">
                  {formatRange(b.start, b.end)} · {b.venue_name} · {b.attendees || "?"} people · {b.event_type}
                </div>
                <div className="small">
                  {b.booked_by} ({b.booked_by_email}){b.organizer && ` for ${b.organizer}`}
                </div>
                {b.description && <div className="small muted">{b.description}</div>}
                {b.clashes && b.clashes.length > 0 && (
                  <div className="clash">⚠ Overlaps {b.clashes.map((x) => `"${x.title}" (${x.status})`).join(", ")}</div>
                )}
              </div>
              <div className="booking-actions">
                <button className="btn btn-primary btn-sm" onClick={() => decide(b, "approved")}>Approve</button>
                <button className="btn btn-ghost btn-sm" onClick={() => decide(b, "rejected")}>Reject</button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="section-head">
        <h2 className="section-title">Venues</h2>
        <button className="btn btn-ghost" onClick={() => setEditing({})}>+ Add venue</button>
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th>Venue</th><th>Type</th><th>Seats</th><th>Hours</th><th>Approval</th><th>Status</th><th /></tr>
          </thead>
          <tbody>
            {allVenues.map((v) => (
              <tr key={v.id}>
                <td><span className="dot" style={{ background: v.color }} /> {v.name}<div className="muted small">{v.block}</div></td>
                <td>{v.type}</td>
                <td>{v.capacity}</td>
                <td>{v.open_time}–{v.close_time}</td>
                <td>{v.requires_approval ? "Required" : "Instant"}</td>
                <td>{v.active ? "Bookable" : <span className="muted">Disabled</span>}</td>
                <td><button className="link" onClick={() => setEditing(v)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="section-title">Booked hours, next 7 days</h2>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Venue</th><th className="num">Approved hours</th></tr></thead>
          <tbody>
            {stats?.utilisation.map((u) => (
              <tr key={u.id}>
                <td><span className="dot" style={{ background: u.color }} /> {u.name}</td>
                <td className="num">{u.hours}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <VenueDialog
          venue={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            toast("Venue saved.");
            load();
            await reloadVenues();
          }}
        />
      )}
    </div>
  );
}

function Stat({ label, value, accent = false }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className={`stat ${accent && value > 0 ? "stat-accent" : ""}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function VenueDialog({ venue, onClose, onSaved }: { venue: Partial<Venue>; onClose: () => void; onSaved: () => void }) {
  const [v, setV] = useState({
    name: venue.name ?? "",
    block: venue.block ?? "",
    type: venue.type ?? "",
    capacity: venue.capacity ?? 50,
    color: venue.color ?? "#2563eb",
    open_time: venue.open_time ?? "08:00",
    close_time: venue.close_time ?? "20:00",
    features: (venue.features ?? []).join(", "),
    requires_approval: venue.requires_approval ?? true,
    active: venue.active ?? true,
  });
  const [error, setError] = useState("");

  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    const body = { ...v, features: v.features.split(",").map((f) => f.trim()).filter(Boolean) };
    try {
      await api(venue.id ? `/venues/${venue.id}` : "/venues", { method: venue.id ? "PUT" : "POST", body });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    }
  }

  const field = (key: keyof typeof v) => ({
    value: v[key] as string | number,
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setV({ ...v, [key]: e.target.type === "number" ? Number(e.target.value) : e.target.value }),
  });

  return (
    <Modal title={venue.id ? `Edit ${venue.name}` : "Add venue"} onClose={onClose}>
      <form onSubmit={save} noValidate>
        <div className="form-grid">
          <label className="span-2">Name<input {...field("name")} required /></label>
          <label>Block / building<input {...field("block")} /></label>
          <label>Type<input {...field("type")} placeholder="Seminar Hall, Lab…" /></label>
          <label>Capacity<input type="number" min={1} {...field("capacity")} /></label>
          <label>Colour<input type="color" {...field("color")} /></label>
          <label>Opens<input type="time" {...field("open_time")} /></label>
          <label>Closes<input type="time" {...field("close_time")} /></label>
          <label className="span-2">Facilities (comma separated)<input {...field("features")} placeholder="projector, sound system, AC" /></label>
          <label className="check"><input type="checkbox" checked={v.requires_approval} onChange={(e) => setV({ ...v, requires_approval: e.target.checked })} /> Bookings need admin approval</label>
          <label className="check"><input type="checkbox" checked={v.active} onChange={(e) => setV({ ...v, active: e.target.checked })} /> Bookable</label>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="modal-foot">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary">Save venue</button>
        </div>
      </form>
    </Modal>
  );
}
