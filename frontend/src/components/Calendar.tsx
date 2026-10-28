"use client";

import { useEffect, useState, type MouseEvent } from "react";
import { addDays, formatDay, fromMinutes, monthGrid, nowCampus, toMinutes } from "@/lib/dates";
import type { Booking, Venue } from "@/lib/types";

export type View = "month" | "week" | "day";

const DAY_START = 7 * 60;
const DAY_END = 22 * 60;
const HOUR_PX = 52;
const px = (mins: number) => ((mins - DAY_START) / 60) * HOUR_PX;

interface Props {
  view: View;
  days: string[]; // dates shown (week: 7, day: 1, month: ignored – uses cursor)
  cursor: string;
  bookings: Booking[];
  venues: Venue[]; // visible venues
  onSlot: (date: string, time: string, venueId?: number) => void;
  onEvent: (b: Booking) => void;
  onShowDay: (date: string) => void;
}

export default function Calendar(props: Props) {
  if (props.view === "month") return <MonthView {...props} />;
  return <TimeGrid {...props} />;
}

// ---------------- month ----------------

function MonthView({ cursor, bookings, onEvent, onShowDay, onSlot }: Props) {
  const today = nowCampus().date;
  const month = cursor.slice(0, 7);
  const byDay = new Map<string, Booking[]>();
  for (const b of bookings) {
    const d = b.start.slice(0, 10);
    byDay.set(d, [...(byDay.get(d) ?? []), b]);
  }
  const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  return (
    <div className="month">
      {weekdays.map((w) => <div key={w} className="month-dow">{w}</div>)}
      {monthGrid(cursor).map((d) => {
        const items = byDay.get(d) ?? [];
        const past = d < today;
        return (
          <div
            key={d}
            className={`month-cell ${d.slice(0, 7) !== month ? "out" : ""} ${d === today ? "today" : ""} ${past ? "past" : ""}`}
            onClick={(e) => e.target === e.currentTarget && !past && onSlot(d, "10:00")}
          >
            <button className="month-date" onClick={() => onShowDay(d)} aria-label={`Show ${formatDay(d, { day: "numeric", month: "long" })} by venue`}>
              {Number(d.slice(8))}
            </button>
            {items.slice(0, 3).map((b) => (
              <button key={b.id} className={`month-chip status-${b.status}`} style={{ "--c": b.venue_color } as React.CSSProperties} onClick={() => onEvent(b)} title={`${b.title} · ${b.venue_name}`}>
                <span className="chip-time">{b.start.slice(11)}</span> {b.title}
              </button>
            ))}
            {items.length > 3 && <button className="month-more" onClick={() => onShowDay(d)}>+{items.length - 3} more</button>}
          </div>
        );
      })}
    </div>
  );
}

// ---------------- week / day-by-venue ----------------

interface Column {
  key: string;
  label: React.ReactNode;
  date: string;
  venue?: Venue;
  items: Booking[];
}

/** Assign overlapping events to side-by-side lanes. */
function layout(items: Booking[]) {
  const sorted = [...items].sort((a, b) => a.start.localeCompare(b.start) || b.end.localeCompare(a.end));
  const out: { b: Booking; lane: number; lanes: number }[] = [];
  let cluster: { b: Booking; lane: number }[] = [];
  let clusterEnd = "";
  const flush = () => {
    const lanes = Math.max(1, ...cluster.map((c) => c.lane + 1));
    cluster.forEach((c) => out.push({ ...c, lanes }));
    cluster = [];
  };
  for (const b of sorted) {
    if (cluster.length && b.start >= clusterEnd) {
      flush();
      clusterEnd = "";
    }
    const taken = new Set(cluster.filter((c) => c.b.end > b.start).map((c) => c.lane));
    let lane = 0;
    while (taken.has(lane)) lane++;
    cluster.push({ b, lane });
    if (b.end > clusterEnd) clusterEnd = b.end;
  }
  if (cluster.length) flush();
  return out;
}

