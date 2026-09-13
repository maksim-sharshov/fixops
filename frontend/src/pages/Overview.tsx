import { useMemo } from "react";
import { Boxes } from "lucide-react";
import { StatCard } from "../components/StatCard";
import { ContainerCard } from "../components/ContainerCard";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { useAppState } from "../hooks/useAppStateHook";

export function Overview() {
  const { containers, incidents } = useAppState();

  const incidentList = useMemo(() => Object.values(incidents), [incidents]);
  const monitored = containers.length;
  const healthy = containers.filter((c) => c.status === "running").length;
  const incidentCount = incidentList.length;
  const repairsInProgress = incidentList.filter((i) => i.status === "repairing").length;

  const activeIncident = incidentList.find((i) => i.status === "repairing");

  const health: "healthy" | "degraded" | "incident" = activeIncident
    ? "incident"
    : healthy < monitored && monitored > 0
    ? "degraded"
    : "healthy";

  return (
    <div className="fade-in">
      {activeIncident && (
        <ErrorBanner
          message={activeIncident.error}
          location={activeIncident.location}
        />
      )}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div className={`health-pill ${health}`}>
          <span className="dot" />
          {health}
        </div>
      </div>

      <div className="stats-grid">
        <StatCard value={monitored} label="Monitored" />
        <StatCard value={healthy} label="Healthy" />
        <StatCard value={incidentCount} label="Incidents" />
        <StatCard value={repairsInProgress} label="Repairs" />
      </div>

      <div className="card">
        <div className="card-title">
          <Boxes size={13} />
          Active Containers
        </div>
        {containers.length === 0 ? (
          <EmptyState
            icon={<Boxes size={28} color="var(--muted)" />}
            text="No containers monitored"
            detail="Waiting for infrastructure discovery..."
          />
        ) : (
          <div className="container-list">
            {containers.map((c) => (
              <ContainerCard key={c.id} container={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
