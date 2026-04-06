import type { EmailItem } from "../types";

interface Props {
  items: EmailItem[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  /** When false (Normal mode list), hide scores, zones, and action badges. */
  showAdaptiveMeta?: boolean;
}

function scorePercent(score: number): number {
  return Math.min(100, Math.max(0, Math.round(score * 100)));
}

export function EmailList({ items, selectedId, onSelect, showAdaptiveMeta = true }: Props) {
  if (!items.length) {
    return (
      <div className="empty empty--inbox">
        <p className="empty-title">Nothing here yet</p>
        <p className="empty-hint">
          {showAdaptiveMeta ? "Try another zone or sync your inbox." : "Sync your inbox or switch to Busy mode for zone filters."}
        </p>
      </div>
    );
  }

  return (
    <ul className="email-list" role="list">
      {items.map((item) => {
        const selected = selectedId === item.id;
        const pct = showAdaptiveMeta ? scorePercent(item.score) : 0;
        return (
          <li key={item.id} className="email-list__row">
            <button
              type="button"
              className={selected ? "email-item email-item--selected" : "email-item"}
              onClick={() => onSelect(item.id)}
              aria-current={selected ? "true" : undefined}
            >
              <div className="email-title">
                <span className="email-subject">{item.subject}</span>
                {showAdaptiveMeta && item.needs_action ? (
                  <span className="badge badge--action">Action</span>
                ) : null}
              </div>
              <div className="email-meta">
                <span className="email-sender">{item.sender}</span>
                {showAdaptiveMeta ? (
                  <span className="email-score-wrap" title="Adaptive priority score">
                    <span className="email-score-bar" aria-hidden>
                      <span className="email-score-fill" style={{ width: `${pct}%` }} />
                    </span>
                    <span className="email-score-val">{pct}%</span>
                  </span>
                ) : null}
              </div>
              <p className="snippet">{item.snippet}</p>
              {showAdaptiveMeta && item.reason_summary ? (
                <p className="reason-chip">{item.reason_summary}</p>
              ) : null}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
