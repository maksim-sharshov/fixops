import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "../components/Sidebar";
import { useAppState } from "../hooks/useAppStateHook";

interface PageHeaderInfo {
  title: string;
  subtitle: string;
}

const PAGE_HEADERS: Record<string, PageHeaderInfo> = {
  "/": {
    title: "Overview",
    subtitle: "System status and monitored workloads",
  },
  "/containers": {
    title: "Containers",
    subtitle: "Monitored Docker workloads",
  },
  "/incidents": {
    title: "Incidents",
    subtitle: "Detected issues and repair status",
  },
};

export function AppLayout() {
  const { connectionState } = useAppState();
  const location = useLocation();
  // Incident Detail renders its own header (with back button + dynamic
  // incident name) inline in content, so no generic header there.
  const header = PAGE_HEADERS[location.pathname];

  return (
    <div className="app-shell">
      <Sidebar connectionState={connectionState} />
      <div className="main">
        {header && (
          <header className="main-header">
            <div className="page-title">{header.title}</div>
            <div className="page-subtitle">{header.subtitle}</div>
          </header>
        )}
        <div className="main-content">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
