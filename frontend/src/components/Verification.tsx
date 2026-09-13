import { CheckCircle2 } from "lucide-react";
import { Collapsible } from "./Collapsible";
import { LogViewer } from "./LogViewer";
import type { VerificationResult } from "../types";

function Badge({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone: "pass" | "fail" | "neutral";
}) {
  return (
    <div className={`test-badge ${tone}`}>
      {label}: {value}
    </div>
  );
}

function boolTone(v: boolean | null): "pass" | "fail" | "neutral" {
  if (v === true) return "pass";
  if (v === false) return "fail";
  return "neutral";
}

export function Verification({ verification }: { verification: VerificationResult }) {
  const {
    testsPassed,
    returnCode,
    resultType,
    reproductionPassed,
    stdout,
    stderr,
    generatedTests,
  } = verification;

  return (
    <div className="card">
      <div className="card-title">
        <CheckCircle2 size={13} />
        Verification
      </div>

      <div className="verification-badges">
        <Badge
          label="TESTS"
          value={testsPassed === true ? "PASSED" : testsPassed === false ? "FAILED" : "—"}
          tone={boolTone(testsPassed)}
        />
        <Badge
          label="RETURN CODE"
          value={returnCode ?? "—"}
          tone={returnCode === 0 ? "pass" : returnCode != null ? "fail" : "neutral"}
        />
        <Badge
          label="RESULT"
          value={resultType || "—"}
          tone={resultType === "SUCCESS" ? "pass" : resultType ? "fail" : "neutral"}
        />
        <Badge
          label="REPRODUCTION"
          value={
            reproductionPassed === true
              ? "PASSED"
              : reproductionPassed === false
              ? "FAILED"
              : "—"
          }
          tone={boolTone(reproductionPassed)}
        />
      </div>

      <Collapsible title="AI Generated Tests" defaultOpen>
        {generatedTests || "No tests generated."}
      </Collapsible>

      <div style={{ marginTop: 8 }}>
        <LogViewer label="stdout" content={stdout} />
      </div>
      <div style={{ marginTop: 8 }}>
        <LogViewer label="stderr" content={stderr} />
      </div>
    </div>
  );
}
