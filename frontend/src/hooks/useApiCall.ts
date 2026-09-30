// The message to show when an API request fails.
import axios, { AxiosError } from 'axios';

/** The message in the server's error body: FastAPI's `detail` (a string, or
 * a 422's list of input errors), else an `errors` list; null when it has
 * none. */
function bodyMessage(data: ApiErrorResponse): string | null {
  const detail: unknown = data.detail;
  if (typeof detail === 'string' && detail) {
    return detail;
  }
  // FastAPI's input errors (422): [{ msg: "Value error, The password ..." }]
  if (Array.isArray(detail)) {
    const messages = detail
      .map((d) => String((d as { msg?: unknown } | null)?.msg ?? '').replace(/^Value error, /, ''))
      .filter(Boolean);
    if (messages.length) return messages.join(' ');
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
