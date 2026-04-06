import { type EmailItem, type ViewMode } from "../types";
import { FeedbackPanel } from "./FeedbackPanel";
import { NormalModeView } from "./NormalModeView";

interface Props {
  email: EmailItem | null;
  mode: ViewMode;
  canReply: boolean;
  onFeedback: (action: "important" | "not_important" | "mute_sender" | "remind_sender") => void;
  onReply: () => void;
  onOpenThreadMessage?: (emailId: number) => void;
}

export function EmailDetail({
  email,
  mode,
  canReply,
  onFeedback,
  onReply,
  onOpenThreadMessage
}: Props) {
  if (!email) {
    return (
      <section className="detail detail--placeholder" aria-live="polite">
        <div className="placeholder-illustration" aria-hidden="true" />
        <h2 className="placeholder-title">Choose a message</h2>
        <p className="placeholder-copy">
          Pick an email from the list. Use <strong>Normal</strong> / <strong>Busy</strong> in the account card
          above to switch views. Compose from the panel at the bottom.
        </p>
      </section>
    );
  }

  const busySummary = email.busy_summary || email.snippet;
  const breakdown = email.score_breakdown || [];
  const openThread = onOpenThreadMessage ?? (() => {});

  return (
    <section className={`detail ${mode === "normal" ? "detail--normal" : "detail--busy"}`}>
      <div className="detail-header">
        <h2 className="detail-subject">{email.subject}</h2>
        <div className="detail-header-actions">
          <button type="button" className="btn btn-ghost btn-reply" disabled={!canReply} onClick={onReply}>
            Reply
          </button>
        </div>
      </div>
      {mode === "busy" ? (
        <>
          <div className="detail-meta">
            <span>{email.sender}</span>
            <span>{new Date(email.received_at).toLocaleString()}</span>
          </div>
          <div className="detail-reason">
            <strong>Why it ranked here:</strong> {email.reason_summary || "No explanation available yet."}
          </div>
        </>
      ) : null}
      {mode === "busy" ? (
        <div className="busy-panel">
          <div className="busy-grid">
            <div className="busy-section">
              <h4>Action items</h4>
              <p>{email.action_items || "No explicit action detected."}</p>
            </div>
            <div className="busy-section">
              <h4>Adaptive notes</h4>
              <p>{email.model_summary || "This message is currently using the baseline model."}</p>
            </div>
          </div>
          <div className="busy-section source-preview">
            <h4>Busy summary</h4>
            <p>{busySummary}</p>
          </div>
          <div className="busy-section source-preview">
            <h4>Score breakdown</h4>
            {breakdown.length ? (
              <ul className="score-list">
                {breakdown.map((item) => (
                  <li key={`${item.label}-${item.source}`}>
                    <strong>{item.label}</strong>
                    <span className={item.value >= 0 ? "positive-score" : "negative-score"}>
                      {item.value >= 0 ? "+" : ""}
                      {item.value.toFixed(2)}
                    </span>
                    <p>{item.detail}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p>No score explanation available yet.</p>
            )}
          </div>
        </div>
      ) : (
        <div className="normal-mode-wrap">
          <NormalModeView email={email} onOpenThreadMessage={openThread} />
        </div>
      )}
      {mode === "busy" ? <FeedbackPanel onAction={onFeedback} /> : null}
    </section>
  );
}
