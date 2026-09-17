import { useEffect, useRef, useState } from "react";
import { WS_URL } from "../services/api";
import {
  getMonitorContainerId,
  getMonitorJobId,
  isJobStartedEvent,
} from "../lib/normalize";
import type { ConnectionState, MonitorEventRaw } from "../types";

const RECONNECT_DELAY_MS = 3000;

export interface JobStartedPayload {
  jobId: string;
  containerId: string | null;
}

interface UseMonitorSocketOptions {
  /** Called whenever the backend reports a new/known job_started event. */
  onJobStarted: (payload: JobStartedPayload) => void;
}

interface UseMonitorSocketResult {
  connectionState: ConnectionState;
}

/**
 * Owns the single long-lived connection to the monitor socket
 * (`/ws`). Mirrors legacy connectMonitor(): auto-reconnects on
 * close/error, and never opens more than one socket at a time.
 */
export function useMonitorSocket({
  onJobStarted,
}: UseMonitorSocketOptions): UseMonitorSocketResult {
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("connecting");
  const onJobStartedRef = useRef(onJobStarted);
  useEffect(() => {
    onJobStartedRef.current = onJobStarted;
  }, [onJobStarted]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    function connect() {
      if (cancelled) return;

      const wsUrl = `${WS_URL}/api/ws`;
      socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        setConnectionState("connected");
      };

      socket.onmessage = (event) => {
        let message: MonitorEventRaw;
        try {
          message = JSON.parse(event.data);
        } catch {
          console.error("Invalid monitor message:", event.data);
          return;
        }

        if (isJobStartedEvent(message)) {
          const jobId = getMonitorJobId(message);
          if (!jobId) return;
          const containerId = getMonitorContainerId(message) ?? null;
          onJobStartedRef.current({ jobId, containerId });
        }
      };

      socket.onerror = () => {
        setConnectionState("disconnected");
      };

      socket.onclose = () => {
        setConnectionState("disconnected");
        if (!cancelled) {
          reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
        }
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  return { connectionState };
}
