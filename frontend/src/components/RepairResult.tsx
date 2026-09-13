import { CheckCircle2, XCircle } from "lucide-react";
import type { RepairResult as RepairResultType } from "../types";

export function RepairResult({ result }: { result: RepairResultType }) {
  return (
    <div className="card">
      <div className="card-title">Repair Result</div>
      <div className={`repair-result ${result.success ? "success" : "failed"}`}>
        <div className="repair-result-icon">
          {result.success ? (
            <CheckCircle2 size={30} color="var(--green)" />
          ) : (
            <XCircle size={30} color="var(--red)" />
          )}
        </div>
        <div className="repair-result-title">
          {result.success ? "Repair Successful" : "Repair Failed"}
        </div>
        <div className="repair-result-detail">
          {result.success
            ? "The incident has been resolved and the application recovered."
            : "The automated repair could not resolve this issue."}
        </div>
      </div>
    </div>
  );
}
