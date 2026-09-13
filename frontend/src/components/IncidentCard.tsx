import { useNavigate } from "react-router-dom";
import { IncidentStatus } from "./IncidentStatus";
import type { Incident } from "../types";

export function IncidentCard({ incident }: { incident: Incident }) {
  const navigate = useNavigate();

  return (
    <div
      className={`incident-card ${incident.status}`}
      onClick={() => navigate(`/incidents/${incident.jobId}`)}
      role="button"
      tabIndex={0}
    >
      <div className="incident-card-header">
        <IncidentStatus status={incident.status} />
        <span className="incident-timestamp">{incident.timestamp}</span>
      </div>
      <div className="incident-container-name">
        {incident.containerName || incident.containerId}
      </div>
      <div className="incident-error">{incident.error || "Unknown error"}</div>
    </div>
  );
}