function TimeGrid({ view, days, bookings, venues, onSlot, onEvent, onShowDay }: Props) {
  const [now, setNow] = useState(nowCampus);
  useEffect(() => {
    const t = setInterval(() => setNow(nowCampus()), 60_000);
    return () => clearInterval(t);
  }, []);

  const columns: Column[] =
    view === "week"
      ? days.map((d) => ({
          key: d,
          date: d,
          label: (
            <button className="col-date" onClick={() => onShowDay(d)}>
              <span>{formatDay(d, { weekday: "short" })}</span>
              <strong className={d === now.date ? "today-num" : ""}>{Number(d.slice(8))}</strong>
            </button>
          ),
          items: bookings.filter((b) => b.start.slice(0, 10) === d),
        }))
      : venues.map((v) => ({
          key: String(v.id),
          date: days[0],
          venue: v,
          label: (
            <div className="col-venue" title={`${v.name} · ${v.capacity} seats`}>
              <span className="dot" style={{ background: v.color }} />
              <span className="col-venue-name">{v.name}</span>
              <span className="muted small">{v.capacity} seats</span>
            </div>
          ),
          items: bookings.filter((b) => b.venue_id === v.id && b.start.slice(0, 10) === days[0]),
        }));

  if (view === "day" && columns.length === 0) {
    return <div className="empty">No venues selected. Turn some on in the venue list.</div>;
  }

  const hours = Array.from({ length: (DAY_END - DAY_START) / 60 }, (_, i) => DAY_START / 60 + i);

  function clickSlot(e: MouseEvent<HTMLDivElement>, col: Column) {
    if (e.target !== e.currentTarget) return;
    const y = e.nativeEvent.offsetY;
    const mins = Math.floor((DAY_START + (y / HOUR_PX) * 60) / 30) * 30;
    if (col.date < now.date || (col.date === now.date && fromMinutes(mins) < now.time)) return;
    onSlot(col.date, fromMinutes(mins), col.venue?.id);
  }

  return (
    <div className={`grid grid-${view}`} style={{ "--cols": columns.length } as React.CSSProperties}>
      <div className="grid-head">
        <div className="gutter" />
        {columns.map((c) => <div key={c.key} className="grid-col-head">{c.label}</div>)}
      </div>
      <div className="grid-body">
        <div className="gutter">
          {hours.map((h) => <div key={h} className="hour-label" style={{ height: HOUR_PX }}>{fromMinutes(h * 60)}</div>)}
        </div>
        {columns.map((col) => {
          const closedBefore = col.venue ? Math.max(0, px(toMinutes(col.venue.open_time))) : 0;
          const closedAfter = col.venue ? Math.max(0, px(DAY_END) - px(toMinutes(col.venue.close_time))) : 0;
          const past = col.date < now.date;
          return (
            <div
              key={col.key}
              className={`grid-col ${past ? "past" : ""} ${col.date === now.date && view === "week" ? "is-today" : ""}`}
              style={{ height: px(DAY_END) }}
              onClick={(e) => clickSlot(e, col)}
            >
              {hours.map((h) => <div key={h} className="hour-line" style={{ top: px(h * 60) }} />)}
              {closedBefore > 0 && <div className="closed" style={{ top: 0, height: closedBefore }} title="Closed" />}
              {closedAfter > 0 && <div className="closed" style={{ bottom: 0, height: closedAfter }} title="Closed" />}
              {col.date === now.date && toMinutes(now.time) >= DAY_START && toMinutes(now.time) <= DAY_END && (
                <div className="now-line" style={{ top: px(toMinutes(now.time)) }} />
              )}
              {layout(col.items).map(({ b, lane, lanes }) => {
                const top = px(Math.max(DAY_START, toMinutes(b.start.slice(11))));
                const height = Math.max(20, px(Math.min(DAY_END, toMinutes(b.end.slice(11)))) - top - 2);
                return (
                  <button
                    key={b.id}
                    className={`event status-${b.status} ${b.mine ? "mine" : ""}`}
                    style={{ top, height, left: `calc(${(lane / lanes) * 100}% + 2px)`, width: `calc(${100 / lanes}% - 4px)`, "--c": b.venue_color } as React.CSSProperties}
                    onClick={() => onEvent(b)}
                    title={`${b.title}\n${b.start.slice(11)}–${b.end.slice(11)} · ${b.venue_name}${b.status === "pending" ? " (pending)" : ""}`}
                  >
                    <span className="event-title">{b.title}</span>
                    <span className="event-meta">
                      {b.start.slice(11)}–{b.end.slice(11)}
                      {view === "week" && ` · ${b.venue_name}`}
                    </span>
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function rangeFor(view: View, cursor: string, weekStart: string): { start: string; end: string; days: string[] } {
  if (view === "month") {
    const grid = monthGrid(cursor);
    return { start: grid[0], end: grid[41], days: grid };
  }
  if (view === "week") {
    const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
    return { start: days[0], end: days[6], days };
  }
  return { start: cursor, end: cursor, days: [cursor] };
}
