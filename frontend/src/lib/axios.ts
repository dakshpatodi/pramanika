/**
 * Shared Axios instance for all API calls.
 *
 * Request interceptor: attaches the access token to every outgoing
 * request (built in Milestone 6, unchanged here).
 *
 * Response interceptor (new in Milestone 7): on a 401, silently
 * refreshes the access token and retries the original request exactly
 * once. If the refresh itself fails - meaning the refresh token is dead,
 * not just the access token - it gives up and signals a forced logout
 * via lib/auth-events.ts rather than trying to touch React state directly.
 */

import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

import { emitForceLogout } from "@/lib/auth-events";
import { tokenStorage } from "@/lib/token-storage";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
  const accessToken = tokenStorage.getAccessToken();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

// A 401 from any of these three should NEVER trigger a refresh-and-retry
// cycle: /login and /register returning 401/422 means "wrong credentials"
// or "validation failed", not "your access token expired" - and /refresh
// itself failing with 401 is exactly the signal that means "stop trying,
// log out," not something to retry.
const REFRESH_EXEMPT_PATHS = ["/api/auth/login", "/api/auth/register", "/api/auth/refresh"];

let refreshPromise: Promise<string | null> | null = null;

/**
 * Ensures at most ONE /refresh request is ever in flight at a time, even
 * if several requests happen to fail with 401 at the same moment (e.g. a
 * page firing a few parallel authenticated calls right as the access
 * token expires) - every one of them awaits this same shared promise
 * instead of each independently calling /refresh and racing each other,
 * which would otherwise both waste requests and race the token rotation
 * logic on the backend (see Milestone 4: refresh tokens are single-use).
 */
async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refreshToken = tokenStorage.getRefreshToken();
      if (!refreshToken) return null;

      try {
        // Deliberately a raw `axios.post`, NOT `apiClient.post` - going
        // through apiClient would route this call back through these
        // same interceptors, which is unnecessary (the request
        // interceptor would attach the already-expired access token for
        // no reason) and needlessly roundabout to reason about.
        const { data } = await axios.post(`${API_BASE_URL}/api/auth/refresh`, {
          refresh_token: refreshToken,
        });

        const { access_token: newAccessToken, refresh_token: newRefreshToken } = data.data;
        tokenStorage.setTokens(newAccessToken, newRefreshToken, tokenStorage.isPersisted());
        return newAccessToken as string;
      } catch {
        return null;
      } finally {
        refreshPromise = null;
      }
    })();
  }

  return refreshPromise;
}

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryableRequestConfig | undefined;
    const isExempt = REFRESH_EXEMPT_PATHS.some((path) => originalRequest?.url?.includes(path));

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry && !isExempt) {
      // Marked before the attempt (not after) so a second 401 on the
      // RETRY itself - e.g. the refreshed token is somehow also rejected -
      // falls through to the rejection below instead of looping forever.
      originalRequest._retry = true;

      const newAccessToken = await refreshAccessToken();

      if (newAccessToken) {
        originalRequest.headers = originalRequest.headers ?? {};
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return apiClient(originalRequest);
      }

      // Refresh itself failed - the refresh token is dead too. Nothing
      // left to try.
      tokenStorage.clearTokens();
      emitForceLogout();
    }

    return Promise.reject(error);
  }
);