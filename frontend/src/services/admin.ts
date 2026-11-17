/**
 * Admin API calls (Phase 9, /api/admin). Every one is authenticated by the
 * shared `apiClient`; the server decides who is an admin on every request
 * (401 signed out, 403 not an admin) - nothing here is a permission check.
 */

import { apiClient } from "@/lib/axios";
import type { AdminDashboard, AdminMe } from "@/types/admin";
import type { ApiResponse } from "@/types/auth";

/** Asks the server whether the caller is currently an active admin (403 if not). */
export async function getAdminMe(): Promise<AdminMe> {
  const { data } = await apiClient.get<ApiResponse<AdminMe>>("/api/admin/me");
  return data.data as AdminMe;
}

export async function getAdminDashboard(): Promise<AdminDashboard> {
  const { data } = await apiClient.get<ApiResponse<AdminDashboard>>("/api/admin/dashboard");
  return data.data as AdminDashboard;
}
