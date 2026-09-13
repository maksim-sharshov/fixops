import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, GitCommitHorizontal } from "lucide-react";
import { ErrorBanner } from "../components/ErrorBanner";
import { Workflow } from "../components/Workflow";
import { AIAnalysis } from "../components/AIAnalysis";
import { DiffViewer } from "../components/DiffViewer";
import { Verification } from "../components/Verification";
import { RepairResult } from "../components/RepairResult";
import { EmptyState } from "../components/EmptyState";
import { useAppState } from "../hooks/useAppStateHook";
import { useJobSocket } from "../hooks/useJobSocket";
import * as api from "../services/api";
import { ApiError } from "../services/api";

type ActionState =
  | { kind: "idle" }
  | { kind: "running"; message: string }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

export function IncidentDetail() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const { incidents, updateIncident } = useAppState();
  const incident = incidents[jobId];

  const [actionState, setActionState] = useState<ActionState>({ kind: "idle" });
  const [actionsLocked, setActionsLocked] = useState(false);

  const handleErrorInfo = useCallback(
    (info: { message: string; location: string }) => {
      updateIncident(jobId, { error: info.message, location: info.location });
    },
    [jobId, updateIncident]
  );

  const handleContainerId = useCallback(
    (containerId: string) => {
      updateIncident(jobId, { containerId });
    },
    [jobId, updateIncident]
  );

  const handleFinished = useCallback(
    (success: boolean) => {
      updateIncident(jobId, {
        status: success ? "resolved" : "failed",
        timestamp: new Date().toLocaleTimeString(),
      });
    },
    [jobId, updateIncident]
  );

  const jobState = useJobSocket({
    jobId: jobId || null,
    onErrorInfo: handleErrorInfo,
    onContainerId: handleContainerId,
    onFinished: handleFinished,
  });

  if (!incident) {
    return (
      <div className="fade-in">
        <button className="btn btn-ghost" onClick={() => navigate("/incidents")}>
          <ArrowLeft size={14} /> Back
        </button>
        <div className="card" style={{ marginTop: 16 }}>
          <EmptyState
            icon={<GitCommitHorizontal size={28} color="var(--muted)" />}
            text="Incident not found"
            detail="It may have rolled out of the current session's memory."
          />
        </div>
      </div>
    );
  }

  const containerId = incident.containerId || jobState.containerId;

  async function handleApplyFix() {
    if (!containerId) {
      setActionState({ kind: "error", message: "No container is associated with the current job." });
      return;
    }
    setActionsLocked(true);
    setActionState({
      kind: "running",
      message: 'Applying fix...\n\ndocker compose down\ndocker compose up --build -d\n git add .\n git commit -m "fix: automated FixOps repair"'
    });

    try {
      const output = await api.applyFix(containerId);
      setActionState({ kind: "success", message: `Fix applied successfully.\n\n${output}` });
      // Buttons stay locked after a successful apply — nothing left to
      // apply again for this incident.
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Unknown error";
      setActionState({ kind: "error", message: `Apply failed.\n\n${message}` });
      setActionsLocked(false);
    }
  }

  async function handleRollback() {
    if (!containerId) {
      setActionState({ kind: "error", message: "No container is associated with the current job." });
      return;
    }
    const confirmed = window.confirm(
      "Rollback will reset the project to its clean Git state and restart the containers. Continue?"
    );
    if (!confirmed) return;

    setActionsLocked(true);
    setActionState({ kind: "running", message: "Rolling back...\n\nResetting project to clean Git state..." });

    try {
      const output = await api.rollback(containerId);
      setActionState({ kind: "success", message: `Rollback completed successfully.\n\n${output}` });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Unknown error";
      setActionState({ kind: "error", message: `Rollback failed.\n\n${message}` });
      setActionsLocked(false);
    }
  }

  const showActions = jobState.result !== null;

  return (
    <div className="fade-in">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          marginBottom: 20,
        }}
      >
        <div>
          <div className="page-title">{incident.containerName || incident.containerId}</div>
          <div className="page-subtitle">{incident.project}</div>
        </div>
        <button className="btn btn-ghost" onClick={() => navigate("/incidents")}>
          <ArrowLeft size={14} /> Back
        </button>
      </div>

      <ErrorBanner
        message={incident.error || "Unknown error"}
        location={incident.location}
        resolved={incident.status === "resolved"}
      />

      <div className="card">
        <div className="card-title">Repair Workflow</div>
        <Workflow steps={jobState.steps} />
      </div>

      <AIAnalysis analysis={jobState.aiAnalysis} />

      {jobState.diff && <DiffViewer diff={jobState.diff} />}

      <Verification verification={jobState.verification} />

      {jobState.result && <RepairResult result={jobState.result} />}

      {showActions && (
        <div className="btn-group">
          <button className="btn btn-primary" disabled={actionsLocked} onClick={handleApplyFix}>
            Apply Fix
          </button>
          <button className="btn btn-secondary" disabled={actionsLocked} onClick={handleRollback}>
            Rollback
          </button>
        </div>
      )}

      {actionState.kind !== "idle" && (
        <div className={`action-result-box ${actionState.kind}`}>{actionState.message}</div>
      )}
    </div>
  );
}
