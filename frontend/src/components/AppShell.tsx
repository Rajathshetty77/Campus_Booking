"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import type { AppConfig, BookingDraft, User, Venue } from "@/lib/types";
import Assistant from "./Assistant";
import BookingDialog from "./BookingDialog";

interface Ctx {
  config: AppConfig;
  user: User;
  venues: Venue[];
  reloadVenues: () => Promise<void>;
  /** Increments whenever bookings change, so pages know to refetch. */
  refreshKey: number;
  bookingsChanged: () => void;
  openBooking: (prefill?: Partial<BookingDraft>) => void;
  toast: (message: string) => void;
}

const AppContext = createContext<Ctx | null>(null);

export function useApp(): Ctx {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppShell>");
  return ctx;
}

const NAV = [
  { href: "/calendar", label: "Calendar" },
  { href: "/mine", label: "My bookings" },
  { href: "/admin", label: "Admin", admin: true },
] as const;

export default function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [venues, setVenues] = useState<Venue[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [bookingPrefill, setBookingPrefill] = useState<Partial<BookingDraft> | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const reloadVenues = useCallback(async () => setVenues(await api<Venue[]>("/venues")), []);

  useEffect(() => {
    api<AppConfig>("/config")
      .then(async (cfg) => {
        if (!cfg.user) return router.replace("/login");
        setConfig(cfg);
        await reloadVenues();
      })
      .catch((e: Error) => setLoadError(e instanceof ApiError ? e.message : "Cannot reach the booking server. Is the backend running?"));
  }, [router, reloadVenues]);

  useEffect(() => {
    if (!toastMsg) return;
    const t = setTimeout(() => setToastMsg(null), 3500);
    return () => clearTimeout(t);
  }, [toastMsg]);

  const value = useMemo<Ctx | null>(
    () =>
      config && config.user
        ? {
            config,
            user: config.user,
            venues,
            reloadVenues,
            refreshKey,
            bookingsChanged: () => setRefreshKey((k) => k + 1),
            openBooking: (prefill = {}) => setBookingPrefill(prefill),
            toast: setToastMsg,
          }
        : null,
    [config, venues, reloadVenues, refreshKey],
  );

  if (loadError) return <div className="splash"><p className="form-error">{loadError}</p></div>;
  if (!value) return <div className="splash"><span className="spinner" aria-label="Loading" /></div>;

  const { user } = value;
  const initials = user.name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();

  async function signOut() {
    await api("/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  return (
    <AppContext.Provider value={value}>
      <div className="app">
        <header className="topbar">
          <Link href="/calendar" className="brand">
            <span className="brand-mark" aria-hidden="true" />
            <span className="brand-name">NMAMIT <span className="muted">Campus Booking</span></span>
          </Link>
          <nav className="tabs" aria-label="Main">
            {NAV.filter((n) => !("admin" in n) || user.role === "admin").map((n) => (
              <Link key={n.href} href={n.href} className={pathname.startsWith(n.href) ? "active" : ""} onNavigate={() => setMenuOpen(false)}>
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="topbar-right">
            <button className={`btn btn-ai ${assistantOpen ? "on" : ""}`} onClick={() => setAssistantOpen((o) => !o)} aria-pressed={assistantOpen}>
              <span aria-hidden="true">✦</span> <span className="hide-sm">Ask AI</span>
            </button>
            <div className="user-menu">
              <button className="avatar" onClick={() => setMenuOpen((o) => !o)} aria-haspopup="true" aria-expanded={menuOpen} title={user.email}>
                {initials}
              </button>
              {menuOpen && (
                <div className="menu" role="menu">
                  <div className="menu-head">
                    <strong>{user.name}</strong>
                    <span className="muted small">{user.email}</span>
                    <span className={`pill pill-${user.role}`}>{user.role}</span>
                  </div>
                  <button className="menu-item" role="menuitem" onClick={signOut}>Sign out</button>
                </div>
              )}
            </div>
          </div>
        </header>

        <div className="body">
          <main className="main">{children}</main>
          {assistantOpen && <Assistant onClose={() => setAssistantOpen(false)} />}
        </div>
      </div>

      {bookingPrefill && <BookingDialog prefill={bookingPrefill} onClose={() => setBookingPrefill(null)} />}
      {toastMsg && <div className="toast" role="status">{toastMsg}</div>}
    </AppContext.Provider>
  );
}
