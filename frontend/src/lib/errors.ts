import axios from "axios";

import type { ApiResponse } from "@/types/auth";

/**
 * Extracts the backend's own `message` field from a failed request
 * (every error response follows `{success: false, message: "..."}` -
 * see the exception handlers in backend/app/main.py), falling back to a
 * generic message for network errors or anything unexpected.
 */
export function getApiErrorMessage(error: unknown, fallback = "Something went wrong. Please try again."): string {
  if (axios.isAxiosError<ApiResponse<unknown>>(error)) {
    return error.response?.data?.message ?? fallback;
  }
  return fallback;
}