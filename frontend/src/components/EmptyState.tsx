import type { ReactNode } from "react";

export function EmptyState({
  icon,
  text,
  detail,
}: {
  icon: ReactNode;
  text: string;
  detail?: string;
}) {
  return (
    <div className="empty-state">
      {icon}
      <div className="empty-state-text">{text}</div>
      {detail && <div className="empty-state-detail">{detail}</div>}
    </div>
  );
}
