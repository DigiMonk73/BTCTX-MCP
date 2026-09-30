import { useState, useCallback, useRef, useEffect } from 'react';
import axios, { AxiosError } from 'axios';
import api from '../api';

interface UseApiCallOptions<T> {
  onSuccess?: (data: T) => void;
  onError?: (error: string) => void;
  immediate?: boolean; // Auto-fetch on mount
}

interface UseApiCallReturn<T> {
  data: T | null;
  isLoading: boolean;
  error: string | null;
  execute: (...args: unknown[]) => Promise<T | null>;
  reset: () => void;
}

/**
 * Generic hook for making API calls with loading and error states
 *
 * @param apiCall - Function that returns an API promise
 * @param options - Optional callbacks and settings
 */
export function useApiCall<T>(
  apiCall: (...args: unknown[]) => Promise<{ data: T }>,
  options: UseApiCallOptions<T> = {}
): UseApiCallReturn<T> {
  const { onSuccess, onError, immediate = false } = options;

  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(immediate);
  const [error, setError] = useState<string | null>(null);

  // Track if component is mounted to prevent state updates after unmount
  const isMountedRef = useRef<boolean>(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const execute = useCallback(
    async (...args: unknown[]): Promise<T | null> => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await apiCall(...args);

        if (!isMountedRef.current) return null;

        setData(response.data);
        onSuccess?.(response.data);
        return response.data;
      } catch (err) {
        if (!isMountedRef.current) return null;

        const errorMessage = extractErrorMessage(err);
        setError(errorMessage);
        onError?.(errorMessage);
        return null;
      } finally {
        if (isMountedRef.current) {
          setIsLoading(false);
        }
      }
    },
    [apiCall, onSuccess, onError]
  );

  const reset = useCallback(() => {
    setData(null);
    setError(null);
    setIsLoading(false);
  }, []);

  // Auto-execute on mount if immediate is true
  useEffect(() => {
    if (immediate) {
      execute();
    }
  }, [immediate, execute]);

  return {
    data,
    isLoading,
    error,
    execute,
    reset,
  };
}

/**
 * Hook for GET requests
 */
export function useGet<T>(
  url: string,
  options: UseApiCallOptions<T> & { immediate?: boolean } = {}
): UseApiCallReturn<T> {
  const apiCall = useCallback(() => api.get<T>(url), [url]);
  return useApiCall(apiCall, options);
}

/**
 * Hook for POST requests
 */
export function usePost<T, D = unknown>(
  url: string,
  options: UseApiCallOptions<T> = {}
): UseApiCallReturn<T> & { post: (data: D) => Promise<T | null> } {
  const apiCall = useCallback((data: unknown) => api.post<T>(url, data), [url]);
  const result = useApiCall(apiCall, options);

  return {
    ...result,
    post: result.execute as (data: D) => Promise<T | null>,
  };
}

/**
 * Hook for PUT requests
 */
export function usePut<T, D = unknown>(
  url: string,
  options: UseApiCallOptions<T> = {}
): UseApiCallReturn<T> & { put: (data: D) => Promise<T | null> } {
  const apiCall = useCallback((data: unknown) => api.put<T>(url, data), [url]);
  const result = useApiCall(apiCall, options);

  return {
    ...result,
    put: result.execute as (data: D) => Promise<T | null>,
  };
}

/**
 * Hook for DELETE requests
 */
export function useDelete<T>(
  url: string,
  options: UseApiCallOptions<T> = {}
): UseApiCallReturn<T> & { del: () => Promise<T | null> } {
  const apiCall = useCallback(() => api.delete<T>(url), [url]);
  const result = useApiCall(apiCall, options);

  return {
    ...result,
    del: result.execute as () => Promise<T | null>,
  };
}

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

export default useApiCall;
