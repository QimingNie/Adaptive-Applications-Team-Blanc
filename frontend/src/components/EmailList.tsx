import type { EmailItem } from "../types";

interface Props {
  items: EmailItem[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export function EmailList({ items, selectedId, onSelect }: Props) {
  if (!items.length) {
    return <div className="empty">No emails in this bucket.</div>;
  }

  return (
    <ul className="email-list">
      {items.map((item) => (
        <li
          key={item.id}
          className={selectedId === item.id ? "email-item selected" : "email-item"}
          onClick={() => onSelect(item.id)}
        >
          <div className="email-title">
            <span>{item.subject}</span>
            {item.needs_action ? <span className="badge">Action</span> : null}
          </div>
          <div className="email-meta">
            <span>{item.sender}</span>
            <span>Score {item.score.toFixed(2)}</span>
          </div>
          <p className="snippet">{item.snippet}</p>
          {item.reason_summary ? <p className="reason-chip">{item.reason_summary}</p> : null}
        </li>
      ))}
    </ul>
  );
}
