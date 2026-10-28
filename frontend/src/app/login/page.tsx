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
  const [password, setPassword] = useState("");
  const [registering, setRegistering] = useState(false);
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
      await api(registering ? "/auth/register" : "/auth/login", {
        body: registering ? { email, name, password } : { email, password },
      });
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
          <img className="brand-mark" src="/logo.png" alt="Campus logo" />
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
            {wrongDomain ? `@${typedDomain} isn't allowed. ` : ""}Only {domainText} addresses can use this app.
          </p>

          {registering && (
            <>
              <label htmlFor="name">Your name <span className="muted small">(optional, shown on your bookings)</span></label>
              <input id="name" autoComplete="name" maxLength={80} placeholder="e.g. Rajath K" value={name} onChange={(e) => setName(e.target.value)} />
            </>
          )}

          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            required
            minLength={registering ? 8 : undefined}
            maxLength={128}
            autoComplete={registering ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {registering && (
            <p className="hint">
              Use at least 8 characters. The app does not verify email ownership.
            </p>
          )}

          <button className="btn btn-primary" type="submit" disabled={busy || !config || !email.trim() || wrongDomain}>
            {busy ? (registering ? "Creating account…" : "Signing in…") : registering ? "Create account" : "Sign in"}
          </button>
          <p className="hint">
            {registering ? "Already have an account? " : "New to campus booking? "}
            <button type="button" className="link" onClick={() => { setRegistering(!registering); setError(""); }}>
              {registering ? "Sign in" : "Create an account"}
            </button>
          </p>
        </form>
        {error && <p className="form-error" role="alert">{error}</p>}
      </section>
    </main>
  );
}
