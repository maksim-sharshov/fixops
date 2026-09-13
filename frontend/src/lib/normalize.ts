import type {
  DiffLine,
  JobEventRaw,
  MonitorEventRaw,
  RepairDiff,
  VerificationResult,
  WorkflowStepId,
} from "../types";

// ---------------------------------------------------------
// Step name normalization — ported from normalizeStepName()
// and stepMapping in the legacy index.html.
// ---------------------------------------------------------

const STEP_NAME_MAP: Record<string, WorkflowStepId> = {
  indexer: "indexer",
  index: "indexer",
  graph_builder: "graph_builder",
  graph: "graph_builder",
  error_analyzer: "error_analyzer",
  analyze: "error_analyzer",
  context_builder: "context_builder",
  context: "context_builder",
  handle_fix_request: "llm",
  llm: "llm",
  code_fixer: "code_fixer",
  fix: "code_fixer",
  apply: "code_fixer",
  apply_fix: "code_fixer",
  test_runner: "test_runner",
  tests: "test_runner",
  test: "test_runner",
  run_tests: "test_runner",
};

export function normalizeStepName(raw: unknown): WorkflowStepId | null {
  if (!raw) return null;
  const normalized = String(raw).toLowerCase().trim();
  return STEP_NAME_MAP[normalized] ?? null;
}

export const WORKFLOW_STEP_ORDER: WorkflowStepId[] = [
  "indexer",
  "graph_builder",
  "error_analyzer",
  "context_builder",
  "llm",
  "code_fixer",
  "test_runner",
];

// ---------------------------------------------------------
// Monitor socket event normalization.
// ---------------------------------------------------------

export function getJobEventType(message: JobEventRaw): string | undefined {
  return message.type || message.event;
}

export function getJobEventNode(message: JobEventRaw): string | undefined {
  return (
    message.node ||
    message.node_name ||
    message.operation ||
    message.function ||
    message.name
  );
}

export function getMonitorJobId(message: MonitorEventRaw): string | undefined {
  return message.job_id;
}

export function getMonitorContainerId(
  message: MonitorEventRaw
): string | undefined {
  return message.container_id || message.container;
}

export function isJobStartedEvent(message: MonitorEventRaw): boolean {
  const type = message.type || message.event;
  return type === "job_started";
}

// ---------------------------------------------------------
// Diff parsing — ported from renderDiffBlock().
// A very small unified-diff-ish line classifier: it does not
// attempt to parse hunk headers, since the backend sends a
// plain +/- annotated diff (not full unified diff w/ @@ hunks).
// If the backend ever sends real unified diff with @@ headers,
// this still degrades gracefully (hunk header lines render as
// context).
// ---------------------------------------------------------

export function parseDiff(fileName: string | null, raw: string): RepairDiff {
  let oldLine = 1;
  let newLine = 1;

  const lines: DiffLine[] = raw.split("\n").map((content) => {
    if (content.startsWith("+") && !content.startsWith("+++")) {
      const line: DiffLine = {
        kind: "add",
        content,
        oldLineNumber: null,
        newLineNumber: newLine,
      };
      newLine += 1;
      return line;
    }
    if (content.startsWith("-") && !content.startsWith("---")) {
      const line: DiffLine = {
        kind: "remove",
        content,
        oldLineNumber: oldLine,
        newLineNumber: null,
      };
      oldLine += 1;
      return line;
    }
    const line: DiffLine = {
      kind: "context",
      content,
      oldLineNumber: oldLine,
      newLineNumber: newLine,
    };
    oldLine += 1;
    newLine += 1;
    return line;
  });

  return { fileName, raw, lines };
}

// ---------------------------------------------------------
// Generated tests extraction — ported from renderGeneratedTests().
// ---------------------------------------------------------

export function extractGeneratedTests(llmResponse: string | null): string | null {
  if (!llmResponse) return null;
  const matches = llmResponse.match(/```test\s*([\s\S]*?)```/gi);
  if (!matches || !matches.length) return null;

  const tests = matches
    .map((block) =>
      block.replace(/^```test\s*/i, "").replace(/```\s*$/i, "").trim()
    )
    .join("\n\n");

  return tests || null;
}

// ---------------------------------------------------------
// Verification result extraction — ported from applyTestResults().
// ---------------------------------------------------------

export function extractVerification(data: JobEventRaw): VerificationResult {
  const testsPassed = data.tests_passed ?? null;
  const returnCode = data.test_return_code ?? data.return_code ?? null;
  const resultType = data.test_result_type || data.result_type || null;
  const reproductionPassed = data.reproduction_passed ?? null;
  const stdout = data.test_stdout || data.stdout_tail || null;
  const stderr = data.test_stderr || data.stderr_tail || null;
  const rawLlmResponse =
    data.llm_response || data.ai_response || data.llm_output || null;

  return {
    testsPassed: testsPassed === undefined ? null : testsPassed,
    returnCode: returnCode === undefined ? null : returnCode,
    resultType: resultType || null,
    reproductionPassed:
      reproductionPassed === undefined ? null : reproductionPassed,
    stdout,
    stderr,
    generatedTests: extractGeneratedTests(rawLlmResponse),
  };
}
