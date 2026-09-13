import type { ConnectionState } from "../types";

const LABELS: Record<ConnectionState, string> = {
  connected: "Connected",
  connecting: "Connecting...",
  disconnected: "Disconnected",
};

export function ConnectionStatus({ state }: { state: ConnectionState }) {
  return (
    <div className="connection-status">
      <div className={`status-dot ${state}`} />
      <span className="connection-text">{LABELS[state]}</span>
    </div>
  );
}
