import type { FeedbackType } from "../types";

interface Props {
  onAction: (action: FeedbackType) => void;
}

const actions: { value: FeedbackType; label: string; hint: string }[] = [
  { value: "important", label: "Important", hint: "Boost this sender for future ranking" },
  { value: "not_important", label: "Not important", hint: "Lower priority for similar mail" },
  { value: "mute_sender", label: "Mute sender", hint: "Deprioritize everything from this address" },
  { value: "remind_sender", label: "Remind later", hint: "Nudge follow-up on this thread" }
];

export function FeedbackPanel({ onAction }: Props) {
  return (
    <div className="feedback-panel">
      <p className="feedback-panel__title">Teach your inbox</p>
      <p className="feedback-panel__hint">Your choices refine how we adapt priority over time.</p>
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
    </div>
  );
}
