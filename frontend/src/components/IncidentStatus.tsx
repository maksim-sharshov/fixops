import type { IncidentStatus as IncidentStatusType } from "../types";

const LABELS: Record<IncidentStatusType, string> = {
  repairing: "Repairing",
  resolved: "Resolved",
  failed: "Failed",
};

export function IncidentStatus({ status }: { status: IncidentStatusType }) {
  return (
    <span className={`incident-status-badge ${status}`}>{LABELS[status]}</span>
  );
}
