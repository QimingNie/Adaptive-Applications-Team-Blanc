import type { FeedbackType, PersonalizationSignalItem } from "../types";

interface Props {
  onAction: (action: FeedbackType) => void;
  manualSignals?: PersonalizationSignalItem[];
  observedSignals?: PersonalizationSignalItem[];
}

const actions: { value: FeedbackType; label: string; hint: string }[] = [
  { value: "important", label: "Important", hint: "Boost this sender for future ranking" },
  { value: "not_important", label: "Not important", hint: "Lower priority for similar mail" },
  { value: "mute_sender", label: "Mute sender", hint: "Deprioritize everything from this address" },
  { value: "remind_sender", label: "Remind later", hint: "Nudge follow-up on this thread" }
];

function renderSignalList(signals: PersonalizationSignalItem[]) {
  return (
    <ul className="feedback-signal-list">
      {signals.map((signal) => (
        <li key={`${signal.origin}-${signal.label}`} className={`feedback-signal feedback-signal--${signal.impact}`}>
          <div className="feedback-signal__head">
            <strong>{signal.label}</strong>
            <span className={`feedback-signal__impact feedback-signal__impact--${signal.impact}`}>
              {signal.impact}
            </span>
          </div>
          <p>{signal.detail}</p>
        </li>
      ))}
    </ul>
  );
}

export function FeedbackPanel({ onAction, manualSignals = [], observedSignals = [] }: Props) {
  return (
    <div className="feedback-panel">
      <p className="feedback-panel__title">Personalize this inbox</p>
      <p className="feedback-panel__hint">
        Manual actions update the model immediately. The system also learns automatically from opens,
        quick closes, and replies.
      </p>
      <div className="feedback-panel__actions">
        {actions.map((action) => (
          <button
            key={action.value}
            type="button"
            title={action.hint}
            className={`feedback-btn feedback-btn--${action.value}`}
            onClick={() => onAction(action.value)}
          >
            {action.label}
          </button>
        ))}
      </div>
      <div className="feedback-panel__signals">
        <section className="feedback-card" aria-label="Manual personalization already applied">
          <div className="feedback-card__head">
            <h4>Applied manually</h4>
            <span>{manualSignals.length}</span>
          </div>
          {manualSignals.length ? (
            renderSignalList(manualSignals)
          ) : (
            <p className="feedback-empty">No manual boosts or mutes have been applied to this email yet.</p>
          )}
        </section>
        <section className="feedback-card" aria-label="Automatic learning signals">
          <div className="feedback-card__head">
            <h4>Learned automatically</h4>
            <span>{observedSignals.length}</span>
          </div>
          {observedSignals.length ? (
            renderSignalList(observedSignals)
          ) : (
            <p className="feedback-empty">
              Open, quick-close, or reply to this email and the system will start showing the learned
              signals here.
            </p>
          )}
        </section>
      </div>
      <p className="feedback-panel__footnote">
        Quick closes are recorded automatically when you leave a message in under 6 seconds.
      </p>
    </div>
  );
}
