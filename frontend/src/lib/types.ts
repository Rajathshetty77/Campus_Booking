export type Role = "member" | "admin";

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  department: string | null;
}

export interface AppConfig {
  allowedDomains: string[];
  ai: { enabled: boolean; model: string | null; reason: string | null };
  eventTypes: string[];
  today: string;
  user: User | null;
}

export interface Venue {
  id: number;
  name: string;
  block: string;
  type: string;
  capacity: number;
  features: string[];
  color: string;
  requires_approval: boolean;
  open_time: string;
  close_time: string;
  active: boolean;
}

export type BookingStatus = "pending" | "approved" | "rejected" | "cancelled";

export interface Conflict {
  id: number;
  title: string;
  start_ts: string;
  end_ts: string;
  status: BookingStatus;
  organizer: string;
}

export interface Booking {
  id: number;
  title: string;
  description: string;
  event_type: string;
  organizer: string;
  venue_id: number;
  venue_name: string;
  venue_color: string;
  start: string; // "YYYY-MM-DD HH:MM" campus time
  end: string;
  attendees: number;
  status: BookingStatus;
  admin_note: string;
  booked_by: string;
  booked_by_email: string;
  created_at: string;
  mine: boolean;
  can_cancel: boolean;
  clashes?: Conflict[];
}

export interface Slot {
  venue_id: number;
  venue: string;
  date: string;
  start_time: string;
  end_time: string;
  capacity?: number;
}

export interface Analysis {
  ok: boolean;
  problems: string[];
  warnings: string[];
  conflicts: Conflict[];
  alternatives: { same_venue: Slot[]; other_venues: Slot[]; other_days: Slot[] };
  recommended_venues: { venue_id: number; name: string; capacity: number; score: number }[];
}

export interface BookingDraft {
  title: string;
  event_type: string;
  organizer: string;
  description: string;
  venue_id: number;
  date: string;
  start_time: string;
  end_time: string;
  attendees: number;
}

export interface AssistantResult {
  reply: string;
  intent: "book" | "query" | "other";
  draft: (BookingDraft & { features: string[] }) | null;
  analysis: Analysis | null;
  source: "claude" | "rules";
}
