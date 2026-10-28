"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { fromMinutes, nowCampus, toMinutes } from "@/lib/dates";
import type { Analysis, Booking, BookingDraft, Slot } from "@/lib/types";
import { useApp } from "./AppShell";
import Modal from "./Modal";

const EMPTY: BookingDraft = {
  title: "", event_type: "Workshop", organizer: "", description: "",
  venue_id: 0, date: "", start_time: "10:00", end_time: "12:00", attendees: 0,
};

export default function BookingDialog({ prefill, onClose }: { prefill: Partial<BookingDraft>; onClose: () => void }) {
  const { config, venues, bookingsChanged, toast } = useApp();
  const [form, setForm] = useState<BookingDraft>(() => {
    const merged = { ...EMPTY, date: nowCampus().date, ...stripEmpty(prefill) };
    if (!config.eventTypes.includes(merged.event_type)) merged.event_type = "Other";
    return merged;
  });
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const set = <K extends keyof BookingDraft>(key: K, value: BookingDraft[K]) => setForm((f) => ({ ...f, [key]: value }));

  // Live availability check, debounced, whenever the where/when/how-many fields change.
  const { venue_id, date, start_time, end_time, attendees } = form;
  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(async () => {
      setChecking(true);
      try {
        const a = await api<Analysis>("/check", { body: { venue_id, date, start_time, end_time, attendees } });
        if (!cancelled) setAnalysis(a);
      } catch {
        if (!cancelled) setAnalysis(null);
      } finally {
        if (!cancelled) setChecking(false);
      }
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [venue_id, date, start_time, end_time, attendees]);

  function applySlot(s: Pick<Slot, "venue_id" | "date" | "start_time" | "end_time">) {
    setForm((f) => ({ ...f, venue_id: s.venue_id, date: s.date, start_time: s.start_time, end_time: s.end_time }));
  }

  function changeStart(value: string) {
    // Keep the duration when the start moves.
    setForm((f) => {
      if (!value || !f.start_time || !f.end_time) return { ...f, start_time: value };
      const dur = Math.max(30, toMinutes(f.end_time) - toMinutes(f.start_time));
      return { ...f, start_time: value, end_time: fromMinutes(Math.min(toMinutes(value) + dur, 23 * 60 + 45)) };
    });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!form.title.trim()) return setError("Give the event a title.");
    if (!form.venue_id) return setError("Choose a venue.");
    setSaving(true);
    try {
      const b = await api<Booking>("/bookings", { body: form });
      bookingsChanged();
      toast(b.status === "approved" ? `Booked ${b.venue_name}. It's on the calendar.` : `Request sent. ${b.venue_name} needs admin approval.`);
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.data.analysis) setAnalysis(err.data.analysis as Analysis);
      setError(err instanceof Error ? err.message : "Could not save the booking.");
    } finally {
      setSaving(false);
    }
  }

  const venue = venues.find((v) => v.id === form.venue_id);

  return (
    <Modal title="New booking" onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <div className="form-grid">
          <label className="span-2">
            Event title
            <input value={form.title} onChange={(e) => set("title", e.target.value)} maxLength={120} placeholder="e.g. Workshop on Cloud Computing" required />
          </label>
          <label>
            Event type
            <select value={form.event_type} onChange={(e) => set("event_type", e.target.value)}>
              {config.eventTypes.map((t) => <option key={t}>{t}</option>)}
            </select>
          </label>
          <label>
            Organising club / department
            <input value={form.organizer} onChange={(e) => set("organizer", e.target.value)} maxLength={120} placeholder="e.g. Dept. of ISE" />
          </label>
          <label className="span-2">
            Venue
            <select value={form.venue_id || ""} onChange={(e) => set("venue_id", Number(e.target.value))} required>
              <option value="">Choose a venue…</option>
              {venues.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} · {v.block} · {v.capacity} seats{v.requires_approval ? "" : " · instant"}
                </option>
              ))}
            </select>
            {venue && <span className="hint">{venue.features.join(" · ")} · open {venue.open_time}–{venue.close_time}</span>}
          </label>
          <label>
            Date
            <input type="date" value={form.date} min={nowCampus().date} onChange={(e) => set("date", e.target.value)} required />
          </label>
          <label>
            Expected attendees
            <input type="number" min={0} step={1} value={form.attendees || ""} onChange={(e) => set("attendees", Math.max(0, Number(e.target.value) || 0))} placeholder="0" />
          </label>
          <label>
            Start
            <input type="time" step={900} value={form.start_time} onChange={(e) => changeStart(e.target.value)} required />
          </label>
          <label>
            End
            <input type="time" step={900} value={form.end_time} onChange={(e) => set("end_time", e.target.value)} required />
          </label>
          <label className="span-2">
            Description
            <textarea rows={2} value={form.description} onChange={(e) => set("description", e.target.value)} maxLength={2000} placeholder="Agenda, equipment needed, resource person…" />
          </label>
        </div>

        <SmartCheck analysis={analysis} checking={checking} currentVenue={form.venue_id} onApply={applySlot} onPickVenue={(id) => set("venue_id", id)} />

        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="modal-foot">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? "Booking…" : venue?.requires_approval ? "Request booking" : "Book venue"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function stripEmpty(p: Partial<BookingDraft>): Partial<BookingDraft> {
  return Object.fromEntries(Object.entries(p).filter(([, v]) => v !== "" && v !== 0 && v != null)) as Partial<BookingDraft>;
}

