import { FileDiff } from "lucide-react";
import type { RepairDiff } from "../types";

export function DiffViewer({ diff }: { diff: RepairDiff }) {
  return (
    <div className="card">
      <div className="card-title">Changes</div>
      <div className="diff-viewer">
        <div className="diff-viewer-header">
          <FileDiff size={13} />
          {diff.fileName || "Changes"}
        </div>
        <div className="diff-viewer-body">
          {diff.lines.map((line, i) => (
            <div className={`diff-line ${line.kind}`} key={i}>
              <span className="diff-line-number">
                {line.kind === "remove" ? line.oldLineNumber : line.newLineNumber}
              </span>
              <span className="diff-line-content">
                {line.content || " "}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
