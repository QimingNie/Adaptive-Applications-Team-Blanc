import { useEffect, useState } from "react";
import { getEmailThread } from "../api";
import type { EmailItem, ThreadContextResponse } from "../types";

interface Props {
  email: EmailItem;
  onOpenThreadMessage: (emailId: number) => void;
}

function readingTimeMinutes(text: string): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 200));
}

export function NormalModeView({ email, onOpenThreadMessage }: Props) {
  const [thread, setThread] = useState<ThreadContextResponse | null>(null);
  const [threadError, setThreadError] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    setThread(null);
    setThreadError("");
    void (async () => {
      try {
        const data = await getEmailThread(email.id);
        if (!cancelled) {
          setThread(data);
        }
      } catch (e) {
        if (!cancelled) {
          setThreadError((e as Error).message);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [email.id]);

  const bodyText = email.body?.trim() || email.snippet;
  const minutes = readingTimeMinutes(bodyText);
  const breakdown = email.score_breakdown ?? [];

  return (
    <div className="normal-mode">
      <div className="normal-chrome normal-mode__chrome normal-dark-panel">
        <dl className="normal-meta-grid">
          <div className="normal-meta-row">
            <dt>From</dt>
            <dd>{email.sender}</dd>
          </div>
          <div className="normal-meta-row">
            <dt>Received</dt>
            <dd>{new Date(email.received_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</dd>
          </div>
          {email.thread_id ? (
            <div className="normal-meta-row">
              <dt>Thread</dt>
              <dd className="thread-id">{email.thread_id}</dd>
            </div>
          ) : null}
        </dl>
        <div className="normal-badges">
          {email.has_attachment ? (
            <span className="normal-badge normal-badge--attachment">Attachment</span>
          ) : null}
          {email.is_cc ? <span className="normal-badge normal-badge--cc">You are CC’d</span> : null}
          <span className="normal-badge normal-badge--muted">~{minutes} min read</span>
          <span className="normal-badge normal-badge--zone">Zone: {email.bucket}</span>
        </div>
      </div>

      <article className="normal-body normal-body--reader" aria-label="Email body">
        {bodyText}
      </article>

      <section className="normal-score-breakdown normal-dark-panel" aria-label="Score breakdown">
        <h3 className="normal-dark-panel__title">Score breakdown</h3>
        <p className="normal-dark-panel__lead">
          Weights and signals that shaped this message&apos;s rank — same logic as Busy mode, shown here for
          full-message reading.
        </p>
        {breakdown.length ? (
          <ul className="normal-score-list">
            {breakdown.map((item) => (
              <li key={`${item.label}-${item.source}`} className="normal-score-list__item">
                <div className="normal-score-list__head">
                  <strong className="normal-score-list__label">{item.label}</strong>
                  <span
                    className={
                      item.value >= 0 ? "normal-score-list__value--pos" : "normal-score-list__value--neg"
                    }
                  >
                    {item.value >= 0 ? "+" : ""}
                    {item.value.toFixed(2)}
                  </span>
                </div>
                <p className="normal-score-list__detail">{item.detail}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="normal-dark-panel__empty">No score explanation available yet.</p>
        )}
      </section>

      <section className="normal-adaptive-panel normal-dark-panel" aria-label="Adaptive notes">
        <h3 className="normal-dark-panel__title">Adaptive notes</h3>
        <p className="normal-dark-panel__lead">
          How the model characterises this message alongside your explicit preferences and past behaviour.
        </p>
        <p className="normal-dark-panel__body">
          {email.model_summary || "This message is currently using the baseline model."}
        </p>
      </section>

      <section className="normal-thread normal-dark-panel" aria-label="Thread context">
        <div className="normal-thread-header">
          <h3>Thread context</h3>
          {thread ? (
            <span className="normal-thread-count">
              {thread.messages.length} message{thread.messages.length === 1 ? "" : "s"}
            </span>
          ) : null}
        </div>
        {threadError ? <p className="normal-thread-error">{threadError}</p> : null}
        {!thread && !threadError ? <p className="normal-thread-loading">Loading thread…</p> : null}
        {thread && thread.messages.length <= 1 ? (
          <p className="normal-thread-empty">No other messages in this thread yet.</p>
        ) : null}
        {thread && thread.messages.length > 1 ? (
          <ol className="normal-thread-list">
            {thread.messages.map((m) => {
              const active = m.id === thread.current_email_id;
              return (
                <li key={m.id}>
                  <button
                    type="button"
                    className={active ? "normal-thread-item normal-thread-item--current" : "normal-thread-item"}
                    onClick={() => onOpenThreadMessage(m.id)}
                    disabled={active}
                  >
                    <span className="normal-thread-item__subject">{m.subject}</span>
                    <span className="normal-thread-item__meta">
                      {m.sender} ·{" "}
                      {new Date(m.received_at).toLocaleString(undefined, {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit"
                      })}
                    </span>
                    <span className="normal-thread-item__snippet">{m.snippet}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        ) : null}
      </section>
    </div>
  );
}
