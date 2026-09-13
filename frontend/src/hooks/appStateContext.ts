import { createContext } from "react";
import type { Container, ConnectionState, Incident } from "../types";

export interface AppStateValue {
  containers: Container[];
  incidents: Record<string, Incident>;
  connectionState: ConnectionState;
  currentJobId: string | null;
  /** Set when a new job appears, so the shell can navigate to Incidents. */
  lastJobStartedId: string | null;
  setCurrentJobId: (jobId: string | null) => void;
  updateIncident: (jobId: string, patch: Partial<Incident>) => void;
}

export const AppStateContext = createContext<AppStateValue | null>(null);
