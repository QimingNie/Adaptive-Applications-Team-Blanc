import { type EmailItem, type ViewMode } from "../types";
import { FeedbackPanel } from "./FeedbackPanel";
import { NormalModeView } from "./NormalModeView";

interface Props {
  email: EmailItem | null;
  mode: ViewMode;
  canReply: boolean;
  onModeChange: (mode: ViewMode) => void;
  onFeedback: (action: "important" | "not_important" | "mute_sender" | "remind_sender") => void;
  onReply: () => void;
  onOpenThreadMessage?: (emailId: number) => void;
}

export function EmailDetail({
  email,
  mode,
  canReply,
  onModeChange,
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
          Pick an email from the list to read in Busy or Normal mode. The app learns from what you open
          and how you rate messages.
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
          <div className="mode-toggle" role="group" aria-label="Reading mode">
            <button
              type="button"
              className={mode === "busy" ? "mode-btn mode-btn--active" : "mode-btn"}
              onClick={() => onModeChange("busy")}
            >
              <span className="mode-btn__label">Busy</span>
              <span className="mode-btn__sub">Summary & actions</span>
            </button>
            <button
              type="button"
              className={mode === "normal" ? "mode-btn mode-btn--active" : "mode-btn"}
              onClick={() => onModeChange("normal")}
            >
              <span className="mode-btn__label">Normal</span>
              <span className="mode-btn__sub">Full message</span>
            </button>
          </div>
          <button type="button" className="btn btn-ghost btn-reply" disabled={!canReply} onClick={onReply}>
            Reply
          </button>
        </div>
      </div>
      <div className="detail-meta">
        <span>{email.sender}</span>
        <span>{new Date(email.received_at).toLocaleString()}</span>
      </div>
      <div className="detail-reason">
        <strong>Why it ranked here:</strong> {email.reason_summary || "No explanation available yet."}
      </div>
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
      <FeedbackPanel onAction={onFeedback} />
    </section>
  );
}
