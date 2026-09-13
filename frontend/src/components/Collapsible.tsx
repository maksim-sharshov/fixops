import { ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";

export function Collapsible({
  title,
  children,
  defaultOpen = true,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={`collapsible${open ? " open" : ""}`}>
      <button className="collapsible-header" onClick={() => setOpen((o) => !o)}>
        <span>{title}</span>
        <span className="collapsible-icon">
          <ChevronRight size={14} />
        </span>
      </button>
      {open && <div className="collapsible-body">{children}</div>}
    </div>
  );
}
