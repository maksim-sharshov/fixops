import type { Container } from "../types";

// The backend host is configurable via Vite env var so it's not
// hardcoded in source. Falls back to the address used by the
// original vanilla-JS frontend.
export const API_URL =
  import.meta.env.VITE_API_URL || "http://138.124.240.14:8000";

export const WS_URL = API_URL.replace(/^http/, "ws");

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseJsonSafe(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function extractErrorMessage(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object") return fallback;
  const d = data as Record<string, unknown>;
  if (typeof d.detail === "string") return d.detail;
  if (typeof d.result === "string") return d.result;
  if (
    d.result &&
    typeof d.result === "object" &&
    typeof (d.result as Record<string, unknown>).error === "string"
  ) {
    return (d.result as Record<string, unknown>).error as string;
  }
  return fallback;
}

function extractOutput(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object") return fallback;
  const d = data as Record<string, unknown>;
  if (typeof d.output === "string") return d.output;
  if (d.result && typeof d.result === "object") {
    const output = (d.result as Record<string, unknown>).output;
    if (typeof output === "string") return output;
  }
  if (typeof d.result === "string") return d.result;
  return fallback;
}

/**
 * GET /api/containers
 * Confirmed existing endpoint — matches legacy frontend exactly.
 */
export async function getContainers(): Promise<Container[]> {
  const response = await fetch(`${API_URL}/api/containers`);
  if (!response.ok) {
    throw new ApiError(`HTTP ${response.status}`, response.status);
  }
  return (await response.json()) as Container[];
}

/**
 * POST /api/containers/{id}/apply
 * Confirmed existing endpoint — matches legacy frontend exactly.
 */
export async function applyFix(containerId: string): Promise<string> {
  const response = await fetch(
    `${API_URL}/api/containers/${encodeURIComponent(containerId)}/apply`,
    { method: "POST", headers: { "Content-Type": "application/json" } }
  );
  const data = await parseJsonSafe(response);
  if (!response.ok) {
    throw new ApiError(
      extractErrorMessage(data, `Apply failed (${response.status})`),
      response.status
    );
  }
  return extractOutput(data, "Fix applied successfully.");
}

/**
 * POST /api/containers/{id}/rollback
 * Confirmed existing endpoint — matches legacy frontend exactly.
 */
export async function rollback(containerId: string): Promise<string> {
  const response = await fetch(
    `${API_URL}/api/containers/${encodeURIComponent(containerId)}/rollback`,
    { method: "POST", headers: { "Content-Type": "application/json" } }
  );
  const data = await parseJsonSafe(response);
  if (!response.ok) {
    throw new ApiError(
      extractErrorMessage(data, `Rollback failed (${response.status})`),
      response.status
    );
  }
  return extractOutput(data, "Rollback completed successfully.");
}

// ---------------------------------------------------------
// TODO: endpoints referenced conceptually by the product spec
// but not present (or not confirmed) in the current backend.
// Do NOT invent request/response shapes for these — wire them
// up once the backend contract is confirmed.
// ---------------------------------------------------------

// TODO: GET /api/containers/{id} — single container detail
// (CPU/memory/logs), used by a future ContainerDetail page.
// export async function getContainerDetail(id: string): Promise<ContainerDetail> {}

// TODO: GET /api/incidents — server-side incident history/persistence.
// Today incidents are derived entirely client-side from WebSocket
// events (see hooks/useMonitorSocket.ts), so a reload loses history.
// export async function getIncidents(): Promise<Incident[]> {}

// TODO: GET /api/jobs/{jobId} — fetch full job state on demand
// (e.g. to support deep-linking directly to an Incident Detail
// page without having lived through the WebSocket session).
// export async function getJob(jobId: string): Promise<JobState> {}
