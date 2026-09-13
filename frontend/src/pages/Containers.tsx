import { Box } from "lucide-react";
import { ContainerCard } from "../components/ContainerCard";
import { EmptyState } from "../components/EmptyState";
import { useAppState } from "../hooks/useAppStateHook";

export function Containers() {
  const { containers } = useAppState();

  return (
    <div className="fade-in">
      <div className="card">
        <div className="card-title">
          <Box size={13} />
          Monitored Docker Workloads
        </div>
        {containers.length === 0 ? (
          <EmptyState
            icon={<Box size={28} color="var(--muted)" />}
            text="Loading containers..."
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
