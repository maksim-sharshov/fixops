import { AlertCircle, CheckCircle2 } from "lucide-react";

export function ErrorBanner({
  message,
  location,
  resolved = false,
}: {
  message: string;
  location?: string;
  resolved?: boolean;
}) {
  return (
    <div className={`error-banner${resolved ? " resolved" : ""}`}>
      <div className="error-banner-label">
        {resolved ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
        {resolved ? "Resolved" : "Error Detected"}
      </div>
      <div className="error-banner-message">{message}</div>
      {location && <div className="error-banner-location">{location}</div>}
    </div>
  );
}