/** Shows whether the slot is free, why not, and one-click alternatives. Shared with the AI assistant. */
export function SmartCheck({
  analysis,
  checking = false,
  currentVenue,
  onApply,
  onPickVenue,
}: {
  analysis: Analysis | null;
  checking?: boolean;
  currentVenue?: number;
  onApply: (s: Slot) => void;
  onPickVenue?: (venueId: number) => void;
}) {
  if (!analysis) return null;
  const { same_venue, other_venues, other_days } = analysis.alternatives;
  const recs = analysis.recommended_venues.filter((r) => r.venue_id !== currentVenue);

  return (
    <div className={`smart ${analysis.ok ? "smart-ok" : "smart-bad"} ${checking ? "smart-checking" : ""}`} aria-live="polite">
      <div className="smart-head">
        <span className="smart-icon" aria-hidden="true">{analysis.ok ? "✓" : "!"}</span>
        <strong>{analysis.ok ? "Available" : analysis.problems[0]}</strong>
      </div>
      {analysis.problems.slice(1).map((p) => <p key={p} className="smart-line">{p}</p>)}
      {analysis.warnings.map((w) => <p key={w} className="smart-line muted">{w}</p>)}

      {same_venue.length > 0 && (
        <SlotRow label="Nearby free times" slots={same_venue} render={(s) => `${s.start_time}–${s.end_time}`} onApply={onApply} />
      )}
      {other_venues.length > 0 && (
        <SlotRow label="Free at the same time" slots={other_venues} render={(s) => `${s.venue} (${s.capacity})`} onApply={onApply} />
      )}
      {other_days.length > 0 && (
        <SlotRow label="Same time, other days" slots={other_days} render={(s) => new Date(s.date + "T12:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" })} onApply={onApply} />
      )}
      {onPickVenue && recs.length > 0 && (
        <div className="chip-row">
          <span className="chip-label">Best-fit venues</span>
          {recs.map((r) => (
            <button type="button" key={r.venue_id} className="chip" onClick={() => onPickVenue(r.venue_id)}>
              {r.name} ({r.capacity})
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function SlotRow({ label, slots, render, onApply }: { label: string; slots: Slot[]; render: (s: Slot) => string; onApply: (s: Slot) => void }) {
  return (
    <div className="chip-row">
      <span className="chip-label">{label}</span>
      {slots.map((s) => (
        <button type="button" key={`${s.venue_id}-${s.date}-${s.start_time}`} className="chip" onClick={() => onApply(s)}>
          {render(s)}
        </button>
      ))}
    </div>
  );
}
