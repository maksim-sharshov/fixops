import type {
  Incident,
  IncidentDetail,
  IncidentListItem,
  JobState,
  VerificationResult,
} from "../types";
import { parseDiff } from "./normalize";
import { createInitialSteps } from "./workflowSteps";

function formatTimestamp(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString();
}

/** Maps a persisted incident (list endpoint) to the frontend Incident card model. */
export function mapIncidentSummary(item: IncidentListItem): Incident {
  return {
    jobId: item.job_id,
    containerId: item.container_id ?? "",
    containerName: item.container_name ?? item.container_id ?? "Unknown",
    project: item.project ?? "Unknown",
    error: item.error_message ?? "Unknown error",
    location: item.error_location ?? "",
    status: item.status,
    timestamp: formatTimestamp(item.created_at),
    createdAt: item.created_at ?? undefined,
  };
}

/**
 * Maps a persisted incident detail to the subset of JobState the
 * Incident Detail page renders. WebSocket events take precedence over
 * these values (see the `hydrate` action in useJobSocket), so this only
 * fills in what the live stream did not provide (e.g. after a reload).
 */
export function mapIncidentDetail(item: IncidentDetail): Partial<JobState> {
  const steps = createInitialSteps().map((step) => {
    const saved = item.steps?.find((savedStep) => savedStep.id === step.id);
    return saved ? { ...step, state: saved.state } : step;
  });

  const verification: VerificationResult = {
    testsPassed: item.tests_passed ?? null,
    returnCode: item.test_return_code ?? null,
    resultType: item.test_result_type ?? null,
    reproductionPassed: item.reproduction_passed ?? null,
    stdout: item.test_stdout ?? null,
    stderr: item.test_stderr ?? null,
    generatedTests: item.generated_tests?.length
      ? item.generated_tests.join("\n\n")
      : null,
  };

  return {
    containerId: item.container_id ?? null,
    steps,
    aiAnalysis: {
      prompt: item.llm_prompt ?? null,
      diagnosis: null,
      context: item.ai_context ?? null,
    },
    diff: item.fix_diff
      ? parseDiff(item.fixed_file ?? null, item.fix_diff)
      : null,
    verification,
    result:
      item.status === "repairing"
        ? null
        : { success: item.status === "resolved" },
  };
}
