/**
 * Thin wrapper around the auth API endpoints. Pages call these functions
 * rather than using `apiClient` directly - this is the one place that
 * knows the exact request/response shape of each auth endpoint. From
 * Milestone 7 onward, AuthContext calls these too rather than the pages
 * calling them directly.
 */

import { apiClient } from "@/lib/axios";
import { tokenStorage } from "@/lib/token-storage";
import type { ApiResponse, LoginResponseData, User } from "@/types/auth";

export interface RegisterPayload {
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string;
  password: string;
  confirm_password: string;
}

export async function registerUser(payload: RegisterPayload): Promise<User> {
  const { data } = await apiClient.post<ApiResponse<User>>("/api/auth/register", payload);
  return data.data as User;
}

export async function loginUser(
  email: string,
  password: string,
  rememberMe: boolean = true
): Promise<LoginResponseData> {
  const { data } = await apiClient.post<ApiResponse<LoginResponseData>>("/api/auth/login", {
    email,
    password,
  });
  const loginData = data.data as LoginResponseData;
  tokenStorage.setTokens(loginData.access_token, loginData.refresh_token, rememberMe);
  return loginData;
}

export async function logoutUser(): Promise<void> {
  const refreshToken = tokenStorage.getRefreshToken();
  // Tokens are cleared client-side unconditionally - the user's browser
  // session ends immediately regardless of whether the server call below
  // succeeds (e.g. the network is down, or the token was already expired).
  tokenStorage.clearTokens();

  if (!refreshToken) return;
  try {
    await apiClient.post("/api/auth/logout", { refresh_token: refreshToken });
  } catch {
    // Deliberately swallowed - see comment above.
  }
}

export async function getCurrentUser(): Promise<User> {
  const { data } = await apiClient.get<ApiResponse<User>>("/api/users/me");
  return data.data as User;
}