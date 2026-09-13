import type { WorkflowStepDefinition, WorkflowStepModel } from "../types";

export const WORKFLOW_STEP_DEFINITIONS: WorkflowStepDefinition[] = [
  {
    id: "indexer",
    title: "Index Project",
    description: "Analyzing codebase structure...",
  },
  {
    id: "graph_builder",
    title: "Build Graph",
    description: "Creating dependency graph...",
  },
  {
    id: "error_analyzer",
    title: "Analyze Error",
    description: "Examining error trace...",
  },
  {
    id: "context_builder",
    title: "Build Context",
    description: "Gathering relevant code context...",
  },
  {
    id: "llm",
    title: "AI Diagnosis",
    description: "Generating solution...",
  },
  {
    id: "code_fixer",
    title: "Apply Repair",
    description: "Applying fix to codebase...",
  },
  {
    id: "test_runner",
    title: "Verify",
    description: "Verifying the fix...",
  },
];

export function createInitialSteps(): WorkflowStepModel[] {
  return WORKFLOW_STEP_DEFINITIONS.map((def) => ({ ...def, state: "pending" }));
}
