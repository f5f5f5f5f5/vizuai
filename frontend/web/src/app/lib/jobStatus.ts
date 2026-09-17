const COMPLETED_STATUSES = new Set(["completed", "success", "degraded_success"]);
const FAILED_STATUSES = new Set(["failed", "error", "blocked"]);

export type UiJobStatus = "processing" | "completed" | "failed";

export function toUiJobStatus(status: string | null | undefined): UiJobStatus {
  const normalized = String(status || "").trim().toLowerCase();
  if (COMPLETED_STATUSES.has(normalized)) {
    return "completed";
  }
  if (FAILED_STATUSES.has(normalized)) {
    return "failed";
  }
  return "processing";
}
