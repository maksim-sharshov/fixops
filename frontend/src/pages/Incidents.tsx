import { AlertTriangle } from "lucide-react";
import { IncidentCard } from "../components/IncidentCard";
import { EmptyState } from "../components/EmptyState";
import { useAppState } from "../hooks/useAppStateHook";

export function Incidents() {
  const { incidents } = useAppState();
  const list = Object.values(incidents).sort((a, b) =>
    a.timestamp < b.timestamp ? 1 : -1
  );

  return (
    <div className="fade-in">
      <div className="card">
        <div className="card-title">
          <AlertTriangle size={13} />
          Detected Issues
        </div>
        {list.length === 0 ? (
          <EmptyState
            icon={<AlertTriangle size={28} color="var(--muted)" />}
            text="No incidents"
            detail="FixOps is protecting your infrastructure."
          />
        ) : (
          <div className="incident-list">
            {list.map((incident) => (
              <IncidentCard key={incident.jobId} incident={incident} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
