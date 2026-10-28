// Calendar dates are plain "YYYY-MM-DD" strings in campus time; Date objects are only used for arithmetic.

const pad = (n: number) => String(n).padStart(2, "0");

export function toDate(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d, 12); // noon avoids DST edge cases
}

export function fromDate(dt: Date): string {
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
}

export function addDays(day: string, n: number): string {
  const dt = toDate(day);
  dt.setDate(dt.getDate() + n);
  return fromDate(dt);
}

export function addMonths(day: string, n: number): string {
  const dt = toDate(day);
  dt.setDate(1);
  dt.setMonth(dt.getMonth() + n);
  return fromDate(dt);
}

/** Monday of the week containing `day`. */
export function startOfWeek(day: string): string {
  const dow = (toDate(day).getDay() + 6) % 7;
  return addDays(day, -dow);
}

export function monthGrid(day: string): string[] {
  const first = day.slice(0, 8) + "01";
  const start = startOfWeek(first);
  return Array.from({ length: 42 }, (_, i) => addDays(start, i));
}

export function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

export function fromMinutes(mins: number): string {
  return `${pad(Math.floor(mins / 60))}:${pad(mins % 60)}`;
}

export function formatDay(day: string, opts: Intl.DateTimeFormatOptions): string {
  return toDate(day).toLocaleDateString("en-IN", opts);
}

export function formatRange(start: string, end: string): string {
  const date = formatDay(start.slice(0, 10), { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  return `${date} · ${start.slice(11)}–${end.slice(11)}`;
}

export function nowCampus(): { date: string; time: string } {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Kolkata",
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    })
      .formatToParts(new Date())
      .map((p) => [p.type, p.value]),
  );
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
}
