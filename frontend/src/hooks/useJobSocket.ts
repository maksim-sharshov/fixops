import { useEffect, useReducer, useRef } from "react";
import { WS_URL, getIncident } from "../services/api";
import {
  extractVerification,
  getJobEventNode,
  getJobEventType,
  normalizeStepName,
  parseDiff,
} from "../lib/normalize";
import { mapIncidentDetail } from "../lib/incidents";
import { createInitialSteps } from "../lib/workflowSteps";
import type {
  ErrorInfo,
  JobEventRaw,
  JobState,
  VerificationResult,
  WorkflowStepModel,
} from "../types";

interface UseJobSocketOptions {
  jobId: string | null;
  /** Fired when the job stream reveals/updates error info for the incident. */
  onErrorInfo?: (info: ErrorInfo) => void;
  /** Fired when the job stream reveals the real container id for this job. */
  onContainerId?: (containerId: string) => void;
  /** Fired once the workflow finishes (success or failure). */
  onFinished?: (success: boolean) => void;
}

function createInitialJobState(jobId: string): JobState {
  return {
    jobId,
    containerId: null,
    steps: createInitialSteps(),
    aiAnalysis: { prompt: null, diagnosis: null, context: null },
    diff: null,
    verification: {
      testsPassed: null,
      returnCode: null,
      resultType: null,
      reproductionPassed: null,
      stdout: null,
      stderr: null,
      generatedTests: null,
    },
    result: null,
  };
}

type Action =
  | { type: "reset"; jobId: string }
  | { type: "hydrate"; state: Partial<JobState> }
  | { type: "workflow_started" }
  | { type: "step_state"; node: string; state: "active" | "completed" | "failed" }
  | { type: "diff"; fileName: string | null; diff: string }
  | { type: "clear_diff" }
  | { type: "prompt"; text: string }
  | { type: "verification"; message: JobEventRaw }
  | { type: "finished"; success: boolean };

/**
 * Merge persisted steps into live state: a step already touched by the
 * WebSocket stream (non-pending) always wins over the persisted value.
 */
function mergeSteps(
  current: WorkflowStepModel[],
  hydrated: WorkflowStepModel[] | undefined
): WorkflowStepModel[] {
  if (!hydrated) return current;
  return current.map((step) => {
    if (step.state !== "pending") return step;
    const saved = hydrated.find((candidate) => candidate.id === step.id);
    return saved ? { ...step, state: saved.state } : step;
  });
}

/** Prefer non-null live verification fields, fall back to persisted ones. */
function mergeVerification(
  current: VerificationResult,
  hydrated: VerificationResult | undefined
): VerificationResult {
  if (!hydrated) return current;
  const pick = <T,>(live: T | null, saved: T | null): T | null =>
    live === null || live === undefined ? saved : live;

  return {
    testsPassed: pick(current.testsPassed, hydrated.testsPassed),
    returnCode: pick(current.returnCode, hydrated.returnCode),
    resultType: pick(current.resultType, hydrated.resultType),
    reproductionPassed: pick(
      current.reproductionPassed,
      hydrated.reproductionPassed
    ),
    stdout: pick(current.stdout, hydrated.stdout),
    stderr: pick(current.stderr, hydrated.stderr),
    generatedTests: pick(current.generatedTests, hydrated.generatedTests),
  };
}

function reducer(state: JobState, action: Action): JobState {
  switch (action.type) {
    case "reset":
      return createInitialJobState(action.jobId);
    case "hydrate": {
      const hydrated = action.state;
      return {
        ...state,
        containerId: state.containerId ?? hydrated.containerId ?? null,
        steps: mergeSteps(state.steps, hydrated.steps),
        aiAnalysis: {
          prompt: state.aiAnalysis.prompt ?? hydrated.aiAnalysis?.prompt ?? null,
          diagnosis:
            state.aiAnalysis.diagnosis ??
            hydrated.aiAnalysis?.diagnosis ??
            null,
          context:
            state.aiAnalysis.context ?? hydrated.aiAnalysis?.context ?? null,
        },
        diff: state.diff ?? hydrated.diff ?? null,
        verification: mergeVerification(
          state.verification,
          hydrated.verification
        ),
        result: state.result ?? hydrated.result ?? null,
      };
    }
    case "workflow_started":
      return { ...state, steps: createInitialSteps() };
    case "step_state":
      return {
        ...state,
        steps: state.steps.map((step) =>
          normalizeStepName(action.node) === step.id
            ? { ...step, state: action.state }
            : step
        ),
      };
    case "diff":
      return {
        ...state,
        diff: parseDiff(action.fileName, action.diff),
      };
    case "clear_diff":
      return { ...state, diff: null };
    case "prompt":
      return {
        ...state,
        aiAnalysis: { ...state.aiAnalysis, prompt: action.text },
      };
    case "verification":
      return { ...state, verification: extractVerification(action.message) };
    case "finished":
      return {
        ...state,
        result: { success: action.success },
        steps: state.steps.map((step) =>
          step.state === "failed" ? step : { ...step, state: "completed" }
        ),
      };
    default:
      return state;
  }
}

