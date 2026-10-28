"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import type { AppConfig } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<AppConfig>("/config")
      .then((cfg) => (cfg.user ? router.replace("/calendar") : setConfig(cfg)))
      .catch(() => setError("Cannot reach the booking server. Is the backend running on port 8000?"));
  }, [router]);

  const domains = config?.allowedDomains ?? ["nmamit.in", "nitte.edu.in"];
  const domainText = domains.map((d) => "@" + d).join(" or ");
  const typedDomain = email.includes("@") ? email.split("@").pop()!.trim().toLowerCase() : "";
  const wrongDomain = typedDomain.includes(".") && !domains.includes(typedDomain);

  async function signIn(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/auth/login", { body: { email, name } });
      router.replace("/calendar");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in.");
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <section className="login-card">
        <div className="brand brand-lg">
          <span className="brand-mark" aria-hidden="true" />
          <div>
            <h1>NMAMIT Campus Booking</h1>
            <p className="muted">One shared calendar for every hall, lab and ground on campus, with an AI assistant that books for you.</p>
          </div>
        </div>

        <form className="stack" onSubmit={signIn} noValidate>
          <label htmlFor="email">College email</label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            placeholder="you@nmamit.in"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={wrongDomain}
            aria-describedby="email-hint"
          />
          <p id="email-hint" className={`hint ${wrongDomain ? "hint-bad" : ""}`}>
            {wrongDomain ? `@${typedDomain} isn't allowed. ` : ""}Only {domainText} addresses can sign in.
          </p>

          <label htmlFor="name">
            Your name <span className="muted small">(optional, shown on your bookings)</span>
          </label>
          <input id="name" autoComplete="name" maxLength={80} placeholder="e.g. Rajath K" value={name} onChange={(e) => setName(e.target.value)} />

          <button className="btn btn-primary" type="submit" disabled={busy || !config || !email.trim() || wrongDomain}>
            {busy ? "Signing in…" : "Continue"}
          </button>
        </form>
        {error && <p className="form-error" role="alert">{error}</p>}
      </section>
    </main>
  );
}
