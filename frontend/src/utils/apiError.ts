// The message to show when an API request fails.
import axios, { AxiosError } from 'axios';

/** Where a 422's input error is, from its `loc` (["body", "rows", 2,
 * "fee_amount"]), said before its words ("Row 6 (Fee)"); null when it
 * can't say. */
export type InputPlace = (loc: unknown[]) => string | null;

/** One of FastAPI's input errors in words: { msg: "Value error, The
 * password ..." }, after its place when `place` names one. */
function inputErrorText(error: unknown, place?: InputPlace): string {
  const { msg, loc } = (error ?? {}) as { msg?: unknown; loc?: unknown };
  const words = String(msg ?? '').replace(/^Value error, /, '');
  const where = words && place && Array.isArray(loc) ? place(loc) : null;
  return where ? `${where}: ${words}` : words;
}

/** The message in the server's error body: FastAPI's `detail` (a string, or
 * a 422's list of input errors, each after its place when `place` names
 * one), else an `errors` list; null when it has none. */
function bodyMessage(data: ApiErrorResponse, place?: InputPlace): string | null {
  const detail: unknown = data.detail;
  if (typeof detail === 'string' && detail) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail.map((d) => inputErrorText(d, place)).filter(Boolean);
    if (messages.length) return messages.join(place ? '; ' : ' ');
  }
  if (data.errors) {
    const messages = Object.values(data.errors).flat();
    return messages.join(', ');
  }
  return null;
}

const STATUS_MESSAGES: Record<number, string> = {
  401: 'Unauthorized. Please log in again.',
  403: 'Access denied.',
  404: 'Resource not found.',
  500: 'Server error. Please try again later.',
};

/** A failed request the server didn't explain: no connection, a timeout,
 * or the HTTP status. */
function failureMessage(axiosError: AxiosError): string {
  if (axiosError.code === 'ERR_NETWORK') {
    return 'Network error. Please check your connection.';
  }
  if (axiosError.code === 'ECONNABORTED') {
    return 'Request timed out. Please try again.';
  }
  const status = axiosError.response?.status;
  if (status) {
    return STATUS_MESSAGES[status] ?? `Request failed with status ${status}`;
  }
  return axiosError.message || 'An error occurred';
}

/** The message to show for a failed request. */
export function extractErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const axiosError = err as AxiosError<ApiErrorResponse>;
    if (axiosError.response?.data) {
      const message = bodyMessage(axiosError.response.data);
      if (message !== null) return message;
    }
    return failureMessage(axiosError);
  }

  if (err instanceof Error) {
    return err.message;
  }

  return 'An unexpected error occurred';
}

/** The server's reason for a failed request, in words (FastAPI's `detail`,
 * a 422's list of input errors included, #448, each after its place when
 * `place` names one), or null when it gave none. */
export function serverReason(err: unknown, place?: InputPlace): string | null {
  const data: unknown = (err as { response?: { data?: unknown } } | null)?.response?.data;
  return data !== null && typeof data === 'object' ? bodyMessage(data as ApiErrorResponse, place) : null;
}

/** The server's reason for a failed request, or the fallback when it gave
 * none. Always text: a React child or a template string can take it. */
export function detailOr(err: unknown, fallback: string, place?: InputPlace): string {
  return serverReason(err, place) || fallback;
}
