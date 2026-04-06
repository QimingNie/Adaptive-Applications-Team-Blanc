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

  return (
    <div className="normal-mode--minimal">
      <header className="normal-minimal-meta">
        <p className="normal-minimal-meta__line">
          <span className="normal-minimal-meta__label">From</span> {email.sender}
        </p>
        <p className="normal-minimal-meta__line">
          <span className="normal-minimal-meta__label">Received</span>{" "}
          {new Date(email.received_at).toLocaleString(undefined, {
            dateStyle: "medium",
            timeStyle: "short"
          })}
        </p>
        <div className="normal-minimal-badges">
          {email.has_attachment ? (
            <span className="normal-minimal-badge">Attachment</span>
          ) : null}
          {email.is_cc ? <span className="normal-minimal-badge">CC</span> : null}
          <span className="normal-minimal-badge normal-minimal-badge--muted">~{minutes} min read</span>
        </div>
      </header>

      <article className="normal-body normal-body--reader normal-body--minimal" aria-label="Email body">
        {bodyText}
      </article>

      <section className="normal-thread-minimal" aria-label="Thread">
        <div className="normal-thread-minimal__head">
          <h3 className="normal-thread-minimal__title">Thread</h3>
          {thread ? (
            <span className="normal-thread-minimal__count">
              {thread.messages.length} message{thread.messages.length === 1 ? "" : "s"}
            </span>
          ) : null}
        </div>
        {threadError ? <p className="normal-thread-minimal__error">{threadError}</p> : null}
        {!thread && !threadError ? <p className="normal-thread-minimal__loading">Loading…</p> : null}
        {thread && thread.messages.length <= 1 ? (
          <p className="normal-thread-minimal__empty">No other messages in this thread.</p>
        ) : null}
        {thread && thread.messages.length > 1 ? (
          <ol className="normal-thread-minimal__list">
            {thread.messages.map((m) => {
              const active = m.id === thread.current_email_id;
              return (
                <li key={m.id}>
                  <button
                    type="button"
                    className={
                      active ? "normal-thread-minimal__item normal-thread-minimal__item--current" : "normal-thread-minimal__item"
                    }
                    onClick={() => onOpenThreadMessage(m.id)}
                    disabled={active}
                  >
                    <span className="normal-thread-minimal__subj">{m.subject}</span>
                    <span className="normal-thread-minimal__meta">
                      {m.sender} ·{" "}
                      {new Date(m.received_at).toLocaleString(undefined, {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit"
                      })}
                    </span>
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
