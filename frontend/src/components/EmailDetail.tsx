import { type EmailItem, type ViewMode } from "../types";
import { FeedbackPanel } from "./FeedbackPanel";

interface Props {
  email: EmailItem | null;
  mode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
  onFeedback: (action: "important" | "not_important" | "mute_sender" | "remind_sender") => void;
}

export function EmailDetail({ email, mode, onModeChange, onFeedback }: Props) {
  if (!email) {
    return <div className="detail empty">Select an email to view details.</div>;
  }

  const busySummary = email.busy_summary || email.snippet;

  return (
    <section className="detail">
      <div className="detail-header">
        <h2>{email.subject}</h2>
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
      </div>
      <div className="detail-meta">
        <span>{email.sender}</span>
        <span>{new Date(email.received_at).toLocaleString()}</span>
      </div>
      {mode === "busy" ? (
        <div className="busy-panel">
          <div className="busy-grid">
            <div className="busy-section">
              <h4>Action Items</h4>
              <p>{email.action_items || "No explicit action detected."}</p>
            </div>
          </div>
          <div className="busy-section source-preview">
            <h4>Busy Summary</h4>
            <p>{busySummary}</p>
          </div>
        </div>
      ) : (
        <div className="normal-panel">
          <h3>Full Content</h3>
          <p>{email.body || email.snippet}</p>
        </div>
      )}
      <FeedbackPanel onAction={onFeedback} />
    </section>
  );
}
