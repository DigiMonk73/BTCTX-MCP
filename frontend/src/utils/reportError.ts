// Why a report download failed, in the server's words. Reports are fetched
// as a Blob (api.ts, downloadPdfWithAxios), so a failed one carries the
// JSON error ({"detail": "..."}) as a Blob too, which axios leaves unread.
export const REPORT_FAILED = "Failed to generate the report. Please try again.";

export async function reportErrorMessage(error: unknown): Promise<string> {
  const data = (error as { response?: { data?: unknown } } | null)?.response?.data;
  try {
    const text = data instanceof Blob ? await data.text() : typeof data === "string" ? data : "";
    const detail: unknown = JSON.parse(text)?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  } catch {
    // not JSON: fall back to the generic message
  }
  return REPORT_FAILED;
}
