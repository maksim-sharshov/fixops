import type { Container } from "../types";

export function ContainerCard({ container }: { container: Container }) {
  const isRunning = container.status === "running";

  return (
    <div className="container-row">
      <div className="container-info">
        <div className={`container-status-dot ${isRunning ? "running" : "stopped"}`} />
        <div className="container-details">
          <div className="container-name">{container.name}</div>
          <div className="container-project">{container.project || "Unknown"}</div>
        </div>
      </div>
      <div className="container-status-label">{container.status}</div>
    </div>
  );
}
