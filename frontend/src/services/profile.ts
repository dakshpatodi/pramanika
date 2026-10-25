/**
 * Profile update (Phase 8 backend, PATCH /api/users/me). Reading the profile
 * is `getCurrentUser` in services/auth. Uses the shared `apiClient`, so the
 * owner is always the logged-in user and an expired access token is
 * refreshed silently.
 */

import { apiClient } from "@/lib/axios";
import type { ApiResponse, User } from "@/types/auth";
import type { ProfileUpdateInput } from "@/types/profile";

/** Saves the changed fields and resolves with the user as the server now has it. */
export async function updateProfile(input: ProfileUpdateInput): Promise<User> {
  const { data } = await apiClient.patch<ApiResponse<User>>("/api/users/me", input);
  return data.data as User;
}
