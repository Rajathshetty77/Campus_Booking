"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { formatDay } from "@/lib/dates";
import type { AssistantResult, BookingDraft, Slot } from "@/lib/types";
import { useApp } from "./AppShell";
import { SmartCheck } from "./BookingDialog";

interface Message {
  role: "user" | "assistant";
  content: string;
  result?: AssistantResult;
}

const EXAMPLES = [
  "Book a seminar hall for 80 people next Friday 2–4pm for an AI workshop",
  "Which venues are free tomorrow afternoon?",
  "I need a room with video conferencing for a 1 hour meeting on Monday at 11",
];

export default function Assistant({ onClose }: { onClose: () => void }) {
  const { config, venues, openBooking } = useApp();
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const log = useRef<HTMLDivElement>(null);

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  async function send(message: string) {
    message = message.trim();
    if (!message || busy) return;
    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((m) => [...m, { role: "user", content: message }]);
    setText("");
    setBusy(true);
    try {
      const result = await api<AssistantResult>("/ai/assistant", { body: { message, history } });
      setMessages((m) => [...m, { role: "assistant", content: result.reply, result }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", content: err instanceof Error ? err.message : "Something went wrong." }]);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send(text);
  }

  return (
    <aside className="assistant" aria-label="AI booking assistant">
      <div className="assistant-head">
        <div>
          <strong>✦ Booking assistant</strong>
          <div className="muted small">
            {config.ai.enabled ? `Powered by Claude (${config.ai.model})` : "Offline mode: rule-based parsing"}
          </div>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close assistant">✕</button>
      </div>

      <div className="assistant-log" ref={log} aria-live="polite">
        {messages.length === 0 && (
          <div className="assistant-intro">
            <p>Describe your event in plain words. I&apos;ll find a venue that fits, check the shared calendar for clashes and fill in the booking form for you.</p>
            <div className="ai-examples">
              {EXAMPLES.map((ex) => <button key={ex} onClick={() => send(ex)}>{ex}</button>)}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg msg-${m.role}`}>
            <div className="bubble">{m.content}</div>
            {m.result?.intent === "book" && m.result.draft && (
              <DraftCard result={m.result} venueName={venues.find((v) => v.id === m.result!.draft!.venue_id)?.name} onOpen={openBooking} />
            )}
          </div>
        ))}
        {busy && <div className="msg msg-assistant"><div className="bubble typing"><span /><span /><span /></div></div>}
      </div>

      <form className="assistant-input" onSubmit={onSubmit}>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(text);
            }
          }}
          rows={2}
          placeholder="Describe your event, or ask what's free…"
          aria-label="Message the booking assistant"
        />
        <button className="btn btn-primary" type="submit" disabled={busy || !text.trim()}>Send</button>
      </form>
    </aside>
  );
}

function DraftCard({
  result,
  venueName,
  onOpen,
}: {
  result: AssistantResult;
  venueName?: string;
  onOpen: (prefill: Partial<BookingDraft>) => void;
}) {
  const { features: _features, ...d } = result.draft!;
  const applyAlt = (s: Slot) => onOpen({ ...d, venue_id: s.venue_id, date: s.date, start_time: s.start_time, end_time: s.end_time });
  return (
    <div className="draft-card">
      <div className="draft-title">{d.title || "Untitled event"}</div>
      <dl className="draft-grid">
        <dt>Venue</dt><dd>{venueName || "Not chosen"}</dd>
        <dt>When</dt>
        <dd>{d.date ? formatDay(d.date, { weekday: "short", day: "numeric", month: "short" }) : "No date"}{d.start_time && ` · ${d.start_time}–${d.end_time}`}</dd>
        {d.attendees > 0 && <><dt>People</dt><dd>{d.attendees}</dd></>}
        {d.event_type && <><dt>Type</dt><dd>{d.event_type}</dd></>}
      </dl>
      {result.analysis && <SmartCheck analysis={result.analysis} onApply={applyAlt} />}
      <div className="draft-actions">
        <button className="btn btn-primary btn-sm" onClick={() => onOpen(d)}>Review &amp; book</button>
        <span className="muted small">{result.source === "claude" ? "Drafted by Claude" : "Drafted by rules"}</span>
      </div>
    </div>
  );
}
