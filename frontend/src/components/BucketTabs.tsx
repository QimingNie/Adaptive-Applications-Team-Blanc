import type { Bucket } from "../types";

const zones: Record<Bucket, { label: string; hint: string }> = {
  now: { label: "Now", hint: "Highest priority — act first" },
  read: { label: "Read", hint: "Worth full attention soon" },
  skim: { label: "Skim", hint: "Scan when you have time" },
  later: { label: "Later", hint: "Low urgency — batch or defer" }
};

interface Props {
  value: Bucket;
  onChange: (bucket: Bucket) => void;
}

export function BucketTabs({ value, onChange }: Props) {
  return (
    <div className="tabs" role="tablist" aria-label="Priority zones">
      {(Object.keys(zones) as Bucket[]).map((bucket) => {
        const { label, hint } = zones[bucket];
        const selected = value === bucket;
        return (
          <button
            key={bucket}
            type="button"
            role="tab"
            id={`tab-${bucket}`}
            aria-selected={selected}
            aria-controls={`panel-inbox`}
            title={hint}
            data-bucket={bucket}
            className={selected ? "tab tab--active" : "tab"}
            onClick={() => onChange(bucket)}
          >
            <span className="tab-dot" aria-hidden />
            <span className="tab-label">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
