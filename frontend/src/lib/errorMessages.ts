import { AxiosError } from 'axios';
import type { ApiError } from '../api/types';

/**
 * Map API error codes (and HTTP status) to friendly copy (§14.3).
 * Falls back to the backend `detail`, then a generic message.
 */
const BY_CODE: Record<string, string> = {
  invalid_content_type: "That file isn't a PDF. Please upload a PDF résumé.",
  payload_too_large: 'This file is too large. Upload a PDF under the size limit.',
  empty_upload: 'No file selected. Choose a PDF to upload.',
  unauthorized: 'Your session expired. Please sign in again.',
  forbidden: "You don't have access to this.",
};

const GENERIC = 'Something went wrong. Please try again.';

export function isApiError(data: unknown): data is ApiError {
  return (
    typeof data === 'object' &&
    data !== null &&
    'error' in data &&
    typeof (data as ApiError).error === 'string'
  );
}

/** Extract the stable error code from an unknown thrown value, if present. */
export function errorCode(err: unknown): string | null {
  if (err instanceof AxiosError && isApiError(err.response?.data)) {
    return err.response.data.error;
  }
  return null;
}

/** Best human-readable message for any thrown value. */
export function errorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    const status = err.response?.status;
    const data = err.response?.data;

    if (isApiError(data)) {
      if (BY_CODE[data.error]) return BY_CODE[data.error];
      if (data.detail) return data.detail;
    }

    if (status === 401) return BY_CODE.unauthorized;
    if (status === 403) return BY_CODE.forbidden;
    if (status === 404) return 'Not found. It may have been deleted.';
    if (status === 413) return BY_CODE.payload_too_large;
    if (err.code === 'ERR_NETWORK') {
      return 'Cannot reach the server. Is the backend running?';
    }
  }
  if (err instanceof Error && err.message) return err.message;
  return GENERIC;
}

/** Friendly message for a FAILED match job (§14.3). */
export function matchFailureMessage(
  errCode: string | null,
  errDetail: string | null,
): string {
  if (errCode === 'nlp_unreachable') {
    return 'The matching service is unavailable. Please try again in a moment.';
  }
  const detail = errDetail ?? 'unknown error';
  return `Matching failed: ${detail}. Please try again.`;
}
