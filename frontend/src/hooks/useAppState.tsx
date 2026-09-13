import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { getContainers, getIncidents } from "../services/api";
import { useMonitorSocket } from "./useMonitorSocket";
import { AppStateContext, type AppStateValue } from "./appStateContext";
import { mapIncidentSummary } from "../lib/incidents";
import type { Container, Incident } from "../types";

const CONTAINERS_POLL_INTERVAL_MS = 3000;

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [containers, setContainers] = useState<Container[]>([]);
  const [incidents, setIncidents] = useState<Record<string, Incident>>({});
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [lastJobStartedId, setLastJobStartedId] = useState<string | null>(null);

  const containersRef = useRef(containers);
  useEffect(() => {
    containersRef.current = containers;
  }, [containers]);

  const loadContainers = useCallback(async () => {
    try {
      const data = await getContainers();
      setContainers(data);
    } catch (error) {
      console.error("Failed to load containers:", error);
    }
  }, []);

  useEffect(() => {
    // Fire the first load from the external system (the API) rather than
    // deriving it during render; the interval keeps it in sync afterwards.
    let cancelled = false;
    (async () => {
      try {
        const data = await getContainers();
        if (!cancelled) setContainers(data);
      } catch (error) {
        console.error("Failed to load containers:", error);
      }
    })();
    const interval = setInterval(loadContainers, CONTAINERS_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [loadContainers]);

  useEffect(() => {
    // Seed the incident list from persisted history so it survives reloads.
    // Live WebSocket incidents always win over the persisted snapshot.
    let cancelled = false;
    (async () => {
      try {
        const data = await getIncidents();
        if (cancelled) return;
        setIncidents((prev) => {
          const merged = { ...prev };
          for (const item of data) {
            const persisted = mapIncidentSummary(item);
            const live = prev[item.job_id];
            merged[item.job_id] = live ? { ...persisted, ...live } : persisted;
          }
          return merged;
        });
      } catch (error) {
        console.error("Failed to load incidents:", error);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const updateIncident = useCallback(
    (jobId: string, patch: Partial<Incident>) => {
      setIncidents((prev) => {
        const existing = prev[jobId];
        if (!existing) return prev;
        return { ...prev, [jobId]: { ...existing, ...patch } };
      });
    },
    []
  );

  const { connectionState } = useMonitorSocket({
    onJobStarted: ({ jobId, containerId }) => {
      setIncidents((prev) => {
        if (prev[jobId]) return prev; // known job — don't clobber accumulated data
        const container = containersRef.current.find((c) => c.id === containerId);
        const now = new Date();
        const incident: Incident = {
          jobId,
          containerId: containerId ?? "",
          containerName: container?.name ?? containerId ?? "Unknown",
          project: container?.project ?? "Unknown",
          error: "Error detected...",
          location: "",
          status: "repairing",
          timestamp: now.toLocaleTimeString(),
          createdAt: now.toISOString(),
        };
        return { ...prev, [jobId]: incident };
      });
      setCurrentJobId(jobId);
      setLastJobStartedId(jobId);
    },
  });

  const value = useMemo<AppStateValue>(
    () => ({
      containers,
      incidents,
      connectionState,
      currentJobId,
      lastJobStartedId,
      setCurrentJobId,
      updateIncident,
    }),
    [containers, incidents, connectionState, currentJobId, lastJobStartedId, updateIncident]
  );

  return (
    <AppStateContext.Provider value={value}>
      {children}
    </AppStateContext.Provider>
  );
}
