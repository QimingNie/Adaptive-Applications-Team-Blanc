import { type EmailItem, type ViewMode } from "../types";
import { FeedbackPanel } from "./FeedbackPanel";

interface Props {
  email: EmailItem | null;
  mode: ViewMode;
  canReply: boolean;
  onModeChange: (mode: ViewMode) => void;
  onFeedback: (action: "important" | "not_important" | "mute_sender" | "remind_sender") => void;
  onReply: () => void;
}

export function EmailDetail({ email, mode, canReply, onModeChange, onFeedback, onReply }: Props) {
  if (!email) {
    return <div className="detail empty">Select an email to view details.</div>;
  }

  const busySummary = email.busy_summary || email.snippet;
  const breakdown = email.score_breakdown || [];

  return (
    <section className="detail">
      <div className="detail-header">
        <h2>{email.subject}</h2>
        <div className="detail-header-actions">
          <div className="mode-toggle">
            <button
              className={mode === "busy" ? "active" : ""}
              onClick={() => onModeChange("busy")}
            >
              Busy
            </button>
            <button
              className={mode === "normal" ? "active" : ""}
              onClick={() => onModeChange("normal")}
            >
              Normal
            </button>
          </div>
          <button className="feedback-btn" disabled={!canReply} onClick={onReply}>
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
              <h4>Action Items</h4>
              <p>{email.action_items || "No explicit action detected."}</p>
            </div>
            <div className="busy-section">
              <h4>Adaptive Notes</h4>
              <p>{email.model_summary || "This message is currently using the baseline model."}</p>
            </div>
          </div>
          <div className="busy-section source-preview">
            <h4>Busy Summary</h4>
            <p>{busySummary}</p>
          </div>
          <div className="busy-section source-preview">
            <h4>Score Breakdown</h4>
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
        <div className="normal-panel">
          <h3>Full Content</h3>
          <p>{email.body || email.snippet}</p>
          <div className="busy-section source-preview">
            <h4>Adaptive Notes</h4>
            <p>{email.model_summary || "This message is currently using the baseline model."}</p>
          </div>
        </div>
      )}
      <FeedbackPanel onAction={onFeedback} />
    </section>
  );
}
