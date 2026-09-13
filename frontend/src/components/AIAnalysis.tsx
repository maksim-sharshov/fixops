import { useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import type { AIAnalysis as AIAnalysisType } from "../types";

type TabId = "diagnosis" | "prompt" | "context";

export function AIAnalysis({ analysis }: { analysis: AIAnalysisType }) {
  const tabs = useMemo(() => {
    const list: { id: TabId; label: string; content: string | null }[] = [
      { id: "prompt", label: "Prompt", content: analysis.prompt },
    ];
    if (analysis.diagnosis) {
      list.unshift({ id: "diagnosis", label: "Diagnosis", content: analysis.diagnosis });
    }
    if (analysis.context) {
      list.push({ id: "context", label: "Context", content: analysis.context });
    }
    return list;
  }, [analysis]);

  const [activeTab, setActiveTab] = useState<TabId>(tabs[0]?.id ?? "prompt");
  const active = tabs.find((t) => t.id === activeTab) ?? tabs[0];

  return (
    <div className="card">
      <div className="card-title">
        <Sparkles size={13} />
        AI Analysis
      </div>
      <div className="ai-analysis-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`ai-analysis-tab${tab.id === activeTab ? " active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="ai-analysis-body">
        {active?.content || "No AI analysis yet."}
      </div>
    </div>
  );
}
