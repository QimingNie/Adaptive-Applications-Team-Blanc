import type { Bucket } from "../types";

const labels: Record<Bucket, string> = {
  now: "Now",
  read: "Read",
  skim: "Skim",
  later: "Later"
};

interface Props {
  value: Bucket;
  onChange: (bucket: Bucket) => void;
}

export function BucketTabs({ value, onChange }: Props) {
  return (
    <div className="tabs">
      {(Object.keys(labels) as Bucket[]).map((bucket) => (
        <button
          key={bucket}
          className={value === bucket ? "tab active" : "tab"}
          onClick={() => onChange(bucket)}
        >
          {labels[bucket]}
        </button>
      ))}
    </div>
  );
}
