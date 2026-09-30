/** The server's reason for a failed request (FastAPI's `detail`), or the
 * fallback when it gave none. */
export function detailOr(err: unknown, fallback: string): string {
  const axiosErr = err as { response?: { data?: { detail?: string } } };
  return axiosErr.response?.data?.detail || fallback;
}