/**
 * Owns the connection to a single job's WebSocket
 * (`/ws/jobs/{jobId}`). Mirrors legacy connectJob() +
 * handleJobEvent() + handleWorkflowFinished(): rebuilds workflow
 * state purely from real server events, no fake timers/progress.
 */
export function useJobSocket({
  jobId,
  onErrorInfo,
  onContainerId,
  onFinished,
}: UseJobSocketOptions) {
  const [jobState, dispatch] = useReducer(
    reducer,
    jobId,
    (id) => createInitialJobState(id ?? "")
  );

  const onErrorInfoRef = useRef(onErrorInfo);
  const onContainerIdRef = useRef(onContainerId);
  const onFinishedRef = useRef(onFinished);
  useEffect(() => {
    onErrorInfoRef.current = onErrorInfo;
    onContainerIdRef.current = onContainerId;
    onFinishedRef.current = onFinished;
  }, [onErrorInfo, onContainerId, onFinished]);

  useEffect(() => {
    if (!jobId) return;

    dispatch({ type: "reset", jobId });

    const socket = new WebSocket(`${WS_URL}/api/ws/jobs/${jobId}`);

    socket.onmessage = (event) => {
      let message: JobEventRaw;
      try {
        message = JSON.parse(event.data);
      } catch {
        console.error("Invalid job message:", event.data);
        return;
      }

      const incomingContainerId = message.container_id || message.container;
      if (incomingContainerId) {
        onContainerIdRef.current?.(incomingContainerId);
      }

      if (message.error || message.exception) {
        onErrorInfoRef.current?.({
          message: (message.error || message.exception) as string,
          location: message.location || message.file || "",
        });
      }

      const type = getJobEventType(message);
      const node = getJobEventNode(message);

      if (type === "workflow_started") {
        dispatch({ type: "workflow_started" });
      }

      if (type === "node_started" && node) {
        dispatch({ type: "step_state", node, state: "active" });
      }

      if (type === "node_completed" && node) {
        dispatch({ type: "step_state", node, state: "completed" });

        const normalized = normalizeStepName(node);
        if (normalized === "code_fixer") {
          if (message.fix_applied === false) {
            dispatch({ type: "clear_diff" });
          } else if (message.fix_diff) {
            dispatch({
              type: "diff",
              fileName: message.fixed_file ?? null,
              diff: message.fix_diff,
            });
          }
        }

        if (normalized === "test_runner") {
          dispatch({ type: "verification", message });
        }
      }

      if (type === "node_failed" && node) {
        dispatch({ type: "step_state", node, state: "failed" });
      }

      if (
        type === "llm_started" ||
        type === "ai_started" ||
        type === "fix_request_started"
      ) {
        dispatch({ type: "step_state", node: "llm", state: "active" });
      }

      if (
        type === "llm_completed" ||
        type === "ai_completed" ||
        type === "fix_request_completed"
      ) {
        dispatch({ type: "step_state", node: "llm", state: "completed" });
      }

      if (type === "llm_prompt" || type === "context_built") {
        const promptText = message.prompt || message.llm_prompt || message.context;
        if (promptText) {
          dispatch({ type: "prompt", text: promptText });
        }
      }

      if (type === "workflow_finished") {
        const success =
          message.status === "success" || message.tests_passed === true;
        dispatch({ type: "finished", success });
        dispatch({ type: "verification", message });
        if (message.fix_diff) {
          dispatch({
            type: "diff",
            fileName: message.fixed_file ?? null,
            diff: message.fix_diff,
          });
        }
        const finalPrompt = message.llm_prompt || message.prompt || message.context;
        if (finalPrompt) {
          dispatch({ type: "prompt", text: finalPrompt });
        }
        onFinishedRef.current?.(success);
      }
    };

    socket.onerror = () => {
      console.error("Job socket error:", jobId);
    };

    return () => {
      socket.close();
    };
  }, [jobId]);

  // Hydrate from the persisted incident so the detail page renders after a
  // reload (the WebSocket history is in-memory and may be gone). Live events
  // take precedence via the merge logic in the `hydrate` reducer case.
  useEffect(() => {
    if (!jobId) return;

    let cancelled = false;

    (async () => {
      try {
        const detail = await getIncident(jobId);
        if (cancelled || !detail) return;
        dispatch({ type: "hydrate", state: mapIncidentDetail(detail) });
      } catch (error) {
        console.error("Failed to load incident detail:", error);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [jobId]);

  return jobState;
}
