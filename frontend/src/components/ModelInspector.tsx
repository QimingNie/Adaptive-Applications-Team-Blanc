import type { UserModel } from "../types";

interface Props {
  isOpen: boolean;
  loading: boolean;
  saving: boolean;
  model: UserModel | null;
  importantDraft: string;
  mutedDraft: string;
  weightDraft: Record<string, string>;
  onImportantChange: (value: string) => void;
  onMutedChange: (value: string) => void;
  onWeightChange: (key: string, value: string) => void;
  onSave: () => void;
  onReset: () => void;
}

function formatAffinity(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

export function ModelInspector({
  isOpen,
  loading,
  saving,
  model,
  importantDraft,
  mutedDraft,
  weightDraft,
  onImportantChange,
  onMutedChange,
  onWeightChange,
  onSave,
  onReset
}: Props) {
  if (!isOpen) {
    return null;
  }

  return (
    <section className="model-panel">
      <div className="model-header">
        <div>
          <h3>User Model Inspector</h3>
          <p>Inspect and tune the data that drives ranking decisions.</p>
        </div>
        <div className="composer-actions">
          <button className="feedback-btn" disabled={saving || loading} onClick={onReset}>
            Reset Draft
          </button>
          <button className="feedback-btn primary-btn" disabled={saving || loading} onClick={onSave}>
            {saving ? "Saving..." : "Save Model"}
          </button>
        </div>
      </div>

      {loading && !model ? <div className="empty">Loading user model...</div> : null}

      {model ? (
        <div className="model-grid">
          <div className="busy-section">
            <h4>Scrutability Notes</h4>
            {model.scrutability_notes.map((note) => (
              <p key={note} className="model-note">
                {note}
              </p>
            ))}
          </div>

          <div className="busy-section">
            <h4>Interaction Summary</h4>
            <div className="model-summary-grid">
              <span>Total events: {model.interaction_summary.total_events}</span>
              <span>Opens: {model.interaction_summary.open_count}</span>
              <span>Quick closes: {model.interaction_summary.quick_close_count}</span>
              <span>Replies: {model.interaction_summary.reply_count}</span>
              <span>Important: {model.interaction_summary.important_feedback_count}</span>
              <span>Not important: {model.interaction_summary.not_important_feedback_count}</span>
              <span>Mutes: {model.interaction_summary.mute_count}</span>
              <span>Remind sender: {model.interaction_summary.remind_count}</span>
            </div>
          </div>

          <div className="busy-section">
            <h4>Explicit Sender Preferences</h4>
            <label className="composer-field">
              <span>Important senders</span>
              <textarea
                rows={4}
                value={importantDraft}
                onChange={(event) => onImportantChange(event.target.value)}
                placeholder="Comma-separated email addresses"
              />
            </label>
            <label className="composer-field">
              <span>Muted senders</span>
              <textarea
                rows={4}
                value={mutedDraft}
                onChange={(event) => onMutedChange(event.target.value)}
                placeholder="Comma-separated email addresses"
              />
            </label>
          </div>

          <div className="busy-section">
            <h4>Feature Weights</h4>
            <div className="weight-grid">
              {model.feature_weights.map((weight) => (
                <label key={weight.key} className="composer-field weight-field">
                  <span>{weight.label}</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="2"
                    value={weightDraft[weight.key] ?? String(weight.value)}
                    onChange={(event) => onWeightChange(weight.key, event.target.value)}
                  />
                  <small>{weight.description}</small>
                </label>
              ))}
            </div>
          </div>

          <div className="busy-section">
            <h4>Learned Sender Profiles</h4>
            <div className="profile-list">
              {model.sender_profiles.length ? (
                model.sender_profiles.map((profile) => (
                  <div key={profile.sender} className="profile-card">
                    <strong>{profile.sender}</strong>
                    <span>Affinity {formatAffinity(profile.learned_affinity)}</span>
                    <span>State: {profile.explicit_state}</span>
                    <span>
                      Opens {profile.open_count} | Replies {profile.reply_count} | Quick closes{" "}
                      {profile.quick_close_count}
                    </span>
                    <span>
                      Important {profile.important_count} | Not important {profile.not_important_count} |
                      Mutes {profile.mute_count}
                    </span>
                  </div>
                ))
              ) : (
                <p className="model-note">No sender learning yet. Open, reply, and rate emails to grow the model.</p>
              )}
            </div>
          </div>

          <div className="busy-section">
            <h4>Learned Thread Profiles</h4>
            <div className="profile-list">
              {model.thread_profiles.length ? (
                model.thread_profiles.map((profile) => (
                  <div key={profile.thread_id} className="profile-card">
                    <strong>{profile.subject_hint || profile.thread_id}</strong>
                    <span>Affinity {formatAffinity(profile.learned_affinity)}</span>
                    <span>
                      Opens {profile.open_count} | Replies {profile.reply_count} | Quick closes{" "}
                      {profile.quick_close_count}
                    </span>
                    <span>
                      Important {profile.important_count} | Not important {profile.not_important_count}
                    </span>
                  </div>
                ))
              ) : (
                <p className="model-note">Thread-level learning will appear once you interact with threads repeatedly.</p>
              )}
            </div>
          </div>

          <div className="busy-section">
            <h4>Recent Learning Activity</h4>
            <p className="model-note">
              This feed shows the last manual actions and observed behaviors that changed the model.
            </p>
            <div className="learning-event-list">
              {model.recent_learning_events.length ? (
                model.recent_learning_events.map((event) => (
                  <div key={`${event.created_at}-${event.email_id}-${event.event_type}`} className="learning-event">
                    <div className="learning-event__head">
                      <span className={`learning-badge learning-badge--${event.origin}`}>
                        {event.origin === "manual" ? "Manual" : "Observed"}
                      </span>
                      <strong className={`learning-impact learning-impact--${event.impact}`}>{event.label}</strong>
                      <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time>
                    </div>
                    <p className="learning-event__detail">{event.detail}</p>
                    <p className="learning-event__meta">
                      {event.email_subject} · {event.sender}
                    </p>
                  </div>
                ))
              ) : (
                <p className="model-note">No learning activity yet. Open, reply, or rate emails to populate this feed.</p>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
