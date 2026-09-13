import { Check, X } from "lucide-react";
import type { WorkflowStepModel } from "../types";

function StepCircle({ index, state }: { index: number; state: WorkflowStepModel["state"] }) {
  if (state === "completed") return <Check size={13} strokeWidth={3} />;
  if (state === "failed") return <X size={13} strokeWidth={3} />;
  return <>{index + 1}</>;
}

export function WorkflowStep({
  step,
  index,
}: {
  step: WorkflowStepModel;
  index: number;
}) {
  return (
    <div className={`workflow-step ${step.state}`}>
      <div className="step-circle">
        <StepCircle index={index} state={step.state} />
      </div>
      <div className="step-content">
        <div className="step-title">{step.title}</div>
        <div className="step-description">{step.description}</div>
      </div>
    </div>
  );
}

export function Workflow({ steps }: { steps: WorkflowStepModel[] }) {
  return (
    <div className="workflow">
      {steps.map((step, i) => (
        <WorkflowStep key={step.id} step={step} index={i} />
      ))}
    </div>
  );
}
