// =========================================================
// FixOps — core domain types
//
// These mirror the data actually produced by the existing
// backend/frontend (see legacy index.html). Fields that the
// backend sends under multiple possible keys are normalized
// once in services/api.ts or lib/normalize.ts, not duplicated
// as optional unions everywhere.
// =========================================================

export type ContainerStatus = "running" | "stopped" | string;

export interface Container {
  id: string;
  name: string;
  project?: string;
  status: ContainerStatus;
  // CPU/Memory are intentionally NOT modeled here: the backend
  // does not currently provide them. Add fields only once a real
  // endpoint exposes them.
}

export type IncidentStatus = "repairing" | "resolved" | "failed";

export interface Incident {
  jobId: string;
  containerId: string;
  containerName: string;
  project: string;
  error: string;
  location: string;
  status: IncidentStatus;
  /** Display timestamp (locale time string). */
  timestamp: string;
  /** ISO timestamp, used for stable sorting when loaded from the API. */
  createdAt?: string;
}

// ---------------------------------------------------------
// Persisted incidents (Postgres) — response shapes of
// GET /api/incidents and GET /api/incidents/{jobId}.
// ---------------------------------------------------------

export interface IncidentListItem {
  id: number;
  job_id: string;
  container_id: string | null;
  container_name: string | null;
  project: string | null;
  error_message: string | null;
  error_location: string | null;
  status: IncidentStatus;
  created_at: string | null;
}

export interface IncidentStepRecord {
  id: WorkflowStepId;
  state: WorkflowStepState;
}

export interface IncidentDetail extends IncidentListItem {
  steps: IncidentStepRecord[] | null;
  llm_prompt: string | null;
  ai_context: string | null;
  fixed_file: string | null;
  fix_diff: string | null;
  tests_passed: boolean | null;
  test_return_code: number | null;
  test_result_type: string | null;
  reproduction_passed: boolean | null;
  test_stdout: string | null;
  test_stderr: string | null;
  generated_tests: string[] | null;
}

// ---------------------------------------------------------
// Repair workflow
// ---------------------------------------------------------

export type WorkflowStepId =
  | "indexer"
  | "graph_builder"
  | "error_analyzer"
  | "context_builder"
  | "llm"
  | "code_fixer"
  | "test_runner";

export type WorkflowStepState = "pending" | "active" | "completed" | "failed";

export interface WorkflowStepDefinition {
  id: WorkflowStepId;
  title: string;
  description: string;
}

export interface WorkflowStepModel extends WorkflowStepDefinition {
  state: WorkflowStepState;
}

// ---------------------------------------------------------
// Verification / test results
// ---------------------------------------------------------

export interface VerificationResult {
  testsPassed: boolean | null;
  returnCode: number | null;
  resultType: string | null;
  reproductionPassed: boolean | null;
  stdout: string | null;
  stderr: string | null;
  generatedTests: string | null;
}

export const EMPTY_VERIFICATION: VerificationResult = {
  testsPassed: null,
  returnCode: null,
  resultType: null,
  reproductionPassed: null,
  stdout: null,
  stderr: null,
  generatedTests: null,
};

// ---------------------------------------------------------
// AI analysis
// ---------------------------------------------------------

export interface AIAnalysis {
  prompt: string | null;
  diagnosis: string | null;
  context: string | null;
}

// ---------------------------------------------------------
// Diff
// ---------------------------------------------------------

export type DiffLineKind = "add" | "remove" | "context";

export interface DiffLine {
  kind: DiffLineKind;
  content: string;
  oldLineNumber: number | null;
  newLineNumber: number | null;
}

export interface RepairDiff {
  fileName: string | null;
  raw: string;
  lines: DiffLine[];
}

// ---------------------------------------------------------
// Repair result (final outcome of a workflow)
// ---------------------------------------------------------

export interface RepairResult {
  success: boolean;
}

// ---------------------------------------------------------
// Job state — everything the Incident Detail page renders
// for a single job, built up incrementally from WebSocket
// events.
// ---------------------------------------------------------

export interface JobState {
  jobId: string;
  containerId: string | null;
  steps: WorkflowStepModel[];
  aiAnalysis: AIAnalysis;
  diff: RepairDiff | null;
  verification: VerificationResult;
  result: RepairResult | null;
}

// ---------------------------------------------------------
// WebSocket events (discriminated unions)
// ---------------------------------------------------------

/** Raw shape coming off the /ws monitor socket. */
export interface MonitorEventRaw {
  type?: string;
  event?: string;
  job_id?: string;
  container_id?: string;
  container?: string;
  [key: string]: unknown;
}

export type MonitorEvent =
  | { kind: "job_started"; jobId: string; containerId: string | null }
  | { kind: "unknown"; raw: MonitorEventRaw };

/** Raw shape coming off the /ws/jobs/{job_id} socket. */
export interface JobEventRaw {
  type?: string;
  event?: string;
  node?: string;
  node_name?: string;
  operation?: string;
  function?: string;
  name?: string;
  container_id?: string;
  container?: string;
  error?: string;
  exception?: string;
  location?: string;
  file?: string;
  fixed_file?: string;
  fix_diff?: string;
  fix_applied?: boolean;
  prompt?: string;
  llm_prompt?: string;
  context?: string;
  status?: string;
  tests_passed?: boolean;
  test_return_code?: number;
  return_code?: number;
  test_result_type?: string;
  result_type?: string;
  reproduction_passed?: boolean;
  test_stdout?: string;
  stdout_tail?: string;
  test_stderr?: string;
  stderr_tail?: string;
  llm_response?: string;
  ai_response?: string;
  llm_output?: string;
  [key: string]: unknown;
}

export type JobEventType =
  | "workflow_started"
  | "node_started"
  | "node_completed"
  | "node_failed"
  | "llm_started"
  | "ai_started"
  | "fix_request_started"
  | "llm_completed"
  | "ai_completed"
  | "fix_request_completed"
  | "llm_prompt"
  | "context_built"
  | "workflow_finished"
  | "unknown";

export type ConnectionState = "connected" | "connecting" | "disconnected";

// ---------------------------------------------------------
// Errors
// ---------------------------------------------------------

export interface ErrorInfo {
  message: string;
  location: string;
}
