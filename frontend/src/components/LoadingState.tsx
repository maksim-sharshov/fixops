export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="loading-state">
      <div className="loading-spinner" />
      <span>{label}</span>
    </div>
  );
}

export function SkeletonList({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skeleton-list">
      {Array.from({ length: rows }).map((_, i) => (
        <div className="skeleton-row" key={i} />
      ))}
    </div>
  );
}
