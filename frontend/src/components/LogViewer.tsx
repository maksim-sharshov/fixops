import { Check, ChevronDown, ChevronUp, Copy, Terminal } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export function LogViewer({
  label,
  content,
}: {
  label: string;
  content: string | null;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [copied, setCopied] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const wasAtBottomRef = useRef(true);

  const text = content && content.trim() ? content : `No ${label}.`;

  useEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    // Only auto-scroll if the user was already at (or near) the bottom,
    // so we never yank the viewport away while someone is reading up.
    if (wasAtBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [text]);

  function handleScroll() {
    const el = bodyRef.current;
    if (!el) return;
    wasAtBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < 24;
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard API unavailable — silently ignore
    }
  }

  return (
    <div className="log-viewer">
      <div className="log-viewer-header">
        <div className="log-viewer-title">
          <Terminal size={12} />
          {label}
        </div>
        <div className="log-viewer-actions">
          <button className="log-viewer-action-btn" onClick={handleCopy} title="Copy">
            {copied ? <Check size={13} /> : <Copy size={13} />}
          </button>
          <button
            className="log-viewer-action-btn"
            onClick={() => setCollapsed((c) => !c)}
            title={collapsed ? "Expand" : "Collapse"}
          >
            {collapsed ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
          </button>
        </div>
      </div>
      <div
        className={`log-viewer-body${collapsed ? " collapsed" : ""}`}
        ref={bodyRef}
        onScroll={handleScroll}
      >
        {text}
      </div>
    </div>
  );
}
