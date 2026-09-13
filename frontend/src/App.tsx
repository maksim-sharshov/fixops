import { Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { Overview } from "./pages/Overview";
import { Containers } from "./pages/Containers";
import { Incidents } from "./pages/Incidents";
import { IncidentDetail } from "./pages/IncidentDetail";
import { AppStateProvider } from "./hooks/useAppState";

export default function App() {
  return (
    <AppStateProvider>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Overview />} />
          <Route path="containers" element={<Containers />} />
          <Route path="incidents" element={<Incidents />} />
          <Route path="incidents/:jobId" element={<IncidentDetail />} />
        </Route>
      </Routes>
    </AppStateProvider>
  );
}
