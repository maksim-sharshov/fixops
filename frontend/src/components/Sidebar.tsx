import { LayoutGrid, Box, AlertTriangle } from "lucide-react";
import { NavLink } from "react-router-dom";
import { ConnectionStatus } from "./ConnectionStatus";
import type { ConnectionState } from "../types";

const NAV_ITEMS = [
  { to: "/", label: "Overview", icon: LayoutGrid, end: true },
  { to: "/containers", label: "Containers", icon: Box, end: true },
  { to: "/incidents", label: "Incidents", icon: AlertTriangle, end: false },
];

export function Sidebar({ connectionState }: { connectionState: ConnectionState }) {
  return (
    <nav className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-title">FixOps</div>
        <div className="sidebar-brand-subtitle">Self-Healing</div>
      </div>

      <div className="sidebar-nav">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              "sidebar-link" + (isActive ? " active" : "")
            }
          >
            <Icon size={16} strokeWidth={2} />
            <span className="label-text">{label}</span>
          </NavLink>
        ))}
      </div>

      <div className="sidebar-spacer" />

      <div className="sidebar-section-label">System</div>
      <ConnectionStatus state={connectionState} />
    </nav>
  );
}
