import type { FeedbackType } from "../types";

interface Props {
  onAction: (action: FeedbackType) => void;
}

const actions: { value: FeedbackType; label: string }[] = [
  { value: "important", label: "Important" },
  { value: "not_important", label: "Not Important" },
  { value: "mute_sender", label: "Mute Sender" },
  { value: "remind_sender", label: "Remind Sender" }
];

export function FeedbackPanel({ onAction }: Props) {
  return (
    <div className="feedback-panel">
      {actions.map((action) => (
        <button key={action.value} className="feedback-btn" onClick={() => onAction(action.value)}>
          {action.label}
        </button>
      ))}
    </div>
  );
}
