import type { EmailItem } from "../types";

interface Props {
  isOpen: boolean;
  connected: boolean;
  canSend: boolean;
  sending: boolean;
  statusMessage: string;
  selectedEmail: EmailItem | null;
  to: string;
  cc: string;
  subject: string;
  body: string;
  onOpenNew: () => void;
  onOpenReply: () => void;
  onClose: () => void;
  onReconnect: () => void;
  onFieldChange: (field: "to" | "cc" | "subject" | "body", value: string) => void;
  onSend: () => void;
}

export function ComposePanel({
  isOpen,
  connected,
  canSend,
  sending,
  statusMessage,
  selectedEmail,
  to,
  cc,
  subject,
  body,
  onOpenNew,
  onOpenReply,
  onClose,
  onReconnect,
  onFieldChange,
  onSend
}: Props) {
  if (!connected) {
    return null;
  }

  return (
    <section className="composer">
      <div className="composer-header">
        <div>
          <h3>Compose</h3>
          <p>Send a new email or reply to the selected message.</p>
        </div>
        <div className="composer-actions">
          <button className="feedback-btn" onClick={onOpenNew}>
            New Email
          </button>
          <button
            className="feedback-btn"
            disabled={!selectedEmail}
            onClick={onOpenReply}
          >
            Reply
          </button>
        </div>
      </div>

      {!canSend ? (
        <div className="composer-warning">
          <p>Sending is not enabled for this Gmail connection yet.</p>
          <button className="feedback-btn" onClick={onReconnect}>
            Reconnect Gmail for Send
          </button>
        </div>
      ) : null}

      {statusMessage ? <div className="success">{statusMessage}</div> : null}

      {!isOpen ? (
        <div className="empty">Open a draft to send a new email or reply.</div>
      ) : (
        <div className="composer-form">
          <label className="composer-field">
            <span>To</span>
            <input
              value={to}
              onChange={(event) => onFieldChange("to", event.target.value)}
              placeholder="name@example.com"
            />
          </label>
          <label className="composer-field">
            <span>Cc</span>
            <input
              value={cc}
              onChange={(event) => onFieldChange("cc", event.target.value)}
              placeholder="Optional, comma-separated"
            />
          </label>
          <label className="composer-field">
            <span>Subject</span>
            <input
              value={subject}
              onChange={(event) => onFieldChange("subject", event.target.value)}
              placeholder="Subject"
            />
          </label>
          <label className="composer-field">
            <span>Body</span>
            <textarea
              rows={10}
              value={body}
              onChange={(event) => onFieldChange("body", event.target.value)}
              placeholder="Write your email here"
            />
          </label>
          <div className="composer-form-actions">
            <button className="feedback-btn" onClick={onClose}>
              Cancel
            </button>
            <button
              className="feedback-btn primary-btn"
              disabled={sending || !canSend}
              onClick={onSend}
            >
              {sending ? "Sending..." : "Send Email"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
