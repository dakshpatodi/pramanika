/**
 * Thin fetch wrapper around the FastAPI backend.
 *
 * Phase 1 scope: just enough to confirm the frontend can reach the API's
 * health check. Real resource methods (getProducts, getCategories, ...)
 * will be added here in Phase 2 once those endpoints exist.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface HealthResponse {
  status: string;
  message: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!res.ok) {
    throw new Error(`API request failed: ${res.status} ${res.statusText}`);
  }

  return res.json() as Promise<T>;
}

/** Calls the backend's `GET /` health check. */
export function getApiHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/");
}
